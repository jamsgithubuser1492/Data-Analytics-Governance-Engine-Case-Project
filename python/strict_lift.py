"""Strict lift iROAS: incremental return from the causal estimate only.

The spec view ("Reported by spec") treats ALL treatment geo revenue as incremental.
Strict lift counts only the gap between actual and the synthetic control
counterfactual, projected to the full population (divided by the geo sample
fraction). Both views are always computed; settings choose the headline.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd

from config import HEADLINE_STRICT, PolicySettings


def strict_lift_row(recon_row: pd.Series, causal_row: pd.Series, settings: PolicySettings,
                    test_period_spend: Optional[float] = None) -> Dict[str, float]:
    """Return strict incremental conversions, revenue and iROAS (point and 95% CI).

    Incrementality is only measured during the treatment period, so the spend in
    the denominator is the TEST PERIOD spend (falls back to total spend if unknown).
    """
    nan = float("nan")
    spend = float(test_period_spend) if test_period_spend is not None else float(recon_row["total_spend"])
    hold_conv = recon_row["total_holdout_conversions"]
    hold_rev = recon_row["total_holdout_revenue"]
    aov = float(hold_rev) / float(hold_conv) if pd.notna(hold_conv) and float(hold_conv) > 0 else settings.avg_order_value
    f = settings.geo_sample_fraction
    out = {}
    for key, col in (("point", "point_estimate"), ("lower", "ci_lower"), ("upper", "ci_upper")):
        conv = float(causal_row[col]) / f
        rev = conv * aov
        out[f"strict_incremental_conversions_{key}"] = conv
        out[f"strict_incremental_revenue_{key}"] = rev
        out[f"strict_iroas_{key}"] = rev / spend if spend > 0 else nan
    return out


def headline_iroas(spec_iroas: float, strict_iroas: float, settings: PolicySettings) -> float:
    """Pick the headline iROAS according to the policy setting."""
    value = strict_iroas if settings.headline_metric == HEADLINE_STRICT else spec_iroas
    return float("nan") if value is None else float(value)


def divergence_warning(spec_iroas: float, strict_iroas: float, settings: PolicySettings) -> bool:
    """True when the spec view overstates the strict view by more than the policy ratio."""
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (spec_iroas, strict_iroas)):
        return False
    if strict_iroas <= 0:
        return spec_iroas > 0
    return spec_iroas / strict_iroas > settings.spec_vs_strict_warning_ratio
