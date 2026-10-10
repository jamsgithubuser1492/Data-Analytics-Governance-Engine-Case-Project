"""Audience tier incrementality: how much of the revenue a platform credits to each audience tier would have happened anyway.

Inputs are aggregate only: one row per day, campaign and audience tier (people reached and conversions in the test and
control markets), plus one propensity decile mix per market. No person level rows and no feature matrices are accepted.

For each tier k (people grouped by how likely they were to buy anyway):
    CVR_test, CVR_control   conversions divided by people reached, in test and control markets
    lift  = max(0, (CVR_test - CVR_control) / CVR_test)       the share of conversions the ads caused
    strict incremental revenue = reported revenue x lift
    cannibalized revenue       = reported revenue - strict incremental revenue
    cannibalization % = (1 - lift) x 100                      the share that would have happened anyway
    spend paying for sales that would have happened anyway = spend x cannibalization %
A 95% range on the lift comes from the binomial sampling error of the two conversion rates (delta method). A tier is only
judged when both arms clear the minimum sample rules; otherwise it reports "not enough data" and recommends nothing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import propensity_scm as pscm
from config import PolicySettings, TIER_DIRECTIONAL, TIER_NOT_DECISION_GRADE, TIER_VERIFIED
from schemas import AUDIENCE_FORBIDDEN_TOKENS, AUDIENCE_SCHEMAS, AUDIENCE_TABLES, DECILE_COLUMNS
from validation import BLOCKER, WARNING, ValidationReport

ROOT = Path(__file__).resolve().parents[1]
AUDIENCE_DIR = ROOT / "data" / "audience"
Z95 = 1.959964
STATUS_CRITICAL, STATUS_REVIEW, STATUS_HEALTHY, STATUS_NO_DATA = "Critical", "Review", "Healthy", "Not enough data"
ACTION_REDUCE = "Consider reducing spend on this audience tier"
ACTION_REVIEW = "Review this tier before the next budget cycle"
ACTION_KEEP = "Keep monitoring"
ACTION_NONE = "Not enough data to judge, so no recommendation"
ACTION_SMALL = "Too small to move money on; keep monitoring"


# ------------------------------------------------------------------------------------------------ validation
def _tokens(col: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", col.lower()) if t]


def validate_audience(frames: Dict[str, pd.DataFrame], settings: Optional[PolicySettings] = None) -> ValidationReport:
    """Contract checks for the three aggregate tables. Blockers stop the audience layer; warnings are advisory."""
    settings = settings or PolicySettings()
    rep = ValidationReport()
    for name in AUDIENCE_TABLES:
        df = frames.get(name)
        if df is None or df.empty:
            rep.add(BLOCKER, "missing_table", name, f"The {name.replace('_', ' ').lower()} table is missing or empty.")
            continue
        for col in df.columns:
            bad = [t for t in _tokens(col) if t in AUDIENCE_FORBIDDEN_TOKENS]
            if bad:
                rep.add(BLOCKER, "person_level_column", name, f"Column '{col}' looks like person level or feature level data. Only aggregate audience data is accepted.")
        required = [f for f in AUDIENCE_SCHEMAS[name] if f.required]
        missing = [f.name for f in required if f.name not in df.columns]
        if missing:
            rep.add(BLOCKER, "missing_columns", name, f"Missing required column(s): {', '.join(missing)}.")
            continue
        for f in AUDIENCE_SCHEMAS[name]:
            if f.name not in df.columns:
                continue
            if f.kind in ("float", "int"):
                num = pd.to_numeric(df[f.name], errors="coerce")
                if num.isna().any():
                    rep.add(BLOCKER, "not_numeric", name, f"Column '{f.name}' has missing or non numeric values.")
                elif f.min_value is not None and (num < f.min_value).any():
                    rep.add(BLOCKER, "below_minimum", name, f"Column '{f.name}' has values below {f.min_value:g}.")
    if rep.blockers:
        return rep
    prop, series, tiers = frames["AUDIENCE_DMA_PROPENSITY"], frames["AUDIENCE_DMA_SERIES"], frames["AUDIENCE_TIER_PERFORMANCE"]
    sums = prop[DECILE_COLUMNS].sum(axis=1)
    off = prop.loc[(sums - 1.0).abs() > 0.01, "dma_code"].tolist()
    if off:
        rep.add(BLOCKER, "decile_mix_not_one", "AUDIENCE_DMA_PROPENSITY", "Each market's ten decile shares must add up to 100%.", off)
    if prop["dma_code"].duplicated().any():
        rep.add(BLOCKER, "duplicate_market", "AUDIENCE_DMA_PROPENSITY", "A market appears more than once in the audience mix table.")
    unknown = sorted(set(series["dma_code"]) - set(prop["dma_code"]))
    if unknown:
        rep.add(BLOCKER, "market_without_mix", "AUDIENCE_DMA_SERIES", "Some markets have sales history but no audience mix.", unknown)
    roles = set(series["role"].str.lower())
    if not roles <= {"treatment", "control", "donor"}:
        rep.add(BLOCKER, "bad_role", "AUDIENCE_DMA_SERIES", "The role column may only say 'treatment' or 'control'.")
    n_donors = series.loc[series["role"].str.lower().isin(["control", "donor"]), "dma_code"].nunique()
    if n_donors == 0:
        rep.add(BLOCKER, "no_donors", "AUDIENCE_DMA_SERIES", "At least one control market is needed.")
    elif n_donors < 3:
        rep.add(WARNING, "few_donors", "AUDIENCE_DMA_SERIES", f"Only {n_donors} control market(s). Matching works better with several.")
    if (tiers["tier_decile_start"] > tiers["tier_decile_end"]).any() or (tiers["tier_decile_end"] > 10).any() or (tiers["tier_decile_start"] < 1).any():
        rep.add(BLOCKER, "bad_decile_range", "AUDIENCE_TIER_PERFORMANCE", "Each tier must cover a range of deciles from 1 to 10, start before end.")
    if tiers.duplicated(["date", "campaign_id", "tier_name"]).any():
        rep.add(BLOCKER, "duplicate_rows", "AUDIENCE_TIER_PERFORMANCE", "There is more than one row for the same day, campaign and tier.")
    if ((tiers["treatment_conversions"] > tiers["treatment_users"]) | (tiers["control_conversions"] > tiers["control_users"])).any():
        rep.add(BLOCKER, "conversions_exceed_users", "AUDIENCE_TIER_PERFORMANCE", "Conversions cannot exceed the people reached.")
    ranges = tiers.groupby("tier_name")[["tier_decile_start", "tier_decile_end"]].agg(["min", "max"])
    spans = sorted((int(r[("tier_decile_start", "min")]), int(r[("tier_decile_end", "max")])) for _, r in ranges.iterrows())
    if any(spans[i][1] >= spans[i + 1][0] for i in range(len(spans) - 1)):
        rep.add(WARNING, "overlapping_tiers", "AUDIENCE_TIER_PERFORMANCE", "Some audience tiers cover overlapping deciles, so their results are not independent.")
    return rep


# ------------------------------------------------------------------------------------------------ tier incrementality
def _lift_range(tt: pd.Series, tu: pd.Series, ct: pd.Series, cu: pd.Series):
    pt = tt / tu.where(tu > 0)
    pc = ct / cu.where(cu > 0)
    r = pc / pt.where(pt > 0)
    var_r = r ** 2 * ((1 - pt) / (tu * pt) + (1 - pc) / (cu * pc.where(pc > 0)))
    se = np.sqrt(var_r.clip(lower=0))
    lift = (1 - r).clip(lower=0, upper=1)
    lo = (1 - (r + Z95 * se)).clip(lower=0, upper=1)
    hi = (1 - (r - Z95 * se)).clip(lower=0, upper=1)
    return pt, pc, lift, lo, hi


def tier_table(tier_df: pd.DataFrame, settings: Optional[PolicySettings] = None, *, match_passed: Optional[Dict[str, bool]] = None,
               breakeven: float = 1.0) -> pd.DataFrame:
    """One row per channel, campaign and audience tier over the whole period, with ranges, a sample guard and a status."""
    s = settings or PolicySettings()
    d = tier_df.copy()
    g = d.groupby(["channel", "campaign_id", "tier_name"], as_index=False).agg(
        decile_start=("tier_decile_start", "min"), decile_end=("tier_decile_end", "max"), spend=("spend", "sum"), reported_revenue=("reported_revenue", "sum"),
        treatment_conversions=("treatment_conversions", "sum"), treatment_users=("treatment_users", "sum"),
        control_conversions=("control_conversions", "sum"), control_users=("control_users", "sum"))
    pt, pc, lift, lo, hi = _lift_range(g["treatment_conversions"], g["treatment_users"], g["control_conversions"], g["control_users"])
    g["cvr_treatment"], g["cvr_control"] = pt, pc
    g["lift_ratio"], g["lift_low"], g["lift_high"] = lift.fillna(0.0), lo.fillna(0.0), hi.fillna(1.0)
    spend = g["spend"].where(g["spend"] > 0)
    g["reported_roas"] = g["reported_revenue"] / spend
    g["strict_incremental_revenue"] = g["reported_revenue"] * g["lift_ratio"]
    g["strict_revenue_low"], g["strict_revenue_high"] = g["reported_revenue"] * g["lift_low"], g["reported_revenue"] * g["lift_high"]
    g["cannibalized_revenue"] = g["reported_revenue"] - g["strict_incremental_revenue"]
    g["strict_iroas"] = g["strict_incremental_revenue"] / spend
    g["strict_iroas_low"], g["strict_iroas_high"] = g["strict_revenue_low"] / spend, g["strict_revenue_high"] / spend
    g["cannibalization_pct"] = (1.0 - g["lift_ratio"]) * 100.0
    g["spend_for_organic_sales"] = g["spend"] * g["cannibalization_pct"] / 100.0
    g["spend_for_net_new_sales"] = g["spend"] - g["spend_for_organic_sales"]
    g["range_width"] = g["lift_high"] - g["lift_low"]
    g["sample_ok"] = ((g["treatment_users"] >= s.tier_min_users) & (g["control_users"] >= s.tier_min_users)
                      & (g["treatment_conversions"] >= s.tier_min_conversions) & (g["control_conversions"] >= s.tier_min_conversions)
                      & (g["cvr_treatment"] > 0))
    mp = match_passed or {}
    g["match_ok"] = g["channel"].map(lambda c: bool(mp.get(c, False)))
    tier = []
    for _, r in g.iterrows():
        if not r["sample_ok"]:
            tier.append(TIER_NOT_DECISION_GRADE)
        elif r["range_width"] <= s.tier_max_range_width and r["match_ok"]:
            tier.append(TIER_VERIFIED)
        else:
            tier.append(TIER_DIRECTIONAL)
    g["evidence_tier"] = tier

    def status(r: pd.Series) -> str:
        if not r["sample_ok"]:
            return STATUS_NO_DATA
        if r["cannibalization_pct"] >= s.cannibalization_critical_threshold:
            return STATUS_CRITICAL
        return STATUS_REVIEW if r["cannibalization_pct"] >= s.cannibalization_warning_threshold else STATUS_HEALTHY

    def action(r: pd.Series) -> str:
        if r["evidence_tier"] == TIER_NOT_DECISION_GRADE:
            return ACTION_NONE
        if r["spend"] < s.tier_min_spend:
            return ACTION_SMALL
        if r["status"] == STATUS_CRITICAL:
            return ACTION_REDUCE
        return ACTION_REVIEW if r["status"] == STATUS_REVIEW else ACTION_KEEP

    g["status"] = g.apply(status, axis=1)
    g["action"] = g.apply(action, axis=1)
    return g.sort_values(["cannibalized_revenue"], ascending=False).reset_index(drop=True)


def judged(table: pd.DataFrame) -> pd.DataFrame:
    """Tiers with enough data to be judged."""
    return table[table["evidence_tier"] != TIER_NOT_DECISION_GRADE]


def summary(table: pd.DataFrame, settings: Optional[PolicySettings] = None) -> Dict[str, Any]:
    """Portfolio level figures over the judged tiers, plus the single largest source of paid but not caused revenue."""
    s = settings or PolicySettings()
    j = judged(table)
    out: Dict[str, Any] = {"tiers": int(len(table)), "judged": int(len(j)), "spend": float(table["spend"].sum()),
                           "reported_revenue": float(j["reported_revenue"].sum()), "strict_revenue": float(j["strict_incremental_revenue"].sum()),
                           "cannibalized_revenue": float(j["cannibalized_revenue"].sum()), "spend_for_organic_sales": float(j["spend_for_organic_sales"].sum()),
                           "judged_spend": float(j["spend"].sum()), "top": None}
    out["cannibalization_pct"] = out["cannibalized_revenue"] / out["reported_revenue"] * 100 if out["reported_revenue"] else float("nan")
    flagged = j[j["cannibalization_pct"] >= s.cannibalization_critical_threshold]
    out["critical_spend_for_organic"] = float(flagged["spend_for_organic_sales"].sum())
    out["critical_spend"] = float(flagged["spend"].sum())
    out["critical_tiers"] = int(len(flagged))
    if len(j):
        top = j.sort_values("spend_for_organic_sales", ascending=False).iloc[0]
        out["top"] = {k: (v.item() if hasattr(v, "item") else v) for k, v in top.items()}
    return out


def best_growth_tier(table: pd.DataFrame) -> Optional[pd.Series]:
    """The judged tier with the highest strict return whose lower range still covers its cost: where more budget has the best case."""
    j = judged(table)
    j = j[(j["strict_iroas_low"] >= 1.0)] if len(j) else j
    return None if j.empty else j.sort_values("strict_iroas", ascending=False).iloc[0]


def shift_scenario(table: pd.DataFrame, fraction: float = 0.20) -> Optional[Dict[str, Any]]:
    """Modeled effect of moving a share of the most wasteful tier's spend to the best growth tier, at today's tier returns.

    A scenario, not a forecast: returns usually fall as a tier takes more money.
    """
    j = judged(table)
    if j.empty:
        return None
    src = j.sort_values("cannibalization_pct", ascending=False).iloc[0]
    dst = best_growth_tier(table)
    if dst is None or src["cannibalization_pct"] <= 50 or (src["channel"], src["tier_name"], src["campaign_id"]) == (dst["channel"], dst["tier_name"], dst["campaign_id"]):
        return None
    amount = float(src["spend"]) * fraction
    given_up = amount * float(src["strict_iroas"])
    gained = amount * float(dst["strict_iroas"])
    return {"from": src, "to": dst, "amount": amount, "given_up": given_up, "gained": gained, "net": gained - given_up, "fraction": fraction}


def tier_facts(table: pd.DataFrame) -> pd.DataFrame:
    """Facts rows for the guardrail engine: one per judged or unjudged tier, using the engine's metric names."""
    f = pd.DataFrame({
        "campaign_id": table["campaign_id"] + "|" + table["tier_name"], "channel": table["channel"], "tier": table["evidence_tier"],
        "trust_score": table["evidence_tier"].map({TIER_VERIFIED: 90.0, TIER_DIRECTIONAL: 65.0, TIER_NOT_DECISION_GRADE: 20.0}),
        "total_spend": table["spend"], "cannibalization_pct": table["cannibalization_pct"], "cannibalized_revenue": table["cannibalized_revenue"],
        "strict_iroas": table["strict_iroas"], "iroas": table["strict_iroas"], "reported_roas": table["reported_roas"], "tier_name": table["tier_name"]})
    f.loc[table["evidence_tier"] == TIER_NOT_DECISION_GRADE, ["cannibalization_pct"]] = np.nan  # unjudged tiers can never trigger a rule
    return f.reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ control market match
