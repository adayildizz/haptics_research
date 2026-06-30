"""Pygame drawing utilities for the 2AFC bar-height experiment."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from .calibration import DisplayCalibration
from .config import SCREEN_HEIGHT, SCREEN_WIDTH, USE_FULLSCREEN

Color = tuple[int, int, int]

BACKGROUND: Color = (18, 20, 24)
PANEL: Color = (32, 36, 44)
PANEL_ACTIVE: Color = (42, 50, 62)
DIVIDER: Color = (110, 116, 128)
BAR_REF: Color = (66, 153, 225)
BAR_TEST: Color = (72, 187, 120)
BAR_OUTLINE: Color = (230, 235, 240)
TEXT: Color = (238, 242, 247)
MUTED: Color = (172, 180, 192)


@dataclass(frozen=True)
class TrialLayout:
    left_bar: pygame.Rect
    right_bar: pygame.Rect
    haptic_area: pygame.Rect
    left_is_test: bool
    reference_height_mm: float
    test_height_mm: float
    bar_width_mm: float


def active_rect(calibration: DisplayCalibration) -> pygame.Rect:
    return pygame.Rect(
        calibration.active_left_px,
        calibration.active_top_px,
        calibration.active_width_px,
        calibration.active_height_px,
    )


def init_window(
    fullscreen: bool = USE_FULLSCREEN,
    size: tuple[int, int] | None = None,
) -> pygame.Surface:
    pygame.display.set_caption("Height JND 2AFC Experiment")
    if fullscreen:
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    return pygame.display.set_mode(size or (SCREEN_WIDTH, SCREEN_HEIGHT))


def make_trial_layout(
    screen: pygame.Surface,
    calibration: DisplayCalibration,
    bar_width_mm: float,
    reference_height_mm: float,
    test_height_mm: float,
    left_is_test: bool,
) -> TrialLayout:
    width_px = max(1, round(bar_width_mm * calibration.px_per_mm_x))
    reference_px = max(1, round(reference_height_mm * calibration.px_per_mm_y))
    test_px = max(1, round(test_height_mm * calibration.px_per_mm_y))
    haptic_area = active_rect(calibration)
    baseline_margin = max(8, round(0.08 * haptic_area.height))
    baseline_y = haptic_area.bottom - baseline_margin
    left_center_x = haptic_area.left + haptic_area.width // 4
    right_center_x = haptic_area.left + haptic_area.width * 3 // 4

    left_height_px = test_px if left_is_test else reference_px
    right_height_px = reference_px if left_is_test else test_px
    left_bar = pygame.Rect(0, 0, width_px, left_height_px)
    right_bar = pygame.Rect(0, 0, width_px, right_height_px)
    left_bar.midbottom = (left_center_x, baseline_y)
    right_bar.midbottom = (right_center_x, baseline_y)
    return TrialLayout(
        left_bar=left_bar,
        right_bar=right_bar,
        haptic_area=haptic_area,
        left_is_test=left_is_test,
        reference_height_mm=reference_height_mm,
        test_height_mm=test_height_mm,
        bar_width_mm=bar_width_mm,
    )


def draw_trial(
    screen: pygame.Surface,
    layout: TrialLayout,
    width_level_mm: float,
    height_level_mm: float,
    trial_number: int,
    reversals: int,
    total_reversals: int,
    active_side: str | None = None,
) -> None:
    screen.fill(BACKGROUND)
    width, height = screen.get_size()
    left_panel = pygame.Rect(0, 84, width // 2, height - 164)
    right_panel = pygame.Rect(width // 2, 84, width // 2, height - 164)
    pygame.draw.rect(screen, PANEL_ACTIVE if active_side == "left" else PANEL, left_panel)
    pygame.draw.rect(screen, PANEL_ACTIVE if active_side == "right" else PANEL, right_panel)
    pygame.draw.line(screen, DIVIDER, (width // 2, 72), (width // 2, height - 60), 2)

    title_font = pygame.font.SysFont("Arial", 30, bold=True)
    label_font = pygame.font.SysFont("Arial", 24, bold=True)
    body_font = pygame.font.SysFont("Arial", 20)

    title = title_font.render("Which bar is taller? Press left or right arrow", True, TEXT)
    screen.blit(title, title.get_rect(center=(width // 2, 34)))

    info = body_font.render(
        (
            f"Width {width_level_mm:g} mm    Height {height_level_mm:g} mm    "
            f"Trial {trial_number}    Reversals {reversals}/{total_reversals}"
        ),
        True,
        MUTED,
    )
    screen.blit(info, info.get_rect(center=(width // 2, 68)))

    pygame.draw.rect(screen, (70, 78, 90), layout.haptic_area, 1)

    pygame.draw.rect(screen, BAR_TEST if layout.left_is_test else BAR_REF, layout.left_bar)
    pygame.draw.rect(screen, BAR_TEST if not layout.left_is_test else BAR_REF, layout.right_bar)
    pygame.draw.rect(screen, BAR_OUTLINE, layout.left_bar, 2)
    pygame.draw.rect(screen, BAR_OUTLINE, layout.right_bar, 2)

    left_label = label_font.render("LEFT", True, TEXT)
    right_label = label_font.render("RIGHT", True, TEXT)
    screen.blit(left_label, left_label.get_rect(center=(width // 4, height - 105)))
    screen.blit(right_label, right_label.get_rect(center=(width * 3 // 4, height - 105)))

    hint = body_font.render("Explore both sides, then answer. ESC exits safely.", True, MUTED)
    screen.blit(hint, hint.get_rect(center=(width // 2, height - 34)))


def draw_break(screen: pygame.Surface, message: str) -> None:
    screen.fill(BACKGROUND)
    font = pygame.font.SysFont("Arial", 30, bold=True)
    subfont = pygame.font.SysFont("Arial", 22)
    text = font.render(message, True, TEXT)
    hint = subfont.render("Press SPACE to continue, or ESC to exit.", True, MUTED)
    screen.blit(text, text.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 24)))
    screen.blit(hint, hint.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 24)))
    pygame.display.flip()
