"""Single-trial orchestration for the tactile bar-height 2AFC task."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pygame

from . import display, stimulus
from .calibration import DisplayCalibration
from .config import ExperimentConfig
from .constant_stimuli import TrialSpec


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


class _PassTracker:
    """Tracks per-bar-crossing ("pass") rendering fidelity within a trial."""

    def __init__(self, max_sample_gap_s: float) -> None:
        self.max_sample_gap_s = max_sample_gap_s
        self.passes: list[dict[str, Any]] = []
        self.side: str | None = None
        self.start_s = 0.0
        self.commanded_s = 0.0
        self.entry_speed_mm_s = 0.0
        self.leading_edge_detected = True

    def start(self, side: str, now_s: float, speed_mm_s: float, commanded_s: float, sample_gap_s: float) -> None:
        self.finish(now_s)
        self.side = side
        self.start_s = now_s
        self.commanded_s = commanded_s
        self.entry_speed_mm_s = speed_mm_s
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
) -> TrialResult | None:
    """Run one 2AFC trial and return the participant response, or ``None`` on quit."""
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
    previous_side: str | None = None

    tracker = _PassTracker(max_sample_gap_s=3.0 / cfg.ir_sample_hz_nominal)

    while True:
        now = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                stimulus.signal_off(instrument)
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    stimulus.signal_off(instrument)
                    return None
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    response = "left" if event.key == pygame.K_LEFT else "right"
                    stimulus.signal_off(instrument)
                    tracker.finish(now)
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
                    if cfg.feedback or spec.is_practice:
                        display.draw_feedback(screen, correct)
                        pygame.display.flip()
                        pygame.time.wait(500)
                    return result

        pos = pygame.mouse.get_pos()
        elapsed = max(now - last_time, 1e-6)
        dx = (pos[0] - last_pos[0]) / calibration.px_per_mm_x
        dy = (pos[1] - last_pos[1]) / calibration.px_per_mm_y
        speed_mm_s = ((dx * dx + dy * dy) ** 0.5) / elapsed

        active_side = _side_for_pos(pos, layout)
        if active_side is not None and active_side != previous_side:
            commanded_s = stimulus.stimulus_duration(cfg.bar_width_mm, speed_mm_s)
            tracker.start(active_side, now, speed_mm_s, commanded_s, elapsed)
        elif active_side is None and previous_side is not None:
            tracker.finish(now)

        if active_side is not None:
            # Finger is physically over the bar right now: keep the signal on
            # regardless of the timed pulse, so dwelling doesn't cut it off early.
            stimulus.signal_on(instrument)
        else:
            # Finger just left the bar's rectangle: honor any still-running timed
            # pulse from the entry speed, so fast/narrow crossings the position
            # sampling might otherwise clip still get their full guaranteed duration.
            stimulus.deliver_timed_signal(instrument, tracker.start_s, tracker.commanded_s, now)

        display.draw_trial(
            screen,
            layout,
            bar_width_mm=cfg.bar_width_mm,
            trial_index=trial_index,
            is_practice=spec.is_practice,
            active_side=active_side,
            show_touch_guide=cfg.show_touch_guide,
        )
        pygame.display.flip()
        previous_side = active_side
        last_pos = pos
        last_time = now
        clock.tick(fps)
