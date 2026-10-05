"""Synthetic control solver and MMM prior calculator."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import mmm_priors as mp  # noqa: E402
import synthetic_control as sc  # noqa: E402


def make(seed=1, days=60, donors=8):
    rng = np.random.default_rng(seed)
    t = np.arange(days)
    base = 100 + 10 * np.sin(t / 6)
    D = np.column_stack([base * rng.uniform(0.5, 3.0) * (1 + 0.01 * rng.standard_normal(days)) + rng.uniform(-5, 5) for _ in range(donors)])
    return t, base, D


def test_known_blend_is_recovered_and_weights_are_convex() -> None:
    rng = np.random.default_rng(0)
    D = rng.uniform(50, 150, size=(60, 6)) + np.cumsum(rng.standard_normal((60, 6)), axis=0)
    true = np.array([0.5, 0.3, 0.2, 0, 0, 0])
    y = D @ true
    f = sc.fit_weights(y, D, normalize="none")
    assert f.weights.sum() == pytest.approx(1.0) and (f.weights >= -1e-9).all()
    assert np.allclose(f.weights, true, atol=0.02) and f.fit_ok and f.relative_rmspe < 0.01
    assert [d for d, _ in f.table()][:3] == ["Donor 1", "Donor 2", "Donor 3"]


def test_mean_scaling_lets_small_and_large_markets_blend() -> None:
    t, base, D = make()
    f = sc.fit_weights(base, D, normalize="mean")
    assert f.fit_ok and f.weights.sum() == pytest.approx(1.0)
    synth = sc.predict(f, D, base, D, "mean")
    assert np.sqrt(np.mean((synth - base) ** 2)) / base.mean() < 0.05


def test_poor_donors_fail_the_fit_check() -> None:
    t = np.arange(60)
    y = 100 + 30 * np.sin(t / 4)
    D = np.column_stack([np.full(60, 300.0), 500 + 20 * np.cos(t / 3), np.linspace(10, 900, 60)])
    f = sc.fit_weights(y, D, normalize="none")
    assert not f.fit_ok and f.relative_rmspe >= sc.FIT_TOLERANCE


def test_top_k_pruning_renormalizes() -> None:
    t, base, D = make(donors=10)
    f = sc.fit_weights(base, D, top_k=3)
    assert (f.weights > 1e-9).sum() <= 3 and f.weights.sum() == pytest.approx(1.0) and any("Kept the 3" in n for n in f.notes)


@pytest.mark.parametrize("y,D", [(np.arange(5.0), np.ones((5, 2))), (np.arange(10.0), np.ones((9, 2))), (np.arange(10.0), np.ones((10, 0))), (np.array([1.0] * 9 + [np.nan]), np.ones((10, 2)))])
def test_bad_inputs_raise_plain_errors(y, D) -> None:
    with pytest.raises(sc.SyntheticControlError):
        sc.fit_weights(y, D)


def test_effect_is_actual_minus_synthetic() -> None:
    e = sc.effect([12, 12, 12], [10, 10, 10])
    assert e["total_gap"] == 6 and e["relative_gap"] == pytest.approx(0.2)


def test_lognormal_prior_recovers_the_mean_and_standard_error() -> None:
    p = mp.lognormal_prior(2.15, 0.35)
    x = np.random.default_rng(3).lognormal(p["mu"], p["sigma"], 400000)
    assert x.mean() == pytest.approx(2.15, rel=0.01) and x.std() == pytest.approx(0.35, rel=0.03)
    assert mp.se_from_interval(1.0, 2.0) == pytest.approx(1.0 / (2 * 1.959964))
    with pytest.raises(ValueError):
        mp.lognormal_prior(-1, 0.3)
    with pytest.raises(ValueError):
        mp.se_from_interval(2.0, 1.0)


def test_priors_table_only_uses_channels_with_intervals_and_explains_the_rest() -> None:
    ch = pd.DataFrame({"channel": ["Google Ads", "Meta Ads", "Netflix Ads"], "proven": [1.0, 0.57, 0.02], "lower": [0.8, 0.4, np.nan], "upper": [1.2, 0.75, np.nan]})
    t = mp.priors_table(ch)
    assert t.set_index("channel")["usable"].to_dict() == {"Google Ads": True, "Meta Ads": True, "Netflix Ads": False}
    assert "No confidence interval" in t.set_index("channel").loc["Netflix Ads", "reason"]
    code = mp.pymc_snippet(t)
    assert "beta_google_ads = pm.LogNormal" in code and "netflix" not in code
    spec = ch.assign(lower=np.nan, upper=np.nan)
    assert not mp.priors_table(spec)["usable"].any()


def test_adstock_and_hill_reference_transforms() -> None:
    a = mp.geometric_adstock(np.array([100.0, 0, 0, 0]), 0.5)
    assert list(a) == [100.0, 50.0, 25.0, 12.5]
    h = mp.hill(np.array([0.0, 1.0, 100.0]), 1.0, 2.0)
    assert h[0] == 0 and h[1] == pytest.approx(0.5) and h[2] > 0.99
    with pytest.raises(ValueError):
        mp.geometric_adstock(np.ones(3), 1.5)
