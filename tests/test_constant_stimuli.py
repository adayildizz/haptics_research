from __future__ import annotations

import random

import pytest

from experiment.config import ExperimentConfig
from experiment.constant_stimuli import (
    build_practice_sequence,
    build_trial_sequence,
    comparison_height_mm,
    compute_levels,
    resolve_seed,
    requeue_timed_out_trial,
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


def test_timed_out_trial_is_requeued_without_reducing_total():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=2, catch_trial_pct=0)
    trials = build_trial_sequence(cfg, seed=4)
    timed_out = trials.pop(0)
    original_total = len(trials) + 1

    requeue_timed_out_trial(trials, timed_out, cfg, random.Random(7))

    assert len(trials) == original_total
    assert timed_out in trials
    assert trials[0].comparison_height_mm != timed_out.comparison_height_mm


def test_last_timed_out_slot_gets_a_different_random_height():
    cfg = _cfg(delta_max_pct=0.30, n_levels=6, trials_per_level=2, catch_trial_pct=0)
    timed_out = build_trial_sequence(cfg, seed=4)[0]
    pending = []

    requeue_timed_out_trial(pending, timed_out, cfg, random.Random(7))

    assert len(pending) == 1
    assert pending[0].comparison_height_mm != timed_out.comparison_height_mm
