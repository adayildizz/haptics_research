"""Entry point for the tactile bar-height JND experiment."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import pygame

from . import calibration as calibration_module
from . import data_logger, display, stimulus, trial
from .config import (
    DH_MIN,
    DH_START,
    DH_STEP,
    HEIGHT_LEVELS,
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
    parser.add_argument("--windowed", action="store_true", help="Use the configured debug window size instead of fullscreen.")
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
    clock = pygame.time.Clock()
    data_dir = data_logger.ensure_data_dir()
    trial_path = data_dir / f"{args.participant}_trials.csv"
    summary_path = data_dir / f"{args.participant}_thresholds.csv"

    screen = display.init_window(fullscreen=not args.windowed)

    current_calibration = calibration_module.make_configured_ir_frame_calibration(screen.get_size())

    print(
        "Using display calibration "
        f"({current_calibration.source}): "
        f"{current_calibration.active_width_mm:.2f} mm x "
        f"{current_calibration.active_height_mm:.2f} mm, "
        f"{current_calibration.px_per_mm_x:.4f} px/mm X, "
        f"{current_calibration.px_per_mm_y:.4f} px/mm Y"
    )

    instrument = None if args.mode == "demo" else stimulus.connect_hardware()
    configurations = [(width, height) for width in WIDTH_LEVELS for height in HEIGHT_LEVELS]
    random.shuffle(configurations)

    try:
        if not wait_for_space_or_escape(
            screen,
            (
                "Ready to begin. "
                f"Calibration: {current_calibration.px_per_mm_x:.2f} px/mm X, "
                f"{current_calibration.px_per_mm_y:.2f} px/mm Y"
            ),
        ):
            return 0

        for width_level, height_level in configurations:
            staircase = StairCase(
                start=DH_START * height_level,
                step=DH_STEP * height_level,
                min_val=DH_MIN * height_level,
                n_reversals=N_REVERSALS,
                n_averaged=N_REVERSALS_AVERAGED,
            )
            trial_number = 1
            if not wait_for_space_or_escape(
                screen,
                f"Width {width_level:g} mm, reference height {height_level:g} mm",
            ):
                return 0

            while not staircase.is_done():
                result = trial.run_trial(
                    screen=screen,
                    clock=clock,
                    calibration=current_calibration,
                    instrument=instrument,
                    width_level_mm=width_level,
                    height_level_mm=height_level,
                    dH_mm=staircase.current,
                    trial_number=trial_number,
                    reversals=len(staircase.reversals),
                )
                if result is None:
                    return 0

                data_logger.append_trial(
                    {
                        "width_level": result.width_level,
                        "height_level": result.height_level,
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
                    "height_level": height_level,
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
