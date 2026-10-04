"""Pure data preparation for the executive dashboard (no Streamlit): easy to unit test.

Everything here follows the active counting basis ("Strict lift" or "Reported by spec") and never invents
numbers: every figure is derived from the stored run tables and the audit report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

CI_LEVEL = "95%"  # the causal estimator reports 95% intervals; the dashboard says so explicitly
AT_BREAKEVEN_BAND = 0.05
SCALE_VS_PORTFOLIO = 1.5  # a channel is a scale leader when it returns 1.5x the portfolio average


def campaign_frame(recon: pd.DataFrame, camp: pd.DataFrame, is_strict: bool, breakeven: float, margin: Optional[float]) -> pd.DataFrame:
    """One row per campaign with claimed, model and proven returns, the interval and the money gaps."""
    r = recon.set_index("campaign_id")
    c = camp.set_index("campaign_id")
    d = pd.DataFrame(index=c.index)
    d["channel"] = c["channel"]
    d["tier"], d["trust_score"] = c["tier"], c["trust_score"]
    d["claimed_roas"] = r["reported_roas"].reindex(d.index)
    d["model_roas"] = r["mta_roas"].reindex(d.index)
    d["platform_revenue"] = r["total_platform_revenue"].reindex(d.index)
    d["spec_iroas"], d["strict_iroas"] = c["spec_iroas"], c["strict_iroas"]
    if is_strict:
        d["spend"] = c["test_period_spend"]
        d["proven_revenue"] = c["strict_incremental_revenue"]
        d["proven"] = c["strict_iroas"]
        d["lower"], d["upper"] = c["strict_iroas_lower"], c["strict_iroas_upper"]
        # platform revenue claimed over the same test period is not stored separately, so scale by the spend share
        full_spend = r["total_spend"].reindex(d.index)
        d["platform_revenue"] = d["platform_revenue"] * (d["spend"] / full_spend.where(full_spend > 0))
    else:
        d["spend"] = r["total_spend"].reindex(d.index)
        d["proven_revenue"] = r["total_holdout_revenue"].reindex(d.index)
        d["proven"] = c["spec_iroas"]
        d["lower"], d["upper"] = np.nan, np.nan
    keep = margin if margin else 1.0
    d["unearned"] = (d["spend"] - d["proven_revenue"] * keep).clip(lower=0)  # spend not earned back
    d["overclaim_revenue"] = (d["platform_revenue"] - d["proven_revenue"]).clip(lower=0)
    d["overclaim_ratio"] = d["claimed_roas"] / d["proven"].where(d["proven"] > 0)
    d["net_at_lower"] = d["spend"] * (d["lower"] * keep - 1) if is_strict else np.nan
    d["net_at_upper"] = d["spend"] * (d["upper"] * keep - 1) if is_strict else np.nan
    d["net_at_point"] = d["spend"] * (d["proven"] * keep - 1)
    return d.reset_index()


def channel_frame(cd: pd.DataFrame, audit: pd.DataFrame, is_strict: bool, breakeven: float) -> pd.DataFrame:
    """Channel level view. Interval bounds are summed across campaigns (a conservative, wider interval)."""
    g = cd.groupby("channel")
    ch = pd.DataFrame({
        "spend": g["spend"].sum(),
        "proven_revenue": g["proven_revenue"].sum(min_count=1),
        "platform_revenue": g["platform_revenue"].sum(min_count=1),
        "unearned": g["unearned"].sum(),
        "overclaim_revenue": g["overclaim_revenue"].sum(),
        "trust_score": g["trust_score"].mean(),
    })
    a = audit.set_index("channel")
    ch["claimed"] = a["platform_roas"].reindex(ch.index)
    ch["model"] = a["mta_roas"].reindex(ch.index)
    ch["total_spend"] = a["total_spend"].reindex(ch.index)
    if is_strict:
        ch["proven"] = ch["proven_revenue"] / ch["spend"].where(ch["spend"] > 0)
        lo_rev = (cd["lower"] * cd["spend"]).groupby(cd["channel"]).sum(min_count=1)
        hi_rev = (cd["upper"] * cd["spend"]).groupby(cd["channel"]).sum(min_count=1)
        ch["lower"], ch["upper"] = lo_rev / ch["spend"], hi_rev / ch["spend"]
    else:
        ch["proven"] = a["incremental_roas"].reindex(ch.index)
        ch["lower"], ch["upper"] = np.nan, np.nan
    order = {"NOT_DECISION_GRADE": 0, "DIRECTIONAL": 1, "VERIFIED": 2}
    ch["tier"] = g["tier"].agg(lambda s: min(s, key=lambda t: order.get(t, 0)))  # weakest tier governs the channel
    ch = ch.reset_index()
    return ch


def portfolio_totals(cd: pd.DataFrame, ch: pd.DataFrame, is_strict: bool) -> Dict[str, Any]:
    spend = float(cd["spend"].sum())
    proven_rev = float(cd["proven_revenue"].sum())
    out = {"spend": spend, "proven_revenue": proven_rev, "platform_revenue": float(cd["platform_revenue"].sum()),
           "overclaim_revenue": float(cd["overclaim_revenue"].sum()), "unearned": float(cd["unearned"].sum()),
           "proven": proven_rev / spend if spend else float("nan"), "lower": float("nan"), "upper": float("nan")}
    if is_strict and spend:
        out["lower"] = float((cd["lower"] * cd["spend"]).sum() / spend)
        out["upper"] = float((cd["upper"] * cd["spend"]).sum() / spend)
    return out


def classify(proven: Optional[float], breakeven: float) -> str:
    if proven is None or pd.isna(proven):
        return "unmeasured"
    if proven >= breakeven * (1 + AT_BREAKEVEN_BAND):
        return "above"
    return "at" if proven >= breakeven * (1 - AT_BREAKEVEN_BAND) else "below"


def portfolio_action(proven: float, tier: str, breakeven: float, blended: float) -> str:
    """Scale, Maintain, Restructure or Cut for a channel (always shown with its text label)."""
    if pd.isna(proven):
        return "Restructure"
    if tier == "NOT_DECISION_GRADE":
        return "Restructure"
    state = classify(proven, breakeven)
    if state == "below":
        return "Cut"
    if state == "above" and tier == "VERIFIED" and (pd.isna(blended) or proven >= SCALE_VS_PORTFOLIO * blended):
        return "Scale"
    return "Maintain"


def with_actions(ch: pd.DataFrame, breakeven: float, blended: float) -> pd.DataFrame:
    ch = ch.copy()
    ch["action"] = [portfolio_action(p, t, breakeven, blended) for p, t in zip(ch["proven"], ch["tier"])]
    tot_spend, tot_rev = ch["spend"].sum(), ch["proven_revenue"].sum()
    ch["spend_share"] = ch["spend"] / tot_spend if tot_spend else np.nan
    ch["revenue_share"] = ch["proven_revenue"] / tot_rev if tot_rev else np.nan
    return ch


def reallocation(ch: pd.DataFrame, shift_from: str = "Netflix Ads", to: Tuple[str, str] = ("Google Ads", "Meta Ads"),
                 shift: Optional[float] = None, google_pct: float = 50.0) -> Optional[Dict[str, float]]:
    """What-if: move spend out of one channel into two others at their proven returns (average returns, no saturation)."""
    c = ch.set_index("channel")
    if shift_from not in c.index or any(t not in c.index for t in to):
        return None
    vals = c.loc[[shift_from, *to], "proven"]
    if vals.isna().any():
        return None
    spend = float(c.loc[shift_from, "spend"])
    amount = spend if shift is None else min(shift, spend)
    gross = amount * google_pct / 100 * float(c.loc[to[0], "proven"]) + amount * (100 - google_pct) / 100 * float(c.loc[to[1], "proven"])
    lost = float(c.loc[shift_from, "proven_revenue"]) * (amount / spend) if spend else 0.0
    return {"amount": amount, "gross": gross, "lost": lost, "net": gross - lost, "spend": spend,
            "from_iroas": float(c.loc[shift_from, "proven"]), "a_iroas": float(c.loc[to[0], "proven"]), "b_iroas": float(c.loc[to[1], "proven"])}


def recommended_reallocation(ch: pd.DataFrame, shift_from: str = "Netflix Ads") -> Optional[Dict[str, Any]]:
    """The what-if worth recommending: only when the source channel is a Cut and money goes to channels that are not Cuts."""
    cut = set(ch[ch["action"] == "Cut"]["channel"])
    if shift_from not in cut:
        return None
    ok = [c for c in ("Google Ads", "Meta Ads") if c in set(ch["channel"]) and c not in cut]
    if len(ok) == 2:
        pct, dest = 50.0, "Google and Meta"
    elif ok == ["Google Ads"]:
        pct, dest = 100.0, "Google"
    elif ok == ["Meta Ads"]:
        pct, dest = 0.0, "Meta"
    else:
        return None
    r = reallocation(ch, shift_from, google_pct=pct)
    return None if r is None else {**r, "dest": dest, "google_pct": pct}


def headroom(ch: pd.DataFrame, days: int, uplift: float = 0.25) -> Dict[str, Any]:
    """Added monthly spend if scale leaders get +25% (the Scale agent rule), with the expected revenue at the interval bounds."""
    leaders = ch[ch["action"] == "Scale"]
    months = max(days / 30.0, 1e-9)
    add = float((leaders["spend"] * uplift).sum() / months) if len(leaders) else 0.0
    rev = float((leaders["spend"] * uplift * leaders["proven"]).sum() / months) if len(leaders) else 0.0
    lo = float((leaders["spend"] * uplift * leaders["lower"]).sum() / months) if len(leaders) and leaders["lower"].notna().all() else float("nan")
    hi = float((leaders["spend"] * uplift * leaders["upper"]).sum() / months) if len(leaders) and leaders["upper"].notna().all() else float("nan")
    return {"channels": leaders["channel"].tolist(), "added_monthly_spend": add, "expected_monthly_revenue": rev, "rev_low": lo, "rev_high": hi}


def waterfall_steps(totals: Dict[str, Any]) -> List[Tuple[str, float, str]]:
    """(label, value, kind) for the Platform claim to Proven reality waterfall."""
    return [("Claimed by platforms", totals["platform_revenue"], "total"),
            ("Over-claim (not caused by ads)", -totals["overclaim_revenue"], "delta"),
            ("Proven by the test", totals["proven_revenue"], "total")]


def divergence(cd: pd.DataFrame, threshold: float = 0.15) -> pd.DataFrame:
    """Campaigns where the spec view exceeds the strict view by more than the threshold (FR-GT02)."""
    d = cd.dropna(subset=["spec_iroas", "strict_iroas"]).copy()
    base = d["strict_iroas"].where(d["strict_iroas"] > 0)
    d["excess"] = (d["spec_iroas"] - d["strict_iroas"]) / base
    d.loc[(d["strict_iroas"] <= 0) & (d["spec_iroas"] > 0), "excess"] = np.inf
    return d[d["excess"] > threshold]


def best_worst_case(row: pd.Series, margin: Optional[float], breakeven: float) -> Optional[str]:
    """Plain sentence stating the outcome at both ends of the interval (strict basis only)."""
    if any(pd.isna(row.get(k)) for k in ("lower", "upper", "spend")):
        return None
    lo, hi = row["net_at_lower"], row["net_at_upper"]
    what = "net profit" if margin else "net revenue after ad spend"
    f = lambda v: ("-" if v < 0 else "") + f"${abs(v):,.0f}"  # noqa: E731
    return (f"At the lower bound ({row['lower']:.2f}x) this campaign generates {f(lo)} {what}. "
            f"At the upper bound ({row['upper']:.2f}x) it generates {f(hi)}.")


def rolling_with_band(rolling: pd.DataFrame, window: int = 14, z: float = 1.645) -> pd.DataFrame:
    """Channel level rolling return plus a descriptive envelope of recent day to day variation.

    The envelope is NOT a statistical confidence interval; the chart says so. It shows how far the 7 day figure
    has typically wandered in the trailing ``window`` days, so executives do not over-read a single day.
    """
    ch = rolling.groupby(["date", "channel"], as_index=False)[["rolling_7d_incremental_revenue", "rolling_7d_covered_spend"]].sum()
    ch["iroas"] = ch["rolling_7d_incremental_revenue"] / ch["rolling_7d_covered_spend"].where(ch["rolling_7d_covered_spend"] > 0)
    ch = ch.sort_values(["channel", "date"])
    sd = ch.groupby("channel")["iroas"].transform(lambda s: s.rolling(window, min_periods=5).std())
    ch["band_low"], ch["band_high"] = ch["iroas"] - z * sd, ch["iroas"] + z * sd
    return ch


# ------------------------------------------------------------------------------ gating and rules in words
def gate(tier: str) -> Dict[str, Any]:
    """What an executive is allowed to do at this trust tier (REQ-02, REQ-03, FR-GT01)."""
    if tier == "VERIFIED":
        return {"label": "Verified", "can_approve": True, "can_execute": True, "message": "Full actionability: one click execution is enabled."}
    if tier == "DIRECTIONAL":
        return {"label": "Directional", "can_approve": True, "can_execute": False,
                "message": "Advisory only: automated execution is off. Review manually before moving money."}
    return {"label": "Not decision grade", "can_approve": False, "can_execute": False,
            "message": "Blocked: financial actions are locked until the data is fixed."}


METRIC_WORDS = {
    "reported_roas": "claimed return", "mta_roas": "attribution model return", "iroas": "proven return", "spec_iroas": "proven return (spec basis)",
    "strict_iroas": "proven return (strict lift)", "inflation_ratio": "over-claim multiple", "trust_score": "trust score",
    "total_spend": "spend", "test_period_spend": "test period spend", "tier": "trust level", "has_holdout_coverage": "holdout coverage",
    "margin": "margin", "breakeven_iroas": "breakeven return", "profit_per_dollar": "profit per $1",
}
OPS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below", "==": "equal to", "in": "one of"}


def rule_in_words(definition: Dict[str, Any]) -> str:
    """Readable trigger text from an agent definition, for example 'claimed return at or above 1.5x and proven return below 1.0x'."""
    trig = definition.get("trigger") or {}
    mode, conds = ("any", trig["any"]) if trig.get("any") and not trig.get("all") else ("all", trig.get("all", []))
    parts = []
    for c in conds:
        name = METRIC_WORDS.get(c["metric"], c["metric"].replace("_", " "))
        v = c["value"]
        val = " and ".join(f"{x:g}" for x in v) if isinstance(v, (list, tuple)) and c["op"] == "between" else (
            ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else (f"{v:g}" if isinstance(v, (int, float)) else str(v)))
        op = "between" if c["op"] == "between" else OPS.get(c["op"], c["op"])
        parts.append(f"{name} {op} {val}")
    joiner = " and " if mode == "all" else " or "
    return joiner.join(parts) or "no conditions"


@dataclass
class Evidence:
    """Source and confidence details for one flagged campaign."""
    campaign_id: str
    trust_score: float
    tier: str
    checks: List[Dict[str, Any]]
    interval: Optional[Tuple[float, float]]


def evidence_for(campaign_id: str, report_campaigns: List[Dict[str, Any]]) -> Optional[Evidence]:
    for c in report_campaigns:
        if c["campaign_id"] == campaign_id:
            iv = (c["strict_iroas_lower"], c["strict_iroas_upper"]) if pd.notna(c.get("strict_iroas_lower")) else None
            return Evidence(campaign_id, c["trust_score"], c["tier"], c["checks"], iv)
    return None
