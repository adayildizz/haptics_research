"""Electroadhesion signal helpers for the height-JND experiment."""

from __future__ import annotations

import time
from typing import Any

from .config import (
    CARRIER_FREQUENCY,
    MAX_SIGNAL_DURATION_S,
    MIN_SPEED_MM_S,
    MIN_VOLTAGE,
    PEAK_VOLTAGE,
    VISA_ADDRESS,
)


def connect_hardware(address: str = VISA_ADDRESS) -> Any | None:
    """Open and configure the VISA signal generator.

    Returns ``None`` when PyVISA or the instrument is unavailable so demo mode
    can run without hardware.
    """
    try:
        import pyvisa

        rm = pyvisa.ResourceManager()
        instrument = rm.open_resource(address)
        instrument.write_termination = "\n"
        instrument.read_termination = "\n"
        instrument.write("*RST")
        instrument.write("VOLT:UNIT VPP")
        instrument.write("OUTP:LOAD INF")
        instrument.write("FUNC SQU")
        instrument.write("FUNC:SQU:DCYC 50")
        instrument.write(f"FREQ {CARRIER_FREQUENCY}")
        instrument.write(f"VOLT {MIN_VOLTAGE}")
        instrument.write("OUTP ON")
        print(f"Connected to signal generator: {instrument.query('*IDN?').strip()}")
        return instrument
    except Exception as exc:
        print(f"Hardware unavailable ({exc}). Running without electroadhesion output.")
        return None


def signal_on(instrument: Any | None) -> None:
    """Activate the bar interior signal."""
    if instrument is None:
        return
    instrument.write(f"FREQ {CARRIER_FREQUENCY}")
    instrument.write(f"VOLT {PEAK_VOLTAGE}")
    instrument.write("OUTP ON")


def signal_off(instrument: Any | None) -> None:
    """Deactivate the signal for bar exterior regions."""
    if instrument is None:
        return
    instrument.write(f"VOLT {MIN_VOLTAGE}")


def close_hardware(instrument: Any | None) -> None:
    """Turn the signal off and close the VISA resource."""
    if instrument is None:
        return
    try:
        signal_off(instrument)
        instrument.write("OUTP OFF")
        instrument.close()
    except Exception:
        pass


def stimulus_duration(bar_width_mm: float, finger_speed_mm_s: float) -> float:
    """Compute timed rendering duration from bar width and finger speed."""
    speed = max(abs(finger_speed_mm_s), MIN_SPEED_MM_S)
    return min(bar_width_mm / speed, MAX_SIGNAL_DURATION_S)


def deliver_timed_signal(
    instrument: Any | None,
    start_time_s: float,
    duration_s: float,
    now_s: float | None = None,
) -> bool:
    """Set signal ON while the current time is inside the requested interval."""
    current_time = time.perf_counter() if now_s is None else now_s
    active = start_time_s <= current_time < start_time_s + duration_s
    if active:
        signal_on(instrument)
    else:
        signal_off(instrument)
    return active
