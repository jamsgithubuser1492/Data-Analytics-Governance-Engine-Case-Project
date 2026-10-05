"""Plain-language settings for the three built-in decision rules, and the three risk appetites.

An executive does not edit metric names and operators. They answer business questions ("How much over-claiming is
acceptable?") and pick a risk appetite. This module translates those answers to and from the stored rule
definitions, so the engine, versioning, validation and trust gating are exactly the same as in the advanced editor.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from agent_schema import validate_definition

RULE_IDS = ["CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT", "SCALE_OPPORTUNITY_AGENT"]
TIER_CHOICES = {"Any evidence level": "NOT_DECISION_GRADE", "Directional or better": "DIRECTIONAL", "Verified only": "VERIFIED"}
TIER_FROM_CODE = {v: k for k, v in TIER_CHOICES.items()}

# plain setting name -> (metric, operator) of the condition it controls
SETTING_MAP: Dict[str, Dict[str, Tuple[str, str]]] = {
    "CAPITAL_PRESERVATION_AGENT": {"claimed_at_least": ("reported_roas", ">="), "proven_below": ("iroas", "<")},
    "ATTRIBUTION_SHIELD_AGENT": {"overclaim_above": ("inflation_ratio", ">"), "overclaim_ceiling": ("inflation_ratio", "<=")},
    "SCALE_OPPORTUNITY_AGENT": {"proven_at_least": ("iroas", ">="), "overclaim_at_most": ("inflation_ratio", "<=")},
}
COMMON = ("min_spend", "min_tier")

# Risk appetites. Balanced reproduces the shipped rules exactly.
APPETITES: Dict[str, Dict[str, Any]] = {
    "Conservative": {
        "blurb": "Wants stronger proof before money moves and reacts to smaller problems. Fewer growth alerts, earlier warnings.",
        "CAPITAL_PRESERVATION_AGENT": {"claimed_at_least": 1.25, "proven_below": 1.25, "min_spend": 10000.0, "min_tier": "DIRECTIONAL"},
        "ATTRIBUTION_SHIELD_AGENT": {"overclaim_above": 1.15, "overclaim_ceiling": 3.0, "min_spend": 0.0, "min_tier": "NOT_DECISION_GRADE"},
        "SCALE_OPPORTUNITY_AGENT": {"proven_at_least": 4.0, "overclaim_at_most": 1.15, "min_spend": 0.0, "min_tier": "VERIFIED"},
    },
    "Balanced": {
        "blurb": "The standard setting used in the case study. A middle path between caution and ambition.",
        "CAPITAL_PRESERVATION_AGENT": {"claimed_at_least": 1.5, "proven_below": 1.0, "min_spend": 0.0, "min_tier": "DIRECTIONAL"},
        "ATTRIBUTION_SHIELD_AGENT": {"overclaim_above": 1.25, "overclaim_ceiling": 3.0, "min_spend": 0.0, "min_tier": "NOT_DECISION_GRADE"},
        "SCALE_OPPORTUNITY_AGENT": {"proven_at_least": 3.0, "overclaim_at_most": 1.25, "min_spend": 0.0, "min_tier": "DIRECTIONAL"},
    },
    "Aggressive": {
        "blurb": "Willing to act on earlier signals and tolerates more noise. More growth alerts, later warnings.",
        "CAPITAL_PRESERVATION_AGENT": {"claimed_at_least": 2.0, "proven_below": 0.8, "min_spend": 25000.0, "min_tier": "DIRECTIONAL"},
        "ATTRIBUTION_SHIELD_AGENT": {"overclaim_above": 1.5, "overclaim_ceiling": 3.0, "min_spend": 0.0, "min_tier": "NOT_DECISION_GRADE"},
        "SCALE_OPPORTUNITY_AGENT": {"proven_at_least": 2.0, "overclaim_at_most": 1.5, "min_spend": 0.0, "min_tier": "DIRECTIONAL"},
    },
}


def read_settings(defn: Dict[str, Any]) -> Dict[str, Any]:
    """The plain-language values currently stored in a rule definition."""
    out: Dict[str, Any] = {"min_spend": float(defn.get("min_spend", 0.0)), "min_tier": defn.get("requires_min_tier", "NOT_DECISION_GRADE")}
    for name, (metric, op) in SETTING_MAP.get(defn["id"], {}).items():
        for c in defn["trigger"]["all"]:
            if c["metric"] == metric and c["op"] == op:
                out[name] = float(c["value"])
    return out


def apply_settings(defn: Dict[str, Any], values: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """New definition with the plain settings applied, validated by the same schema as every other rule."""
    d = copy.deepcopy(defn)
    for name, (metric, op) in SETTING_MAP.get(d["id"], {}).items():
        if name in values:
            for c in d["trigger"]["all"]:
                if c["metric"] == metric and c["op"] == op:
                    c["value"] = float(values[name])
    if "min_spend" in values:
        d["min_spend"] = float(values["min_spend"])
    if "min_tier" in values:
        d["requires_min_tier"] = values["min_tier"]
    return validate_definition(d)


def apply_appetite(defs: Dict[str, Dict[str, Any]], appetite: str) -> Dict[str, Dict[str, Any]]:
    """Definitions for all three rules under a risk appetite (raises on an invalid result)."""
    out = {}
    for rid in RULE_IDS:
        norm, errs = apply_settings(defs[rid], APPETITES[appetite][rid])
        if errs:
            raise ValueError("; ".join(errs))
        out[rid] = norm
    return out


def describe(defn: Dict[str, Any]) -> str:
    """One plain sentence describing when a built-in rule raises its hand."""
    s = read_settings(defn)
    tier = TIER_FROM_CODE.get(s["min_tier"], s["min_tier"]).lower()
    stake = f" and at least ${s['min_spend']:,.0f} is being spent" if s["min_spend"] else ""
    if defn["id"] == "CAPITAL_PRESERVATION_AGENT":
        return (f"A platform claims a return of {s['claimed_at_least']:g}x or more, but the test proves less than {s['proven_below']:g}x{stake}. Evidence level: {tier}.")
    if defn["id"] == "ATTRIBUTION_SHIELD_AGENT":
        return f"A platform claims more than {s['overclaim_above']:g} times what the test confirms{stake}. Evidence level: {tier}."
    return f"The proven return is {s['proven_at_least']:g}x or more and platforms claim no more than {s['overclaim_at_most']:g} times what the test confirms{stake}. Evidence level: {tier}."


def detect_appetite(defs: Dict[str, Dict[str, Any]]) -> str:
    """Which risk appetite the stored rules currently match, or 'Custom' when they were tuned individually."""
    for name, spec in APPETITES.items():
        ok = True
        for rid in RULE_IDS:
            cur = read_settings(defs[rid])
            for key, want in spec[rid].items():
                if abs(float(cur.get(key, -1)) - float(want)) > 1e-9 if not isinstance(want, str) else cur.get(key) != want:
                    ok = False
        if ok:
            return name
    return "Custom"
