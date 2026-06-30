# Tactile Bar Graph Perception Experiment

Psychophysics experiment measuring height JND (just noticeable difference) for electroadhesion-based tactile bar graphs across independent bar-width and reference-height levels. The goal is to characterize tactile height discrimination without visual information, enabling data access for non-visual users.

## Research Question

How do bar width and reference height affect the JND threshold for bar height in a tactile bar graph rendered via electroadhesion?

## Hardware

| Component | Specification |
|-----------|---------------|
| Tactile display | Electroadhesion, 4V peak, 125 Hz carrier frequency |
| Position sensor | Nexio NIB170BP infrared frame, ~100 Hz |
| Interface | IR frame presents as virtual mouse via OS driver |

## Experimental Design

### Structure

A 2D grid design: bar width and reference height are independently varied across four levels each. A separate height-JND staircase runs for every width x height configuration, producing 16 threshold estimates.

### Bar Design: Separated (Non-Adjacent) Bars

Bars are rendered as discrete, non-adjacent stimuli. Adjacent bars were rejected because they introduce a dual-task interference problem: the participant must simultaneously perform boundary segmentation (where does one bar end and another begin?) and magnitude judgment (which bar is taller?). This conflation makes threshold measurement ambiguous — a variant of the classical two-point discrimination problem (Holmes & Tamè, 2023). Separated bars isolate the height discrimination task.

### Paradigm

2AFC (two-alternative forced choice): on each trial, the participant explores two bars sequentially and indicates which is taller. One bar is the reference (fixed height = current height level), the other is the test bar (reference height + dH). Target placement is randomized.

### Width and Height Levels

Four fixed width levels and four fixed reference-height levels:

```
2, 6, 10, 14 mm
```

A separate staircase runs for each width x reference-height pair.

### Height Staircase

At each width x reference-height configuration, a 1-up/2-down adaptive staircase measures height JND.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Reference height | Current height level | Independent from bar width |
| dH start | 200% of reference height | Well above threshold; ensures initial correct responses |
| dH minimum | 50% of reference height | Lower bound on test range |
| dH step size | 10% of reference height | Fine enough resolution for reliable threshold estimate |
| Stopping criterion | 12 reversals | Sun et al. (2023) |
| Threshold estimate | Mean of last 8 reversals | Sun et al. (2023) |

The 1-up/2-down rule converges on the ~70.7% correct point on the psychometric function.

## Rendering Method

Bar width is rendered using a **software-based timing method** rather than position-based polling. When the leading edge of a bar is detected, stimulus duration is computed as:

```
duration = bar_width / finger_speed
```

A high-resolution timer (`time.perf_counter()`) controls signal delivery independently of the IR frame rate. This bypasses the sampling bottleneck: at ~100 Hz with 10 cm/s finger speed, classical position-based rendering cannot reliably deliver bars narrower than ~2–3 mm. The timing method removes this constraint, shifting the rendering bottleneck to the signal generator's timing resolution.

## Display and Frame Calibration

The IR frame presents as a virtual mouse, so the experiment receives screen-pixel coordinates, not native millimeter coordinates. The normal experiment window is locked to the physical frame area:

```
FRAME_ACTIVE_WIDTH_MM = 200.0
FRAME_ACTIVE_HEIGHT_MM = 100.0
```

The saved display calibration tells the software how many screen pixels correspond to 1 physical millimeter on the monitor. The experiment uses that value to open a window whose physical size is approximately 200 mm x 100 mm. Inside that window:

```
bar width px = bar width mm * px_per_mm_x
bar height px = bar height mm * px_per_mm_y
```

To calibrate from measured screen/display dimensions:

```bash
python3 -m experiment.main --calibrate --active-width-mm <WIDTH_MM> --active-height-mm <HEIGHT_MM>
```

For a rough 14-inch estimate:

```bash
python3 -m experiment.main --calibrate --screen-diagonal-inch 14
```

This saves `experiment/data/display_calibration.json`. Bar widths use the X calibration, bar heights use the Y calibration, and finger speed converts pixel motion back to millimeters using the same two scale factors. When the real frame dimensions are measured, update `FRAME_ACTIVE_WIDTH_MM` and `FRAME_ACTIVE_HEIGHT_MM` in `config.py`.

The experiment refuses to run without this file unless `--allow-fallback-calibration` is passed. The fallback is only for software demos, not data collection.

## Variables

| Variable | Role | Notes |
|----------|------|-------|
| Bar width | Independent (fixed per staircase) | 4 levels: 2, 6, 10, 14 mm |
| Reference height | Independent (fixed per staircase) | 4 levels: 2, 6, 10, 14 mm |
| dH | Staircase variable | Converges to JND threshold |
| Finger speed | Covariate (recorded, not controlled) | To be revisited after hardware timing resolution is confirmed |

## Repository Structure

```
experiment/
├── main.py          # Entry point; orchestrates experiment flow
├── config.py        # All parameters and constants
├── staircase.py     # Staircase algorithm (no pygame dependency)
├── stimulus.py      # Bar rendering and signal control
├── trial.py         # Single trial logic
├── display.py       # Pygame UI and screen layout
├── data_logger.py   # Result recording (CSV)
└── data/            # Output directory
```

## Configuration (`config.py`)

```python
# Hardware
CARRIER_FREQUENCY = 125       # Hz
PEAK_VOLTAGE = 4              # V

# Stimulus levels (mm)
WIDTH_LEVELS = [2, 6, 10, 14]
HEIGHT_LEVELS = [2, 6, 10, 14]

# Height staircase
DH_START = 2.0                # 200% of reference height
DH_MIN = 0.5                  # 50% of reference height
DH_STEP = 0.1                 # 10% step size

# Stopping criterion (Sun et al., 2023)
N_REVERSALS = 12
N_REVERSALS_AVERAGED = 8
```

## Key References

- Sun et al. (2023). Investigating the minimum perceived linewidth of electroadhesion devices. *Displays*, 76, 102342.
- Holmes & Tamè (2023). Two-point discrimination. *(methodology rationale for separated bar design)*
- Tang & Beebe (1998). *(inter-bar spacing baseline: 5.8 mm edge-to-edge minimum)*
