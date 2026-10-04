"""Synthetic control / time series causal impact estimation for geo holdouts.

For every campaign the treatment geo is regressed on the control geo over the
30 day pre-period (OLS). The fitted relationship predicts the counterfactual
treatment series during the 60 day treatment period; the gap between actual and
counterfactual is the causal estimate.

Data note: the synthetic generator produces a noise free pre-period (control
equals treatment exactly), so residual variance is zero. A Poisson noise floor
(variance = mean daily conversions) is applied so intervals stay honest, and the
result is flagged with ``noise_floor_applied``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_CSV = ROOT / "data" / "RAW_HOLDOUT_DATA.csv"
PRE_PERIOD_DAYS = 30
Z_95 = 1.959964
GEO_SAMPLE_FRACTION = 0.40


@dataclass
class CausalResult:
    """Causal impact estimate for one campaign (units: conversions in the test geo)."""
    campaign_id: str
    pre_period_days: int
    post_period_days: int
    actual_conversions: float
    counterfactual_conversions: float
    point_estimate: float
    ci_lower: float
    ci_upper: float
    relative_lift_pct: float
    relative_lift_ci_lower_pct: float
    relative_lift_ci_upper_pct: float
    parallel_trend_p_value: float
    pre_period_r2: float
    cumulative_se: float
    mde_relative_pct: float
    control_drift_pct: float
    noise_floor_applied: bool
    significant: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def load_holdout(path: "Path | pd.DataFrame" = HOLDOUT_CSV) -> pd.DataFrame:
    """Load the raw holdout CSV (or accept a DataFrame) with parsed dates."""
    if isinstance(path, pd.DataFrame):
        df = path.copy()
        df["date"] = pd.to_datetime(df["date"])
        return df
    if not Path(path).exists():
        raise FileNotFoundError(f"Holdout file not found: {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "campaign_id", "group_type", "conversions"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Holdout data missing columns: {sorted(missing)}")
    return df


def _parallel_trend_p_value(diff: np.ndarray) -> float:
    """p-value for a non-zero linear trend in (treatment - control) over the pre-period.

    p > 0.05 means no evidence of diverging trends (parallel trends plausible).
    A constant difference series (zero variance) has no trend, so p = 1.0.
    """
    if len(diff) < 3 or np.allclose(diff, diff[0]):
        return 1.0
    slope = stats.linregress(np.arange(len(diff)), diff)
    return 1.0 if np.isnan(slope.pvalue) else float(slope.pvalue)


def estimate_campaign(df: pd.DataFrame, campaign_id: str,
                      pre_days: int = PRE_PERIOD_DAYS) -> CausalResult:
    """Run the synthetic control estimate for a single campaign."""
    sub = df[df["campaign_id"] == campaign_id]
    wide = (sub.pivot_table(index="date", columns="group_type", values="conversions", aggfunc="sum")
            .sort_index())
    if not {"control", "treatment"} <= set(wide.columns):
        raise ValueError(f"{campaign_id}: both control and treatment groups are required")
    if len(wide) <= pre_days + 2:
        raise ValueError(f"{campaign_id}: need more than {pre_days + 2} days, got {len(wide)}")

    pre, post = wide.iloc[:pre_days], wide.iloc[pre_days:]
    x_pre = sm.add_constant(pre["control"].astype(float), has_constant="add")
    fit = sm.OLS(pre["treatment"].astype(float), x_pre).fit()

    x_post = sm.add_constant(post["control"].astype(float), has_constant="add")
    pred = fit.get_prediction(x_post)
    counterfactual = np.asarray(pred.predicted_mean)

    sigma2 = float(fit.scale)
    floor = float(pre["treatment"].mean())  # Poisson noise floor
    floor_applied = sigma2 < floor * 0.05
    sigma2 = max(sigma2, floor)
    se_day = np.sqrt(np.asarray(pred.se_mean) ** 2 + sigma2)
    cum_se = float(np.sqrt(np.sum(se_day ** 2)))

    actual = float(post["treatment"].sum())
    cf = float(counterfactual.sum())
    point = actual - cf
    lo, hi = point - Z_95 * cum_se, point + Z_95 * cum_se
    lift = lambda a, b: (a / b - 1.0) * 100.0 if b > 0 else float("nan")  # noqa: E731
    mde = Z_95 + 0.8416  # 80% power multiplier

    control_drift = (post["control"].mean() / pre["control"].mean() - 1.0) * 100.0
    return CausalResult(
        campaign_id=campaign_id, pre_period_days=len(pre), post_period_days=len(post),
        actual_conversions=actual, counterfactual_conversions=cf,
        point_estimate=point, ci_lower=lo, ci_upper=hi,
        relative_lift_pct=lift(actual, cf),
        relative_lift_ci_lower_pct=lift(actual, cf + Z_95 * cum_se),
        relative_lift_ci_upper_pct=lift(actual, max(cf - Z_95 * cum_se, 1e-9)),
        parallel_trend_p_value=_parallel_trend_p_value((pre["treatment"] - pre["control"]).to_numpy(float)),
        pre_period_r2=float(fit.rsquared) if not np.isnan(fit.rsquared) else 1.0,
        cumulative_se=cum_se, mde_relative_pct=mde * cum_se / cf * 100.0 if cf > 0 else float("nan"),
        control_drift_pct=float(control_drift), noise_floor_applied=bool(floor_applied),
        significant=bool(lo > 0 or hi < 0),
    )


def run_all(path: "Path | pd.DataFrame" = HOLDOUT_CSV, pre_days: int = PRE_PERIOD_DAYS) -> pd.DataFrame:
    """Estimate every campaign in the holdout file and return a results table."""
    df = load_holdout(path)
    rows: List[Dict[str, object]] = [estimate_campaign(df, c, pre_days).to_dict()
                                     for c in sorted(df["campaign_id"].unique())]
    return pd.DataFrame(rows)


def main(path: Optional[Path] = None) -> None:
    """Print the causal impact table."""
    res = run_all(path or HOLDOUT_CSV)
    cols = ["campaign_id", "point_estimate", "ci_lower", "ci_upper", "relative_lift_pct",
            "parallel_trend_p_value", "significant"]
    print(res[cols].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
