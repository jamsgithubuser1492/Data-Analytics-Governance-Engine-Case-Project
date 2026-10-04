"""Agent engine: evaluates agent definitions (data) against per-campaign facts.

Features: whitelisted metrics, trust tier gating for money actions, minimum spend floor,
deadband (hysteresis) using the previous run's active set, priority ordering, conflict
suppression of opposing money actions, sensitivity analysis, and packet output compatible
with the inbox and dashboard.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

import safe_expr
from agent_presets import PRESETS
from agent_schema import (ACTIONS, ALL_NAMES, OPPOSING_MONEY, TIER_RANK, format_value, render_template,
                          validate_definition)
from config import TIER_NOT_DECISION_GRADE

Active = Set[Tuple[str, str]]


def default_definitions() -> List[Dict[str, Any]]:
    """The built-in preset agents, validated and versioned as 1."""
    out = []
    for p in PRESETS:
        d, errs = validate_definition(p)
        if errs:  # presets are code owned; a failure is a programming error
            raise ValueError(f"Invalid preset {p['id']}: {errs}")
        out.append({**d, "version": 1})
    return out


def fingerprint(definitions: Iterable[Dict[str, Any]]) -> str:
    """Stable hash of enabled and disabled definitions with versions, used in run keys."""
    canon = sorted(({k: v for k, v in d.items()} for d in definitions), key=lambda d: d["id"])
    return hashlib.sha256(json.dumps(canon, sort_keys=True, default=str).encode()).hexdigest()[:12]


def build_facts(recon_df: pd.DataFrame, audit_report: Dict[str, Any], use_strict: bool = False) -> pd.DataFrame:
    """One facts row per campaign: reconciliation columns plus audit fields and the headline view metrics.

    ``iroas`` is the headline view: reported-by-spec incremental ROAS, or the strict lift iROAS
    (with spend and revenue switched to the test period) when ``use_strict``.
    """
    df = recon_df.copy()
    audit = pd.DataFrame(audit_report["campaigns"]).set_index("campaign_id")
    for col in ("tier", "trust_score", "spec_iroas", "strict_iroas", "strict_incremental_revenue", "test_period_spend", "divergence_warning"):
        df[col] = df["campaign_id"].map(audit[col]) if col in audit else None
    df["tier"] = df["tier"].fillna(TIER_NOT_DECISION_GRADE)
    df["trust_score"] = pd.to_numeric(df["trust_score"], errors="coerce").fillna(0.0)
    for col in ("spec_iroas", "strict_iroas", "strict_incremental_revenue", "test_period_spend"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["divergence_warning"] = df["divergence_warning"].fillna(False).astype(float)
    df["iroas"] = df["incremental_roas"]
    if use_strict:
        df = df[df["strict_iroas"].notna()].copy()
        df["iroas"] = df["strict_iroas"].round(2)
        df["total_holdout_revenue"] = df["strict_incremental_revenue"]
        df["total_spend"] = df["test_period_spend"]
    plat = df["total_platform_conversions"].where(df["total_platform_conversions"] > 0)
    df["platform_vs_mta_gap"] = (df["total_platform_conversions"] - df["total_mta_conversions"]) / plat
    for col in ("has_holdout_coverage", "has_mta_coverage"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.reset_index(drop=True)


# ------------------------------------------------------------------ condition logic
def _isnum(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _cond_true(cond: Dict[str, Any], row: Dict[str, Any], active_before: bool, deadband: float, scale: float) -> bool:
    v, op, t = row.get(cond["metric"]), cond["op"], cond["value"]
    if cond["metric"] == "tier":
        return v == t if op == "==" else v in (t if isinstance(t, list) else [t])
    if not _isnum(v):
        return False
    d = deadband / 100.0 if active_before else 0.0
    if op == "between":
        lo, hi = t[0] * scale, t[1] * scale
        return (lo - abs(lo) * d) <= v <= (hi + abs(hi) * d)
    t = t * scale
    if op in (">", ">="):
        t = t - abs(t) * d
        return v > t if op == ">" else v >= t
    if op in ("<", "<="):
        t = t + abs(t) * d
        return v < t if op == "<" else v <= t
    return abs(v - t) <= abs(t) * d if (op == "==" and d) else v == t


def _fires(defn: Dict[str, Any], row: Dict[str, Any], active_before: bool = False, scale: float = 1.0) -> bool:
    """Whether the definition fires for one facts row (tier, spend floor, trigger groups, deadband)."""
    money = ACTIONS[defn["action"]][1]
    min_rank = max(TIER_RANK[defn.get("requires_min_tier", TIER_NOT_DECISION_GRADE)], 1 if money else 0)
    if TIER_RANK.get(row.get("tier"), 0) < min_rank:
        return False
    spend = row.get("total_spend")
    if defn.get("min_spend", 0) and not (_isnum(spend) and spend >= defn["min_spend"]):
        return False
    db = defn.get("deadband_pct", 0.0)
    all_ok = all(_cond_true(c, row, active_before, db, scale) for c in defn["trigger"]["all"])
    any_c = defn["trigger"]["any"]
    any_ok = (not any_c) or any(_cond_true(c, row, active_before, db, scale) for c in any_c)
    return all_ok and any_ok


def _row_values(row: pd.Series) -> Dict[str, Any]:
    vals: Dict[str, Any] = {}
    for name in ALL_NAMES:
        v = row.get(name)
        if isinstance(v, float) and not math.isfinite(v):
            v = None
        vals[name] = v.item() if hasattr(v, "item") else v
    return vals


def _packet(defn: Dict[str, Any], row: pd.Series) -> Dict[str, Any]:
    values = _row_values(row)
    context = dict(values)
    metrics, raw = {}, {}
    for i, m in enumerate(defn["value_add"], 1):
        val = safe_expr.evaluate(m["expression"], values, ALL_NAMES)
        raw[m["label"]] = val
        metrics[m["label"]] = format_value(val, m["format"])
        context[f"m{i}"] = metrics[m["label"]]
    # plain placeholders print the stored value (same as a Python f-string of the cell)
    for name in ALL_NAMES:
        if name in ("channel", "campaign_id", "tier"):
            continue
        orig = row.get(name)
        context[name] = orig if orig is not None and not (isinstance(orig, float) and not math.isfinite(orig)) else None
    return {
        "packet_id": f"{defn['id']}:{row['campaign_id']}", "agent_id": defn["id"], "agent_version": defn.get("version", 1),
        "agent_name": defn["name"], "target_persona": defn["persona"], "campaign_id": row["campaign_id"], "channel": row["channel"],
        "severity": defn["severity"], "tier": values["tier"], "priority": defn["priority"],
        "title": render_template(defn["title"], context), "value_add_metrics": metrics, "raw_metrics": raw,
        "strategic_callout": render_template(defn["callout"], context), "recommended_action": defn["action"], "notes": [],
    }


def evaluate_agents(definitions: Iterable[Dict[str, Any]], facts: pd.DataFrame,
                    previously_active: Optional[Active] = None) -> List[Dict[str, Any]]:
    """Return packets for every enabled definition whose trigger fires, in campaign then priority order."""
    prev = previously_active or set()
    defs = sorted([d for d in definitions if d.get("enabled", True)], key=lambda d: (d["priority"], d["id"]))
    packets: List[Dict[str, Any]] = []
    for _, row in facts.iterrows():
        rv = _row_values(row)
        fired = [d for d in defs if _fires(d, rv, (d["id"], row["campaign_id"]) in prev)]
        # conflict resolution: the higher priority money action wins over an opposing one
        kept: List[Dict[str, Any]] = []
        notes: Dict[str, List[str]] = {}
        for d in fired:
            opp = OPPOSING_MONEY.get(d["action"])
            winner = next((k for k in kept if k["action"] == opp), None) if opp else None
            if winner:
                notes.setdefault(winner["id"], []).append(f"Suppressed {d['id']} (opposing action {d['action']}).")
                continue
            kept.append(d)
        for d in kept:
            p = _packet(d, row)
            p["notes"] = notes.get(d["id"], [])
            packets.append(p)
    return packets


def sensitivity(defn: Dict[str, Any], facts: pd.DataFrame, previously_active: Optional[Active] = None,
                pct: float = 0.10) -> pd.DataFrame:
    """Per campaign: does the agent fire at thresholds scaled down, as is, and up by ``pct``? Cliff edge if it changes."""
    prev = previously_active or set()
    rows = []
    for _, row in facts.iterrows():
        rv, was = _row_values(row), (defn["id"], row["campaign_id"]) in prev
        res = [_fires(defn, rv, was, s) for s in (1 - pct, 1.0, 1 + pct)]
        rows.append({"campaign_id": row["campaign_id"], "channel": row["channel"], f"fires_at_{int((1 - pct) * 100)}pct": res[0],
                     "fires_now": res[1], f"fires_at_{int((1 + pct) * 100)}pct": res[2], "cliff_edge": len(set(res)) > 1})
    return pd.DataFrame(rows)
