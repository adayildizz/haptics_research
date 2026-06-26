"""
Single 2-AFC trial — simultaneous presentation.

Both bars are shown at the same time (left / right halves).
User presses ← or → to indicate which side felt taller.
"""

import random
import pygame
from experiment.stimulus import show_pair


def run(
    screen: pygame.Surface,
    haptics,
    width_mm: float,
    ref_height_mm: float,
    delta_mm: float,
    admin: bool = False,
) -> bool:
    """
    Returns True if the participant correctly identified the taller bar.
    """
    comparison_height = ref_height_mm + delta_mm

    # Randomly assign which side is taller
    taller_side = random.choice([1, 2])   # 1 = left, 2 = right

    if taller_side == 1:
        left_h, right_h = comparison_height, ref_height_mm
    else:
        left_h, right_h = ref_height_mm, comparison_height

    response = show_pair(
        screen          = screen,
        haptics         = haptics,
        width_mm        = width_mm,
        left_height_mm  = left_h,
        right_height_mm = right_h,
        admin           = admin,
    )

    return response == taller_side
