from __future__ import annotations

import collections
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


def test_every_block_holds_each_level_the_same_number_of_times():
    """Blocking is what keeps level from drifting with time-on-task."""
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, catch_trial_pct=0)
    levels = compute_levels(cfg)
    block_size = len(levels) * cfg.sweeps_per_block

    sequence = build_trial_sequence(cfg, seed=4)

    for start in range(0, len(sequence), block_size):
        block = sequence[start:start + block_size]
        counts = collections.Counter(round(t.level_pct, 6) for t in block)
        assert counts == {round(l, 6): cfg.sweeps_per_block for l in levels}


def test_level_counts_and_side_balance_survive_blocking():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, catch_trial_pct=0)
    levels = compute_levels(cfg)

    sequence = build_trial_sequence(cfg, seed=4)

    by_level = collections.Counter(round(t.level_pct, 6) for t in sequence)
    assert by_level == {round(l, 6): 10 for l in levels}
    for level in levels:
        sides = [t.reference_side for t in sequence if abs(t.level_pct - level) < 1e-9]
        assert sides.count("left") == sides.count("right") == 5


def test_each_half_of_the_block_gets_the_same_level_counts():
    """A single global shuffle put up to all 10 of a level's trials in one half."""
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, catch_trial_pct=0)

    for seed in range(50):
        sequence = build_trial_sequence(cfg, seed)
        half = len(sequence) // 2
        first = collections.Counter(round(t.level_pct, 6) for t in sequence[:half])
        second = collections.Counter(round(t.level_pct, 6) for t in sequence[half:])
        assert first == second


def test_catch_trials_are_spread_across_blocks():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, catch_trial_pct=0.10)
    block_size = len(compute_levels(cfg)) * cfg.sweeps_per_block

    sequence = build_trial_sequence(cfg, seed=4)
    catch_positions = [i for i, t in enumerate(sequence) if t.is_catch]

    assert len(catch_positions) == 6
    # No block may take more than one, so they cannot bunch up in one stretch.
    blocks_used = [p // (block_size + 1) for p in catch_positions]
    assert len(set(blocks_used)) == len(blocks_used)


def test_wider_blocks_stay_balanced():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=10, sweeps_per_block=2,
               catch_trial_pct=0)
    levels = compute_levels(cfg)

    sequence = build_trial_sequence(cfg, seed=4)

    block_size = len(levels) * 2
    for start in range(0, len(sequence), block_size):
        counts = collections.Counter(round(t.level_pct, 6) for t in sequence[start:start + block_size])
        assert counts == {round(l, 6): 2 for l in levels}


def test_block_size_must_divide_the_trial_count():
    with pytest.raises(ValueError, match="divisible"):
        _cfg(trials_per_level=10, sweeps_per_block=3)