def match_quality(series: pd.DataFrame, prop: pd.DataFrame, settings: Optional[PolicySettings] = None) -> pd.DataFrame:
    """One row per test market group: how well the chosen control markets match on sales history and audience mix."""
    s = settings or PolicySettings()
    series = series.copy()
    series["date"] = pd.to_datetime(series["date"])
    series["role"] = series["role"].str.lower()
    dates = sorted(series["date"].unique())
    pre_days = min(s.pre_period_days, len(dates) - 1)
    pre = set(dates[:pre_days])
    donors = series[series["role"].isin(["control", "donor"])].pivot_table(index="date", columns="dma_code", values="revenue", aggfunc="sum").sort_index()
    pm = prop.set_index("dma_code")[DECILE_COLUMNS]
    rows = []
    for (code, channel), grp in series[series["role"] == "treatment"].groupby(["dma_code", series["channel"].fillna("All channels")]):
        y = grp.set_index("date")["revenue"].sort_index()
        y_pre, D_pre = y[y.index.isin(pre)], donors[donors.index.isin(pre)]
        names = list(donors.columns)
        res = pscm.match(y_pre.values, D_pre.loc[y_pre.index].values, pm.loc[code].values, pm.loc[names].T.values, names, phi=s.propensity_weight_phi,
                         min_r2=s.match_min_r2, min_overlap=s.match_min_overlap, max_rmspe_pct=s.match_max_rmspe_pct)
        top = ", ".join(f"{d} {w:.0%}" for d, w in res.table()[:3])
        rows.append({"channel": channel, "test_market": code, "r2": res.r2, "relative_rmspe": res.relative_rmspe, "overlap": res.overlap,
                     "baseline_r2": res.baseline_r2, "baseline_relative_rmspe": res.baseline_relative_rmspe, "baseline_overlap": res.baseline_overlap,
                     "phi": res.phi, "passed": res.passed, "reasons": "; ".join(res.reasons), "top_markets": top, "control_markets": len(names),
                     "pre_days": int(len(y_pre))})
    return pd.DataFrame(rows)


def match_flags(match_df: pd.DataFrame) -> Dict[str, bool]:
    return {r["channel"]: bool(r["passed"]) for _, r in match_df.iterrows()} if len(match_df) else {}


# ------------------------------------------------------------------------------------------------ demo data
def load_demo_audience(directory: Path = AUDIENCE_DIR) -> Dict[str, pd.DataFrame]:
    """The synthetic audience tables shipped with the project (separate from the verified case study files)."""
    d = Path(directory)
    return {name: pd.read_csv(d / f"{name}.csv") for name in AUDIENCE_TABLES}


def compute(frames: Dict[str, pd.DataFrame], settings: Optional[PolicySettings] = None, breakeven: float = 1.0) -> Dict[str, pd.DataFrame]:
    """Match quality first (it feeds the evidence level), then the tier table."""
    s = settings or PolicySettings()
    m = match_quality(frames["AUDIENCE_DMA_SERIES"], frames["AUDIENCE_DMA_PROPENSITY"], s)
    t = tier_table(frames["AUDIENCE_TIER_PERFORMANCE"], s, match_passed=match_flags(m), breakeven=breakeven)
    return {"AUDIENCE_TIER_RESULTS": t, "AUDIENCE_MATCH_QUALITY": m}
