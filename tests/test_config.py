from __future__ import annotations

import pytest

from experiment.config import ExperimentConfig, load_experiment_config


def test_load_default_yaml_config():
    cfg = load_experiment_config("experiment/configs/default.yaml")
    assert isinstance(cfg, ExperimentConfig)
    assert cfg.base_height_mm == 10.0
    assert cfg.delta_max_pct == 0.30
    assert cfg.response_timeout_s == 30.0
    assert cfg.mode == "constant_stimuli"


def test_non_positive_response_timeout_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, response_timeout_s=0)


def test_load_pilot_yaml_config():
    cfg = load_experiment_config("experiment/configs/pilot.yaml")
    assert cfg.mode == "staircase_pilot"


def test_unknown_config_key_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("base_height_mm: 10.0\nbar_width_mm: 10.0\ntypo_field: 1\n")
    with pytest.raises(ValueError):
        load_experiment_config(bad)


def test_changing_yaml_changes_config_with_zero_code_edits(tmp_path):
    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "base_height_mm: 20.0\nbar_width_mm: 5.0\ninter_bar_gap_mm: 6.0\n"
        "delta_max_pct: 0.15\nn_levels: 4\ntrials_per_level: 20\n"
    )
    cfg = load_experiment_config(custom)
    assert cfg.base_height_mm == 20.0
    assert cfg.delta_max_pct == 0.15
    assert cfg.n_levels == 4
    assert cfg.trials_per_level == 20
