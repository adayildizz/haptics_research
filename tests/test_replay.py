from __future__ import annotations

import pytest

from experiment.demo_trace import ensure_demo_trace
from experiment.replay_data import discover_trace_files, load_trace
from experiment.replay_renderer import draw_attempt_frame


def test_demo_trace_loads_attempts_in_chronological_order(tmp_path):
    path = ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3")
    session = load_trace(path)

    assert session.session_id == "DEMO_REPLAY"
    assert [(attempt.trial_index, attempt.attempt_index) for attempt in session.attempts] == [
        (1, 1),
        (2, 1),
        (2, 2),
        (3, 1),
    ]
    assert [attempt.outcome for attempt in session.attempts] == [
        "answered",
        "timeout",
        "answered",
        "answered",
    ]
    assert [attempt.response for attempt in session.attempts] == ["left", None, "right", "left"]
    assert all(attempt.samples for attempt in session.attempts)
    assert [attempt.correct for attempt in session.attempts] == [True, None, False, True]


def test_replay_interpolates_cursor_but_keeps_previous_signal_state(tmp_path):
    session = load_trace(ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3"))
    attempt = session.attempts[0]
    left = attempt.samples[10]
    right = attempt.samples[11]
    midpoint_us = (left.t_us + right.t_us) // 2

    state = attempt.state_at(midpoint_us)

    assert state is not None
    assert state.x_px == pytest.approx((left.x_px + right.x_px) / 2, abs=0.6)
    assert state.y_px == pytest.approx((left.y_px + right.y_px) / 2, abs=0.6)
    assert state.signal_on is left.signal_on


def test_discovery_places_demo_after_real_recordings(tmp_path):
    demo = ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3")
    real = ensure_demo_trace(tmp_path / "P01_20260814_120000_trace.sqlite3")

    discovered = discover_trace_files(tmp_path)

    assert discovered[0] == real
    assert discovered[-1] == demo


def test_replay_frame_renders_without_opening_a_pygame_window(tmp_path):
    import pygame

    session = load_trace(ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3"))
    surface = pygame.Surface((640, 400))

    draw_attempt_frame(surface, session, session.attempts[0], 500_000, surface.get_rect())

    rgb = pygame.image.tostring(surface, "RGB")
    assert len(rgb) == 640 * 400 * 3


def test_replay_prefers_recorded_correct_value(tmp_path):
    session = load_trace(ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3"))
    attempt = session.attempts[0]
    response_event = attempt.events[-1]
    forced_event = type(response_event)(
        t_us=response_event.t_us,
        event_type="response",
        payload={"response": attempt.response, "correct": False},
    )
    forced_attempt = type(attempt)(
        **{**attempt.__dict__, "events": (*attempt.events, forced_event)}
    )

    assert forced_attempt.correct is False
