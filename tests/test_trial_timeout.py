from __future__ import annotations

from experiment.display import countdown_seconds
from experiment.trial import should_time_out


def test_main_trial_times_out_at_configured_limit():
    assert not should_time_out(False, 29.999, 30.0)
    assert should_time_out(False, 30.0, 30.0)


def test_practice_trial_has_no_timeout():
    assert not should_time_out(True, 300.0, 30.0)


def test_countdown_rounds_up_and_never_goes_negative():
    assert countdown_seconds(30.0) == 30
    assert countdown_seconds(29.01) == 30
    assert countdown_seconds(29.0) == 29
    assert countdown_seconds(-0.1) == 0
