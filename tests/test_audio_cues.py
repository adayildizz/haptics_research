"""The cues are synthesized, so the shape of the buffer is testable without a speaker."""

from __future__ import annotations

import pytest

from experiment.audio_cues import RESPONSE_CUE, TIMEOUT_CUE, render_cue


def _expected_frames(tones, sample_rate: int) -> int:
    return sum(
        max(1, int(sample_rate * tone.duration_s)) + int(sample_rate * tone.gap_after_s)
        for tone in tones
    )


@pytest.mark.parametrize("channels", [1, 2])
def test_cue_is_interleaved_for_the_mixer_channel_count(channels: int):
    """The old inline beep always built mono, so a stereo mixer replayed it an octave high."""
    sample_rate = 44_100
    samples = render_cue(RESPONSE_CUE, sample_rate, channels)

    assert len(samples) == _expected_frames(RESPONSE_CUE, sample_rate) * channels
    # Interleaved copies of one mono frame: every channel of a frame matches.
    for frame_start in range(0, min(len(samples), 4_000), channels):
        assert len(set(samples[frame_start:frame_start + channels])) == 1


def test_cues_fade_in_and_out_instead_of_clicking():
    samples = render_cue(TIMEOUT_CUE, 44_100, 2)

    assert samples[0] == 0
    assert samples[-1] == 0
    assert max(abs(v) for v in samples) > 1_000  # ...but not silent


def test_timeout_cue_falls_and_response_cue_rises():
    """The two cues must be distinguishable, and the timeout one must not read as an alarm."""
    response_freqs = [tone.freq_hz for tone in RESPONSE_CUE]
    timeout_freqs = [tone.freq_hz for tone in TIMEOUT_CUE]

    assert response_freqs == sorted(response_freqs)
    assert timeout_freqs == sorted(timeout_freqs, reverse=True)
    # Gentle means slower attack and a longer tail than the response blip.
    assert min(t.attack_s for t in TIMEOUT_CUE) > max(t.attack_s for t in RESPONSE_CUE)
    assert sum(t.duration_s for t in TIMEOUT_CUE) > sum(t.duration_s for t in RESPONSE_CUE)
