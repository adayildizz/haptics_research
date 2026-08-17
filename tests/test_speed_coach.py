from __future__ import annotations

from types import SimpleNamespace

from experiment import speed_coach
from experiment.speed_coach import PracticeSpeedCoach, SystemVoice, classify_speed


def test_speed_classification_uses_configured_band():
    assert classify_speed(69.0, 100.0, 0.30) == "too_slow"
    assert classify_speed(70.0, 100.0, 0.30) == "ideal"
    assert classify_speed(130.0, 100.0, 0.30) == "ideal"
    assert classify_speed(131.0, 100.0, 0.30) == "too_fast"


def test_coach_speaks_only_after_stable_movement_and_repeats_errors():
    spoken: list[str] = []
    coach = PracticeSpeedCoach(
        100.0,
        0.30,
        spoken.append,
        smoothing_tau_s=0.01,
        stable_duration_s=0.30,
        repeat_interval_s=2.0,
    )

    coach.update(50.0, 0.1, 0.0, in_active_area=True)
    coach.update(50.0, 0.1, 0.29, in_active_area=True)
    assert spoken == []

    coach.update(50.0, 0.1, 0.31, in_active_area=True)
    assert spoken == ["Faster"]

    coach.update(50.0, 0.1, 1.0, in_active_area=True)
    assert spoken == ["Faster"]
    coach.update(50.0, 0.1, 2.32, in_active_area=True)
    assert spoken == ["Faster", "Faster"]


def test_coach_ignores_stationary_and_outside_area_samples():
    spoken: list[str] = []
    coach = PracticeSpeedCoach(100.0, 0.30, spoken.append, stable_duration_s=0.0)

    coach.update(0.0, 0.1, 0.0, in_active_area=True)
    coach.update(50.0, 0.1, 1.0, in_active_area=False)

    assert spoken == []


def test_coach_retries_when_voice_is_temporarily_busy():
    attempts: list[str] = []

    def busy_once(message: str) -> bool:
        attempts.append(message)
        return len(attempts) > 1

    coach = PracticeSpeedCoach(
        100.0,
        0.30,
        busy_once,
        stable_duration_s=0.0,
    )
    coach.update(100.0, 0.1, 0.0, in_active_area=True)
    coach.update(100.0, 0.1, 0.1, in_active_area=True)
    coach.update(100.0, 0.1, 0.2, in_active_area=True)

    assert attempts == ["Good speed", "Good speed"]


def test_windows_voice_uses_native_sapi_and_passes_text_over_stdin(monkeypatch):
    monkeypatch.setattr(speed_coach.sys, "platform", "win32")
    monkeypatch.setattr(
        speed_coach.shutil,
        "which",
        lambda name: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        if name == "powershell.exe"
        else None,
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(speed_coach.subprocess, "run", fake_run)

    voice = SystemVoice()
    assert voice.available
    assert voice.backend == "windows_sapi"
    assert voice.speak("Good speed", wait=True)

    command, kwargs = calls[0]
    assert command[0].endswith("powershell.exe")
    assert "System.Speech" in command[-1]
    assert kwargs["input"] == b"Good speed"


def test_windows_voice_falls_back_when_powershell_is_missing(monkeypatch):
    monkeypatch.setattr(speed_coach.sys, "platform", "win32")
    monkeypatch.setattr(
        speed_coach.shutil,
        "which",
        lambda name: r"C:\Program Files\eSpeak\command_line\espeak.exe"
        if name == "espeak"
        else None,
    )

    voice = SystemVoice()

    assert voice.available
    assert voice.backend == "espeak"
