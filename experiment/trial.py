"""
Single 2-AFC trial.

Presents two bars sequentially and waits for a left/right keypress indicating
which bar felt taller. Returns True if the participant chose the taller bar.
"""

import pygame
import random
from experiment.stimulus import show

ISI_MS = 800  # inter-stimulus interval (blank screen)


def _blank(screen: pygame.Surface, duration_ms: int) -> None:
    screen.fill((0, 0, 0))
    pygame.display.flip()
    pygame.time.wait(duration_ms)


def _wait_response() -> int:
    """Block until ← (1) or → (2). Returns 1 or 2."""
    while True:
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    return 1
                if event.key == pygame.K_RIGHT:
                    return 2
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit


def run(
    screen: pygame.Surface,
    haptics,
    width_mm: float,
    ref_height_mm: float,
    delta_mm: float,
) -> bool:
    """
    Present reference and comparison bars in random order.

    Returns True if the participant correctly identified the taller bar.
    """
    comparison_height = ref_height_mm + delta_mm

    # Randomly assign which interval contains the taller bar
    taller_interval = random.choice([1, 2])

    if taller_interval == 1:
        heights = [comparison_height, ref_height_mm]
    else:
        heights = [ref_height_mm, comparison_height]

    show(screen, haptics, width_mm, heights[0], label="1", timeout_ms=10_000)
    _blank(screen, ISI_MS)
    show(screen, haptics, width_mm, heights[1], label="2", timeout_ms=10_000)

    _blank(screen, 200)

    # Prompt
    font = pygame.font.SysFont("Arial", 32)
    screen.fill((0, 0, 0))
    prompt = font.render("Which was taller?   ←  First     Second  →", True, (200, 200, 200))
    screen.blit(prompt, prompt.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2)))
    pygame.display.flip()

    response = _wait_response()
    return response == taller_interval
