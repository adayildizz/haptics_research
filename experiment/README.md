# Experiment — Tactile Bar Graph Height JND

Psychophysics study measuring the height **just-noticeable difference (JND)** for bars in a tactile bar chart rendered via electroadhesion, across four bar widths. The goal is to characterise how bar geometry affects height discrimination when no visual information is available — relevant for accessible data representation.

---

## Research Question

> How does bar width affect the smallest detectable height difference (JND) in an electroadhesive tactile bar graph?

---

## Design

| Parameter | Value |
|-----------|-------|
| Independent variable | Bar width (5, 10, 15, 20 mm) |
| Dependent variable | Height JND (mm) |
| Reference heights | 2, 4, 6, 8, 10, 12, 14, 16 mm |
| Task | 2-AFC: "which bar is taller?" |
| Staircase | 1-up 2-down (targets 70.7 % correct) |
| Initial Δh | 2.0 mm |
| Minimum Δh | 0.5 mm |
| Step size | 0.1 mm |
| Stopping criterion | 12 reversals |
| Threshold estimate | Mean of last 8 reversals |

Each combination of bar width × reference height is one **condition** (4 × 8 = 32 conditions per participant). Conditions are presented in randomised order.

---

## Stimulus

A single bar is rendered on the touchscreen. The participant slides a finger from bottom to top across the bar and judges its height. Two bars are presented sequentially in each trial (2-AFC): one at the reference height, one at reference ± Δh. The haptic signal is a square wave at 125 Hz, 4 V, delivered only while the finger is within the bar's horizontal extent.

```
Presentation order (counterbalanced):
  Trial A:  [reference]  →  [comparison]
  Trial B:  [comparison]  →  [reference]
```

The participant presses **← / →** to indicate which bar felt taller. Feedback is not provided.

---

## File Structure

```
experiment/
├── main.py        # Entry point — orchestrates conditions and saves results
├── trial.py       # Single 2-AFC trial (show two stimuli, collect response)
├── stimulus.py    # Renders one bar and delivers haptic feedback during touch
├── staircase.py   # 1-up 2-down staircase controller
└── data/          # CSV output — one file per participant
```

### `staircase.py`

Implements a 1-up 2-down transformed staircase:
- Two consecutive correct responses → Δh decreases by one step
- One incorrect response → Δh increases by one step
- Stops after `N_REVERSALS` (12) direction reversals
- Threshold = mean of the last `N_REVERSALS_AVERAGED` (8) reversal values

### `stimulus.py`

Draws a single bar of specified width and height to the screen. Activates haptic output (`WAVE_SQUARE`, 125 Hz, 4 V) while the finger is inside the bar region. Returns when the finger leaves the bar or a timeout expires.

### `trial.py`

Runs one 2-AFC trial:
1. Show bar A (ISI blank screen between stimuli)
2. Show bar B
3. Wait for keypress (← = first, → = second)
4. Return `correct: bool`

### `main.py`

- Parses `--participant` and `--session` arguments
- Shuffles conditions
- Runs the staircase for each condition
- Writes results to `data/<participant>_<session>.csv`

---

## Running

```bash
python main.py --experiment
# then follow on-screen prompts for participant ID and session number
```

Or directly:

```bash
cd experiment
python main.py --participant P01 --session 1
```

---

## Output Format

`data/<participant>_<session>.csv`

| Column | Description |
|--------|-------------|
| `participant` | Participant ID |
| `session` | Session number |
| `bar_width_mm` | Bar width condition (mm) |
| `ref_height_mm` | Reference bar height (mm) |
| `threshold_mm` | Estimated JND (mm) |
| `n_trials` | Number of trials in staircase |
| `reversals` | Comma-separated reversal values |

---

## Hardware Parameters

| Parameter | Value |
|-----------|-------|
| Waveform | Square (`SQU`) |
| Carrier frequency | 125 Hz |
| Voltage | 4.0 V |
| Display | Electroadhesion touchscreen |
| Position sensor | Nexio NIB170BP (~100 Hz) |

---

## References

- Sun, X. et al. (2023). *Staircase stopping criterion for JND estimation.* [reference for N_REVERSALS=12, N_AVERAGED=8 criterion]
