"""Finger-movement animations and grid heat maps from a session trace.

Reads the ``<session>_trace.sqlite3`` written during a session (practice and
main block) and produces two kinds of offline artefact:

``animate``
    One GIF/MP4 per attempt: the two bars drawn to scale in surface
    millimetres, the finger's full path so far in grey, the last second as
    a coloured trail, and the current fingertip as a marker that is green
    while the electroadhesion signal is on and grey while it is off. Time,
    speed and the side being touched are printed in the corner.

``heatmap``
    A grid laid over the bars and their surroundings; each cell counts how
    many times the finger *entered* it (``visits``) and how long it stayed
    (``dwell_ms``). Rendered as a heat map with the bar outlines on top, and
    written as CSV so the numbers can be re-plotted or compared between
    participants. By default the whole main block is aggregated; practice
    can be included or every attempt can get its own map.

Both work in the coordinate system the trace stores: millimetres from the
active surface's top-left corner, y increasing downwards (screen
orientation). The bars are reconstructed from the same numbers the live
layout used (``inter_bar_gap_mm`` from the session config; width and
heights from the attempt; the surface size from the calibration), so what
is drawn is where the signal actually switched on.

Usage::

    python -m analysis.trace_movement animate experiment/data/P01_x_trace.sqlite3 --out out/anim
    python -m analysis.trace_movement animate TRACE --trial 12            # one trial, all attempts
    python -m analysis.trace_movement animate TRACE --include-practice --speed 2 --format mp4
    python -m analysis.trace_movement heatmap TRACE --out out/heat        # main block, aggregated
    python -m analysis.trace_movement heatmap TRACE --per-attempt --cell-mm 2 --metric dwell_ms

No pygame dependency: only matplotlib (+ Pillow for GIF, ffmpeg for MP4).
"""

from __future__ import annotations

import argparse
import bisect
import csv
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from experiment.replay_data import ReplayAttempt, ReplaySession, load_trace

METRICS = ("visits", "dwell_ms", "samples")


# --------------------------------------------------------------------------- geometry


@dataclass(frozen=True)
class BarGeometry:
    """Both bars in surface millimetres (x from the left edge, y down from the top)."""

    surface_width_mm: float
    surface_height_mm: float
    bar_width_mm: float
    left_x0: float
    right_x0: float
    left_height_mm: float
    right_height_mm: float
    left_is_comparison: bool

    @property
    def baseline_y(self) -> float:
        return self.surface_height_mm

    @property
    def left_x1(self) -> float:
        return self.left_x0 + self.bar_width_mm

    @property
    def right_x1(self) -> float:
        return self.right_x0 + self.bar_width_mm

    @property
    def taller_side(self) -> str | None:
        if math.isclose(self.left_height_mm, self.right_height_mm):
            return None
        return "left" if self.left_height_mm > self.right_height_mm else "right"

    def rects(self) -> list[tuple[str, float, float, float, float]]:
        """``(side, x0, y_top, width, height)`` for each bar, in mm."""
        return [
            ("left", self.left_x0, self.baseline_y - self.left_height_mm, self.bar_width_mm, self.left_height_mm),
            ("right", self.right_x0, self.baseline_y - self.right_height_mm, self.bar_width_mm, self.right_height_mm),
        ]


def _surface_size_mm(session: ReplaySession) -> tuple[float, float]:
    cal = session.calibration
    width = cal.get("active_width_mm")
    height = cal.get("active_height_mm")
    if width is None:
        width = float(cal["active_width_px"]) / float(cal["px_per_mm_x"])
    if height is None:
        height = float(cal["active_height_px"]) / float(cal["px_per_mm_y"])
    return float(width), float(height)


def bar_geometry(session: ReplaySession, attempt: ReplayAttempt) -> BarGeometry:
    """Reconstruct the bars exactly as ``display.make_trial_layout`` placed them."""
    surface_w, surface_h = _surface_size_mm(session)
    gap = float(session.config.get("inter_bar_gap_mm", 40.0))
    width = attempt.bar_width_mm
    center = surface_w / 2.0
    left_center = center - gap / 2.0 - width / 2.0
    right_center = center + gap / 2.0 + width / 2.0
    left_is_comparison = attempt.reference_side == "right"
    left_h = attempt.comparison_height_mm if left_is_comparison else attempt.reference_height_mm
    right_h = attempt.reference_height_mm if left_is_comparison else attempt.comparison_height_mm
    return BarGeometry(
        surface_width_mm=surface_w,
        surface_height_mm=surface_h,
        bar_width_mm=width,
        left_x0=left_center - width / 2.0,
        right_x0=right_center - width / 2.0,
        left_height_mm=left_h,
        right_height_mm=right_h,
        left_is_comparison=left_is_comparison,
    )


