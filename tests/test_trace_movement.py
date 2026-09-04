from __future__ import annotations

import csv

import numpy as np
import pytest

from analysis.trace_movement import (
    animate_attempt,
    bar_geometry,
    compute_heatmap,
    grid_edges,
    plot_heatmap,
    select_attempts,
    write_heatmap_csv,
)
from experiment.demo_trace import ensure_demo_trace
from experiment.replay_data import load_trace


@pytest.fixture
def demo_session(tmp_path):
    return load_trace(ensure_demo_trace(tmp_path / "demo_replay_trace.sqlite3"))


def test_bar_geometry_matches_live_layout(demo_session):
    attempt = demo_session.attempts[0]  # level -18%, reference left -> comparison right, shorter
    geometry = bar_geometry(demo_session, attempt)

    assert geometry.surface_width_mm == pytest.approx(194.0)
    assert geometry.baseline_y == pytest.approx(145.0)
    # 40 mm gap between the bars' inner edges, both 10 mm wide, centred.
    assert geometry.right_x0 - geometry.left_x1 == pytest.approx(40.0)
    assert (geometry.left_x0 + geometry.right_x1) / 2 == pytest.approx(97.0)
    assert geometry.left_is_comparison is False
    assert geometry.left_height_mm == pytest.approx(10.0)
    assert geometry.right_height_mm == pytest.approx(8.2)
    assert geometry.taller_side == "left"


def test_grid_is_anchored_on_bar_edges(demo_session):
    geometry = bar_geometry(demo_session, demo_session.attempts[0])
    x_edges, y_edges = grid_edges([geometry], cell_mm=2.0, margin_mm=15.0)

    assert np.isclose(x_edges, geometry.left_x0).any()
    assert np.isclose(y_edges, geometry.baseline_y).any()
    assert x_edges[0] <= geometry.left_x0 - 15.0 + 1e-9
    assert x_edges[-1] >= geometry.right_x1 + 15.0 - 1e-9


def test_heatmap_counts_visits_and_dwell(demo_session, tmp_path):
    attempts = select_attempts(demo_session, answered_only=True)
    assert len(attempts) == 3

    grid = compute_heatmap(demo_session, attempts, cell_mm=2.0, margin_mm=15.0)

    assert grid.n_attempts == 3
    assert grid.visits.shape == grid.dwell_ms.shape == grid.samples.shape
    assert grid.visits.sum() > 0
    # A visit is an entry, so a cell can never have more visits than samples.
    assert (grid.visits <= grid.samples).all()
    assert grid.dwell_ms.sum() == pytest.approx(
        sum(s.frame_dt_us for a in attempts for s in a.samples
            if grid.x_edges[0] <= s.x_mm < grid.x_edges[-1] and grid.y_edges[0] <= s.y_mm < grid.y_edges[-1]) / 1000
    )

    png = plot_heatmap(grid, [bar_geometry(demo_session, a) for a in attempts], tmp_path / "heat.png")
    write_heatmap_csv(grid, tmp_path / "heat.csv")
    assert png.exists() and png.stat().st_size > 0
    with (tmp_path / "heat.csv").open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == grid.visits.size
    assert sum(int(r["visits"]) for r in rows) == int(grid.visits.sum())


def test_selection_defaults_to_main_block(demo_session):
    assert all(not a.is_practice for a in select_attempts(demo_session))
    assert [a.trial_index for a in select_attempts(demo_session, trial=2)] == [2, 2]


def test_animation_renders_gif(demo_session, tmp_path):
    attempt = demo_session.attempts[0]
    out = animate_attempt(demo_session, attempt, tmp_path / "trial.gif", fps=10, speed=4.0, max_frames=4)
    assert out.exists() and out.stat().st_size > 0
