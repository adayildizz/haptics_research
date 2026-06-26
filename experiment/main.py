"""Entry point for the tactile bar-height JND experiment."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import pygame

from . import data_logger, display, stimulus, trial
from .config import (
    DH_MIN,
    DH_START,
    DH_STEP,
    FPS,
    N_REVERSALS,
    N_REVERSALS_AVERAGED,
    WIDTH_LEVELS,
)
from .staircase import StairCase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the tactile bar-height JND experiment.")
    parser.add_argument("--mode", choices=["demo", "experiment"], default="experiment")
    parser.add_argument("--participant", default=time.strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def wait_for_space_or_escape(screen: pygame.Surface, message: str) -> bool:
    display.draw_break(screen, message)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_SPACE:
                    return True


def run() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    pygame.init()
    screen = display.init_window()
    clock = pygame.time.Clock()
    data_dir = data_logger.ensure_data_dir()
    trial_path = data_dir / f"{args.participant}_trials.csv"
    summary_path = data_dir / f"{args.participant}_thresholds.csv"

    instrument = None if args.mode == "demo" else stimulus.connect_hardware()
    width_order = WIDTH_LEVELS[:]
    random.shuffle(width_order)

    try:
        if not wait_for_space_or_escape(screen, "Ready to begin the height-JND experiment"):
            return 0

        for width_level in width_order:
            staircase = StairCase(
                start=DH_START * width_level,
                step=DH_STEP * width_level,
                min_val=DH_MIN * width_level,
                n_reversals=N_REVERSALS,
                n_averaged=N_REVERSALS_AVERAGED,
            )
            trial_number = 1
            if not wait_for_space_or_escape(screen, f"Width level {width_level:g} mm"):
                return 0

            while not staircase.is_done():
                result = trial.run_trial(
                    screen=screen,
                    clock=clock,
                    instrument=instrument,
                    width_level_mm=width_level,
                    dH_mm=staircase.current,
                    trial_number=trial_number,
                    reversals=len(staircase.reversals),
                )
                if result is None:
                    return 0

                data_logger.append_trial(
                    {
                        "width_level": result.width_level,
                        "trial_number": result.trial_number,
                        "dH": f"{result.dH:.4f}",
                        "response": result.response,
                        "correct": int(result.correct),
                        "finger_speed": f"{result.finger_speed:.4f}",
                        "timestamp": result.timestamp,
                    },
                    trial_path,
                )
                staircase.update(result.correct)
                trial_number += 1

            threshold = staircase.threshold()
            data_logger.append_summary(
                {
                    "width_level": width_level,
                    "threshold": f"{threshold:.4f}",
                    "n_trials": trial_number - 1,
                    "n_reversals": len(staircase.reversals),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                summary_path,
            )

        display.draw_break(screen, f"Experiment complete. Data saved in {Path(data_dir).name}/")
        pygame.time.wait(1500)
        return 0
    finally:
        stimulus.close_hardware(instrument)
        pygame.quit()


if __name__ == "__main__":
    sys.exit(run())
