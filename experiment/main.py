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
    HAPTIC_SURFACE_HEIGHT_MM,
    HAPTIC_SURFACE_WIDTH_MM,
    HEIGHT_LEVELS,
    MONITOR_DIAGONAL_INCH,
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
    parser.add_argument("--diagonal-calibration", action="store_true", help="Use a rough screen-diagonal px/mm estimate instead of the saved haptic surface calibration.")
    parser.add_argument("--calibrate-haptic-surface", action="store_true", help="Touch-calibrate the haptic surface area inside the experiment window.")
    parser.add_argument("--haptic-width-mm", type=float, default=HAPTIC_SURFACE_WIDTH_MM, help="Measured haptic surface width in millimeters.")
    parser.add_argument("--haptic-height-mm", type=float, default=HAPTIC_SURFACE_HEIGHT_MM, help="Measured haptic surface height in millimeters.")
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


def wait_for_mouse_point(screen: pygame.Surface, message: str) -> tuple[int, int] | None:
    font = pygame.font.SysFont("Arial", 26, bold=True)
    subfont = pygame.font.SysFont("Arial", 20)
    clock = pygame.time.Clock()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_SPACE:
                    return pygame.mouse.get_pos()

        screen.fill(display.BACKGROUND)
        pos = pygame.mouse.get_pos()
        text = font.render(message, True, display.TEXT)
        hint = subfont.render("Touch/hold the corner, then press SPACE. ESC exits.", True, display.MUTED)
        coords = subfont.render(f"Current mouse/IR position: {pos[0]}, {pos[1]}", True, display.MUTED)
        screen.blit(text, text.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 52)))
        screen.blit(hint, hint.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2)))
        screen.blit(coords, coords.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 36)))
        pygame.draw.circle(screen, display.TEXT, pos, 8, 2)
        pygame.display.flip()
        clock.tick(FPS)


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

    if args.calibrate_haptic_surface:
        top_left = wait_for_mouse_point(screen, "Touch the TOP-LEFT corner of the haptic surface")
        if top_left is None:
            pygame.quit()
            return 0
        bottom_right = wait_for_mouse_point(screen, "Touch the BOTTOM-RIGHT corner of the haptic surface")
        if bottom_right is None:
            pygame.quit()
            return 0
        haptic_calibration = calibration_module.make_haptic_surface_calibration(
            screen.get_size(),
            top_left=top_left,
            bottom_right=bottom_right,
            active_width_mm=args.haptic_width_mm,
            active_height_mm=args.haptic_height_mm,
        )
        path = calibration_module.save_haptic_surface_calibration(haptic_calibration)
        print(f"Saved haptic surface calibration to {path}")
        print(
            "Haptic surface: "
            f"{haptic_calibration.active_width_px} x {haptic_calibration.active_height_px} px, "
            f"{haptic_calibration.active_width_mm:.2f} x {haptic_calibration.active_height_mm:.2f} mm, "
            f"{haptic_calibration.px_per_mm_x:.4f} px/mm X, "
            f"{haptic_calibration.px_per_mm_y:.4f} px/mm Y"
        )
        display.draw_break(screen, "Haptic surface calibration saved")
        pygame.time.wait(1200)
        pygame.quit()
        return 0

    if args.diagonal_calibration:
        current_calibration = calibration_module.make_diagonal_centered_calibration(
            screen.get_size(),
            diagonal_inch=MONITOR_DIAGONAL_INCH,
            active_width_mm=HAPTIC_SURFACE_WIDTH_MM,
            active_height_mm=HAPTIC_SURFACE_HEIGHT_MM,
        )
    else:
        current_calibration = calibration_module.load_haptic_surface_calibration(screen.get_size())
        if current_calibration is None:
            current_calibration = calibration_module.make_diagonal_centered_calibration(
                screen.get_size(),
                diagonal_inch=MONITOR_DIAGONAL_INCH,
                active_width_mm=HAPTIC_SURFACE_WIDTH_MM,
                active_height_mm=HAPTIC_SURFACE_HEIGHT_MM,
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
