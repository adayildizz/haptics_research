"""Electroadhesion signal helpers for the height-JND experiment."""

from __future__ import annotations

import time
from typing import Any

from .config import (
    CARRIER_FREQUENCY,
    DISABLE_OUTPUT_WHEN_OFF,
    MAX_SIGNAL_DURATION_S,
    MIN_SPEED_MM_S,
    MIN_VOLTAGE,
    PEAK_VOLTAGE,
    VISA_ADDRESS,
)

_current_frequency: float | None = None
_current_voltage: float | None = None
_output_enabled = False


def _write_frequency(instrument: Any, frequency: float, *, force: bool = False) -> None:
    global _current_frequency
    if force or _current_frequency is None or int(frequency) != int(_current_frequency):
        instrument.write(f"FREQ {int(frequency)}")
        _current_frequency = frequency


def _write_voltage(instrument: Any, voltage: float, *, force: bool = False) -> None:
    global _current_voltage
    if force or _current_voltage is None or abs(voltage - _current_voltage) > 0.05:
        instrument.write(f"VOLT {voltage:.2f}")
        _current_voltage = voltage


def _write_output(instrument: Any, enabled: bool, *, force: bool = False) -> None:
    global _output_enabled
    if force or enabled != _output_enabled:
        instrument.write(f"OUTP {'ON' if enabled else 'OFF'}")
        _output_enabled = enabled


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
        _write_frequency(instrument, CARRIER_FREQUENCY, force=True)
        _write_voltage(instrument, MIN_VOLTAGE, force=True)
        _write_output(instrument, True, force=True)
        print(f"Connected to signal generator: {instrument.query('*IDN?').strip()}")
        return instrument
    except Exception as exc:
        print(f"Hardware unavailable ({exc}). Running without electroadhesion output.")
        return None


def signal_on(instrument: Any | None) -> None:
    """Activate the bar interior signal."""
    if instrument is None:
        return
    _write_frequency(instrument, CARRIER_FREQUENCY)
    _write_output(instrument, True)
    _write_voltage(instrument, PEAK_VOLTAGE)


def signal_off(instrument: Any | None) -> None:
    """Deactivate the signal for bar exterior regions."""
    if instrument is None:
        return
    if DISABLE_OUTPUT_WHEN_OFF:
        _write_output(instrument, False)
    else:
        _write_output(instrument, True)
        _write_voltage(instrument, MIN_VOLTAGE)


def close_hardware(instrument: Any | None) -> None:
    """Turn the signal off and close the VISA resource."""
    if instrument is None:
        return
    try:
        _write_voltage(instrument, MIN_VOLTAGE, force=True)
        _write_output(instrument, False, force=True)
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
