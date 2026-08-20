"""Single-trial orchestration for the tactile bar-height 2AFC task."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from typing import TYPE_CHECKING

import pygame

from . import audio_cues, display, stimulus
from .calibration import DisplayCalibration
from .config import ExperimentConfig
from .constant_stimuli import TrialSpec
from .input_keys import is_exit_key, response_for_key
from .trace_store import CursorSample

if TYPE_CHECKING:
    from .speed_coach import PracticeSpeedCoach
    from .trace_recorder import AttemptTraceBuffer


@dataclass(frozen=True)
class TrialResult:
    trial_index: int
    level_pct: float
    comparison_height_mm: float
    reference_height_mm: float
    bar_width_mm: float
    reference_side: str
    response: str
    correct: bool
    is_catch: bool
    is_practice: bool
    response_time_s: float
    passes: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""


@dataclass(frozen=True)
class TrialAborted:
    """The trial was cut short by an exit key or a closed window.

    Returned instead of ``None`` so the caller can log the partial trial
    before shutting the session down: an abort is a real thing that
    happened to a participant, and the trial CSV should say so rather than
    the row simply being absent.
    """

    reason: str  # "exit_key" | "window_closed"
    elapsed_s: float
    passes: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""


@dataclass(frozen=True)
class TrialTimeout:
    """Signals that a trial expired without a response (practice included).

    Carries the same exploration record an answered trial does: the passes
    show whether the participant was working the bars or idle when the
    window closed, which is the interesting question about a timeout.
    """

    elapsed_s: float
    passes: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""


_contact_warning_printed = False
# Set once the device is seen reporting a finger down. Until then the touch
# state is not trusted for anything behavioural: a driver that never reports
# it would otherwise read as "the finger is never on the glass" and silence
# the stimulus for the whole session.
_touch_state_available = False


def _warn_if_touch_state_missing(contact_ever_reported: bool) -> None:
    """Say so, once per session, if the device never reports a finger down.

    The ``contact`` column is only meaningful on a driver that emits touch
    (or emulated mouse-button) state. On one that does not, the column is
    uniformly ``False`` and would silently look like "the participant never
    touched anything" -- so make the absence explicit instead.
    """
    global _contact_warning_printed
    if contact_ever_reported or _contact_warning_printed:
        return
    _contact_warning_printed = True
    print(
        "WARNING: no touch-down reported by the input device; the trace's "
        "'contact' column will be uniformly false and cannot be used to tell "
        "a lifted finger from a stationary one."
    )


def frame_samples(
    reports: list[tuple[tuple[int, int], bool]],
    *,
    first_sequence: int,
    previous_pos: tuple[int, int],
    previous_t: float,
    frame_end_t: float,
    trial_start: float,
    calibration: DisplayCalibration,
    layout: display.TrialLayout,
    signal_on: bool,
) -> list[CursorSample]:
    """Turn one frame's worth of input reports into cursor samples.

    ``reports`` is every ``(position, finger_down)`` the device delivered
    since the previous frame -- one per IR update, not one per rendered
    frame. pygame does not expose SDL's per-event timestamp, so the frame
    interval is divided evenly between the reports: the error is bounded by
    one frame, and ``frame_dt_us`` on each sample keeps it auditable. Speed
    and side are recomputed between consecutive reports rather than reused
    from the frame, which is the point of sampling them separately.
    """
    samples: list[CursorSample] = []
    count = len(reports)
    for index, (pos, contact) in enumerate(reports, start=1):
        t = previous_t + (frame_end_t - previous_t) * index / count
        dt = max(t - previous_t, 1e-6)
        dx = (pos[0] - previous_pos[0]) / calibration.px_per_mm_x
        dy = (pos[1] - previous_pos[1]) / calibration.px_per_mm_y
        samples.append(
            CursorSample(
                sequence=first_sequence + index - 1,
                t_us=round((t - trial_start) * 1_000_000),
                frame_dt_us=round(dt * 1_000_000),
                x_px=pos[0],
                y_px=pos[1],
                x_mm=(pos[0] - calibration.active_left_px) / calibration.px_per_mm_x,
                y_mm=(pos[1] - calibration.active_top_px) / calibration.px_per_mm_y,
                speed_mm_s=((dx * dx + dy * dy) ** 0.5) / dt,
                in_active_area=layout.haptic_area.collidepoint(pos),
                active_side=_side_for_pos(pos, layout),
                signal_on=signal_on,
                contact=contact,
            )
        )
        previous_pos, previous_t = pos, t
    return samples


def should_time_out(elapsed_s: float, timeout_s: float) -> bool:
    """Every trial, practice included, uses the configured response limit.

    Practice used to be unlimited, which meant participants first met the
    countdown in the main block -- the one place where running out of time
    actually costs a trial. Practicing under the same clock is the point of
    practice.
    """
    return elapsed_s >= timeout_s


class _PassTracker:
    """Tracks per-bar-crossing ("pass") rendering fidelity within a trial.

    ``max_sample_gap_s`` is compared against the gap between *input reports*.
    It used to be handed the gap between rendered frames, which at 60 Hz is
    16.7 ms against a 30 ms threshold -- so the flag was structurally almost
    always true and was really reporting render hitches, not IR dropouts.
    """

    def __init__(self, max_sample_gap_s: float) -> None:
        self.max_sample_gap_s = max_sample_gap_s
        self.passes: list[dict[str, Any]] = []
        self.side: str | None = None
        self.start_s = 0.0
        self.commanded_s = 0.0
        self.entry_speed_mm_s = 0.0
        self.entry_gap_s = 0.0
        self.leading_edge_detected = True

    def start(self, side: str, now_s: float, speed_mm_s: float, commanded_s: float, sample_gap_s: float) -> None:
        self.finish(now_s)
        self.side = side
        self.start_s = now_s
        self.commanded_s = commanded_s
        self.entry_speed_mm_s = speed_mm_s
        self.entry_gap_s = sample_gap_s
        self.leading_edge_detected = sample_gap_s <= self.max_sample_gap_s

    def finish(self, now_s: float) -> None:
        if self.side is None:
            return
        actual_s = min(self.commanded_s, max(0.0, now_s - self.start_s))
        self.passes.append(
            {
                "side": self.side,
                "commanded_duration_s": self.commanded_s,
                "actual_duration_s": actual_s,
                "finger_speed_mm_s": self.entry_speed_mm_s,
                "entry_report_gap_s": self.entry_gap_s,
                "leading_edge_detected": self.leading_edge_detected,
            }
        )
        self.side = None


def _side_for_pos(pos: tuple[int, int], layout: display.TrialLayout) -> str | None:
    if layout.left_bar.collidepoint(pos):
        return "left"
    if layout.right_bar.collidepoint(pos):
        return "right"
    return None


def _taller_side(spec: TrialSpec) -> str:
    """The objectively taller side, given the signed level percentage."""
    if spec.level_pct > 0:
        return "right" if spec.reference_side == "left" else "left"
    return spec.reference_side


def run_trial(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    calibration: DisplayCalibration,
    instrument: Any | None,
    cfg: ExperimentConfig,
    spec: TrialSpec,
    trial_index: int,
    fps: int,
    speed_coach: PracticeSpeedCoach | None = None,
    trace_attempt: AttemptTraceBuffer | None = None,
) -> TrialResult | TrialTimeout | TrialAborted:
    """Run one 2AFC trial, returning a response, a timeout, or an abort."""
    comparison_side = "right" if spec.reference_side == "left" else "left"
    left_is_comparison = comparison_side == "left"
    layout = display.make_trial_layout(
        screen,
        calibration=calibration,
        bar_width_mm=cfg.bar_width_mm,
        reference_height_mm=spec.reference_height_mm,
        comparison_height_mm=spec.comparison_height_mm,
        left_is_comparison=left_is_comparison,
        inter_bar_gap_mm=cfg.inter_bar_gap_mm,
    )

    trial_start = time.perf_counter()
    last_pos = pygame.mouse.get_pos()
    last_time = trial_start
    # Touch state. Nothing here gates the signal -- that still keys off
    # position alone -- because a driver that never reports touch would then
    # silence the stimulus entirely. It is recorded so the rig can be checked
    # first; without it a lifted finger is indistinguishable from a finger
    # held still, since the cursor keeps returning its last position.
    global _touch_state_available
    contact = bool(pygame.mouse.get_pressed()[0])
    contact_ever_reported = contact
    _touch_state_available = _touch_state_available or contact
    previous_contact = contact
    previous_side: str | None = None
    previous_signal_on = False
    trace_sequence = 0

    if speed_coach is not None and spec.is_practice:
        speed_coach.reset_trial()

    tracker = _PassTracker(max_sample_gap_s=3.0 / cfg.ir_sample_hz_nominal)

    while True:
        now = time.perf_counter()
        # (position, finger-down) for every input report that arrived since the
        # last frame. The event queue is drained here either way; reading the
        # motion events instead of dropping them is what keeps the trace at the
        # IR frame's rate rather than the render loop's.
        motion: list[tuple[tuple[int, int], bool]] = []
        for event in pygame.event.get():
            if event.type == pygame.MOUSEMOTION:
                motion.append((event.pos, bool(event.buttons[0])))
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                contact = True
                contact_ever_reported = True
                _touch_state_available = True
                continue
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                contact = False
                continue
            if event.type == pygame.QUIT:
                stimulus.signal_off(instrument)
                tracker.finish(now)
                if trace_attempt is not None:
                    t_us = round((now - trial_start) * 1_000_000)
                    if previous_signal_on:
                        trace_attempt.add_event(
                            t_us=t_us,
                            event_type="signal_off",
                            payload={"reason": "window_closed"},
                        )
                    trace_attempt.add_event(t_us=t_us, event_type="aborted", payload={"reason": "window_closed"})
                    trace_attempt.finish(
                        ended_us=trace_attempt.session_elapsed_us(),
                        outcome="aborted",
                    )
                return TrialAborted(
                    reason="window_closed",
                    elapsed_s=now - trial_start,
                    passes=tracker.passes,
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                )
            if event.type == pygame.KEYDOWN:
                if is_exit_key(event.key, pygame):
                    stimulus.signal_off(instrument)
                    tracker.finish(now)
                    if trace_attempt is not None:
                        t_us = round((now - trial_start) * 1_000_000)
                        if previous_signal_on:
                            trace_attempt.add_event(
                                t_us=t_us,
                                event_type="signal_off",
                                payload={"reason": "numpad_0"},
                            )
                        trace_attempt.add_event(t_us=t_us, event_type="aborted", payload={"reason": "numpad_0"})
                        trace_attempt.finish(
                            ended_us=trace_attempt.session_elapsed_us(),
                            outcome="aborted",
                        )
                    return TrialAborted(
                        reason="exit_key",
                        elapsed_s=now - trial_start,
                        passes=tracker.passes,
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    )
                response = response_for_key(event.key, pygame)
                if response is not None:
                    stimulus.signal_off(instrument)
                    tracker.finish(now)
                    # Same cue whether the answer was right or wrong: it marks
                    # "recorded, moving on", not correctness.
                    audio_cues.play_response_cue()
                    correct = response == _taller_side(spec)
                    result = TrialResult(
                        trial_index=trial_index,
                        level_pct=spec.level_pct,
                        comparison_height_mm=spec.comparison_height_mm,
                        reference_height_mm=spec.reference_height_mm,
                        bar_width_mm=cfg.bar_width_mm,
                        reference_side=spec.reference_side,
                        response=response,
                        correct=correct,
                        is_catch=spec.is_catch,
                        is_practice=spec.is_practice,
                        response_time_s=now - trial_start,
                        passes=tracker.passes,
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    )
                    if trace_attempt is not None:
                        t_us = round((now - trial_start) * 1_000_000)
                        if previous_signal_on:
                            trace_attempt.add_event(
                                t_us=t_us,
                                event_type="signal_off",
                                payload={"reason": "response"},
                            )
                        trace_attempt.add_event(
                            t_us=t_us,
                            event_type="response",
                            payload={"response": response, "correct": correct},
                        )
                        trace_attempt.finish(
                            ended_us=trace_attempt.session_elapsed_us(),
                            outcome="answered",
                            response=response,
                            response_time_us=t_us,
                        )
                    _warn_if_touch_state_missing(contact_ever_reported)
                    if cfg.feedback or spec.is_practice:
                        display.draw_feedback(screen, correct)
                        pygame.display.flip()
                        pygame.time.wait(500)
                    return result

        elapsed_trial_s = now - trial_start
        if should_time_out(elapsed_trial_s, cfg.response_timeout_s):
            stimulus.signal_off(instrument)
            tracker.finish(now)
            audio_cues.play_timeout_cue()
            if trace_attempt is not None:
                t_us = round(elapsed_trial_s * 1_000_000)
                if previous_signal_on:
                    trace_attempt.add_event(
                        t_us=t_us,
                        event_type="signal_off",
                        payload={"reason": "timeout"},
                    )
                trace_attempt.add_event(
                    t_us=t_us,
                    event_type="timeout",
                    payload={"limit_s": cfg.response_timeout_s},
                )
                trace_attempt.finish(
                    ended_us=trace_attempt.session_elapsed_us(),
                    outcome="timeout",
                )
            _warn_if_touch_state_missing(contact_ever_reported)
            return TrialTimeout(
                elapsed_s=elapsed_trial_s,
                passes=tracker.passes,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )

        if motion:
            contact = motion[-1][1]
            if any(down for _, down in motion):
                contact_ever_reported = True
                _touch_state_available = True
        pos = pygame.mouse.get_pos()
        elapsed = max(now - last_time, 1e-6)
        dx = (pos[0] - last_pos[0]) / calibration.px_per_mm_x
        dy = (pos[1] - last_pos[1]) / calibration.px_per_mm_y
        speed_mm_s = ((dx * dx + dy * dy) ** 0.5) / elapsed

        if speed_coach is not None and spec.is_practice:
            speed_coach.update(
                speed_mm_s,
                elapsed,
                now,
                in_active_area=layout.haptic_area.collidepoint(pos),
            )

        # A lifted finger reports no new position, so the cursor keeps sitting
        # where it was -- which used to read as "still over the bar". Only
        # trust that once the device has actually been seen reporting touch.
        finger_down = contact or not _touch_state_available
        active_side = _side_for_pos(pos, layout) if finger_down else None
        # The gap between input reports, not between rendered frames: this is
        # what decides whether the crossing point is well localised, so it has
        # to be measured against the device's rate, not the loop's.
        report_gap_s = elapsed / len(motion) if motion else elapsed
        if active_side is not None and active_side != previous_side:
            commanded_s = stimulus.stimulus_duration(cfg.bar_width_mm, speed_mm_s)
            tracker.start(active_side, now, speed_mm_s, commanded_s, report_gap_s)
        elif active_side is None and previous_side is not None:
            tracker.finish(now)

        if active_side is not None:
            # Finger is physically over the bar right now: keep the signal on
            # regardless of the timed pulse, so dwelling doesn't cut it off early.
            stimulus.signal_on(instrument)
            signal_on = True
        elif not finger_down:
            # Finger is off the glass: there is nothing to feel, so no timed
            # pulse should keep running against a stale position.
            stimulus.signal_off(instrument)
            signal_on = False
        else:
            # Finger just left the bar's rectangle: honor any still-running timed
            # pulse from the entry speed, so fast/narrow crossings the position
            # sampling might otherwise clip still get their full guaranteed duration.
            signal_on = stimulus.deliver_timed_signal(
                instrument,
                tracker.start_s,
                tracker.commanded_s,
                now,
            )

        if trace_attempt is not None:
            t_us = round(elapsed_trial_s * 1_000_000)
            # With no motion at all, one sample still records that the finger
            # stayed where it was.
            for sample in frame_samples(
                motion or [(pos, contact)],
                first_sequence=trace_sequence,
                previous_pos=last_pos,
                previous_t=last_time,
                frame_end_t=now,
                trial_start=trial_start,
                calibration=calibration,
                layout=layout,
                signal_on=signal_on,
            ):
                trace_attempt.add_sample(sample)
                trace_sequence += 1
            if signal_on != previous_signal_on:
                trace_attempt.add_event(
                    t_us=t_us,
                    event_type="signal_on" if signal_on else "signal_off",
                    payload={"active_side": active_side},
                )
            if contact != previous_contact and _touch_state_available:
                trace_attempt.add_event(
                    t_us=t_us,
                    event_type="contact_down" if contact else "contact_up",
                    payload={"active_side": active_side},
                )
        previous_signal_on = signal_on
        previous_contact = contact

        display.draw_trial(
            screen,
            layout,
            bar_width_mm=cfg.bar_width_mm,
            trial_index=trial_index,
            is_practice=spec.is_practice,
            active_side=active_side,
            blind_test_mode=cfg.blind_test_mode,
            touch_pos=pos,
            remaining_time_s=max(0.0, cfg.response_timeout_s - elapsed_trial_s),
        )
        pygame.display.flip()
        previous_side = active_side
        last_pos = pos
        last_time = now
        clock.tick(fps)
