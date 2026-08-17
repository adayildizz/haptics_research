"""Spoken cursor-speed guidance used exclusively during practice trials."""

from __future__ import annotations

import math
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Literal

SpeedState = Literal["too_slow", "ideal", "too_fast"]

PRACTICE_INSTRUCTION = (
    "Speed guidance is active. Faster means move your finger faster. "
    "Slower means move your finger slower. Good speed means your speed is correct."
)

_MESSAGES: dict[SpeedState, str] = {
    "too_slow": "Faster",
    "ideal": "Good speed",
    "too_fast": "Slower",
}

_WINDOWS_SAPI_SCRIPT = (
    "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
    "Add-Type -AssemblyName System.Speech; "
    "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "try { $voice.Rate = 2; $voice.Speak([Console]::In.ReadToEnd()) } "
    "finally { $voice.Dispose() }"
)


def classify_speed(speed_mm_s: float, target_mm_s: float, tolerance_pct: float) -> SpeedState:
    """Classify speed relative to the configured acceptable band."""
    lower = target_mm_s * (1.0 - tolerance_pct)
    upper = target_mm_s * (1.0 + tolerance_pct)
    if speed_mm_s < lower:
        return "too_slow"
    if speed_mm_s > upper:
        return "too_fast"
    return "ideal"


class SystemVoice:
    """Small non-blocking wrapper around an available operating-system TTS command."""

    def __init__(self) -> None:
        self._command: list[str] | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._message_via_stdin = False
        self._backend: str | None = None
        self._failure_reported = False

        powershell = None
        if sys.platform == "win32":
            powershell = (
                shutil.which("powershell.exe")
                or shutil.which("powershell")
                or shutil.which("pwsh.exe")
                or shutil.which("pwsh")
            )
        if powershell is not None:
            self._command = [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _WINDOWS_SAPI_SCRIPT,
            ]
            self._message_via_stdin = True
            self._backend = "windows_sapi"
        elif shutil.which("say"):
            self._command = ["say", "-r", "220"]
            self._backend = "macos_say"
        elif shutil.which("espeak"):
            self._command = ["espeak", "-s", "180"]
            self._backend = "espeak"
        elif shutil.which("spd-say"):
            self._command = ["spd-say"]
            self._backend = "spd_say"
        else:
            print("Practice voice feedback unavailable: no system TTS command found.")

    @property
    def available(self) -> bool:
        return self._command is not None

    @property
    def backend(self) -> str | None:
        return self._backend

    def speak(self, message: str, *, wait: bool = False) -> bool:
        if self._command is None:
            return False
        if self._process is not None:
            returncode = self._process.poll()
            if returncode is None:
                return False
            self._process = None
            if returncode != 0:
                self._disable(f"TTS process exited with code {returncode}")
                return False

        command = list(self._command)
        input_bytes = message.encode("utf-8") if self._message_via_stdin else None
        if not self._message_via_stdin:
            command.append(message)
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if self._backend == "windows_sapi"
            else 0
        )
        try:
            if wait:
                completed = subprocess.run(
                    command,
                    check=False,
                    input=input_bytes,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                self._process = None
                if completed.returncode != 0:
                    self._disable(f"TTS process exited with code {completed.returncode}")
                    return False
            else:
                self._process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE if input_bytes is not None else None,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                if input_bytes is not None:
                    assert self._process.stdin is not None
                    self._process.stdin.write(input_bytes)
                    self._process.stdin.close()
            return True
        except (OSError, BrokenPipeError) as exc:
            self._disable(str(exc))
            return False

    def _disable(self, reason: str) -> None:
        self._command = None
        self._backend = None
        if not self._failure_reported:
            print(f"Practice voice feedback unavailable: {reason}.")
            self._failure_reported = True

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        self._process = None


class PracticeSpeedCoach:
    """Smooth and debounce speed samples before issuing short spoken prompts."""

    def __init__(
        self,
        target_mm_s: float,
        tolerance_pct: float,
        speaker: Callable[[str], object],
        *,
        smoothing_tau_s: float = 0.30,
        stable_duration_s: float = 0.30,
        repeat_interval_s: float = 2.0,
        stationary_threshold_mm_s: float = 5.0,
        idle_reset_s: float = 0.30,
    ) -> None:
        self.target_mm_s = target_mm_s
        self.tolerance_pct = tolerance_pct
        self._speaker = speaker
        self.smoothing_tau_s = smoothing_tau_s
        self.stable_duration_s = stable_duration_s
        self.repeat_interval_s = repeat_interval_s
        self.stationary_threshold_mm_s = stationary_threshold_mm_s
        self.idle_reset_s = idle_reset_s
        self.reset_trial()

    def reset_trial(self) -> None:
        self.smoothed_speed_mm_s: float | None = None
        self._candidate: SpeedState | None = None
        self._candidate_since_s = 0.0
        self._accepted: SpeedState | None = None
        self._last_spoken_s = float("-inf")
        self._idle_since_s: float | None = None

    def update(self, raw_speed_mm_s: float, sample_interval_s: float, now_s: float, *, in_active_area: bool) -> None:
        moving = in_active_area and raw_speed_mm_s >= self.stationary_threshold_mm_s
        if not moving:
            if self._idle_since_s is None:
                self._idle_since_s = now_s
            elif now_s - self._idle_since_s >= self.idle_reset_s:
                self._candidate = None
                self._accepted = None
                self.smoothed_speed_mm_s = None
            return

        self._idle_since_s = None
        if self.smoothed_speed_mm_s is None:
            self.smoothed_speed_mm_s = raw_speed_mm_s
        else:
            alpha = 1.0 - math.exp(-sample_interval_s / self.smoothing_tau_s)
            self.smoothed_speed_mm_s += alpha * (raw_speed_mm_s - self.smoothed_speed_mm_s)

        state = classify_speed(self.smoothed_speed_mm_s, self.target_mm_s, self.tolerance_pct)
        if state != self._candidate:
            self._candidate = state
            self._candidate_since_s = now_s
            return
        if now_s - self._candidate_since_s < self.stable_duration_s:
            return

        state_changed = state != self._accepted
        should_repeat_error = state != "ideal" and now_s - self._last_spoken_s >= self.repeat_interval_s
        if state_changed or should_repeat_error:
            speech_started = self._speaker(_MESSAGES[state])
            if speech_started is False:
                return
            self._accepted = state
            self._last_spoken_s = now_s
