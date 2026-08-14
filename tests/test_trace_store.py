from __future__ import annotations

import json
import sqlite3

from experiment.trace_store import AttemptDefinition, CursorSample, TraceStore


def _attempt(attempt_index: int = 1) -> AttemptDefinition:
    return AttemptDefinition(
        session_id="P01_session",
        trial_index=12,
        attempt_index=attempt_index,
        started_us=1_000_000,
        level_pct=0.18,
        comparison_height_mm=11.8,
        reference_height_mm=10.0,
        bar_width_mm=10.0,
        reference_side="left",
        is_catch=False,
    )


def test_trace_store_round_trip(tmp_path):
    path = tmp_path / "session_trace.sqlite3"
    with TraceStore(path) as store:
        store.create_session(
            session_id="P01_session",
            participant_id="P01",
            started_at="2026-08-14T12:00:00+03:00",
            config={"response_timeout_s": 30.0},
            calibration={"px_per_mm_x": 7.7, "px_per_mm_y": 5.8},
            app_version="test-version",
        )
        attempt_id = store.start_attempt(_attempt())
        store.append_samples(
            attempt_id,
            [
                CursorSample(0, 0, 16_667, 100, 200, 10.0, 20.0, 0.0, True, None, False),
                CursorSample(1, 16_667, 16_667, 108, 200, 11.0, 20.0, 60.0, True, "left", True),
            ],
        )
        store.append_event(attempt_id, t_us=16_667, event_type="signal_on", payload={"side": "left"})
        store.finish_attempt(
            attempt_id,
            ended_us=2_500_000,
            outcome="answered",
            response="right",
            response_time_us=1_500_000,
        )

    connection = sqlite3.connect(path)
    session = connection.execute(
        "SELECT participant_id, config_json, calibration_json FROM sessions"
    ).fetchone()
    assert session is not None
    assert session[0] == "P01"
    assert json.loads(session[1]) == {"response_timeout_s": 30.0}
    assert json.loads(session[2])["px_per_mm_x"] == 7.7

    attempt = connection.execute(
        "SELECT trial_index, attempt_index, outcome, response FROM attempts"
    ).fetchone()
    assert attempt == (12, 1, "answered", "right")

    samples = connection.execute(
        "SELECT sequence, t_us, x_px, active_side, signal_on FROM cursor_samples ORDER BY sequence"
    ).fetchall()
    assert samples == [(0, 0, 100, None, 0), (1, 16_667, 108, "left", 1)]

    event = connection.execute(
        "SELECT event_type, payload_json FROM trace_events"
    ).fetchone()
    assert event is not None
    assert event[0] == "signal_on"
    assert json.loads(event[1]) == {"side": "left"}
    connection.close()


def test_same_trial_can_store_multiple_attempts(tmp_path):
    path = tmp_path / "session_trace.sqlite3"
    with TraceStore(path) as store:
        store.create_session(
            session_id="P01_session",
            participant_id="P01",
            started_at="2026-08-14T12:00:00+03:00",
            config={},
            calibration={},
            app_version="test-version",
        )
        first_id = store.start_attempt(_attempt(attempt_index=1))
        store.finish_attempt(first_id, ended_us=31_000_000, outcome="timeout")
        second_id = store.start_attempt(_attempt(attempt_index=2))
        store.finish_attempt(
            second_id,
            ended_us=42_000_000,
            outcome="answered",
            response="left",
            response_time_us=11_000_000,
        )

    connection = sqlite3.connect(path)
    attempts = connection.execute(
        "SELECT trial_index, attempt_index, outcome FROM attempts ORDER BY attempt_index"
    ).fetchall()
    assert attempts == [(12, 1, "timeout"), (12, 2, "answered")]
    connection.close()
