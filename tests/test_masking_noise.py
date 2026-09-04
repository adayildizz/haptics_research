from __future__ import annotations

import numpy as np

from experiment.masking_noise import render_brown_noise


def test_noise_buffer_is_interleaved_and_loop_safe():
    sample_rate, channels, duration = 8_000, 2, 1.0
    samples = render_brown_noise(sample_rate, channels, duration_s=duration, seed=1)

    assert len(samples) == int(sample_rate * duration) * channels
    frames = np.frombuffer(samples.tobytes(), dtype=np.int16).reshape(-1, channels)
    # Same signal in both ears.
    assert (frames[:, 0] == frames[:, 1]).all()
    # Faded edges so the loop point never clicks; loud in the middle.
    assert abs(int(frames[0, 0])) < 50 and abs(int(frames[-1, 0])) < 50
    assert np.abs(frames[:, 0]).max() > 10_000
    assert np.abs(frames[:, 0]).max() <= 32_767


def test_noise_is_brown_not_white():
    """Power should fall with frequency: low band carries far more than high band."""
    sample_rate = 8_000
    samples = render_brown_noise(sample_rate, 1, duration_s=2.0, seed=3)
    mono = np.frombuffer(samples.tobytes(), dtype=np.int16).astype(float)
    spectrum = np.abs(np.fft.rfft(mono)) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1 / sample_rate)
    low = spectrum[(freqs > 20) & (freqs < 200)].mean()
    high = spectrum[(freqs > 2_000) & (freqs < 4_000)].mean()
    assert low > 50 * high


def test_noise_is_deterministic():
    assert render_brown_noise(4_000, 1, 0.5, seed=7) == render_brown_noise(4_000, 1, 0.5, seed=7)
