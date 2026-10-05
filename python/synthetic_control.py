"""Synthetic control for geo experiments: build a weighted blend of untreated markets that mirrors the treated markets before launch.

Weights are non-negative and sum to one (a convex combination). Because the weights sum to one, an L1 penalty would be a
constant and do nothing, so sparsity is offered instead as an explicit "keep the top k donors and renormalize" step.
The fit check asks whether the pre-period prediction error is small compared with the level of the series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
from scipy.optimize import minimize

FIT_TOLERANCE = 0.05  # pre-period RMSPE must be under 5% of the pre-period mean


class SyntheticControlError(ValueError):
    """Raised when the inputs cannot be matched (shape problems, empty donor pool, optimizer failure)."""


@dataclass
class Fit:
    weights: np.ndarray
    donors: List[str]
    rmspe: float
    relative_rmspe: float
    fit_ok: bool
    pre_mean: float
    notes: List[str] = field(default_factory=list)

    def table(self) -> List[tuple]:
        return sorted(((d, float(w)) for d, w in zip(self.donors, self.weights) if w > 1e-6), key=lambda x: -x[1])


def _scale(y: np.ndarray, Y: np.ndarray, normalize: str):
    if normalize == "none":
        return y, Y, np.ones(Y.shape[1])
    if normalize == "mean":
        s = Y.mean(axis=0)
        s = np.where(s == 0, 1.0, s)
        return y / y.mean(), Y / s, s
    raise SyntheticControlError("normalize must be 'mean' or 'none'")


def fit_weights(y_pre: Sequence[float], donors_pre: np.ndarray, donor_names: Optional[Sequence[str]] = None, *, normalize: str = "mean",
                top_k: Optional[int] = None, tolerance: float = FIT_TOLERANCE) -> Fit:
    """Fit donor weights to the treated pre-period series.

    ``donors_pre`` has shape (days, donors). With ``normalize='mean'`` each donor is divided by its own mean first so large
    markets do not dominate; weights are then converted back so they apply to the raw donor series.
    """
    y = np.asarray(y_pre, dtype=float)
    Y = np.asarray(donors_pre, dtype=float)
    if Y.ndim != 2 or Y.shape[0] != y.shape[0]:
        raise SyntheticControlError("The donor table needs one row per pre-period day, matching the treated series.")
    if Y.shape[1] < 1:
        raise SyntheticControlError("At least one donor market is needed.")
    if y.shape[0] < 7:
        raise SyntheticControlError("At least 7 pre-period days are needed.")
    if not np.isfinite(y).all() or not np.isfinite(Y).all():
        raise SyntheticControlError("The data contains missing or non-numeric values.")
    names = list(donor_names) if donor_names is not None else [f"Donor {i + 1}" for i in range(Y.shape[1])]
    ys, Ys, scale = _scale(y, Y, normalize)
    n = Ys.shape[1]

    def loss(w: np.ndarray) -> float:
        return float(np.mean((ys - Ys @ w) ** 2))

    res = minimize(loss, np.full(n, 1.0 / n), method="SLSQP", bounds=[(0.0, 1.0)] * n,
                   constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},), options={"maxiter": 500, "ftol": 1e-12})
    if not res.success and not np.isfinite(res.fun):
        raise SyntheticControlError(f"The optimizer did not converge: {res.message}")
    w = np.clip(res.x, 0.0, None)
    w = w / w.sum()
    notes: List[str] = []
    if top_k is not None and 0 < top_k < n:
        keep = np.argsort(-w)[:top_k]
        pruned = np.zeros(n)
        pruned[keep] = w[keep]
        w = pruned / pruned.sum()
        notes.append(f"Kept the {top_k} largest donors and renormalized.")
    # on scaled donors the blend is (Y / s) @ w * mean(y), so the weight on each raw donor is w_j * mean(y) / s_j
    raw_weights = w * (y.mean() / scale) if normalize == "mean" else w
    pred = Y @ raw_weights if normalize == "mean" else Y @ w
    rmspe = float(np.sqrt(np.mean((y - pred) ** 2)))
    pre_mean = float(y.mean())
    rel = rmspe / abs(pre_mean) if pre_mean else float("inf")
    if normalize == "mean":
        notes.append("Donors were scaled by their own average, so weights describe shares of the blend rather than shares of each market's volume.")
    return Fit(w, names, rmspe, rel, bool(rel < tolerance), pre_mean, notes)


def predict(fit: Fit, donors: np.ndarray, y_pre: Sequence[float], donors_pre: np.ndarray, normalize: str = "mean") -> np.ndarray:
    """Synthetic series for any period (pre or post) using the fitted weights."""
    D, Dp = np.asarray(donors, float), np.asarray(donors_pre, float)
    if normalize == "mean":
        s = np.where(Dp.mean(axis=0) == 0, 1.0, Dp.mean(axis=0))
        return (D / s) @ fit.weights * float(np.mean(y_pre))
    return D @ fit.weights


def effect(actual_post: Sequence[float], synthetic_post: Sequence[float]) -> dict:
    """Treatment effect: actual minus synthetic, day by day and in total."""
    a, s = np.asarray(actual_post, float), np.asarray(synthetic_post, float)
    gap = a - s
    return {"daily_gap": gap, "total_gap": float(gap.sum()), "relative_gap": float(gap.sum() / s.sum()) if s.sum() else float("nan")}
