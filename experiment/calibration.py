"""Physical millimeter to screen-pixel calibration."""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    HAPTIC_SURFACE_HEIGHT_MM,
    HAPTIC_SURFACE_LEFT_PADDING_MM,
    HAPTIC_SURFACE_TOP_PADDING_MM,
    HAPTIC_SURFACE_WIDTH_MM,
    IR_FRAME_HEIGHT_MM,
    IR_FRAME_SCREEN_HEIGHT_PX,
    IR_FRAME_SCREEN_WIDTH_PX,
    IR_FRAME_WIDTH_MM,
)


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


def make_configured_ir_frame_calibration(screen_size: tuple[int, int]) -> DisplayCalibration:
    """Map the configured physical touch surface through the configured IR frame."""
    screen_width_px, screen_height_px = screen_size
    scale_x = screen_width_px / IR_FRAME_SCREEN_WIDTH_PX
    scale_y = screen_height_px / IR_FRAME_SCREEN_HEIGHT_PX
    px_per_mm_x = (IR_FRAME_SCREEN_WIDTH_PX / IR_FRAME_WIDTH_MM) * scale_x
    px_per_mm_y = (IR_FRAME_SCREEN_HEIGHT_PX / IR_FRAME_HEIGHT_MM) * scale_y

    active_width_px = max(1, round(HAPTIC_SURFACE_WIDTH_MM * px_per_mm_x))
    active_height_px = max(1, round(HAPTIC_SURFACE_HEIGHT_MM * px_per_mm_y))
    active_left_px = round(HAPTIC_SURFACE_LEFT_PADDING_MM * px_per_mm_x)
    active_top_px = round(HAPTIC_SURFACE_TOP_PADDING_MM * px_per_mm_y)

    return DisplayCalibration(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        active_left_px=active_left_px,
        active_top_px=active_top_px,
        active_width_px=active_width_px,
        active_height_px=active_height_px,
        active_width_mm=HAPTIC_SURFACE_WIDTH_MM,
        active_height_mm=HAPTIC_SURFACE_HEIGHT_MM,
        px_per_mm_x=px_per_mm_x,
        px_per_mm_y=px_per_mm_y,
        source="configured_ir_frame",
    )