# --------------------------------------------------------------------------- heat map


@dataclass(frozen=True)
class HeatGrid:
    x_edges: np.ndarray  # nx + 1
    y_edges: np.ndarray  # ny + 1
    visits: np.ndarray   # (ny, nx) number of entries into the cell
    dwell_ms: np.ndarray  # (ny, nx) time spent in the cell
    samples: np.ndarray  # (ny, nx) raw sample count
    n_attempts: int

    @property
    def cell_mm(self) -> float:
        return float(self.x_edges[1] - self.x_edges[0])

    def metric(self, name: str) -> np.ndarray:
        if name not in METRICS:
            raise ValueError(f"unknown metric {name!r}; choose from {METRICS}")
        return getattr(self, name)


def grid_edges(
    geometries: Sequence[BarGeometry],
    cell_mm: float,
    margin_mm: float,
    below_mm: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Cell edges covering the bars plus ``margin_mm`` on the left/right/top.

    ``below_mm`` extends the grid a little under the baseline: the baseline is
    the surface's bottom edge in the live layout, but the IR frame keeps
    reporting positions past it, and "how often did the finger overshoot the
    bottom" is itself a strategy question.
    """
    if cell_mm <= 0:
        raise ValueError("cell_mm must be > 0")
    geometry = geometries[0]
    tallest = max(max(g.left_height_mm, g.right_height_mm) for g in geometries)
    x0 = min(g.left_x0 for g in geometries) - margin_mm
    x1 = max(g.right_x1 for g in geometries) + margin_mm
    y0 = geometry.baseline_y - tallest - margin_mm
    y1 = geometry.baseline_y + below_mm
    nx = max(1, math.ceil((x1 - x0) / cell_mm))
    ny = max(1, math.ceil((y1 - y0) / cell_mm))
    # Anchor the grid on the baseline so a row of cells ends exactly at the
    # bars' bottom edge, and on the left bar's left edge so columns line up
    # with the bar sides -- otherwise a bar edge falls mid-cell and the map
    # smears "on the bar" into "beside the bar".
    x_start = geometry.left_x0 - cell_mm * math.ceil((geometry.left_x0 - x0) / cell_mm)
    y_end = geometry.baseline_y + cell_mm * math.ceil((y1 - geometry.baseline_y) / cell_mm)
    nx = math.ceil((x1 - x_start) / cell_mm)
    ny = math.ceil((y_end - y0) / cell_mm)
    x_edges = x_start + cell_mm * np.arange(nx + 1)
    y_edges = (y_end - cell_mm * ny) + cell_mm * np.arange(ny + 1)
    return x_edges, y_edges


def _accumulate(attempt: ReplayAttempt, x_edges: np.ndarray, y_edges: np.ndarray, visits, dwell_ms, samples) -> None:
    nx = len(x_edges) - 1
    ny = len(y_edges) - 1
    previous: tuple[int, int] | None = None
    for sample in attempt.samples:
        ix = int(np.searchsorted(x_edges, sample.x_mm, side="right")) - 1
        iy = int(np.searchsorted(y_edges, sample.y_mm, side="right")) - 1
        if not (0 <= ix < nx and 0 <= iy < ny):
            previous = None
            continue
        cell = (iy, ix)
        if cell != previous:
            visits[cell] += 1
            previous = cell
        dwell_ms[cell] += sample.frame_dt_us / 1000.0
        samples[cell] += 1


def compute_heatmap(
    session: ReplaySession,
    attempts: Sequence[ReplayAttempt],
    cell_mm: float = 2.0,
    margin_mm: float = 15.0,
) -> HeatGrid:
    """Grid-count the finger samples of ``attempts`` over the bar region."""
    if not attempts:
        raise ValueError("no attempts to map")
    geometries = [bar_geometry(session, attempt) for attempt in attempts]
    x_edges, y_edges = grid_edges(geometries, cell_mm, margin_mm)
    shape = (len(y_edges) - 1, len(x_edges) - 1)
    visits = np.zeros(shape, dtype=np.int64)
    dwell_ms = np.zeros(shape, dtype=np.float64)
    samples = np.zeros(shape, dtype=np.int64)
    for attempt in attempts:
        _accumulate(attempt, x_edges, y_edges, visits, dwell_ms, samples)
    return HeatGrid(x_edges, y_edges, visits, dwell_ms, samples, len(attempts))


def write_heatmap_csv(grid: HeatGrid, path: Path) -> None:
    with Path(path).open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["ix", "iy", "x0_mm", "x1_mm", "y0_mm", "y1_mm", "visits", "dwell_ms", "samples"])
        for iy in range(grid.visits.shape[0]):
            for ix in range(grid.visits.shape[1]):
                writer.writerow(
                    [
                        ix,
                        iy,
                        f"{grid.x_edges[ix]:.3f}",
                        f"{grid.x_edges[ix + 1]:.3f}",
                        f"{grid.y_edges[iy]:.3f}",
                        f"{grid.y_edges[iy + 1]:.3f}",
                        int(grid.visits[iy, ix]),
                        f"{grid.dwell_ms[iy, ix]:.1f}",
                        int(grid.samples[iy, ix]),
                    ]
                )


def _draw_bars(ax, geometries: Sequence[BarGeometry], *, fill: bool) -> None:
    """Bar outlines. With several geometries (aggregate map) the reference
    height is drawn solid on both sides and the tallest comparison dashed."""
    from matplotlib.patches import Rectangle

    if len(geometries) == 1:
        geometry = geometries[0]
        for side, x0, y_top, width, height in geometry.rects():
            is_comparison = (side == "left") == geometry.left_is_comparison
            ax.add_patch(
                Rectangle(
                    (x0, y_top), width, height,
                    fill=fill,
                    facecolor=("#48bb78" if is_comparison else "#4299e1") if fill else "none",
                    alpha=0.35 if fill else 1.0,
                    edgecolor="#48bb78" if is_comparison else "#4299e1",
                    linewidth=2.0,
                )
            )
        return
    geometry = geometries[0]
    reference = [
        g.right_height_mm if g.left_is_comparison else g.left_height_mm for g in geometries
    ][0]
    tallest = max(max(g.left_height_mm, g.right_height_mm) for g in geometries)
    shortest = min(min(g.left_height_mm, g.right_height_mm) for g in geometries)
    for x0 in (geometry.left_x0, geometry.right_x0):
        ax.add_patch(
            Rectangle((x0, geometry.baseline_y - reference), geometry.bar_width_mm, reference,
                      fill=False, edgecolor="#4299e1", linewidth=2.0)
        )
        for height in (tallest, shortest):
            ax.add_patch(
                Rectangle((x0, geometry.baseline_y - height), geometry.bar_width_mm, height,
                          fill=False, edgecolor="#48bb78", linewidth=1.2, linestyle="--")
            )


def plot_heatmap(
    grid: HeatGrid,
    geometries: Sequence[BarGeometry],
    out_path: Path,
    *,
    metric: str = "visits",
    title: str = "",
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = grid.metric(metric).astype(float)
    fig, ax = plt.subplots(figsize=(10, 6))
    extent = (grid.x_edges[0], grid.x_edges[-1], grid.y_edges[-1], grid.y_edges[0])  # y down
    image = ax.imshow(values, origin="upper", extent=extent, cmap="magma", interpolation="nearest", aspect="equal")
    # Faint grid lines so individual cells can be read off.
    for x in grid.x_edges:
        ax.axvline(x, color="white", alpha=0.08, linewidth=0.5)
    for y in grid.y_edges:
        ax.axhline(y, color="white", alpha=0.08, linewidth=0.5)
    _draw_bars(ax, geometries, fill=False)
    ax.axhline(geometries[0].baseline_y, color="#f5a623", linewidth=1.0, alpha=0.8)
    ax.set_xlim(grid.x_edges[0], grid.x_edges[-1])
    ax.set_ylim(grid.y_edges[-1], grid.y_edges[0])
    ax.set_xlabel("x (mm from surface left edge)")
    ax.set_ylabel("y (mm from surface top edge)")
    label = {"visits": "visits (entries into cell)", "dwell_ms": "dwell time (ms)", "samples": "samples"}[metric]
    fig.colorbar(image, ax=ax, label=label, shrink=0.8)
    ax.set_title(title or f"{label} · {grid.n_attempts} attempt(s) · {grid.cell_mm:g} mm cells")
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- animation


def _attempt_stem(session: ReplaySession, attempt: ReplayAttempt) -> str:
    prefix = f"practice{attempt.practice_round}_" if attempt.is_practice else "main_"
    return f"{session.participant_id}_{prefix}trial{attempt.trial_index:02d}_attempt{attempt.attempt_index}"


def animate_attempt(
    session: ReplaySession,
    attempt: ReplayAttempt,
    out_path: Path,
    *,
    fps: int = 30,
    speed: float = 1.0,
    trail_s: float = 1.0,
    fmt: str = "gif",
    margin_mm: float = 15.0,
    max_frames: int | None = None,
) -> Path:
    """Render one attempt's finger path over the bars to a GIF or MP4.

    ``speed`` > 1 plays faster than real time (fewer frames). ``max_frames``
    is for tests and previews.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

    geometry = bar_geometry(session, attempt)
    duration_us = attempt.duration_us
    step_us = 1_000_000.0 * speed / fps
    n_frames = max(2, int(duration_us / step_us) + 1)
    if max_frames is not None:
        n_frames = min(n_frames, max_frames)
    frame_times = [min(duration_us, round(i * step_us)) for i in range(n_frames)]

    xs = np.array([s.x_mm for s in attempt.samples])
    ys = np.array([s.y_mm for s in attempt.samples])
    ts = list(attempt.sample_times_us)

    tallest = max(geometry.left_height_mm, geometry.right_height_mm)
    x_lo, x_hi = geometry.left_x0 - margin_mm, geometry.right_x1 + margin_mm
    y_lo, y_hi = geometry.baseline_y - tallest - margin_mm, geometry.baseline_y + 5.0
    if len(xs):
        # Widen so an excursion well outside the bars is still visible.
        x_lo, x_hi = min(x_lo, xs.min() - 3), max(x_hi, xs.max() + 3)
        y_lo, y_hi = min(y_lo, ys.min() - 3), max(y_hi, ys.max() + 3)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor("#191d24")
    fig.patch.set_facecolor("#0e1116")
    _draw_bars(ax, [geometry], fill=True)
    ax.axhline(geometry.baseline_y, color="#f5a623", linewidth=1.0, alpha=0.8)
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_hi, y_lo)  # y down, like the screen and the trace
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)", color="#aab")
    ax.set_ylabel("y (mm)", color="#aab")
    ax.tick_params(colors="#aab")
    for spine in ax.spines.values():
        spine.set_color("#444")

    outcome = attempt.outcome or "open"
    verdict = ""
    if attempt.correct is True:
        verdict = " ✓"
    elif attempt.correct is False:
        verdict = " ✗"
    ax.set_title(
        f"{session.participant_id} · {attempt.label} · attempt {attempt.attempt_index} · "
        f"level {attempt.level_pct:+.0%} · taller: {geometry.taller_side} · "
        f"{outcome}{(' ' + attempt.response) if attempt.response else ''}{verdict}",
        color="#eef", fontsize=10,
    )

    (path_line,) = ax.plot([], [], color="#8892a0", linewidth=0.8, alpha=0.7)
    (trail_line,) = ax.plot([], [], color="#ff4141", linewidth=2.0, alpha=0.9)
    marker = ax.scatter([], [], s=90, zorder=5, edgecolors="white", linewidths=0.8)
    # Top-left: y is inverted so the bars sit at the bottom of the axes and
    # the top is the emptiest corner.
    hud = ax.text(
        0.01, 0.98, "", transform=ax.transAxes, color="#eef", fontsize=9,
        family="monospace", va="top", ha="left",
        bbox={"facecolor": "#000", "alpha": 0.5, "edgecolor": "none"},
    )

    def render(frame_index: int):
        t_us = frame_times[frame_index]
        state = attempt.state_at(t_us)
        upto = bisect.bisect_right(ts, t_us)
        since = bisect.bisect_left(ts, t_us - trail_s * 1_000_000)
        path_line.set_data(xs[:upto], ys[:upto])
        trail_line.set_data(xs[since:upto], ys[since:upto])
        if state is not None:
            marker.set_offsets([[state.x_mm, state.y_mm]])
            marker.set_facecolor("#48dc78" if state.signal_on else "#7d8590")
            hud.set_text(
                f"t {t_us / 1e6:5.2f} s   speed {state.speed_mm_s:5.1f} mm/s   "
                f"side {state.active_side or '-':5s}   signal {'ON ' if state.signal_on else 'off'}"
            )
        return path_line, trail_line, marker, hud

    animation = FuncAnimation(fig, render, frames=n_frames, interval=1000 / fps, blit=False)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "mp4":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("mp4 export needs ffmpeg on PATH; use --format gif")
        writer = FFMpegWriter(fps=fps, bitrate=2400)
    else:
        writer = PillowWriter(fps=fps)
    animation.save(str(out_path), writer=writer, dpi=100)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- CLI


