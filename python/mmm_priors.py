"""Turn geo experiment results into informative priors for a media mix model, and reference transforms.

A test result with a standard error becomes a log normal prior for the channel's efficiency parameter, so the model starts from
causal evidence instead of correlation alone. Only the strict lift basis has an interval, so only it can yield a prior.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

Z95 = 1.959964


def se_from_interval(lower: float, upper: float, z: float = Z95) -> float:
    """Standard error implied by a symmetric confidence interval."""
    if lower is None or upper is None or not (math.isfinite(lower) and math.isfinite(upper)) or upper < lower:
        raise ValueError("A valid interval is needed.")
    return (upper - lower) / (2 * z)


def lognormal_prior(mean: float, se: float) -> Dict[str, float]:
    """Log normal parameters whose mean equals ``mean`` and whose standard deviation equals ``se``."""
    if not (mean > 0 and se > 0):
        raise ValueError("A log normal prior needs a positive mean and a positive standard error.")
    sigma2 = math.log(1 + (se / mean) ** 2)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - 0.5 * sigma2
    return {"mu": mu, "sigma": sigma}


def priors_table(ch: pd.DataFrame) -> pd.DataFrame:
    """One row per channel with a usable interval. Channels without an interval or with a non-positive return are listed with a reason."""
    rows: List[Dict[str, Any]] = []
    for r in ch.itertuples():
        base = {"channel": r.channel, "proven": r.proven, "lower": getattr(r, "lower", np.nan), "upper": getattr(r, "upper", np.nan)}
        if pd.isna(base["lower"]) or pd.isna(base["upper"]):
            rows.append({**base, "se": np.nan, "mu": np.nan, "sigma": np.nan, "usable": False, "reason": "No confidence interval on this counting basis. Use the strict lift basis."})
        elif not (r.proven and r.proven > 0):
            rows.append({**base, "se": np.nan, "mu": np.nan, "sigma": np.nan, "usable": False, "reason": "The proven return is not positive, so a log normal prior does not apply."})
        else:
            se = se_from_interval(base["lower"], base["upper"])
            p = lognormal_prior(float(r.proven), se)
            rows.append({**base, "se": se, **p, "usable": True, "reason": ""})
    return pd.DataFrame(rows)


def pymc_snippet(table: pd.DataFrame) -> str:
    """Ready to adapt PyMC code with the calibrated priors filled in. PyMC is not required to run this app."""
    use = table[table["usable"]]
    lines = ["import pymc as pm", "", "with pm.Model() as mmm_model:",
             "    # Informative priors from geo holdout results (strict lift basis, 95% interval)"]
    for r in use.itertuples():
        key = "".join(ch if ch.isalnum() else "_" for ch in r.channel.lower()).strip("_")
        lines.append(f"    beta_{key} = pm.LogNormal(\"beta_{key}\", mu={r.mu:.4f}, sigma={r.sigma:.4f})  # proven {r.proven:.2f}x, standard error {r.se:.3f}")
    lines += ["    # Channels without a test result keep a weak prior", "    beta_untested = pm.HalfNormal(\"beta_untested\", sigma=1.0)",
              "    # Add adstock (carry over) and saturation per channel, then the likelihood, as in your MMM framework."]
    return "\n".join(lines)


def geometric_adstock(spend: np.ndarray, decay: float, lags: int = 8) -> np.ndarray:
    """Carry over of spend: a_t = sum over l of decay^l * x_(t-l)."""
    if not 0 < decay < 1:
        raise ValueError("decay must be between 0 and 1")
    x = np.asarray(spend, float)
    out = np.zeros_like(x)
    for l in range(min(lags, len(x) - 1) + 1):
        out[l:] += (decay ** l) * x[: len(x) - l]
    return out


def hill(a: np.ndarray, half_saturation: float, shape: float) -> np.ndarray:
    """Saturation: a^g / (a^g + K^g). Returns a value between 0 and 1."""
    a = np.asarray(a, float)
    if half_saturation <= 0 or shape <= 0:
        raise ValueError("half_saturation and shape must be positive")
    return a ** shape / (a ** shape + half_saturation ** shape)
