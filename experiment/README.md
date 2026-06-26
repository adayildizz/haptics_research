# Tactile Bar Graph Perception Experiment

Psychophysics experiment measuring height JND (just noticeable difference) for electroadhesion-based tactile bar graphs across varying bar widths. The goal is to characterize how bar width affects height discrimination ability without visual information, enabling data access for non-visual users.

## Research Question

How does bar width affect the JND threshold for bar height in a tactile bar graph rendered via electroadhesion?

## Hardware

| Component | Specification |
|-----------|---------------|
| Tactile display | Electroadhesion, 4V peak, 125 Hz carrier frequency |
| Position sensor | Nexio NIB170BP infrared frame, ~100 Hz |
| Interface | IR frame presents as virtual mouse via OS driver |

## Experimental Design

### Structure

A 2D grid design: bar width is held fixed at multiple levels, and height JND is measured via staircase at each level. This produces a **width × JND curve** — a single unified experiment, not a sequential two-phase design.

### Bar Design: Separated (Non-Adjacent) Bars

Bars are rendered as discrete, non-adjacent stimuli. Adjacent bars were rejected because they introduce a dual-task interference problem: the participant must simultaneously perform boundary segmentation (where does one bar end and another begin?) and magnitude judgment (which bar is taller?). This conflation makes threshold measurement ambiguous — a variant of the classical two-point discrimination problem (Holmes & Tamè, 2023). Separated bars isolate the height discrimination task.

### Paradigm

2AFC (two-alternative forced choice): on each trial, the participant explores two bars sequentially and indicates which is taller. One bar is the reference (fixed height = current width level), the other is the test bar (reference height + dH). Target placement is randomized.

### Width Levels

Eight fixed width levels, uniformly spaced across the testable range:

```
2, 4, 6, 8, 10, 12, 14, 16 mm
```

Uniform spacing was chosen to avoid imposing prior assumptions about where JND changes most steeply. A separate staircase runs for each width level.

### Height Staircase

At each width level, a 1-up/2-down adaptive staircase measures height JND.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Reference height | Equal to current width level | Symmetric bar aspect ratio as baseline |
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

## Variables

| Variable | Role | Notes |
|----------|------|-------|
| Bar width | Independent (fixed per staircase) | 8 levels: 2–16 mm |
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

# Width levels (mm)
WIDTH_LEVELS = [2, 4, 6, 8, 10, 12, 14, 16]

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