"""Generate a deterministic trace used to demonstrate the replay browser."""

from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path

from .calibration import make_configured_ir_frame_calibration
from .trace_store import AttemptDefinition, CursorSample, TraceStore


def ensure_demo_trace(path: str | Path) -> Path:
    demo_path = Path(path)
    if demo_path.exists():
        return demo_path

    calibration = make_configured_ir_frame_calibration((1280, 720))
    config = {
        "base_height_mm": 10.0,
        "bar_width_mm": 10.0,
        "inter_bar_gap_mm": 40.0,
        "blind_test_mode": True,
        "response_timeout_s": 30.0,
    }

    with TraceStore(demo_path) as store:
        store.create_session(
            session_id="DEMO_REPLAY",
            participant_id="DEMO",
            started_at="2026-08-14T12:00:00+03:00",
            config=config,
            calibration=asdict(calibration),
            app_version="ea-demo-trace-v1",
        )

        definitions = [
            (1, 1, -0.18, 8.2, "left", 6.0, "answered", "left"),
            (2, 1, 0.30, 13.0, "right", 30.0, "timeout", None),
            (2, 2, -0.30, 7.0, "left", 7.0, "answered", "right"),
            (3, 1, 0.18, 11.8, "right", 5.0, "answered", "left"),
        ]
        session_cursor_us = 0
        for trial_index, attempt_index, level, comparison_height, reference_side, duration_s, outcome, response in definitions:
            attempt_id = store.start_attempt(
                AttemptDefinition(
                    session_id="DEMO_REPLAY",
                    trial_index=trial_index,
                    attempt_index=attempt_index,
                    started_us=session_cursor_us,
                    level_pct=level,
                    comparison_height_mm=comparison_height,
                    reference_height_mm=10.0,
                    bar_width_mm=10.0,
                    reference_side=reference_side,
                    is_catch=False,
                )
            )
            samples = _make_samples(calibration, duration_s, attempt_index)
            store.append_samples(attempt_id, samples)
            event_time_us = round(duration_s * 1_000_000)
            store.append_event(
                attempt_id,
                t_us=event_time_us,
                event_type=outcome,
                payload={"response": response} if response else {"limit_s": duration_s},
            )
            store.finish_attempt(
                attempt_id,
                ended_us=session_cursor_us + event_time_us,
                outcome=outcome,
                response=response,
                response_time_us=event_time_us if response else None,
            )
            session_cursor_us += event_time_us + 1_000_000
    return demo_path


def _make_samples(calibration, duration_s: float, phase_offset: int) -> list[CursorSample]:
    fps = 60
    count = max(2, round(duration_s * fps))
    left_x = calibration.active_left_px + calibration.active_width_px * 0.35
    right_x = calibration.active_left_px + calibration.active_width_px * 0.65
    top = calibration.active_top_px + calibration.active_height_px * 0.20
    bottom = calibration.active_top_px + calibration.active_height_px * 0.92
    samples: list[CursorSample] = []
    for sequence in range(count):
        progress = sequence / (count - 1)
        on_left = int(progress * 4) % 2 == 0
        x_px = left_x if on_left else right_x
        x_px += math.sin(progress * math.pi * 12 + phase_offset) * 7
        vertical_phase = (progress * 4) % 1.0
        y_px = bottom + (top - bottom) * vertical_phase
        speed = 95.0 + 22.0 * math.sin(progress * math.pi * 8)
        signal_on = 0.15 < vertical_phase < 0.85
        samples.append(
            CursorSample(
                sequence=sequence,
                t_us=round(progress * duration_s * 1_000_000),
                frame_dt_us=round(1_000_000 / fps),
                x_px=round(x_px),
                y_px=round(y_px),
                x_mm=(x_px - calibration.active_left_px) / calibration.px_per_mm_x,
                y_mm=(y_px - calibration.active_top_px) / calibration.px_per_mm_y,
                speed_mm_s=speed,
                in_active_area=True,
                active_side="left" if on_left else "right",
                signal_on=signal_on,
            )
        )
    return samples
