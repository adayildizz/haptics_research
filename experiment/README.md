# Tactile Bar Graph Perception Experiment

Psychophysics experiment measuring the JND (just noticeable difference) for tactile bar height on an electroadhesion haptic display, using the method of constant stimuli. The goal is to characterize tactile height discrimination without visual information, enabling data access for non-visual users.

## Hardware

| Component | Specification |
|-----------|---------------|
| Tactile display | Electroadhesion, 4V peak, 125 Hz carrier frequency |
| Position sensor | Nexio NIB170BP infrared frame, ~100 Hz |
| Interface | IR frame presents as virtual mouse via OS driver |

## Experimental Design: Method of Constant Stimuli

One base (reference) height and one bar width are fixed per session (a "configuration"). Comparison heights are placed symmetrically around the base at fixed percentage offsets (`±delta_max_pct` by default), with a fixed number of trials per level -- no staircase, no reversals. Every parameter of this design is a field on `ExperimentConfig` (see `config.py`), loaded from a YAML/TOML file; nothing about the design is hard-coded.

- `levels = linspace(-delta_max_pct, +delta_max_pct, n_levels)`, dropping the 0% level unless `include_zero_level` is set.
- `comparison_height_mm = base_height_mm * (1 + level)`.
- `trials_per_level` reps per level, plus `catch_trial_pct` extra easy (±`delta_max_pct`) trials as a lapse/attention check.
- Reference/comparison side (left/right) is counterbalanced within each level.
- All trials for a configuration are shuffled into one sequence using a seeded RNG; the seed actually used is always logged, even when `rng_seed` is left unset (a fresh one is drawn and recorded).

Both bars are rendered simultaneously on a split screen. Bar interior = signal ON, exterior = OFF.

### Pilot mode

`mode: staircase_pilot` runs the original 1-up/2-down adaptive staircase (`staircase.py`) at one base height, to locate the approximate JND before committing to a `delta_max_pct` range for constant stimuli. At the end it prints the pilot JND and warns if it exceeds `delta_max_pct / 1.5` (range likely too narrow).

## Rendering Method

Bar width is rendered using a **software-based timing method** rather than position-based polling. When the leading edge of a bar is detected, stimulus duration is computed as:

```
duration = bar_width / finger_speed
```

A high-resolution timer (`time.perf_counter()`) controls signal delivery independently of the IR frame rate. This bypasses the sampling bottleneck: at ~100 Hz with 10 cm/s finger speed, classical position-based rendering cannot reliably deliver bars narrower than ~2-3 mm. Per trial, each bar crossing ("pass") is logged separately with its commanded duration, actual on-duration, entry finger speed, and whether the leading edge was cleanly detected (used to separate perceptual failures from rendering failures during analysis).

## Procedure

Each session runs as a single participant-facing fullscreen flow, advanced with
the **spacebar** and abortable at any point with **Escape** (or closing the
window). The task is two-alternative forced choice (2AFC): two bars are shown
side-by-side and the participant decides which is **taller**.

1. **Start screen.** The session opens on a "Ready to begin" prompt showing the
   mode and the base height/width for this configuration. Press **space** to begin.
2. **Practice block** (skipped if `n_practice_trials == 0`). A short run of easy
   trials at the extreme levels (±`delta_max_pct`) with **feedback forced on**,
   so the participant learns the response mapping before real data is collected.
   Optional spoken speed coaching says “Faster,” “Good speed,” or “Slower” after
   a stable speed reading. This coaching is disabled throughout the main block.
3. **Main block.** The full shuffled constant-stimuli sequence (levels + catch
   trials, interleaved). **Feedback is off** here unless `feedback: true` is set.
4. **Breaks.** Every `break_every_n_trials` trials the screen pauses on a break
   prompt showing progress; the participant resumes with **space**.
5. **End screen.** A "Session complete" message confirms data was saved.

Within a single trial the participant slides a finger across the touch surface to
explore the two bars. The electroadhesion signal is delivered over the **bar
interior only** (interior = ON, exterior = OFF), so each bar is felt as a raised
region whose width is governed by the timing method above. When ready, the
participant responds with the arrow keys:

- **← (Left arrow)** — the left bar felt taller.
- **→ (Right arrow)** — the right bar felt taller.

Practice trials are unspeeded. Main-block trials have a configurable response
limit (`response_timeout_s`, 30 seconds by default). If no bar is selected before
the limit, a beep sounds and another randomly selected pending bar pair is shown
under the same trial number. The unanswered slot remains pending, so the session
still collects exactly the configured number of responses. Response time is logged
per completed trial for reference. A visible countdown is shown during main trials
and turns red for the final five seconds. Which
side holds the reference vs. the comparison is counterbalanced within each level,
and a response is scored correct when it matches the objectively taller side.

### Blind test variant

