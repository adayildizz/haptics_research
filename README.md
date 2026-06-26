# haptic-lab

Research repository for electroadhesion-based haptic display systems. Built at the Haptics Lab, Koç University.

---

## Repository Structure

```
haptic-lab/
├── experiment/    # Psychophysics experiment: tactile bar graph JND
├── demo/          # Interactive haptic demo modes
├── core/          # Hardware controller (HapticController)
├── config.py      # Hardware constants and display settings
└── main.py        # Entry point — see usage below
```

### Usage

```bash
# Demo modes
python demo/main.py --heart
python demo/main.py --train
python demo/main.py --texture
python demo/main.py --bar
python demo/main.py --pie
python demo/main.py --image path/to/image.png

# Psychophysics experiment
python experiment/main.py --participant P01 --session 1
```

### `experiment/`

A psychophysics experiment measuring height JND for tactile bar graphs rendered via electroadhesion, across varying bar widths. The goal is to characterize how bar geometry affects height discrimination without visual information — enabling data access for non-visual users.

See [`experiment/README.md`](experiment/README.md) for full design documentation.

### `demo/`

An interactive application demonstrating electroadhesion haptic feedback through three modes: heartbeat simulation, surface texture rendering, and train momentum. Forked from [emirbahadirunsal/EA-Demo](https://github.com/emirbahadirunsal/EA-Demo).

Start with `python main.py --demo heart` (see usage below).

---

## Hardware

Both modules run on the same hardware stack:

| Component | Specification |
|-----------|---------------|
| Tactile display | Electroadhesion, 4V peak, 125 Hz carrier frequency |
| Position sensor | Nexio NIB170BP infrared frame, ~100 Hz |
| Signal generator | VISA-compatible (e.g. Keysight 81150A) |
| Amplifier | 50× voltage amplifier |

---

## Lab

[Haptics Lab, Koç University](https://haptics.ku.edu.tr) — supervised by Prof. Çağatay Başdoğan.