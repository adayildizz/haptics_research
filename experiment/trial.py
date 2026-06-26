"""Single-trial orchestration for the tactile bar-height 2AFC task."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import pygame

from . import display, stimulus
from .config import FPS, MM_TO_PX, N_REVERSALS


@dataclass(frozen=True)
class TrialResult:
    width_level: float
    trial_number: int
    dH: float
    response: str
    correct: bool
    finger_speed: float
    timestamp: str
    left_is_test: bool


def _side_for_pos(pos: tuple[int, int], layout: display.TrialLayout) -> str | None:
    if layout.left_bar.collidepoint(pos):
        return "left"
    if layout.right_bar.collidepoint(pos):
        return "right"
    return None


def run_trial(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    instrument: Any | None,
    width_level_mm: float,
    dH_mm: float,
    trial_number: int,
    reversals: int,
) -> TrialResult | None:
    """Run one 2AFC trial and return the participant response."""
    reference_height_mm = width_level_mm
    test_height_mm = reference_height_mm + dH_mm
    left_is_test = random.choice([True, False])
    layout = display.make_trial_layout(
        screen,
        bar_width_mm=width_level_mm,
        reference_height_mm=reference_height_mm,
        test_height_mm=test_height_mm,
        left_is_test=left_is_test,
    )

    last_pos = pygame.mouse.get_pos()
    last_time = time.perf_counter()
    speed_samples: list[float] = []
    active_side: str | None = None
    previous_side: str | None = None
    signal_start_s = 0.0
    signal_duration_s = 0.0

    while True:
        now = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                stimulus.signal_off(instrument)
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    stimulus.signal_off(instrument)
                    return None
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    response = "left" if event.key == pygame.K_LEFT else "right"
                    correct_response = "left" if left_is_test else "right"
                    stimulus.signal_off(instrument)
                    average_speed = sum(speed_samples) / len(speed_samples) if speed_samples else 0.0
                    return TrialResult(
                        width_level=width_level_mm,
                        trial_number=trial_number,
                        dH=dH_mm,
                        response=response,
                        correct=response == correct_response,
                        finger_speed=average_speed,
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        left_is_test=left_is_test,
                    )

        pos = pygame.mouse.get_pos()
        elapsed = max(now - last_time, 1e-6)
        dx = (pos[0] - last_pos[0]) / MM_TO_PX
        dy = (pos[1] - last_pos[1]) / MM_TO_PX
        speed_mm_s = ((dx * dx + dy * dy) ** 0.5) / elapsed
        if speed_mm_s > 0:
            speed_samples.append(speed_mm_s)

        active_side = _side_for_pos(pos, layout)
        if active_side is not None and active_side != previous_side:
            signal_start_s = now
            signal_duration_s = stimulus.stimulus_duration(width_level_mm, speed_mm_s)

        if active_side is not None:
            stimulus.deliver_timed_signal(instrument, signal_start_s, signal_duration_s, now)
        else:
            stimulus.signal_off(instrument)

        display.draw_trial(
            screen,
            layout,
            width_level_mm=width_level_mm,
            trial_number=trial_number,
            reversals=reversals,
            total_reversals=N_REVERSALS,
            active_side=active_side,
        )
        pygame.display.flip()
        previous_side = active_side
        last_pos = pos
        last_time = now
        clock.tick(FPS)
