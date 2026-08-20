"""Psychometric-function fitting for the constant-stimuli bar-height task.

Standalone and pygame-free: takes saved trial CSVs (or synthetic data from
``simulate_ideal_observer``) and produces PSE, slope, lapse, and JND
estimates, plus a plot. Re-fittable later with different settings since it
only reads the logged CSV, not any in-memory experiment state.

JND is defined as (x75 - x25) / 2 on the fitted cumulative-Gaussian-with-lapse
curve; this definition is itself a parameter (``jnd_lower_pct``/``jnd_upper_pct``)
rather than a hard-coded 25/75 split.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    from scipy.optimize import minimize
    from scipy.stats import norm

    _HAVE_SCIPY = True
except ModuleNotFoundError:
    _HAVE_SCIPY = False

try:
    import psignifit

    _HAVE_PSIGNIFIT = True
except ModuleNotFoundError:
    _HAVE_PSIGNIFIT = False


@dataclass(frozen=True)
class PsychometricFit:
    levels: list[float]
    n_trials: list[int]
    n_comparison_taller: list[int]
    pse: float
    slope_sigma: float
    lapse_rate: float
    jnd: float
    jnd_lower_pct: float
    jnd_upper_pct: float
    backend: str

    def to_dict(self) -> dict:
        return {
            "levels": self.levels,
            "n_trials": self.n_trials,
            "n_comparison_taller": self.n_comparison_taller,
            "pse": self.pse,
            "slope_sigma": self.slope_sigma,
            "lapse_rate": self.lapse_rate,
            "jnd": self.jnd,
            "jnd_lower_pct": self.jnd_lower_pct,
            "jnd_upper_pct": self.jnd_upper_pct,
            "backend": self.backend,
        }


def _norm_cdf(x: np.ndarray | float) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x, dtype=float) / math.sqrt(2.0)))


def _norm_ppf(p: np.ndarray | float) -> np.ndarray:
    if _HAVE_SCIPY:
        return norm.ppf(p)
    # Peter Acklam's rational approximation for the standard normal inverse CDF.
    p = np.asarray(p, dtype=float)
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    p_low = 0.02425
    out = np.empty_like(p)
    low = p < p_low
    high = p > 1 - p_low
    mid = ~low & ~high

    q = np.sqrt(-2 * np.log(p[low]))
    out[low] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)

    q = p[mid] - 0.5
    r = q * q
    out[mid] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)

    q = np.sqrt(-2 * np.log(1 - p[high]))
    out[high] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    return out


def psychometric_curve(x: np.ndarray | float, pse: float, sigma: float, lapse: float) -> np.ndarray:
    return lapse / 2.0 + (1.0 - lapse) * _norm_cdf((np.asarray(x, dtype=float) - pse) / sigma)


def _neg_log_likelihood(params: np.ndarray, levels: np.ndarray, n_trials: np.ndarray, n_taller: np.ndarray) -> float:
    pse, log_sigma, lapse = params
    sigma = math.exp(log_sigma)
    lapse = min(max(lapse, 1e-6), 0.2)
    p = np.clip(psychometric_curve(levels, pse, sigma, lapse), 1e-9, 1 - 1e-9)
    ll = n_taller * np.log(p) + (n_trials - n_taller) * np.log(1 - p)
    return -float(np.sum(ll))


def _fit_scipy_mle(levels: list[float], n_trials: list[int], n_taller: list[int]) -> tuple[float, float, float]:
    levels_a = np.asarray(levels, dtype=float)
    n_trials_a = np.asarray(n_trials, dtype=float)
    n_taller_a = np.asarray(n_taller, dtype=float)
    span = max(levels_a) - min(levels_a) if len(levels_a) > 1 else 1.0
    x0 = np.array([0.0, math.log(span / 4.0 if span > 0 else 0.1), 0.02])
    result = minimize(
        _neg_log_likelihood,
        x0,
        args=(levels_a, n_trials_a, n_taller_a),
        method="Nelder-Mead",
    )
    pse, log_sigma, lapse = result.x
    sigma = math.exp(log_sigma)
    lapse = min(max(lapse, 0.0), 0.2)
    return float(pse), float(sigma), float(lapse)


def _fit_psignifit(levels: list[float], n_trials: list[int], n_taller: list[int]) -> tuple[float, float, float]:
    data = np.array([levels, n_taller, n_trials]).T
    result = psignifit.psignifit(data, sigmoid="norm", experiment_type="yes/no")
    pse = float(result.parameter_estimate["threshold"])
    sigma = float(result.parameter_estimate["width"]) / (norm.ppf(0.95) - norm.ppf(0.05)) if _HAVE_SCIPY else float(result.parameter_estimate["width"]) / 3.29
    lapse = float(result.parameter_estimate["lambda"])
    return pse, sigma, lapse


def fit_psychometric(
    levels: list[float],
    n_trials: list[int],
    n_comparison_taller: list[int],
    jnd_lower_pct: float = 0.25,
    jnd_upper_pct: float = 0.75,
    prefer_psignifit: bool = False,
) -> PsychometricFit:
    """Fit a cumulative-Gaussian-with-lapse psychometric function.

    Defaults to a scipy MLE fit (point estimate only, no credible intervals).
    Pass ``prefer_psignifit=True`` to use psignifit instead (Bayesian, gives
    credible intervals -- valuable at only ~10 trials/level -- but also warns
    on small per-level trial counts, which is noisy during quick testing).
    """
    if prefer_psignifit and _HAVE_PSIGNIFIT:
        pse, sigma, lapse = _fit_psignifit(levels, n_trials, n_comparison_taller)
        backend = "psignifit"
    elif _HAVE_SCIPY:
        pse, sigma, lapse = _fit_scipy_mle(levels, n_trials, n_comparison_taller)
        backend = "scipy_mle"
    else:
        raise ModuleNotFoundError("fit_psychometric requires scipy or psignifit to be installed")

    x_lower = pse + sigma * float(_norm_ppf(np.array([(jnd_lower_pct - lapse / 2) / (1 - lapse)]))[0])
    x_upper = pse + sigma * float(_norm_ppf(np.array([(jnd_upper_pct - lapse / 2) / (1 - lapse)]))[0])
    jnd = (x_upper - x_lower) / 2.0

    return PsychometricFit(
        levels=list(levels),
        n_trials=list(n_trials),
        n_comparison_taller=list(n_comparison_taller),
        pse=pse,
        slope_sigma=sigma,
        lapse_rate=lapse,
        jnd=jnd,
        jnd_lower_pct=jnd_lower_pct,
        jnd_upper_pct=jnd_upper_pct,
        backend=backend,
    )


def aggregate_by_level(
    level_pct: list[float],
    reference_side: list[str],
    response: list[str],
) -> tuple[list[float], list[int], list[int]]:
    """Collapse raw per-trial rows into (levels, n_trials, n_comparison_taller) per level."""
    counts: dict[float, list[int]] = {}
    for level, ref_side, resp in zip(level_pct, reference_side, response):
        comparison_side = "right" if ref_side == "left" else "left"
        bucket = counts.setdefault(round(level, 10), [0, 0])
        bucket[0] += 1
        if resp == comparison_side:
            bucket[1] += 1
    levels = sorted(counts)
    n_trials = [counts[level][0] for level in levels]
    n_taller = [counts[level][1] for level in levels]
    return levels, n_trials, n_taller


def load_session_csvs(paths: list[Path]) -> tuple[list[float], list[int], list[int]]:
    """Load one or more trial CSVs (main.py's data_logger schema) and aggregate by level.

    Only ``outcome == "answered"`` rows are used: the CSV also carries the
    trials that expired (``timeout``/``abandoned``), which have no response to
    score. Practice trials are excluded; catch trials are included since they
    are just extra reps at the extreme levels.
    """
    from experiment import data_logger  # local import: keeps this module pygame-free at import time

    level_pct: list[float] = []
    reference_side: list[str] = []
    response: list[str] = []
    for path in paths:
        for row in data_logger.load_trials(Path(path)):
            if row["is_practice"] or row["outcome"] != "answered":
                continue
            level_pct.append(row["level_pct"])
            reference_side.append(row["reference_side"])
            response.append(row["response"])
    return aggregate_by_level(level_pct, reference_side, response)


def simulate_ideal_observer(
    levels: list[float],
    trials_per_level: int,
    true_pse: float = 0.0,
    true_sigma: float = 0.1,
    true_lapse: float = 0.02,
    seed: int | None = None,
) -> tuple[list[float], list[int], list[int]]:
    """Generate synthetic responses from a known psychometric function (dry-run / testing)."""
    rng = np.random.default_rng(seed)
    n_trials = [trials_per_level for _ in levels]
    n_taller = []
    for level in levels:
        p = float(psychometric_curve(np.array([level]), true_pse, true_sigma, true_lapse)[0])
        n_taller.append(int(rng.binomial(trials_per_level, p)))
    return list(levels), n_trials, n_taller


def plot_psychometric(fit: PsychometricFit, save_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    save_path = Path(save_path)
    p_obs = [t / n if n else 0.0 for t, n in zip(fit.n_comparison_taller, fit.n_trials)]
    sizes = [20 + 8 * n for n in fit.n_trials]

    x_fit = np.linspace(min(fit.levels), max(fit.levels), 200)
    y_fit = psychometric_curve(x_fit, fit.pse, fit.slope_sigma, fit.lapse_rate)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(fit.levels, p_obs, s=sizes, color="tab:blue", zorder=3, label="observed")
    ax.plot(x_fit, y_fit, color="tab:orange", zorder=2, label="fitted")
    ax.axvline(fit.pse, color="gray", linestyle="--", linewidth=1, label=f"PSE={fit.pse:.3f}")
    ax.axvspan(fit.pse - fit.jnd, fit.pse + fit.jnd, color="tab:orange", alpha=0.1, label=f"JND={fit.jnd:.3f}")
    ax.set_xlabel("Level (signed % of base height)")
    ax.set_ylabel('P("comparison taller")')
    ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)

    save_path.with_suffix(".json").write_text(json.dumps(fit.to_dict(), indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit a psychometric function to constant-stimuli trial CSVs.")
    parser.add_argument("csv_paths", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("psychometric_fit.png"))
    parser.add_argument("--jnd-lower-pct", type=float, default=0.25)
    parser.add_argument("--jnd-upper-pct", type=float, default=0.75)
    parser.add_argument(
        "--psignifit", action="store_true", help="Use psignifit (Bayesian) instead of the default scipy MLE fit."
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    levels, n_trials, n_taller = load_session_csvs(args.csv_paths)
    fit = fit_psychometric(
        levels,
        n_trials,
        n_taller,
        jnd_lower_pct=args.jnd_lower_pct,
        jnd_upper_pct=args.jnd_upper_pct,
        prefer_psignifit=args.psignifit,
    )
    plot_psychometric(fit, args.out)
    print(f"backend={fit.backend} pse={fit.pse:.4f} slope_sigma={fit.slope_sigma:.4f} "
          f"lapse={fit.lapse_rate:.4f} jnd={fit.jnd:.4f}")
    print(f"saved {args.out} and {args.out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