Setting `blind_test_mode: true` hides the bars visually so they can be located
**by touch alone** — no on-screen rectangles, only the haptic signal and a touch
cursor. This enforces the study's premise of height discrimination *without*
visual information, and is the condition of interest for non-visual data access;
leave it `false` for sighted-guided piloting and rig checks.

## Repository Structure

```
experiment/
├── main.py              # Entry point; mode dispatch (constant_stimuli / staircase_pilot / --dry-run)
├── config.py            # Rig constants + ExperimentConfig (the single design-parameter source)
├── constant_stimuli.py  # Level generation + trial scheduling (no pygame dependency)
├── staircase.py         # Staircase algorithm for pilot mode (no pygame dependency)
├── stimulus.py          # Bar rendering and signal control
├── trial.py             # Single trial logic, per-pass fidelity logging
├── display.py           # Pygame UI and screen layout
├── data_logger.py       # CSV/JSON logging
├── configs/             # Example YAML configs (default.yaml, pilot.yaml)
└── data/                # Output directory

analysis/
└── fit_psychometric.py  # Psychometric-function fitting (psignifit preferred, scipy MLE fallback),
                          # plotting, ideal-observer simulation. No pygame dependency; runs standalone
                          # on saved CSVs.

tests/                   # pytest: level generation, scheduling, psychometric-fit recovery
```

## Configuration (`ExperimentConfig`, loaded from YAML)

```yaml
base_height_mm: 10.0
bar_width_mm: 10.0
inter_bar_gap_mm: 40.0   # >= 3.0 mm (BANA 3.4.3.13; Tang & Beebe 1998)

delta_max_pct: 0.30
n_levels: 6
include_zero_level: false
trials_per_level: 10
catch_trial_pct: 0.10

feedback: false
n_practice_trials: 8
break_every_n_trials: 30
response_timeout_s: 30.0
practice_voice_feedback: true
ideal_finger_speed_mm_s: 100.0
ideal_speed_tolerance_pct: 0.30
record_main_trace: true

blind_test_mode: false   # true -> hide bars, locate them by touch only (no visual)

rng_seed: null           # null -> random, but the resolved seed is always logged
participant_id: ""
mode: constant_stimuli   # or staircase_pilot
```

Run with:

```
python -m experiment.main --config experiment/configs/default.yaml --participant P01
python -m experiment.main --config experiment/configs/pilot.yaml --participant P01   # pilot mode
python -m experiment.main --config experiment/configs/default.yaml --dry-run         # ideal-observer sanity check, no pygame/hardware
```

Fit a saved session:

```
python -m analysis.fit_psychometric experiment/data/P01_*_trials.csv --out fit.png
```

### Main-trial movement trace

With `record_main_trace: true`, each constant-stimuli session also creates
`experiment/data/<session_id>_trace.sqlite3`. It records every main-block
attempt, including attempts that end in timeout or abort. Practice trials and
staircase-pilot sessions are not recorded. Cursor samples are accumulated in
small in-memory batches and SQLite writes run on a dedicated worker thread, so
the real-time trial loop never performs disk I/O. The trace is intended for the
offline replay and video-export tools; those tools do not run during an
experiment.

Open the interactive replay browser with:

```bash
python -m experiment.replay
```

The left panel lists trace databases and their attempts in chronological order.
Select an attempt, then use **Play/Pause**, **Restart**, or the clickable timeline.
The left/right arrow keys seek by one second and Space toggles playback. A
deterministic `demo_replay_trace.sqlite3` recording is created automatically so
the browser can be evaluated before real participant traces are available. Pass
`--no-demo` to hide that recording.

### Supervisor launcher (GUI)

`experiment/gui.py` is a small Tkinter control panel for the supervisor, so
repeat sessions don't require re-typing config values or CLI flags by hand:

```
python -m experiment.gui
```

It opens pre-filled with the previously used configuration
(`experiment/configs/.last_used.yaml`, not versioned), so most sessions only
need the participant ID changed before pressing **Apply**. Apply writes the
form values out, hides the panel, and launches the participant-facing pygame
screen (`experiment.main`) as a subprocess; the panel reappears automatically
once that session ends.

The **Past Recordings** tab lists saved trace databases and their attempts in
chronological order. Selecting an attempt opens Play/Pause, Restart, and
timeline controls and renders the replay directly inside the launcher window;
it does not create a separate Pygame window. Replay modules are loaded only
when that tab is opened and playback is stopped before an experiment starts.
Answered attempts show the selected side (Left or Right), prefixed by a check
mark for a correct response or a cross for an incorrect response. With
Auto-next enabled, the player waits briefly at the end of an attempt and then
continues with the next attempt in chronological order.

## Key References

- Sun et al. (2023). Investigating the minimum perceived linewidth of electroadhesion devices. *Displays*, 76, 102342.
- Holmes & Tamè (2023). Two-point discrimination. *(methodology rationale for separated bar design)*
- Tang & Beebe (1998). *(inter-bar spacing baseline)*
