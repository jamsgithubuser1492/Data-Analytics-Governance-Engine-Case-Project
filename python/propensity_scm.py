"""Propensity weighted synthetic control: choose control markets that match the test markets on sales history AND audience mix.

A standard synthetic control blends untreated markets so that their combined sales track the test markets before launch.
This version adds a second requirement: the blended audience mix (the share of each market's population in each of ten
propensity deciles) must also resemble the test markets. Two markets can have the same sales history and very different
people in them, and a control built only on history can then drift apart after launch for reasons unrelated to advertising.

Objective (weights are non negative and sum to one):
    mean(((y - Y w) / std(y)) ** 2)  +  phi * mean(((p - P w) / std(p)) ** 2)
Because the weights sum to one, an L1 penalty would be a constant, so sparsity is offered as an explicit top k step.

Everything is computed from the inputs. Match quality is reported as three numbers (share of pre period movement
explained, audience overlap, pre period error as a share of average sales) and compared with the policy thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import numpy as np
from scipy.optimize import minimize


class MatchError(ValueError):
    """Raised when markets cannot be matched (bad shapes, missing values, no donors)."""


@dataclass
class MatchResult:
    weights: np.ndarray
    donors: List[str]
    phi: float
    r2: float  # share of pre period sales movement explained by the blend
    relative_rmspe: float  # pre period prediction error as a share of the average pre period sales
    overlap: float  # 1 minus half the total absolute gap between the two audience mixes (1.0 is identical)
    baseline_r2: float  # same measures for a history only match (phi = 0), shown so the benefit is visible, never assumed
    baseline_relative_rmspe: float
    baseline_overlap: float
    passed: bool = False
    reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def table(self) -> List[tuple]:
        return sorted(((d, float(w)) for d, w in zip(self.donors, self.weights) if w > 1e-6), key=lambda x: -x[1])


def _std(x: np.ndarray) -> float:
    s = float(np.std(x))
    return s if s > 1e-12 else 1.0


def _solve(y: np.ndarray, Y: np.ndarray, p: np.ndarray, P: np.ndarray, phi: float) -> np.ndarray:
    n = Y.shape[1]
    ys, ps = _std(y), _std(p)

    def loss(w: np.ndarray) -> float:
        return float(np.mean(((y - Y @ w) / ys) ** 2) + phi * np.mean(((p - P @ w) / ps) ** 2))

    res = minimize(loss, np.full(n, 1.0 / n), method="SLSQP", bounds=[(0.0, 1.0)] * n,
                   constraints=({"type": "eq", "fun": lambda w: w.sum() - 1.0},), options={"maxiter": 600, "ftol": 1e-12})
    if not np.isfinite(res.fun):
        raise MatchError(f"The optimizer did not converge: {res.message}")
    w = np.clip(res.x, 0.0, None)
    return w / w.sum()


def _measures(y: np.ndarray, Y: np.ndarray, w: np.ndarray, p: np.ndarray, P: np.ndarray):
    pred = Y @ w
    sse = float(np.sum((y - pred) ** 2))
    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    rmspe = float(np.sqrt(np.mean((y - pred) ** 2)))
    rel = rmspe / abs(float(y.mean())) if y.mean() else float("inf")
    overlap = 1.0 - 0.5 * float(np.abs(p - P @ w).sum())
    return r2, rel, overlap


def match(y_pre: Sequence[float], donors_pre: np.ndarray, p_treatment: Sequence[float], p_donors: np.ndarray,
          donor_names: Optional[Sequence[str]] = None, *, phi: float = 0.25, top_k: Optional[int] = None,
          min_r2: float = 0.85, min_overlap: float = 0.90, max_rmspe_pct: float = 5.0) -> MatchResult:
    """Fit donor weights.

    ``donors_pre`` is (days, donors); ``p_donors`` is (deciles, donors); ``p_treatment`` is (deciles,).
    """
    y = np.asarray(y_pre, float)
    Y = np.asarray(donors_pre, float)
    p = np.asarray(p_treatment, float)
    P = np.asarray(p_donors, float)
    if Y.ndim != 2 or Y.shape[0] != y.shape[0]:
        raise MatchError("The donor table needs one row per pre period day, matching the test series.")
    if P.ndim != 2 or P.shape[0] != p.shape[0] or P.shape[1] != Y.shape[1]:
        raise MatchError("The audience mix table needs one row per decile and one column per donor market.")
    if Y.shape[1] < 1 or y.shape[0] < 7:
        raise MatchError("At least one donor market and 7 pre period days are needed.")
    if not (np.isfinite(y).all() and np.isfinite(Y).all() and np.isfinite(p).all() and np.isfinite(P).all()):
        raise MatchError("The data contains missing or non numeric values.")
    names = list(donor_names) if donor_names is not None else [f"Market {i + 1}" for i in range(Y.shape[1])]
    scale = np.where(Y.mean(axis=0) == 0, 1.0, Y.mean(axis=0))
    Ys, ysc = Y / scale, y / y.mean()  # each market is scaled by its own average so large markets do not dominate
    w_scaled = _solve(ysc, Ys, p, P, phi)
    w_base = _solve(ysc, Ys, p, P, 0.0)
    notes: List[str] = []
    if top_k is not None and 0 < top_k < Y.shape[1]:
        keep = np.argsort(-w_scaled)[:top_k]
        pruned = np.zeros_like(w_scaled)
        pruned[keep] = w_scaled[keep]
        w_scaled = pruned / pruned.sum()
        notes.append(f"Kept the {top_k} largest control markets and renormalized.")
    to_raw = lambda w: w * (y.mean() / scale)  # noqa: E731  weights that apply to the raw market series
    r2, rel, overlap = _measures(y, Y, to_raw(w_scaled), p, P)
    # audience overlap uses the share weights (they sum to one), not the volume weights
    overlap = 1.0 - 0.5 * float(np.abs(p - P @ w_scaled).sum())
    b_r2, b_rel, _ = _measures(y, Y, to_raw(w_base), p, P)
    b_overlap = 1.0 - 0.5 * float(np.abs(p - P @ w_base).sum())
    reasons: List[str] = []
    if not (r2 >= min_r2):
        reasons.append(f"the sales history match explains {r2:.0%} of the pre period movement, below the {min_r2:.0%} standard")
    if not (overlap >= min_overlap):
        reasons.append(f"the audience mix overlaps {overlap:.1%}, below the {min_overlap:.0%} standard")
    if not (rel * 100 <= max_rmspe_pct):
        reasons.append(f"the pre period error is {rel:.1%} of average sales, above the {max_rmspe_pct:g}% limit")
    return MatchResult(w_scaled, names, phi, float(r2), float(rel), float(overlap), float(b_r2), float(b_rel), float(b_overlap),
                       passed=not reasons, reasons=reasons, notes=notes)


def counterfactual(result: MatchResult, donors: np.ndarray, donors_pre: np.ndarray, y_pre: Sequence[float]) -> np.ndarray:
    """Synthetic sales series for any period (before or after launch) using the fitted weights."""
    D, Dp = np.asarray(donors, float), np.asarray(donors_pre, float)
    scale = np.where(Dp.mean(axis=0) == 0, 1.0, Dp.mean(axis=0))
    return (D / scale) @ result.weights * float(np.mean(y_pre))
