"""Practice repeats until the participant clears the pass mark."""

from __future__ import annotations

import pytest

from experiment.config import ExperimentConfig
from experiment.constant_stimuli import practice_passed, practice_required_correct


def test_pass_mark_is_ceiling_of_fraction():
    assert practice_required_correct(16, 0.75) == 12
    assert practice_required_correct(8, 0.75) == 6
    assert practice_required_correct(10, 0.75) == 8  # 7.5 -> at least 75% means 8
    assert practice_required_correct(16, 0.0) == 0


def test_below_twelve_of_sixteen_repeats():
    assert practice_passed(12, 16, 0.75)
    assert practice_passed(16, 16, 0.75)
    assert not practice_passed(11, 16, 0.75)
    assert not practice_passed(0, 16, 0.75)


def test_pass_fraction_is_validated():
    with pytest.raises(ValueError):
        ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0, practice_pass_fraction=1.5)
    cfg = ExperimentConfig(base_height_mm=10.0, bar_width_mm=10.0)
    assert cfg.practice_pass_fraction == 0.75
