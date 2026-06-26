"""
Renders a single tactile bar and delivers haptic feedback during touch.

Call `show(screen, haptics, width_mm, height_mm)` to present one stimulus.
Returns when the participant lifts their finger or a timeout is reached.
"""

import pygame
import sys
sys.path.insert(0, "..")
from config import (
    WIDTH, HEIGHT, INVERT_X, INVERT_Y,
    CARRIER_FREQUENCY, VOLTAGE, WAVE_SQUARE, MIN_VOLTAGE,
)

# Pixels-per-mm — calibrate to the physical display (96 dpi default)
PX_PER_MM = 3.78

BAR_COLOR        = (54, 162, 235)
BAR_COLOR_ACTIVE = (120, 200, 255)
BG_COLOR         = (0, 0, 0)
FONT_COLOR       = (200, 200, 200)

LIFTOFF_GRACE_MS = 300  # ms to wait after finger lift before returning


def mm_to_px(mm: float) -> int:
    return int(mm * PX_PER_MM)


def show(
    screen: pygame.Surface,
    haptics,
    width_mm: float,
    height_mm: float,
    label: str = "",
    timeout_ms: int = 10_000,
    admin: bool = False,
) -> None:
    """Display one bar; deliver haptic feedback while finger is inside. Blocking."""
    clock = pygame.time.Clock()

    bar_w = mm_to_px(width_mm)
    bar_h = mm_to_px(height_mm)
    bar_x = (WIDTH  - bar_w) // 2
    bar_y = (HEIGHT - bar_h) // 2
    bar_rect = pygame.Rect(bar_x, bar_y, bar_w, bar_h)

    if admin:
        font_admin = pygame.font.SysFont("Arial", 20)
        admin_lines = [
            f"width:  {width_mm} mm  →  {bar_w} px",
            f"height: {height_mm} mm  →  {bar_h} px",
            f"x: {bar_x}–{bar_x + bar_w}   y: {bar_y}–{bar_y + bar_h}",
        ]

    font = pygame.font.SysFont("Arial", 28)
    hint = font.render(label, True, FONT_COLOR)

    start_ms   = pygame.time.get_ticks()
    liftoff_ms = None

    while True:
        now = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                haptics.close()
                pygame.quit()
                raise SystemExit

        if now - start_ms > timeout_ms:
            haptics.update_signal(WAVE_SQUARE, CARRIER_FREQUENCY, MIN_VOLTAGE)
            return

        finger_pos = None
        mx, my = pygame.mouse.get_pos()
        if pygame.mouse.get_pressed()[0]:
            raw_x = mx / WIDTH
            raw_y = my / HEIGHT
            if INVERT_X:
                raw_x = 1.0 - raw_x
            if INVERT_Y:
                raw_y = 1.0 - raw_y
            finger_pos = (int(raw_x * WIDTH), int(raw_y * HEIGHT))

        inside = finger_pos is not None and bar_rect.collidepoint(finger_pos)
        haptics.update_signal(
            WAVE_SQUARE,
            CARRIER_FREQUENCY,
            VOLTAGE if inside else MIN_VOLTAGE,
        )

        if finger_pos is None and liftoff_ms is None:
            liftoff_ms = now
        elif finger_pos is not None:
            liftoff_ms = None

        if liftoff_ms is not None and (now - liftoff_ms) > LIFTOFF_GRACE_MS:
            return

        screen.fill(BG_COLOR)
        pygame.draw.rect(screen, BAR_COLOR_ACTIVE if inside else BAR_COLOR, bar_rect)
        screen.blit(hint, hint.get_rect(center=(WIDTH // 2, bar_y - 40)))
        if finger_pos:
            pygame.draw.circle(screen, (255, 255, 255), finger_pos, 14)

        if admin:
            for i, line in enumerate(admin_lines):
                surf = font_admin.render(line, True, (255, 220, 80))
                screen.blit(surf, (12, 12 + i * 24))
            # bar boundary lines
            pygame.draw.rect(screen, (255, 220, 80), bar_rect, 2)

        pygame.display.flip()
        clock.tick(60)
