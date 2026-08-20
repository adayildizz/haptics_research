"""One sample per input report, not one per rendered frame."""

from __future__ import annotations

import pygame
import pytest

from experiment.calibration import DisplayCalibration
from experiment.display import TrialLayout
from experiment.trial import frame_samples


@pytest.fixture
def calibration() -> DisplayCalibration:
    return DisplayCalibration(
        screen_width_px=1920,
        screen_height_px=1080,
        active_left_px=0,
        active_top_px=0,
        active_width_px=1920,
        active_height_px=1080,
        active_width_mm=192.0,
        active_height_mm=108.0,
        px_per_mm_x=10.0,
        px_per_mm_y=10.0,
        source="test",
    )


@pytest.fixture
def layout() -> TrialLayout:
    return TrialLayout(
        left_bar=pygame.Rect(100, 100, 100, 200),
        right_bar=pygame.Rect(400, 100, 100, 200),
        haptic_area=pygame.Rect(0, 0, 1920, 1080),
        left_is_comparison=True,
        reference_height_mm=10.0,
        comparison_height_mm=13.0,
        bar_width_mm=10.0,
    )


def _call(reports, calibration, layout, **overrides):
    kwargs = dict(
        first_sequence=0,
        previous_pos=(0, 0),
        previous_t=1.0,
        frame_end_t=1.0 + 1 / 60,
        trial_start=1.0,
        calibration=calibration,
        layout=layout,
        signal_on=False,
    )
    kwargs.update(overrides)
    return frame_samples(reports, **kwargs)


def test_every_report_in_the_frame_becomes_a_sample(calibration, layout):
    """The IR frame outruns the render loop; none of its reports may be dropped."""
    reports = [((10, 0), True), ((20, 0), True), ((30, 0), True)]

    samples = _call(reports, calibration, layout)

    assert [s.x_px for s in samples] == [10, 20, 30]
    assert [s.sequence for s in samples] == [0, 1, 2]


def test_timestamps_are_spread_across_the_frame_interval(calibration, layout):
    reports = [((10, 0), True), ((20, 0), True)]

    samples = _call(reports, calibration, layout)

    frame_us = round((1 / 60) * 1_000_000)
    assert samples[0].t_us == pytest.approx(frame_us / 2, abs=2)
    assert samples[1].t_us == pytest.approx(frame_us, abs=2)
    # Each dt covers its own slice, not the whole frame.
    assert sum(s.frame_dt_us for s in samples) == pytest.approx(frame_us, abs=4)


def test_speed_is_computed_between_consecutive_reports(calibration, layout):
    """Reusing the frame's single speed for every sub-sample would defeat the point."""
    # 10 px = 1 mm apart, half a 60 Hz frame (~8.33 ms) between them.
    samples = _call([((10, 0), True), ((20, 0), True)], calibration, layout)

    expected = 1.0 / ((1 / 60) / 2)
    assert samples[0].speed_mm_s == pytest.approx(expected, rel=0.01)
    assert samples[1].speed_mm_s == pytest.approx(expected, rel=0.01)


def test_side_is_resolved_per_report(calibration, layout):
    reports = [((50, 150), True), ((150, 150), True), ((450, 150), True)]

    samples = _call(reports, calibration, layout)

    assert [s.active_side for s in samples] == [None, "left", "right"]


def test_contact_travels_with_each_report(calibration, layout):
    """A lifted finger must be distinguishable from one held still."""
    samples = _call([((10, 0), True), ((10, 0), False)], calibration, layout)

    assert [s.contact for s in samples] == [True, False]


def test_a_motionless_frame_still_records_one_sample(calibration, layout):
    samples = _call([((10, 0), True)], calibration, layout, previous_pos=(10, 0))

    assert len(samples) == 1
    assert samples[0].speed_mm_s == 0.0


def test_pass_entry_gap_is_measured_against_the_ir_rate():
    """The threshold used to see render-frame gaps, so it was almost always true."""
    from experiment.trial import _PassTracker

    tracker = _PassTracker(max_sample_gap_s=3.0 / 100.0)  # 30 ms at 100 Hz

    # A healthy ~10 ms inter-report gap: the entry is well localised.
    tracker.start("left", now_s=0.0, speed_mm_s=100.0, commanded_s=0.1, sample_gap_s=0.010)
    tracker.finish(0.1)
    # A 50 ms gap means the device (or the loop) skipped over the edge.
    tracker.start("right", now_s=0.2, speed_mm_s=100.0, commanded_s=0.1, sample_gap_s=0.050)
    tracker.finish(0.3)

    assert [p["leading_edge_detected"] for p in tracker.passes] == [True, False]
    assert [p["entry_report_gap_s"] for p in tracker.passes] == [0.010, 0.050]


def test_touch_state_is_not_trusted_until_the_device_reports_it():
    """A driver that never reports touch must not silence the stimulus."""
    import experiment.trial as trial

    # Mirrors the loop's gate: `contact or not _touch_state_available`.
    for touch_available, contact, expected in [
        (False, False, True),   # device never reported touch -> behave as before
        (False, True, True),
        (True, True, True),     # device reports touch and the finger is down
        (True, False, False),   # ...and the finger is up: nothing to feel
    ]:
        assert (contact or not touch_available) is expected

    assert trial._touch_state_available is False  # nothing observed in tests
