"""Method-of-constant-stimuli level generation and trial scheduling.

No pygame dependency: this module is pure data/logic so it can be unit
tested and reused by the analysis and dry-run tooling.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from .config import ExperimentConfig


@dataclass(frozen=True)
class TrialSpec:
    level_pct: float             # signed offset from base, e.g. -0.30 .. +0.30
    comparison_height_mm: float
    reference_height_mm: float
    reference_side: str          # "left" or "right"
    is_catch: bool = False
    is_practice: bool = False


def compute_levels(cfg: ExperimentConfig) -> list[float]:
    """Symmetric percentage offsets around the base height.

    ``levels = linspace(-delta_max_pct, +delta_max_pct, n_levels)``, with the
    0% level dropped unless ``include_zero_level`` is set. For an odd
    ``n_levels`` the midpoint of the linspace is exactly 0 and gets dropped
    (or kept) by that rule; for an even ``n_levels`` no point is ever exactly
    0, so nothing is dropped.
    """
    raw = np.linspace(-cfg.delta_max_pct, cfg.delta_max_pct, cfg.n_levels)
    levels = [float(x) for x in raw if cfg.include_zero_level or abs(x) > 1e-12]
    return levels


def comparison_height_mm(base_height_mm: float, level_pct: float) -> float:
    return base_height_mm * (1.0 + level_pct)


def _side_assignment(n: int, rng: random.Random) -> list[str]:
    """Half "left", half "right", counterbalanced within a level.

    For odd n, the leftover trial's side is picked at random (still
    deterministic given the seeded rng).
    """
    half = n // 2
    sides = ["left"] * half + ["right"] * half
    if n % 2:
        sides.append(rng.choice(["left", "right"]))
    rng.shuffle(sides)
    return sides


def build_practice_sequence(cfg: ExperimentConfig, rng: random.Random) -> list[TrialSpec]:
    """Easy (±delta_max) practice trials, feedback is expected to be forced on by the caller."""
    trials: list[TrialSpec] = []
    levels = [-cfg.delta_max_pct, cfg.delta_max_pct]
    sides = _side_assignment(cfg.n_practice_trials, rng)
    for i in range(cfg.n_practice_trials):
        level = levels[i % len(levels)]
        trials.append(
            TrialSpec(
                level_pct=level,
                comparison_height_mm=comparison_height_mm(cfg.base_height_mm, level),
                reference_height_mm=cfg.base_height_mm,
                reference_side=sides[i],
                is_catch=False,
                is_practice=True,
            )
        )
    rng.shuffle(trials)
    return trials


def build_trial_sequence(cfg: ExperimentConfig, seed: int) -> list[TrialSpec]:
    """Build the full, shuffled main-block trial sequence for one configuration.

    Deterministic given ``seed``: same seed + config always produces the same
    order (used both for reproducibility and for testing).
    """
    rng = random.Random(seed)
    levels = compute_levels(cfg)
    trials: list[TrialSpec] = []

    for level in levels:
        sides = _side_assignment(cfg.trials_per_level, rng)
        for side in sides:
            trials.append(
                TrialSpec(
                    level_pct=level,
                    comparison_height_mm=comparison_height_mm(cfg.base_height_mm, level),
                    reference_height_mm=cfg.base_height_mm,
                    reference_side=side,
                    is_catch=False,
                )
            )

    n_main = len(trials)
    n_catch = round(cfg.catch_trial_pct * n_main)
    catch_levels = [-cfg.delta_max_pct, cfg.delta_max_pct]
    catch_sides = _side_assignment(n_catch, rng)
    for i in range(n_catch):
        level = catch_levels[i % len(catch_levels)]
        trials.append(
            TrialSpec(
                level_pct=level,
                comparison_height_mm=comparison_height_mm(cfg.base_height_mm, level),
                reference_height_mm=cfg.base_height_mm,
                reference_side=catch_sides[i],
                is_catch=True,
            )
        )

    rng.shuffle(trials)
    return trials


def resolve_seed(cfg: ExperimentConfig) -> int:
    """Return the rng seed to actually use, generating and logging one if unset."""
    if cfg.rng_seed is not None:
        return cfg.rng_seed
    return random.SystemRandom().randrange(0, 2**32 - 1)