def select_attempts(
    session: ReplaySession,
    *,
    include_practice: bool = False,
    practice_only: bool = False,
    trial: int | None = None,
    answered_only: bool = False,
) -> list[ReplayAttempt]:
    chosen: Iterable[ReplayAttempt] = session.attempts
    if practice_only:
        chosen = [a for a in chosen if a.is_practice]
    elif not include_practice:
        chosen = [a for a in chosen if not a.is_practice]
    if trial is not None:
        chosen = [a for a in chosen if a.trial_index == trial]
    if answered_only:
        chosen = [a for a in chosen if a.outcome == "answered"]
    return [a for a in chosen if a.samples]


def _add_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("trace", type=Path, help="<session>_trace.sqlite3")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: next to the trace).")
    parser.add_argument("--trial", type=int, default=None, help="Only this trial_index (all its attempts).")
    parser.add_argument("--include-practice", action="store_true", help="Also include practice attempts.")
    parser.add_argument("--practice-only", action="store_true", help="Only practice attempts.")
    parser.add_argument("--answered-only", action="store_true", help="Skip timed-out / aborted attempts.")
    parser.add_argument("--margin-mm", type=float, default=15.0, help="Space around the bars to show/grid.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    animate = sub.add_parser("animate", help="One GIF/MP4 per attempt.")
    _add_selection_args(animate)
    animate.add_argument("--fps", type=int, default=30)
    animate.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier (2 = twice real time).")
    animate.add_argument("--trail-s", type=float, default=1.0, help="Seconds of path highlighted as the trail.")
    animate.add_argument("--format", choices=("gif", "mp4"), default="gif")

    heat = sub.add_parser("heatmap", help="Grid visit/dwell heat map over the bars.")
    _add_selection_args(heat)
    heat.add_argument("--cell-mm", type=float, default=2.0)
    heat.add_argument("--metric", choices=METRICS, default="visits")
    heat.add_argument("--per-attempt", action="store_true", help="One map per attempt instead of one aggregate.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    session = load_trace(args.trace)
    out_dir = args.out or args.trace.parent / f"{args.trace.stem}_{args.command}"
    out_dir.mkdir(parents=True, exist_ok=True)
    attempts = select_attempts(
        session,
        include_practice=args.include_practice,
        practice_only=args.practice_only,
        trial=args.trial,
        answered_only=args.answered_only,
    )
    if not attempts:
        print("No attempts with samples match the selection.")
        return 1

    if args.command == "animate":
        for attempt in attempts:
            path = out_dir / f"{_attempt_stem(session, attempt)}.{args.format}"
            animate_attempt(
                session, attempt, path,
                fps=args.fps, speed=args.speed, trail_s=args.trail_s, fmt=args.format, margin_mm=args.margin_mm,
            )
            print(f"wrote {path}")
        return 0

    if args.per_attempt:
        for attempt in attempts:
            grid = compute_heatmap(session, [attempt], cell_mm=args.cell_mm, margin_mm=args.margin_mm)
            stem = out_dir / _attempt_stem(session, attempt)
            geometry = bar_geometry(session, attempt)
            plot_heatmap(
                grid, [geometry], stem.with_suffix(".png"), metric=args.metric,
                title=f"{session.participant_id} · {attempt.label} · attempt {attempt.attempt_index} · "
                      f"level {attempt.level_pct:+.0%} · {args.metric}",
            )
            write_heatmap_csv(grid, stem.with_suffix(".csv"))
            print(f"wrote {stem}.png / .csv")
        return 0

    grid = compute_heatmap(session, attempts, cell_mm=args.cell_mm, margin_mm=args.margin_mm)
    scope = "practice" if args.practice_only else ("all" if args.include_practice else "main")
    stem = out_dir / f"{session.participant_id}_{scope}_heatmap_{args.metric}_{args.cell_mm:g}mm"
    geometries = [bar_geometry(session, a) for a in attempts]
    plot_heatmap(
        grid, geometries, stem.with_suffix(".png"), metric=args.metric,
        title=f"{session.participant_id} · {scope} block · {len(attempts)} attempts · {args.metric} · {args.cell_mm:g} mm cells",
    )
    write_heatmap_csv(grid, stem.with_suffix(".csv"))
    print(f"wrote {stem}.png / .csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
