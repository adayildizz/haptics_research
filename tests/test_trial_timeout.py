from __future__ import annotations

from experiment.display import countdown_seconds
from experiment.trial import should_time_out


def test_trial_times_out_at_configured_limit():
    assert not should_time_out(29.999, 30.0)
    assert should_time_out(30.0, 30.0)


def test_practice_trials_are_timed_too():
    """Practice used to be unlimited; it now runs under the same clock."""
    assert should_time_out(30.0, 30.0)
    assert not should_time_out(10.0, 30.0)


def test_countdown_rounds_up_and_never_goes_negative():
    assert countdown_seconds(30.0) == 30
    assert countdown_seconds(29.01) == 30
    assert countdown_seconds(29.0) == 29
    assert countdown_seconds(-0.1) == 0
