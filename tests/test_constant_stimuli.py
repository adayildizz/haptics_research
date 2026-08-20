from __future__ import annotations

import random

import pytest

from experiment.config import ExperimentConfig
from experiment.constant_stimuli import (
    ScheduledTrial,
    build_practice_sequence,
    build_schedule,
    build_trial_sequence,
    comparison_height_mm,
    compute_levels,
    defer_timed_out_trial,
    resolve_seed,
    take_retry_round,
)


def _cfg(**overrides) -> ExperimentConfig:
    base = dict(base_height_mm=10.0, bar_width_mm=10.0, inter_bar_gap_mm=10.0)
    base.update(overrides)
    return ExperimentConfig(**base)


def test_levels_symmetric_and_excludes_zero_by_default():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6)
    levels = compute_levels(cfg)
    assert len(levels) == 6
    assert all(abs(l) > 1e-9 for l in levels)
    assert sorted(levels) == pytest.approx(sorted(-l for l in levels))
    assert max(levels) == pytest.approx(0.30)
    assert min(levels) == pytest.approx(-0.30)


def test_levels_odd_n_drops_zero_by_default():
    cfg = _cfg(delta_max_pct=0.30, n_levels=7, include_zero_level=False)
    levels = compute_levels(cfg)
    assert len(levels) == 6
    assert all(abs(l) > 1e-9 for l in levels)


def test_levels_odd_n_includes_zero_when_requested():
    cfg = _cfg(delta_max_pct=0.30, n_levels=7, include_zero_level=True)
    levels = compute_levels(cfg)
    assert len(levels) == 7
    assert any(abs(l) < 1e-9 for l in levels)


def test_levels_changeable_without_code_changes():
    cfg_narrow = _cfg(delta_max_pct=0.10, n_levels=4)
    cfg_wide = _cfg(delta_max_pct=0.50, n_levels=8)
    assert max(compute_levels(cfg_narrow)) == pytest.approx(0.10)
    assert max(compute_levels(cfg_wide)) == pytest.approx(0.50)
    assert len(compute_levels(cfg_narrow)) == 4
    assert len(compute_levels(cfg_wide)) == 8


def test_comparison_height_mm():
    assert comparison_height_mm(10.0, 0.30) == pytest.approx(13.0)
    assert comparison_height_mm(10.0, -0.30) == pytest.approx(7.0)


def test_trial_sequence_counts_and_counterbalance():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, catch_trial_pct=0.10)
    trials = build_trial_sequence(cfg, seed=42)

    n_levels = len(compute_levels(cfg))
    n_main = n_levels * cfg.trials_per_level
    n_catch = round(cfg.catch_trial_pct * n_main)
    assert len(trials) == n_main + n_catch
    assert sum(1 for t in trials if t.is_catch) == n_catch

    per_level_sides: dict[float, list[str]] = {}
    for t in trials:
        if t.is_catch:
            continue
        per_level_sides.setdefault(t.level_pct, []).append(t.reference_side)
    for level, sides in per_level_sides.items():
        assert len(sides) == cfg.trials_per_level
        assert sides.count("left") == cfg.trials_per_level // 2
        assert sides.count("right") == cfg.trials_per_level // 2


def test_trial_sequence_deterministic_given_seed():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10)
    a = build_trial_sequence(cfg, seed=7)
    b = build_trial_sequence(cfg, seed=7)
    assert [(t.level_pct, t.reference_side, t.is_catch) for t in a] == [
        (t.level_pct, t.reference_side, t.is_catch) for t in b
    ]


def test_trial_sequence_different_seed_differs():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10)
    a = build_trial_sequence(cfg, seed=1)
    b = build_trial_sequence(cfg, seed=2)
    assert [(t.level_pct, t.reference_side) for t in a] != [(t.level_pct, t.reference_side) for t in b]


def test_practice_sequence_uses_easy_levels_only():
    cfg = _cfg(delta_max_pct=0.30, n_practice_trials=8)
    trials = build_practice_sequence(cfg, random.Random(1))
    assert len(trials) == 8
    assert all(t.is_practice for t in trials)
    assert all(abs(abs(t.level_pct) - cfg.delta_max_pct) < 1e-9 for t in trials)


def test_resolve_seed_uses_configured_seed_when_set():
    cfg = _cfg(rng_seed=123)
    assert resolve_seed(cfg) == 123


def test_resolve_seed_generates_when_unset():
    cfg = _cfg(rng_seed=None)
    seed = resolve_seed(cfg)
    assert isinstance(seed, int)


def test_inter_bar_gap_below_minimum_rejected():
    with pytest.raises(ValueError):
        _cfg(inter_bar_gap_mm=1.0)


def test_build_schedule_wraps_every_spec_with_zero_attempts():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=2, catch_trial_pct=0)
    schedule = build_schedule(cfg, seed=4)

    assert [item.spec for item in schedule] == build_trial_sequence(cfg, seed=4)
    assert all(item.attempts == 0 for item in schedule)


def test_timed_out_trial_is_deferred_until_the_attempt_cap():
    scheduled = ScheduledTrial(build_trial_sequence(_cfg(), seed=4)[0])
    deferred = []

    scheduled.attempts = 1
    assert defer_timed_out_trial(scheduled, deferred, max_attempts=3) is True
    scheduled.attempts = 2
    assert defer_timed_out_trial(scheduled, deferred, max_attempts=3) is True
    scheduled.attempts = 3
    assert defer_timed_out_trial(scheduled, deferred, max_attempts=3) is False

    assert len(deferred) == 2


def test_retry_round_drains_and_reshuffles_the_deferred_pool():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=4, catch_trial_pct=0)
    deferred = build_schedule(cfg, seed=4)
    original = list(deferred)

    round_trials = take_retry_round(deferred, random.Random(7))

    assert deferred == []
    assert sorted(map(id, round_trials)) == sorted(map(id, original))
    assert round_trials != original  # reshuffled, not replayed in timeout order


def test_session_length_is_bounded_by_the_attempt_cap():
    """A participant who never answers still terminates the block."""
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=2, catch_trial_pct=0)
    max_attempts = 3
    pending = build_schedule(cfg, seed=4)
    scheduled_total = len(pending)
    deferred = []
    rng = random.Random(7)

    presentations = 0
    while pending or deferred:
        if not pending:
            pending = take_retry_round(deferred, rng)
        item = pending.pop(0)
        item.attempts += 1
        presentations += 1
        defer_timed_out_trial(item, deferred, max_attempts)
        assert presentations <= scheduled_total * max_attempts

    assert presentations == scheduled_total * max_attempts
