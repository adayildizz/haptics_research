"""CSV logging for trial-level and staircase-summary experiment data."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
TRIAL_FIELDS = [
    "width_level",
    "trial_number",
    "dH",
    "response",
    "correct",
    "finger_speed",
    "timestamp",
]
SUMMARY_FIELDS = ["width_level", "threshold", "n_trials", "n_reversals", "timestamp"]


def ensure_data_dir(data_dir: Path = DATA_DIR) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def init_csv(path: Path, fields: list[str]) -> None:
    if path.exists():
        return
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()


def append_trial(row: dict[str, Any], path: Path) -> None:
    init_csv(path, TRIAL_FIELDS)
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TRIAL_FIELDS)
        writer.writerow({field: row.get(field, "") for field in TRIAL_FIELDS})


def append_summary(row: dict[str, Any], path: Path) -> None:
    init_csv(path, SUMMARY_FIELDS)
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})
