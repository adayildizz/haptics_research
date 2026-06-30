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
    FPS,
    FRAME_ACTIVE_HEIGHT_MM,
    FRAME_ACTIVE_WIDTH_MM,
    HEIGHT_LEVELS,
    LOCK_WINDOW_TO_FRAME_SIZE,
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
    parser.add_argument("--windowed", action="store_true", help="Use the configured debug window size instead of the frame-sized experiment window.")
    parser.add_argument("--calibrate", action="store_true", help="Save a physical display calibration and exit.")
    parser.add_argument("--allow-fallback-calibration", action="store_true", help="Use the rough fallback px/mm value if no calibration exists.")
    parser.add_argument("--active-width-mm", type=float, help="Measured active tactile/display width in millimeters.")
    parser.add_argument("--active-height-mm", type=float, help="Measured active tactile/display height in millimeters.")
    parser.add_argument("--screen-diagonal-inch", type=float, help="Approximate calibration from screen diagonal and current fullscreen aspect ratio.")
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

    if args.calibrate:
        screen = display.init_window(fullscreen=not args.windowed)
        if args.screen_diagonal_inch is not None:
            current_calibration = calibration_module.make_diagonal_calibration(
                screen.get_size(),
                diagonal_inch=args.screen_diagonal_inch,
            )
        elif args.active_width_mm is not None and args.active_height_mm is not None:
            current_calibration = calibration_module.make_calibration(
                screen.get_size(),
                active_width_mm=args.active_width_mm,
                active_height_mm=args.active_height_mm,
            )
        else:
            print("--calibrate requires either --screen-diagonal-inch or both --active-width-mm and --active-height-mm")
            pygame.quit()
            return 2
        path = calibration_module.save_calibration(current_calibration)
        print(f"Saved calibration to {path}")
        print(
            "Calibration: "
            f"{current_calibration.active_width_mm:.2f} mm x "
            f"{current_calibration.active_height_mm:.2f} mm, "
            f"{current_calibration.px_per_mm_x:.4f} px/mm X, "
            f"{current_calibration.px_per_mm_y:.4f} px/mm Y"
        )
        display.draw_break(screen, "Calibration saved")
        pygame.time.wait(1200)
        pygame.quit()
        return 0

    desktop_info = pygame.display.Info()
    desktop_size = (desktop_info.current_w, desktop_info.current_h)
    try:
        display_calibration = calibration_module.load_calibration(
            desktop_size,
            allow_fallback=args.allow_fallback_calibration,
        )
    except FileNotFoundError as exc:
        print(exc)
        pygame.quit()
        return 2

    if LOCK_WINDOW_TO_FRAME_SIZE and not args.windowed:
        window_size = (
            max(1, round(FRAME_ACTIVE_WIDTH_MM * display_calibration.px_per_mm_x)),
            max(1, round(FRAME_ACTIVE_HEIGHT_MM * display_calibration.px_per_mm_y)),
        )
        screen = display.init_window(fullscreen=False, size=window_size)
        current_calibration = calibration_module.make_calibration(
            screen.get_size(),
            active_width_mm=FRAME_ACTIVE_WIDTH_MM,
            active_height_mm=FRAME_ACTIVE_HEIGHT_MM,
            source=f"frame_window_{display_calibration.source}",
        )
    else:
        screen = display.init_window(fullscreen=not args.windowed)
        current_calibration = calibration_module.load_calibration(
            screen.get_size(),
            allow_fallback=args.allow_fallback_calibration,
        )

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
