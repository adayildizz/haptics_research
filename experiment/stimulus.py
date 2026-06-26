"""
Renders two bars simultaneously — one in each screen half.
Haptic feedback is active when the finger is inside a bar region.
In normal mode bars are invisible; in admin mode they are visible.
The center dividing line is always drawn.
"""

import pygame
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import (
    WIDTH, HEIGHT, INVERT_X, INVERT_Y,
    CARRIER_FREQUENCY, VOLTAGE, WAVE_SQUARE, MIN_VOLTAGE,
)

# Pixels-per-mm — calibrate to the physical display (96 dpi default)
PX_PER_MM = 3.78

BG_COLOR       = (0, 0, 0)
BAR_COLOR      = (54, 162, 235)
BAR_COLOR_HOT  = (120, 200, 255)
DIVIDER_COLOR  = (180, 180, 180)
ADMIN_COLOR    = (255, 220, 80)
FONT_COLOR     = (200, 200, 200)


def mm_to_px(mm: float) -> int:
    return int(mm * PX_PER_MM)


def show_pair(
    screen: pygame.Surface,
    haptics,
    width_mm: float,
    left_height_mm: float,
    right_height_mm: float,
    admin: bool = False,
) -> int:
    """
    Show two bars side by side and wait for a ← / → response.

    Left half  → bar with left_height_mm
    Right half → bar with right_height_mm

    Returns 1 if user pressed ← (left), 2 if → (right).
    """
    clock = pygame.time.Clock()
    font_admin = pygame.font.SysFont("Arial", 20)

    half = WIDTH // 2

    def make_bar(height_mm: float, x_offset: int) -> pygame.Rect:
        bw = mm_to_px(width_mm)
        bh = mm_to_px(height_mm)
        bx = x_offset + (half - bw) // 2
        by = (HEIGHT - bh) // 2
        return pygame.Rect(bx, by, bw, bh)

    left_rect  = make_bar(left_height_mm,  0)
    right_rect = make_bar(right_height_mm, half)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                haptics.close()
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    haptics.update_signal(WAVE_SQUARE, CARRIER_FREQUENCY, MIN_VOLTAGE)
                    return 1
                if event.key == pygame.K_RIGHT:
                    haptics.update_signal(WAVE_SQUARE, CARRIER_FREQUENCY, MIN_VOLTAGE)
                    return 2

        # Finger position
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

        # Haptic
        in_left  = finger_pos is not None and left_rect.collidepoint(finger_pos)
        in_right = finger_pos is not None and right_rect.collidepoint(finger_pos)
        haptics.update_signal(
            WAVE_SQUARE,
            CARRIER_FREQUENCY,
            VOLTAGE if (in_left or in_right) else MIN_VOLTAGE,
        )

        # Draw
        screen.fill(BG_COLOR)

        # Dividing line — always visible
        pygame.draw.line(screen, DIVIDER_COLOR, (half, 0), (half, HEIGHT), 2)

        if admin:
            # Bars visible with outline
            left_color  = BAR_COLOR_HOT if in_left  else BAR_COLOR
            right_color = BAR_COLOR_HOT if in_right else BAR_COLOR
            pygame.draw.rect(screen, left_color,  left_rect)
            pygame.draw.rect(screen, right_color, right_rect)
            pygame.draw.rect(screen, ADMIN_COLOR, left_rect,  2)
            pygame.draw.rect(screen, ADMIN_COLOR, right_rect, 2)

            # Dimension labels
            def admin_label(rect: pygame.Rect, height_mm: float) -> None:
                lines = [
                    f"w: {width_mm} mm = {rect.width} px",
                    f"h: {height_mm} mm = {rect.height} px",
                    f"x: {rect.x}–{rect.x + rect.width}",
                    f"y: {rect.y}–{rect.y + rect.height}",
                ]
                for i, line in enumerate(lines):
                    surf = font_admin.render(line, True, ADMIN_COLOR)
                    screen.blit(surf, (rect.x, rect.y - 20 - (len(lines) - i) * 22))

            admin_label(left_rect,  left_height_mm)
            admin_label(right_rect, right_height_mm)

        if finger_pos:
            pygame.draw.circle(screen, (255, 255, 255), finger_pos, 14)

        pygame.display.flip()
        clock.tick(60)
