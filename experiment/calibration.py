"""Physical millimeter to screen-pixel calibration."""

from __future__ import annotations

import math
from dataclasses import dataclass


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


def make_diagonal_centered_calibration(
    screen_size: tuple[int, int],
    diagonal_inch: float,
    active_width_mm: float,
    active_height_mm: float,
) -> DisplayCalibration:
    """Estimate px/mm from the screen diagonal, then center a fixed-size (mm) rect on screen."""
    screen_width_px, screen_height_px = screen_size
    diagonal_mm = diagonal_inch * 25.4
    diagonal_px = math.hypot(screen_width_px, screen_height_px)
    px_per_mm = diagonal_px / diagonal_mm

    active_width_px = max(1, round(active_width_mm * px_per_mm))
    active_height_px = max(1, round(active_height_mm * px_per_mm))
    active_left_px = max(0, (screen_width_px - active_width_px) // 2)
    active_top_px = max(0, (screen_height_px - active_height_px) // 2)

    return DisplayCalibration(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        active_left_px=active_left_px,
        active_top_px=active_top_px,
        active_width_px=active_width_px,
        active_height_px=active_height_px,
        active_width_mm=active_width_mm,
        active_height_mm=active_height_mm,
        px_per_mm_x=px_per_mm,
        px_per_mm_y=px_per_mm,
        source=f"diagonal_{diagonal_inch:g}in_centered",
    )
