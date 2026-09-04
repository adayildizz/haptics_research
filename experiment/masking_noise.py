"""Continuous brown masking noise for the participant's headphones.

The briefing promises "continuous brown noise -- a soft hush that masks the
sounds of the device". Rather than relying on a phone or a separate player
being set up correctly every session, the experiment renders the noise
itself and loops it on a reserved mixer channel for the whole session, so it
starts and stops with the program and its level is part of the config.

Brown noise is white noise passed through a leaky integrator (a first-order
low-pass with its pole very close to 1): the spectrum falls ~6 dB/octave,
which is what makes it a hush rather than a hiss. The leak keeps the random
walk from drifting off into DC.

A single long buffer is looped. Its edges are faded to zero over a few
milliseconds so the loop point never clicks; at 20 s the dip is well below
what anyone notices under the masking level in use.
"""

from __future__ import annotations

from array import array

import numpy as np
import pygame

LOOP_SECONDS = 20.0
EDGE_FADE_S = 0.02
LEAK = 0.995        # integrator pole; closer to 1 = darker, more bass-heavy
PEAK = 0.6          # fraction of full scale after normalisation
NOISE_SEED = 20260905

_channel: pygame.mixer.Channel | None = None
_sound: pygame.mixer.Sound | None = None


def render_brown_noise(
    sample_rate: int,
    channels: int,
    duration_s: float = LOOP_SECONDS,
    seed: int = NOISE_SEED,
) -> array:
    """Render loopable brown noise as interleaved signed-16-bit samples.

    Deterministic given ``seed`` so every session hears the same thing and
    tests can check the buffer without an audio device.
    """
    n = max(2, int(sample_rate * duration_s))
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n)

    # Leaky integration: b[i] = LEAK * b[i-1] + w[i]. scipy's lfilter does
    # this in C; fall back to a numpy loop-free formulation if unavailable.
    try:
        from scipy.signal import lfilter

        brown = lfilter([1.0], [1.0, -LEAK], white)
    except ImportError:  # pragma: no cover - scipy is in requirements
        brown = np.empty(n)
        acc = 0.0
        for i, w in enumerate(white):
            acc = LEAK * acc + w
            brown[i] = acc

    brown -= brown.mean()
    brown *= PEAK / max(1e-9, float(np.max(np.abs(brown))))

    fade_n = max(1, min(n // 2, int(sample_rate * EDGE_FADE_S)))
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, fade_n))
    brown[:fade_n] *= ramp
    brown[-fade_n:] *= ramp[::-1]

    mono = np.clip(brown * 32_767.0, -32_767, 32_767).astype(np.int16)
    interleaved = np.repeat(mono, max(1, channels))
    return array("h", interleaved.tobytes())


def start(volume: float) -> bool:
    """Start looping the noise on a reserved channel. Returns False if audio is unavailable."""
    global _channel, _sound
    if _channel is not None:
        _channel.set_volume(volume)
        return True
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=44_100, size=-16, channels=2)
        init = pygame.mixer.get_init()
        if init is None:
            raise pygame.error("mixer did not initialize")
        sample_rate, sample_format, channels = init
        if sample_format != -16:
            raise pygame.error(f"unsupported mixer sample format {sample_format}")
        # Reserve channel 0 so a burst of cue playback can never steal it.
        pygame.mixer.set_reserved(1)
        _sound = pygame.mixer.Sound(buffer=render_brown_noise(sample_rate, abs(channels)).tobytes())
        _channel = pygame.mixer.Channel(0)
        _channel.set_volume(max(0.0, min(1.0, volume)))
        _channel.play(_sound, loops=-1)
        return True
    except (pygame.error, ValueError) as exc:
        print(f"Masking noise unavailable ({exc}).")
        _channel = None
        _sound = None
        return False


def stop() -> None:
    global _channel, _sound
    if _channel is not None:
        try:
            _channel.stop()
        except pygame.error:
            pass
    _channel = None
    _sound = None
