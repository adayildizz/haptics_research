"""Entry point for the tactile bar-height JND experiment.

Two run modes, selected by ``ExperimentConfig.mode`` in the YAML config:

- ``staircase_pilot``: a quick adaptive staircase at one base height, used to
  locate the approximate JND before committing to a constant-stimuli range.
- ``constant_stimuli``: the main method-of-constant-stimuli block.

``--dry-run`` simulates an ideal observer end-to-end (no pygame, no
hardware) to sanity-check that a config produces a reasonable psychometric
curve before running a live participant.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import calibration as calibration_module
from . import constant_stimuli, data_logger
from .config import ExperimentConfig, load_experiment_config, write_config_snapshot
from .constant_stimuli import TrialSpec, resolve_seed
from .staircase import StairCase, pilot_range_check


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the tactile bar-height JND experiment.")
    parser.add_argument("--config", type=Path, required=True, help="Path to a YAML/TOML ExperimentConfig file.")
    parser.add_argument("--participant", default=None)
    parser.add_argument("--windowed", action="store_true", help="Use a debug window instead of fullscreen.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate an ideal observer; no pygame/hardware.")
    return parser.parse_args()


def _session_paths(cfg: ExperimentConfig, participant: str) -> tuple[str, Path, Path, Path]:
    data_dir = data_logger.ensure_data_dir()
    session_id = f"{participant}_{time.strftime('%Y%m%d_%H%M%S')}"
    trial_path = data_dir / f"{session_id}_trials.csv"
    summary_path = data_dir / f"{session_id}_thresholds.csv"
    config_snapshot_path = data_dir / f"{session_id}_config.json"
    return session_id, trial_path, summary_path, config_snapshot_path


def run_dry_run(cfg: ExperimentConfig) -> int:
    """Simulate an ideal observer through the configured design; no pygame."""
    from analysis.fit_psychometric import fit_psychometric, plot_psychometric, simulate_ideal_observer

    seed = resolve_seed(cfg)
    levels = constant_stimuli.compute_levels(cfg)
    print(f"dry-run: mode={cfg.mode} seed={seed} levels={[f'{l:+.1%}' for l in levels]}")

    true_sigma = cfg.delta_max_pct / 3.0
    levels_out, n_trials, n_taller = simulate_ideal_observer(
        levels,
        trials_per_level=cfg.trials_per_level,
        true_pse=0.0,
        true_sigma=true_sigma,
        true_lapse=0.02,
        seed=seed,
    )
    fit = fit_psychometric(levels_out, n_trials, n_taller)
    data_dir = data_logger.ensure_data_dir()
    out_path = data_dir / f"dry_run_{time.strftime('%Y%m%d_%H%M%S')}.png"
    plot_psychometric(fit, out_path)
    print(
        f"dry-run fit ({fit.backend}): pse={fit.pse:+.4f} slope_sigma={fit.slope_sigma:.4f} "
        f"lapse={fit.lapse_rate:.4f} jnd={fit.jnd:.4f} (true_sigma={true_sigma:.4f})"
    )
    print(f"saved {out_path} and {out_path.with_suffix('.json')}")
    return 0


def wait_for_space_or_escape(screen, message: str) -> bool:
    import pygame

    from . import display

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


def run_staircase_pilot(
    screen, clock, calibration, instrument, cfg: ExperimentConfig, summary_path: Path, seed: int
) -> None:
    from . import trial as trial_module

    staircase = StairCase(
        start=cfg.staircase_dh_start_pct * cfg.base_height_mm,
        step=cfg.staircase_dh_step_pct * cfg.base_height_mm,
        min_val=cfg.staircase_dh_min_pct * cfg.base_height_mm,
        n_reversals=cfg.staircase_n_reversals,
        n_averaged=cfg.staircase_n_reversals_averaged,
    )
    trial_index = 1
    import random

    rng = random.Random(seed)

    while not staircase.is_done():
        spec = TrialSpec(
            level_pct=staircase.current / cfg.base_height_mm,
            comparison_height_mm=cfg.base_height_mm + staircase.current,
            reference_height_mm=cfg.base_height_mm,
            reference_side=rng.choice(["left", "right"]),
            is_catch=False,
            is_practice=False,
        )
        result = trial_module.run_trial(screen, clock, calibration, instrument, cfg, spec, trial_index, fps=60)
        if result is None:
            return
        if isinstance(result, trial_module.TrialTimeout):
            continue
        staircase.update(result.correct)
        trial_index += 1

    threshold_mm = staircase.threshold()
    threshold_pct = threshold_mm / cfg.base_height_mm
    data_logger.append_summary(
        {
            "base_height_mm": cfg.base_height_mm,
            "bar_width_mm": cfg.bar_width_mm,
            "threshold_pct": f"{threshold_pct:.4f}",
            "n_trials": trial_index - 1,
            "n_reversals": len(staircase.reversals),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        summary_path,
    )
    print(f"Pilot JND: {threshold_pct:.1%} of base height ({threshold_mm:.3f} mm)")
    warning = pilot_range_check(threshold_pct, cfg.delta_max_pct)
    if warning:
        print(f"WARNING: {warning}")


def run_constant_stimuli(
    screen,
    clock,
    calibration,
    instrument,
    cfg: ExperimentConfig,
    session_id: str,
    trial_path: Path,
    seed: int,
) -> None:
    from . import trial as trial_module

    print(f"constant_stimuli rng_seed={seed}")

    import random

    rng = random.Random(seed)

    if cfg.n_practice_trials > 0:
        from .speed_coach import PRACTICE_INSTRUCTION, PracticeSpeedCoach, SystemVoice

        voice = SystemVoice() if cfg.practice_voice_feedback else None
        speed_coach = (
            PracticeSpeedCoach(
                cfg.ideal_finger_speed_mm_s,
                cfg.ideal_speed_tolerance_pct,
                voice.speak,
            )
            if voice is not None and voice.available
            else None
        )
        try:
            if not wait_for_space_or_escape(screen, "Practice trials (feedback on)."):
                return
            if voice is not None and voice.available:
                voice.speak(PRACTICE_INSTRUCTION, wait=True)
            for i, spec in enumerate(constant_stimuli.build_practice_sequence(cfg, rng), start=1):
                result = trial_module.run_trial(
                    screen,
                    clock,
                    calibration,
                    instrument,
                    cfg,
                    spec,
                    i,
                    fps=60,
                    speed_coach=speed_coach,
                )
                if result is None:
                    return
        finally:
            if voice is not None:
                voice.close()

    if not wait_for_space_or_escape(screen, "Main block. No feedback unless configured."):
        return

    pending_trials = constant_stimuli.build_trial_sequence(cfg, seed)
    total_trials = len(pending_trials)
    completed_trials = 0
    while pending_trials:
        spec = pending_trials.pop(0)
        trial_index = completed_trials + 1
        result = trial_module.run_trial(
            screen, clock, calibration, instrument, cfg, spec, trial_index, fps=60
        )
        if result is None:
            return
        if isinstance(result, trial_module.TrialTimeout):
            constant_stimuli.requeue_timed_out_trial(pending_trials, spec, cfg, rng)
            continue

        data_logger.append_trial(
            {
                "session_id": session_id,
                "participant_id": cfg.participant_id,
                "timestamp": result.timestamp,
                "trial_index": result.trial_index,
                "mode": cfg.mode,
                "level_pct": f"{result.level_pct:.6f}",
                "comparison_height_mm": f"{result.comparison_height_mm:.4f}",
                "reference_height_mm": f"{result.reference_height_mm:.4f}",
                "bar_width_mm": f"{result.bar_width_mm:.4f}",
                "reference_side": result.reference_side,
                "response": result.response,
                "correct": int(result.correct),
                "is_catch": int(result.is_catch),
                "is_practice": int(result.is_practice),
                "response_time_s": f"{result.response_time_s:.4f}",
                "passes": result.passes,
            },
            trial_path,
        )
        completed_trials += 1

        if (
            cfg.break_every_n_trials
            and completed_trials % cfg.break_every_n_trials == 0
            and completed_trials < total_trials
        ):
            if not wait_for_space_or_escape(
                screen,
                f"Break. {completed_trials}/{total_trials} trials done.",
            ):
                return


def run() -> int:
    args = parse_args()
    cfg = load_experiment_config(args.config)
    participant = args.participant or cfg.participant_id or time.strftime("%Y%m%d_%H%M%S")

    if args.dry_run:
        return run_dry_run(cfg)

    import pygame

    from . import display, stimulus

    pygame.init()
    clock = pygame.time.Clock()
    session_id, trial_path, summary_path, config_snapshot_path = _session_paths(cfg, participant)

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

    resolved_seed = resolve_seed(cfg)
    write_config_snapshot(cfg, config_snapshot_path, extra={"session_id": session_id, "resolved_rng_seed": resolved_seed})

    instrument = stimulus.connect_hardware(cfg)

    try:
        if not wait_for_space_or_escape(
            screen,
            f"Ready to begin ({cfg.mode}). Base height {cfg.base_height_mm:g} mm, width {cfg.bar_width_mm:g} mm.",
        ):
            return 0

        if cfg.mode == "staircase_pilot":
            run_staircase_pilot(screen, clock, current_calibration, instrument, cfg, summary_path, resolved_seed)
        else:
            run_constant_stimuli(
                screen, clock, current_calibration, instrument, cfg, session_id, trial_path, resolved_seed
            )

        display.draw_break(screen, f"Session complete. Data saved in {trial_path.parent.name}/")
        pygame.display.flip()
        pygame.time.wait(1500)
        return 0
    finally:
        stimulus.close_hardware(instrument)
        pygame.quit()


if __name__ == "__main__":
    sys.exit(run())
