"""Short synthesized audio cues for the participant-facing screen.

Two cues, deliberately easy to tell apart without teaching the participant
anything about whether their answer was right:

- ``play_response_cue()`` -- a brief rising blip the moment a response is
  registered. It means "recorded, moving on" and nothing else: the *same*
  sound plays for correct and incorrect answers, so it never leaks
  feedback in the no-feedback main block.
- ``play_timeout_cue()`` -- a soft descending chime when the response
  window closes. Deliberately gentle (slow attack, falling interval, long
  release, moderate level) so it reads as an invitation back to the task
  rather than an alarm.

Everything is synthesized in-process, so the repo carries no audio assets.

Why this module exists instead of a beep inlined in ``trial.py``: the
inlined version built a *mono* buffer and handed it to a mixer that
``pygame.init()`` has already opened in *stereo*. pygame then reads that
buffer as interleaved stereo, so every cue played back an octave high and
at half its intended length. The rendering below asks the mixer how many
channels it actually has and interleaves to match.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass

import pygame

# Cue shapes. These are perceptual judgment calls, not measured constants:
# short/rising/bright for "answer taken", long/falling/soft for "time is up".
# Amplitudes are fractions of full scale.


@dataclass(frozen=True)
class _Tone:
    freq_hz: float
    duration_s: float
    amplitude: float
    attack_s: float
    release_s: float
    gap_after_s: float = 0.0


# E5 -> B5, ~150 ms total: quick, neutral, clearly "next trial".
RESPONSE_CUE: tuple[_Tone, ...] = (
    _Tone(659.25, 0.055, 0.20, 0.006, 0.030, gap_after_s=0.012),
    _Tone(987.77, 0.090, 0.18, 0.006, 0.055),
)

# D5 -> A4, ~550 ms total: descending, slow attack, long release. Falling
# and unhurried is what keeps this from sounding like an alarm.
TIMEOUT_CUE: tuple[_Tone, ...] = (
    _Tone(587.33, 0.170, 0.24, 0.035, 0.090, gap_after_s=0.020),
    _Tone(440.00, 0.340, 0.26, 0.045, 0.220),
)

_cache: dict[str, pygame.mixer.Sound] = {}
_unavailable = False


def _ensure_mixer() -> tuple[int, int, int] | None:
    """Return ``(sample_rate, size, channels)``, initializing the mixer if needed."""
    init = pygame.mixer.get_init()
    if init is None:
        pygame.mixer.init(frequency=44_100, size=-16, channels=2)
        init = pygame.mixer.get_init()
    return init


def _envelope(i: int, n: int, attack_n: int, release_n: int) -> float:
    """Raised-cosine attack/release, so tones fade in and out instead of clicking."""
    level = 1.0
    if i < attack_n:
        level = 0.5 - 0.5 * math.cos(math.pi * i / attack_n)
    if i >= n - release_n:
        remaining = (n - i) / release_n
        level = min(level, 0.5 - 0.5 * math.cos(math.pi * remaining))
    return level


def render_cue(tones: tuple[_Tone, ...], sample_rate: int, channels: int) -> array:
    """Render ``tones`` to an interleaved signed-16-bit sample array.

    Split out from ``_sound_for`` so the interleaving can be unit tested
    without an audio device.
    """
    samples = array("h")
    for tone in tones:
        n = max(1, int(sample_rate * tone.duration_s))
        attack_n = max(1, int(sample_rate * tone.attack_s))
        release_n = max(1, int(sample_rate * tone.release_s))
        for i in range(n):
            value = (
                tone.amplitude
                * _envelope(i, n, attack_n, release_n)
                * math.sin(2.0 * math.pi * tone.freq_hz * i / sample_rate)
            )
            frame = int(max(-1.0, min(1.0, value)) * 32_767)
            for _ in range(channels):
                samples.append(frame)
        for _ in range(int(sample_rate * tone.gap_after_s)):
            for _ in range(channels):
                samples.append(0)
    return samples


def _sound_for(name: str, tones: tuple[_Tone, ...]) -> pygame.mixer.Sound | None:
    global _unavailable
    if _unavailable:
        return None
    cached = _cache.get(name)
    if cached is not None:
        return cached
    try:
        init = _ensure_mixer()
        if init is None:
            raise pygame.error("mixer did not initialize")
        sample_rate, sample_format, channels = init
        if sample_format != -16:
            raise pygame.error(f"unsupported mixer sample format {sample_format}")
        sound = pygame.mixer.Sound(buffer=render_cue(tones, sample_rate, abs(channels)).tobytes())
    except (pygame.error, ValueError) as exc:
        _unavailable = True
        print(f"Audio cues unavailable ({exc}).")
        return None
    _cache[name] = sound
    return sound


def preload() -> None:
    """Synthesize both cues up front.

    Building a cue takes tens of thousands of Python-level sine
    evaluations; doing that lazily inside the trial loop would drop frames
    on the first response. Call once after ``pygame.init()``.
    """
    _sound_for("response", RESPONSE_CUE)
    _sound_for("timeout", TIMEOUT_CUE)


def play_response_cue() -> None:
    """Neutral 'answer recorded, next trial' blip. Never signals correctness."""
    sound = _sound_for("response", RESPONSE_CUE)
    if sound is not None:
        sound.play()


def play_timeout_cue() -> None:
    """Gentle 'the response window closed' chime."""
    sound = _sound_for("timeout", TIMEOUT_CUE)
    if sound is not None:
        sound.play()
