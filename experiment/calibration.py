"""Physical millimeter to screen-pixel calibration."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import CALIBRATION_FILENAME, FALLBACK_MM_TO_PX
from .data_logger import DATA_DIR, ensure_data_dir


@dataclass(frozen=True)
class DisplayCalibration:
    screen_width_px: int
    screen_height_px: int
    active_width_mm: float
    active_height_mm: float
    px_per_mm_x: float
    px_per_mm_y: float
    source: str


def calibration_path() -> Path:
    return DATA_DIR / CALIBRATION_FILENAME


def make_calibration(
    screen_size: tuple[int, int],
    active_width_mm: float,
    active_height_mm: float,
    source: str = "measured",
) -> DisplayCalibration:
    screen_width_px, screen_height_px = screen_size
    return DisplayCalibration(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        active_width_mm=active_width_mm,
        active_height_mm=active_height_mm,
        px_per_mm_x=screen_width_px / active_width_mm,
        px_per_mm_y=screen_height_px / active_height_mm,
        source=source,
    )


def make_diagonal_calibration(
    screen_size: tuple[int, int],
    diagonal_inch: float,
) -> DisplayCalibration:
    screen_width_px, screen_height_px = screen_size
    diagonal_mm = diagonal_inch * 25.4
    diagonal_px = math.hypot(screen_width_px, screen_height_px)
    active_width_mm = diagonal_mm * screen_width_px / diagonal_px
    active_height_mm = diagonal_mm * screen_height_px / diagonal_px
    return make_calibration(
        screen_size,
        active_width_mm=active_width_mm,
        active_height_mm=active_height_mm,
        source=f"diagonal_{diagonal_inch:g}in",
    )


def fallback_calibration(screen_size: tuple[int, int]) -> DisplayCalibration:
    screen_width_px, screen_height_px = screen_size
    return DisplayCalibration(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        active_width_mm=screen_width_px / FALLBACK_MM_TO_PX,
        active_height_mm=screen_height_px / FALLBACK_MM_TO_PX,
        px_per_mm_x=FALLBACK_MM_TO_PX,
        px_per_mm_y=FALLBACK_MM_TO_PX,
        source="fallback",
    )


def save_calibration(calibration: DisplayCalibration, path: Path | None = None) -> Path:
    ensure_data_dir()
    output_path = calibration_path() if path is None else path
    with output_path.open("w") as file:
        json.dump(asdict(calibration), file, indent=2)
        file.write("\n")
    return output_path


def load_calibration(
    screen_size: tuple[int, int],
    path: Path | None = None,
    allow_fallback: bool = False,
) -> DisplayCalibration:
    input_path = calibration_path() if path is None else path
    if not input_path.exists():
        if allow_fallback:
            return fallback_calibration(screen_size)
        raise FileNotFoundError(
            f"No display calibration found at {input_path}. "
            "Run calibration first with --calibrate --active-width-mm ... --active-height-mm ..."
        )

    with input_path.open() as file:
        data = json.load(file)

    calibration = DisplayCalibration(
        screen_width_px=int(data["screen_width_px"]),
        screen_height_px=int(data["screen_height_px"]),
        active_width_mm=float(data["active_width_mm"]),
        active_height_mm=float(data["active_height_mm"]),
        px_per_mm_x=float(data["px_per_mm_x"]),
        px_per_mm_y=float(data["px_per_mm_y"]),
        source=str(data.get("source", "measured")),
    )

    if (calibration.screen_width_px, calibration.screen_height_px) != screen_size:
        return make_calibration(
            screen_size,
            active_width_mm=calibration.active_width_mm,
            active_height_mm=calibration.active_height_mm,
            source="measured_rescaled",
        )

    return calibration
