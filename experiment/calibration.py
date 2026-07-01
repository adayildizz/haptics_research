"""Physical millimeter to screen-pixel calibration."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import HAPTIC_SURFACE_CALIBRATION_FILENAME
from .data_logger import DATA_DIR, ensure_data_dir


@dataclass(frozen=True)
class DisplayCalibration:
    screen_width_px: int
    screen_height_px: int
    active_left_px: int
    active_top_px: int
    active_width_px: int
    active_height_px: int
    active_width_mm: float
    active_height_mm: float
    px_per_mm_x: float
    px_per_mm_y: float
    source: str


def haptic_surface_calibration_path() -> Path:
    return DATA_DIR / HAPTIC_SURFACE_CALIBRATION_FILENAME


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
        active_left_px=0,
        active_top_px=0,
        active_width_px=screen_width_px,
        active_height_px=screen_height_px,
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


def make_haptic_surface_calibration(
    screen_size: tuple[int, int],
    top_left: tuple[int, int],
    bottom_right: tuple[int, int],
    active_width_mm: float,
    active_height_mm: float,
) -> DisplayCalibration:
    left = min(top_left[0], bottom_right[0])
    top = min(top_left[1], bottom_right[1])
    right = max(top_left[0], bottom_right[0])
    bottom = max(top_left[1], bottom_right[1])
    active_width_px = max(1, right - left)
    active_height_px = max(1, bottom - top)
    return DisplayCalibration(
        screen_width_px=screen_size[0],
        screen_height_px=screen_size[1],
        active_left_px=left,
        active_top_px=top,
        active_width_px=active_width_px,
        active_height_px=active_height_px,
        active_width_mm=active_width_mm,
        active_height_mm=active_height_mm,
        px_per_mm_x=active_width_px / active_width_mm,
        px_per_mm_y=active_height_px / active_height_mm,
        source="haptic_surface_touch",
    )


def save_haptic_surface_calibration(calibration: DisplayCalibration) -> Path:
    ensure_data_dir()
    output_path = haptic_surface_calibration_path()
    with output_path.open("w") as file:
        json.dump(asdict(calibration), file, indent=2)
        file.write("\n")
    return output_path


def _read_calibration_file(path: Path) -> DisplayCalibration:
    with path.open() as file:
        data = json.load(file)

    screen_width_px = int(data["screen_width_px"])
    screen_height_px = int(data["screen_height_px"])
    active_left_px = int(data.get("active_left_px", 0))
    active_top_px = int(data.get("active_top_px", 0))
    active_width_px = int(data.get("active_width_px", screen_width_px))
    active_height_px = int(data.get("active_height_px", screen_height_px))
    return DisplayCalibration(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        active_left_px=active_left_px,
        active_top_px=active_top_px,
        active_width_px=active_width_px,
        active_height_px=active_height_px,
        active_width_mm=float(data["active_width_mm"]),
        active_height_mm=float(data["active_height_mm"]),
        px_per_mm_x=float(data["px_per_mm_x"]),
        px_per_mm_y=float(data["px_per_mm_y"]),
        source=str(data.get("source", "measured")),
    )


def _rescale_calibration(
    calibration: DisplayCalibration,
    screen_size: tuple[int, int],
) -> DisplayCalibration:
    if (calibration.screen_width_px, calibration.screen_height_px) == screen_size:
        return calibration

    scale_x = screen_size[0] / calibration.screen_width_px
    scale_y = screen_size[1] / calibration.screen_height_px
    active_left_px = round(calibration.active_left_px * scale_x)
    active_top_px = round(calibration.active_top_px * scale_y)
    active_width_px = round(calibration.active_width_px * scale_x)
    active_height_px = round(calibration.active_height_px * scale_y)
    return DisplayCalibration(
        screen_width_px=screen_size[0],
        screen_height_px=screen_size[1],
        active_left_px=active_left_px,
        active_top_px=active_top_px,
        active_width_px=max(1, active_width_px),
        active_height_px=max(1, active_height_px),
        active_width_mm=calibration.active_width_mm,
        active_height_mm=calibration.active_height_mm,
        px_per_mm_x=max(1, active_width_px) / calibration.active_width_mm,
        px_per_mm_y=max(1, active_height_px) / calibration.active_height_mm,
        source=f"{calibration.source}_rescaled",
    )


def load_haptic_surface_calibration(
    screen_size: tuple[int, int],
) -> DisplayCalibration | None:
    path = haptic_surface_calibration_path()
    if not path.exists():
        return None
    return _rescale_calibration(_read_calibration_file(path), screen_size)
