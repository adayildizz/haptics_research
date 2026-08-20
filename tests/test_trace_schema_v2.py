"""Schema 2 adds practice attempts and per-sample touch state."""

from __future__ import annotations

import sqlite3

import pytest

from experiment.replay_data import load_trace
from experiment.trace_store import SCHEMA_VERSION, AttemptDefinition, CursorSample, TraceStore


def _definition(**overrides) -> AttemptDefinition:
    values = dict(
        session_id="S1",
        trial_index=1,
        attempt_index=1,
        started_us=0,
        level_pct=0.3,
        comparison_height_mm=13.0,
        reference_height_mm=10.0,
        bar_width_mm=10.0,
        reference_side="left",
        is_catch=False,
    )
    values.update(overrides)
    return AttemptDefinition(**values)


def _sample(sequence: int, **overrides) -> CursorSample:
    values = dict(
        sequence=sequence,
        t_us=sequence * 10_000,
        frame_dt_us=10_000,
        x_px=100 + sequence,
        y_px=200,
        x_mm=10.0,
        y_mm=20.0,
        speed_mm_s=100.0,
        in_active_area=True,
        active_side="left",
        signal_on=True,
    )
    values.update(overrides)
    return CursorSample(**values)


def _session(store: TraceStore) -> None:
    store.create_session(
        session_id="S1",
        participant_id="01",
        started_at="2026-08-19T14:00:00+03:00",
        config={},
        calibration={},
        app_version="test",
    )


def test_practice_and_main_trial_one_do_not_collide(tmp_path):
    """attempts is UNIQUE on (session, trial, attempt); practice uses negative slots."""
    path = tmp_path / "trace.sqlite3"
    store = TraceStore(path)
    _session(store)
    practice_id = store.start_attempt(_definition(trial_index=-1, is_practice=True))
    main_id = store.start_attempt(_definition(trial_index=1, is_practice=False))
    store.finish_attempt(practice_id, ended_us=1, outcome="answered", response="left")
    store.finish_attempt(main_id, ended_us=2, outcome="answered", response="left")
    store.close()

    attempts = load_trace(path).attempts

    assert len(attempts) == 2
    assert [a.is_practice for a in attempts] == [True, False]


def test_attempts_load_in_chronological_order(tmp_path):
    """Practice uses negative slots, so ordering keys off started_us, not trial_index."""
    path = tmp_path / "trace.sqlite3"
    store = TraceStore(path)
    _session(store)
    for slot, started in ((-1, 10), (-2, 20), (1, 30), (2, 40)):
        store.start_attempt(
            _definition(trial_index=slot, started_us=started, is_practice=slot < 0)
        )
    store.close()

    assert [a.trial_index for a in load_trace(path).attempts] == [-1, -2, 1, 2]


def test_contact_round_trips_per_sample(tmp_path):
    path = tmp_path / "trace.sqlite3"
    store = TraceStore(path)
    _session(store)
    attempt_id = store.start_attempt(_definition())
    store.append_samples(
        attempt_id,
        [_sample(0, contact=True), _sample(1, contact=False), _sample(2, contact=True)],
    )
    store.close()

    samples = load_trace(path).attempts[0].samples

    assert [s.contact for s in samples] == [True, False, True]


def test_schema_1_database_is_migrated_in_place(tmp_path):
    """Existing recordings must keep opening, with defined values for the new columns."""
    path = tmp_path / "legacy.sqlite3"
    store = TraceStore(path)
    _session(store)
    attempt_id = store.start_attempt(_definition())
    store.append_samples(attempt_id, [_sample(0)])
    store.close()

    # Roll the file back to what schema 1 produced.
    connection = sqlite3.connect(path)
    for table, column in (("attempts", "is_practice"), ("cursor_samples", "contact")):
        connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    connection.commit()
    connection.close()

    reopened = TraceStore(path)  # runs the migration
    reopened.close()

    attempt = load_trace(path).attempts[0]
    assert attempt.is_practice is False   # everything traced back then was main-block
    assert attempt.samples[0].contact is True  # ...and assumed a finger was down


def test_schema_1_database_still_readable_without_migrating(tmp_path):
    """The replay browser opens traces read-only, so it cannot rely on the migration."""
    path = tmp_path / "legacy.sqlite3"
    store = TraceStore(path)
    _session(store)
    attempt_id = store.start_attempt(_definition())
    store.append_samples(attempt_id, [_sample(0)])
    store.close()

    connection = sqlite3.connect(path)
    for table, column in (("attempts", "is_practice"), ("cursor_samples", "contact")):
        connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    connection.commit()
    connection.close()

    attempt = load_trace(path).attempts[0]

    assert attempt.is_practice is False
    assert attempt.samples[0].contact is True


def test_schema_version_is_recorded(tmp_path):
    path = tmp_path / "trace.sqlite3"
    TraceStore(path).close()

    connection = sqlite3.connect(path)
    value = connection.execute(
        "SELECT value FROM trace_metadata WHERE key = 'schema_version'"
    ).fetchone()[0]
    connection.close()

    assert int(value) == SCHEMA_VERSION == 2
