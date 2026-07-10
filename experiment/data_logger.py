"""CSV/JSON logging for trial-level, per-pass, and session-summary data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"

TRIAL_FIELDS = [
    "session_id",
    "participant_id",
    "timestamp",
    "trial_index",
    "mode",
    "level_pct",
    "comparison_height_mm",
    "reference_height_mm",
    "bar_width_mm",
    "reference_side",
    "response",
    "correct",
    "is_catch",
    "is_practice",
    "response_time_s",
    "passes_json",
]

# Staircase pilot-mode threshold summary (unchanged shape from the previous
# staircase-only design, kept for mode == "staircase_pilot").
SUMMARY_FIELDS = ["base_height_mm", "bar_width_mm", "threshold_pct", "n_trials", "n_reversals", "timestamp"]


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
    serializable = dict(row)
    if "passes" in serializable and "passes_json" not in serializable:
        serializable["passes_json"] = json.dumps(serializable.pop("passes"))
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TRIAL_FIELDS)
        writer.writerow({field: serializable.get(field, "") for field in TRIAL_FIELDS})


def append_summary(row: dict[str, Any], path: Path) -> None:
    init_csv(path, SUMMARY_FIELDS)
    with path.open("a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def load_trials(path: Path) -> list[dict[str, Any]]:
    """Read a trial CSV back, decoding ``passes_json`` and coercing types."""
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as file:
        for raw in csv.DictReader(file):
            row: dict[str, Any] = dict(raw)
            row["trial_index"] = int(row["trial_index"])
            row["level_pct"] = float(row["level_pct"])
            row["comparison_height_mm"] = float(row["comparison_height_mm"])
            row["reference_height_mm"] = float(row["reference_height_mm"])
            row["correct"] = row["correct"] in ("1", "True", "true")
            row["is_catch"] = row["is_catch"] in ("1", "True", "true")
            row["is_practice"] = row["is_practice"] in ("1", "True", "true")
            row["response_time_s"] = float(row["response_time_s"]) if row["response_time_s"] else None
            row["passes"] = json.loads(row["passes_json"]) if row.get("passes_json") else []
            rows.append(row)
    return rows
