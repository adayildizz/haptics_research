from __future__ import annotations

import sqlite3

from experiment.trace_recorder import AsyncTraceRecorder
from experiment.trace_store import AttemptDefinition, CursorSample


def test_async_recorder_writes_batched_attempt_in_order(tmp_path):
    path = tmp_path / "async_trace.sqlite3"
    recorder = AsyncTraceRecorder(path)
    recorder.create_session(
        session_id="P01_session",
        participant_id="P01",
        started_at="2026-08-14T12:00:00+03:00",
        config={"record_main_trace": True},
        calibration={"px_per_mm_x": 7.7, "px_per_mm_y": 5.8},
        app_version="test-version",
    )
    attempt = recorder.start_attempt(
        "12:1",
        AttemptDefinition(
            session_id="P01_session",
            trial_index=12,
            attempt_index=1,
            started_us=recorder.elapsed_us(),
            level_pct=0.18,
            comparison_height_mm=11.8,
            reference_height_mm=10.0,
            bar_width_mm=10.0,
            reference_side="left",
            is_catch=False,
        ),
    )

    for sequence in range(600):
        attempt.add_sample(
            CursorSample(
                sequence=sequence,
                t_us=sequence * 16_667,
                frame_dt_us=16_667,
                x_px=100 + sequence,
                y_px=200,
                x_mm=10.0 + sequence / 10,
                y_mm=20.0,
                speed_mm_s=100.0,
                in_active_area=True,
                active_side="left" if sequence % 2 else None,
                signal_on=bool(sequence % 2),
            )
        )
    attempt.add_event(t_us=10_000_000, event_type="response", payload={"response": "right"})
    attempt.finish(
        ended_us=recorder.elapsed_us(),
        outcome="answered",
        response="right",
        response_time_us=10_000_000,
    )

    assert recorder.close() is None

    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM cursor_samples").fetchone() == (600,)
    assert connection.execute("SELECT MIN(sequence), MAX(sequence) FROM cursor_samples").fetchone() == (0, 599)
    assert connection.execute("SELECT outcome, response FROM attempts").fetchone() == ("answered", "right")
    assert connection.execute("SELECT event_type FROM trace_events").fetchone() == ("response",)
    connection.close()
