"""Propensity weighted synthetic control: weights, audience alignment, match quality verdicts."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import propensity_scm as pscm  # noqa: E402


def simple_case():
    y = np.array([100, 105, 110, 115, 120, 118, 122, 125.])
    Y = np.array([[95, 105], [100, 110], [105, 115], [110, 120], [115, 125], [113, 123], [117, 127], [120, 130.]])
    p = np.array([0.1, 0.2, 0.7])
    P = np.array([[0.1, 0.3], [0.2, 0.2], [0.7, 0.5]])
    return y, Y, p, P


def test_weights_are_a_convex_combination() -> None:
    r = pscm.match(*simple_case(), phi=0.25)
    assert np.isclose(r.weights.sum(), 1.0) and (r.weights >= 0).all()


def test_audience_overlap_is_one_minus_half_the_total_gap() -> None:
    y, Y, p, P = simple_case()
    r = pscm.match(y, Y, p, P, phi=0.25)
    assert r.overlap == pytest.approx(1 - 0.5 * np.abs(p - P @ r.weights).sum())


def test_audience_weight_improves_overlap_when_history_alone_is_ambiguous() -> None:
    rng = np.random.default_rng(3)
    t = np.arange(40)
    base = 1000 + 20 * np.sin(t / 5)
    Y = np.column_stack([base * (1 + 0.001 * rng.standard_normal(40)) for _ in range(4)])  # four donors with near identical history
    p = np.array([0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 0.2, 0.2])
    P = np.column_stack([p, np.roll(p, 3), np.roll(p, -3), np.full(10, 0.1)])
    r = pscm.match(base, Y, p, P, phi=2.0)
    assert r.overlap > r.baseline_overlap + 0.05  # matching on audience as well finds the donor with the right people
    assert r.weights[0] > 0.8


def test_verdict_uses_the_thresholds_and_explains_a_failure() -> None:
    y, Y, p, P = simple_case()
    ok = pscm.match(y, Y, p, P, phi=0.25, min_r2=0.5, min_overlap=0.5, max_rmspe_pct=50)
    assert ok.passed and not ok.reasons
    bad = pscm.match(y, Y, p, P, phi=0.25, min_overlap=0.9999)
    assert not bad.passed and any("audience mix" in r for r in bad.reasons)


def test_top_k_keeps_the_largest_markets_and_renormalizes() -> None:
    rng = np.random.default_rng(1)
    Y = rng.uniform(80, 120, (30, 6))
    y = Y[:, :3].mean(axis=1)
    p = np.full(10, 0.1)
    P = np.tile(p[:, None], (1, 6))
    r = pscm.match(y, Y, p, P, phi=0.0, top_k=2)
    assert (r.weights > 1e-9).sum() <= 2 and np.isclose(r.weights.sum(), 1.0)


def test_bad_inputs_are_rejected_in_plain_terms() -> None:
    y, Y, p, P = simple_case()
    with pytest.raises(pscm.MatchError):
        pscm.match(y[:5], Y, p, P)
    with pytest.raises(pscm.MatchError):
        pscm.match(y, Y, p, P[:, :1])
    Y2 = Y.copy()
    Y2[0, 0] = np.nan
    with pytest.raises(pscm.MatchError):
        pscm.match(y, Y2, p, P)


def test_counterfactual_projects_with_the_fitted_weights() -> None:
    y, Y, p, P = simple_case()
    r = pscm.match(y, Y, p, P)
    cf = pscm.counterfactual(r, Y, Y, y)
    assert cf.shape == y.shape and abs(cf.mean() - y.mean()) / y.mean() < 0.05
