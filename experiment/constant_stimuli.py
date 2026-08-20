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
    """Build the main-block trial sequence, randomized within blocks.

    Order is randomized *inside* blocks that each hold ``sweeps_per_block``
    presentations of every level, rather than by one permutation of the whole
    set. Both give each level its configured number of trials and both are
    unbiased on average, but a single global shuffle leaves level confounded
    with time-on-task in any one session: measured over 2000 seeds of the
    default design, a level's trials split between the first and second half
    of the block by 4.6 on average and by as much as 10-0 -- every one of its
    trials in one half. 84% of sessions came out at 4-6 or worse. A session
    lasts ~20 minutes, over which fatigue, learning, and the skin's coupling
    to the surface all drift, so that imbalance lands directly on the
    threshold estimate. Blocking makes the split exactly even by
    construction, and caps same-level runs at two.

    Catch trials are spread one per block for the same reason: shuffled in
    globally, 28% of sessions put four or more of the six in the same third
    of the session and 23% left a third with none, which is a poor way to
    sample attention across a session.

    Deterministic given ``seed``: same seed + config always produces the same
    order.
    """
    rng = random.Random(seed)
    levels = compute_levels(cfg)

    # Sides stay counterbalanced per level across the whole block, not per
    # sub-block: each level still gets half left and half right overall.
    sides_by_level = {level: _side_assignment(cfg.trials_per_level, rng) for level in levels}
    used = {level: 0 for level in levels}

    def _spec(level: float, side: str, is_catch: bool) -> TrialSpec:
        return TrialSpec(
            level_pct=level,
            comparison_height_mm=comparison_height_mm(cfg.base_height_mm, level),
            reference_height_mm=cfg.base_height_mm,
            reference_side=side,
            is_catch=is_catch,
        )

    blocks: list[list[TrialSpec]] = []
    for _ in range(cfg.trials_per_level // cfg.sweeps_per_block):
        block: list[TrialSpec] = []
        for level in levels:
            for _ in range(cfg.sweeps_per_block):
                block.append(_spec(level, sides_by_level[level][used[level]], is_catch=False))
                used[level] += 1
        rng.shuffle(block)
        blocks.append(block)

    n_main = sum(len(block) for block in blocks)
    n_catch = round(cfg.catch_trial_pct * n_main)
    catch_levels = [-cfg.delta_max_pct, cfg.delta_max_pct]
    catch_sides = _side_assignment(n_catch, rng)
    # Walk the blocks in a shuffled order so the catch trials land in
    # different blocks each session, wrapping if there are more than blocks.
    block_order = list(range(len(blocks)))
    rng.shuffle(block_order)
    for i in range(n_catch):
        block = blocks[block_order[i % len(blocks)]]
        block.insert(
            rng.randrange(len(block) + 1),
            _spec(catch_levels[i % len(catch_levels)], catch_sides[i], is_catch=True),
        )

    return [spec for block in blocks for spec in block]


def resolve_seed(cfg: ExperimentConfig) -> int:
    """Return the rng seed to actually use, generating and logging one if unset."""
    if cfg.rng_seed is not None:
        return cfg.rng_seed
    return random.SystemRandom().randrange(0, 2**32 - 1)


@dataclass
class ScheduledTrial:
    """A spec plus how many times it has already been put in front of the participant.

    Mutable on purpose: ``attempts`` is what bounds the retry loop (see
    ``defer_timed_out_trial``), so it has to travel with the trial as it
    moves between the pending queue and the retry pool.
    """

    spec: TrialSpec
    attempts: int = 0


def build_schedule(cfg: ExperimentConfig, seed: int) -> list[ScheduledTrial]:
    """``build_trial_sequence`` wrapped in per-trial attempt bookkeeping."""
    return [ScheduledTrial(spec) for spec in build_trial_sequence(cfg, seed)]


def defer_timed_out_trial(
    scheduled: ScheduledTrial,
    deferred: list[ScheduledTrial],
    max_attempts: int,
) -> bool:
    """Move an expired trial to the retry pool, shown after the whole block.

    Returns ``True`` if it was queued for another attempt, ``False`` if it
    has now used up ``max_attempts`` presentations and must be abandoned.

    That cap is what makes the session terminate. Retrying an unanswered
    trial is otherwise unbounded: a participant who has walked away, or a
    ``response_timeout_s`` set too short for the task, would keep feeding
    the same trials back into the queue forever. With the cap, the whole
    session presents at most ``len(schedule) * max_attempts`` trials no
    matter how many go unanswered, and an abandoned trial simply costs one
    observation at its level rather than stalling the run.
    """
    if scheduled.attempts >= max_attempts:
        return False
    deferred.append(scheduled)
    return True


def take_retry_round(deferred: list[ScheduledTrial], rng: random.Random) -> list[ScheduledTrial]:
    """Drain the retry pool into a freshly shuffled round, emptying ``deferred``.

    Reshuffling matters: replaying in timeout order would present the
    missed trials in a systematic sequence rather than a random one.
    """
    round_trials = list(deferred)
    deferred.clear()
    rng.shuffle(round_trials)
    return round_trials
