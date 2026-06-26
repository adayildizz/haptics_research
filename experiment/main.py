"""
Experiment entry point.

Runs the height JND staircase for all width × reference-height conditions.
Results are saved to experiment/data/<participant>_<session>.csv.

Usage (via root main.py):
    python main.py --experiment

Direct usage:
    python experiment/main.py --participant P01 --session 1
"""

import argparse
import csv
import os
import random
import sys

import pygame

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import (
    WIDTH, HEIGHT, X_COORDINATE, Y_COORDINATE,
    INITIAL_WIDTHS, INITIAL_HEIGHTS,
    DH_INITIAL, DH_MIN, DH_STEP,
    N_REVERSALS, N_REVERSALS_AVERAGED,
)
from core.haptics import HapticController
from experiment.staircase import StairCase
from experiment.trial import run as run_trial

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _parse_args():
    parser = argparse.ArgumentParser(description="JND Experiment")
    parser.add_argument("--participant", required=True, help="Participant ID (e.g. P01)")
    parser.add_argument("--session",     required=True, type=int, help="Session number")
    return parser.parse_args()


def _init_display():
    os.environ['SDL_VIDEO_WINDOW_POS'] = f"{X_COORDINATE},{Y_COORDINATE}"
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
    pygame.display.set_caption("Haptic Experiment")
    return screen


def _show_text(screen: pygame.Surface, lines: list[str]) -> None:
    screen.fill((0, 0, 0))
    font = pygame.font.SysFont("Arial", 32)
    for i, line in enumerate(lines):
        surf = font.render(line, True, (220, 220, 220))
        screen.blit(surf, surf.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 60 + i * 50)))
    pygame.display.flip()


def _wait_space(screen: pygame.Surface) -> None:
    _show_text(screen, ["Press SPACE to continue"])
    while True:
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                return
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit


def run_experiment():
    args  = _parse_args()
    screen  = _init_display()
    haptics = HapticController()

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"{args.participant}_{args.session}.csv")

    # Build condition list and shuffle
    conditions = [
        (width_mm, ref_mm)
        for width_mm in INITIAL_WIDTHS
        for ref_mm   in INITIAL_HEIGHTS
    ]
    random.shuffle(conditions)

    _show_text(screen, [
        f"Participant: {args.participant}  |  Session: {args.session}",
        f"{len(conditions)} conditions",
        "",
        "Press SPACE to begin",
    ])
    _wait_space(screen)

    results = []

    for cond_idx, (width_mm, ref_mm) in enumerate(conditions):
        staircase = StairCase(
            start      = DH_INITIAL,
            step       = DH_STEP,
            min_val    = DH_MIN,
            n_reversals= N_REVERSALS,
            n_averaged = N_REVERSALS_AVERAGED,
        )

        _show_text(screen, [
            f"Condition {cond_idx + 1} / {len(conditions)}",
            f"Width: {width_mm} mm   Reference height: {ref_mm} mm",
            "",
            "Press SPACE to start",
        ])
        _wait_space(screen)

        n_trials = 0
        while not staircase.is_done():
            correct = run_trial(
                screen      = screen,
                haptics     = haptics,
                width_mm    = width_mm,
                ref_height_mm = ref_mm,
                delta_mm    = staircase.current,
            )
            staircase.update(correct)
            n_trials += 1

        threshold = staircase.threshold()
        reversal_str = ",".join(f"{r:.2f}" for r in staircase.reversals)

        results.append({
            "participant"  : args.participant,
            "session"      : args.session,
            "bar_width_mm" : width_mm,
            "ref_height_mm": ref_mm,
            "threshold_mm" : round(threshold, 3),
            "n_trials"     : n_trials,
            "reversals"    : reversal_str,
        })

        print(f"  [{cond_idx+1}/{len(conditions)}] w={width_mm}mm h={ref_mm}mm  → JND={threshold:.2f}mm")

    # Write CSV
    fieldnames = ["participant","session","bar_width_mm","ref_height_mm","threshold_mm","n_trials","reversals"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to {out_path}")

    _show_text(screen, ["Experiment complete!", f"Data saved to {os.path.basename(out_path)}", "", "Press SPACE to exit"])
    _wait_space(screen)

    haptics.close()
    pygame.quit()


if __name__ == "__main__":
    run_experiment()
