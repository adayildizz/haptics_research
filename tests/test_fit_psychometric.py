from __future__ import annotations

import pytest

from analysis.fit_psychometric import (
    aggregate_by_level,
    fit_psychometric,
    psychometric_curve,
    simulate_ideal_observer,
)
from experiment.config import ExperimentConfig
from experiment.constant_stimuli import compute_levels


def test_aggregate_by_level_counts_comparison_taller():
    level_pct = [0.1, 0.1, -0.1, -0.1]
    reference_side = ["left", "right", "left", "right"]
    response = ["right", "left", "right", "left"]  # comparison chosen each time
    levels, n_trials, n_taller = aggregate_by_level(level_pct, reference_side, response)
    assert levels == [-0.1, 0.1]
    assert n_trials == [2, 2]
    assert n_taller == [2, 2]


def test_ideal_observer_fit_recovers_known_jnd():
    cfg = ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, inter_bar_gap_mm=10.0, delta_max_pct=0.30, n_levels=6)
    levels = compute_levels(cfg)
    true_sigma = 0.10
    true_lapse = 0.02
    levels_out, n_trials, n_taller = simulate_ideal_observer(
        levels,
        trials_per_level=400,  # large N to make the recovery tolerance tight and fast
        true_pse=0.0,
        true_sigma=true_sigma,
        true_lapse=true_lapse,
        seed=0,
    )
    fit = fit_psychometric(levels_out, n_trials, n_taller, prefer_psignifit=False)

    true_jnd = true_sigma * (
        _norm_ppf(0.75, true_lapse) - _norm_ppf(0.25, true_lapse)
    ) / 2.0

    assert fit.pse == pytest.approx(0.0, abs=0.02)
    assert fit.jnd == pytest.approx(true_jnd, rel=0.25)


def _norm_ppf(p: float, lapse: float) -> float:
    from scipy.stats import norm

    return float(norm.ppf((p - lapse / 2) / (1 - lapse)))


def test_fit_changes_with_delta_max_pct_config():
    cfg_narrow = ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, inter_bar_gap_mm=10.0, delta_max_pct=0.10, n_levels=6)
    cfg_wide = ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, inter_bar_gap_mm=10.0, delta_max_pct=0.30, n_levels=6)
    for cfg in (cfg_narrow, cfg_wide):
        levels = compute_levels(cfg)
        assert max(levels) == pytest.approx(cfg.delta_max_pct)


def test_dry_run_produces_sane_curve():
    cfg = ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, inter_bar_gap_mm=10.0, delta_max_pct=0.30, n_levels=6, trials_per_level=50)
    levels = compute_levels(cfg)
    levels_out, n_trials, n_taller = simulate_ideal_observer(
        levels, trials_per_level=cfg.trials_per_level, true_sigma=0.10, seed=1
    )
    p = [t / n for t, n in zip(n_taller, n_trials)]
    # monotonically non-decreasing in level, roughly, given enough trials
    sorted_pairs = sorted(zip(levels_out, p))
    p_sorted = [p for _, p in sorted_pairs]
    assert p_sorted[0] < p_sorted[-1]
    assert psychometric_curve(0.0, 0.0, 0.1, 0.02) == pytest.approx(0.51, abs=0.02)
