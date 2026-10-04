"""Agent definition schema, validation and safe template rendering.

An agent is plain data: a trigger (conditions on whitelisted metrics), a persona,
value-add formulas (safe expressions), a callout template and an allowed action.
Nothing in a definition can execute code. Validation returns plain language errors.
"""
from __future__ import annotations

import math
import re
import string
from typing import Any, Dict, List, Optional, Tuple

import safe_expr
from agent_orchestrator import PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM
from config import TIER_DIRECTIONAL, TIER_NOT_DECISION_GRADE, TIER_VERIFIED

PERSONAS = [PERSONA_CFO, PERSONA_AGENCY, PERSONA_PLATFORM]
SEVERITIES = ["CRITICAL", "WARNING", "OPPORTUNITY", "INFO"]
TIERS = [TIER_NOT_DECISION_GRADE, TIER_DIRECTIONAL, TIER_VERIFIED]
TIER_RANK = {TIER_NOT_DECISION_GRADE: 0, TIER_DIRECTIONAL: 1, TIER_VERIFIED: 2}

# action code -> (label, is_money_action). Money actions are blocked below the Directional tier.
ACTIONS: Dict[str, Tuple[str, bool]] = {
    "REDUCE_BUDGET_50%": ("Reduce budget by 50%", True),
    "SCALE_BUDGET_25%": ("Scale budget by 25%", True),
    "CLIENT_GOVERNANCE_AUDIT": ("Run a client governance audit", False),
    "HOLD_SCALE_REQUESTS": ("Pause scale requests", False),
    "RERUN_HOLDOUT": ("Rerun or extend the holdout", False),
    "REVIEW_MEASUREMENT": ("Review the measurement setup", False),
}
OPPOSING_MONEY = {"REDUCE_BUDGET_50%": "SCALE_BUDGET_25%", "SCALE_BUDGET_25%": "REDUCE_BUDGET_50%"}

NUMERIC_BOUNDS: Dict[str, Tuple[float, float]] = {
    "reported_roas": (-50, 500), "mta_roas": (-50, 500), "iroas": (-50, 500), "spec_iroas": (-50, 500),
    "strict_iroas": (-50, 500), "inflation_ratio": (0, 100), "trust_score": (0, 100),
    "platform_vs_mta_gap": (-5, 5), "total_spend": (0, 1e9), "test_period_spend": (0, 1e9),
    "total_platform_conversions": (0, 1e9), "total_mta_conversions": (0, 1e9), "total_holdout_conversions": (0, 1e9),
    "total_platform_revenue": (0, 1e10), "total_mta_revenue": (0, 1e10), "total_holdout_revenue": (-1e10, 1e10),
    "strict_incremental_revenue": (-1e10, 1e10), "has_holdout_coverage": (0, 1), "has_mta_coverage": (0, 1),
    "divergence_warning": (0, 1),
}
NUMERIC_METRICS = sorted(NUMERIC_BOUNDS)
STRING_METRICS = ["tier", "channel", "campaign_id"]
ALL_NAMES = NUMERIC_METRICS + STRING_METRICS
CONDITION_METRICS = NUMERIC_METRICS + ["tier"]
NUMERIC_OPS = [">", ">=", "<", "<=", "==", "between"]
TIER_OPS = ["==", "in"]
FORMATS = {"x2": "{:.2f}x", "usd": "${:,.2f}", "pct1": "{:.1f}%", "number": "{:,.2f}", "int": "{:,.0f}", "text": "{}"}
MEASURE_SLOTS = [f"m{i}" for i in range(1, 6)]
TEMPLATE_NAMES = set(ALL_NAMES) | set(MEASURE_SLOTS)
SPEC_OK = re.compile(r"^(,?\.\d+f|,?\d*d|\.\d+%)?$")
ID_PAT = re.compile(r"^[A-Z][A-Z0-9_]{2,40}$")


def format_value(value: Any, fmt: str) -> str:
    """Display string for a metric value; None and non-finite numbers become 'n/a'."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    if fmt == "text":
        return str(value)
    if isinstance(value, str):
        return value
    return FORMATS[fmt].format(value)


def render_template(template: str, context: Dict[str, Any]) -> str:
    """Safe ``str.format``: identifier fields from a whitelist only, limited format specs, no conversions."""
    out: List[str] = []
    for literal, field, spec, conv in string.Formatter().parse(template):
        out.append(literal)
        if field is None:
            continue
        if conv or not field.isidentifier() or field not in TEMPLATE_NAMES or not SPEC_OK.match(spec or ""):
            raise ValueError(f"Placeholder '{{{field}{':' + spec if spec else ''}}}' is not allowed.")
        v = context.get(field)
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            out.append("n/a")
        elif spec:
            try:
                out.append(format(v, spec))
            except (ValueError, TypeError):
                out.append("n/a")
        else:
            out.append(str(v))
    return "".join(out)


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def validate_condition(cond: Any, where: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    errs: List[str] = []
    if not isinstance(cond, dict):
        return None, [f"{where}: condition must be an object."]
    metric, op, val = cond.get("metric"), cond.get("op"), cond.get("value")
    if metric not in CONDITION_METRICS:
        return None, [f"{where}: unknown metric '{metric}'."]
    if metric == "tier":
        if op not in TIER_OPS:
            return None, [f"{where}: tier supports {TIER_OPS}."]
        vals = val if isinstance(val, list) else [val]
        if op == "==" and isinstance(val, list):
            return None, [f"{where}: '==' needs a single tier."]
        if not vals or any(v not in TIERS for v in vals):
            return None, [f"{where}: tier must be one of {TIERS}."]
        return {"metric": metric, "op": op, "value": val}, []
    if op not in NUMERIC_OPS:
        return None, [f"{where}: operator must be one of {NUMERIC_OPS}."]
    lo, hi = NUMERIC_BOUNDS[metric]
    if op == "between":
        if not (isinstance(val, (list, tuple)) and len(val) == 2 and all(_num(x) is not None for x in val)):
            return None, [f"{where}: 'between' needs two numbers."]
        a, b = float(val[0]), float(val[1])
        if a > b:
            errs.append(f"{where}: first number must not exceed the second.")
        if not (lo <= a <= hi and lo <= b <= hi):
            errs.append(f"{where}: values for {metric} must be between {lo:g} and {hi:g}.")
        return (None, errs) if errs else ({"metric": metric, "op": op, "value": [a, b]}, [])
    n = _num(val)
    if n is None:
        return None, [f"{where}: value must be a number."]
    if not lo <= n <= hi:
        return None, [f"{where}: value for {metric} must be between {lo:g} and {hi:g}."]
    return {"metric": metric, "op": op, "value": n}, []


def validate_definition(raw: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate and normalize an agent definition. Returns (definition, errors); definition is None if errors."""
    errs: List[str] = []
    if not isinstance(raw, dict):
        return None, ["Definition must be an object."]
    d: Dict[str, Any] = {}
    d["id"] = str(raw.get("id", "")).strip()
    if not ID_PAT.match(d["id"]):
        errs.append("Agent id must be 3 to 41 characters: capital letters, digits and underscores, starting with a letter.")
    d["name"] = str(raw.get("name", "")).strip()
    if not 3 <= len(d["name"]) <= 80:
        errs.append("Name must be 3 to 80 characters.")
    d["description"] = str(raw.get("description", ""))[:300]
    d["persona"] = raw.get("persona")
    if d["persona"] not in PERSONAS:
        errs.append(f"Persona must be one of {PERSONAS}.")
    d["severity"] = raw.get("severity")
    if d["severity"] not in SEVERITIES:
        errs.append(f"Severity must be one of {SEVERITIES}.")
    d["action"] = raw.get("action")
    if d["action"] not in ACTIONS:
        errs.append(f"Action must be one of {sorted(ACTIONS)}.")
    d["enabled"] = bool(raw.get("enabled", True))
    pr = raw.get("priority", 50)
    d["priority"] = int(pr) if isinstance(pr, (int, float)) and not isinstance(pr, bool) and 1 <= pr <= 100 else None
    if d["priority"] is None:
        errs.append("Priority must be a whole number from 1 (first) to 100.")
    d["requires_min_tier"] = raw.get("requires_min_tier", TIER_NOT_DECISION_GRADE)
    if d["requires_min_tier"] not in TIERS:
        errs.append(f"requires_min_tier must be one of {TIERS}.")
    elif d["action"] in ACTIONS and ACTIONS[d["action"]][1] and TIER_RANK[d["requires_min_tier"]] < 1:
        d["requires_min_tier"] = TIER_DIRECTIONAL  # money actions can never fire below Directional
    ms = _num(raw.get("min_spend", 0))
    d["min_spend"] = ms if ms is not None and 0 <= ms <= 1e9 else None
    if d["min_spend"] is None:
        errs.append("Minimum spend must be a number from 0 to 1,000,000,000.")
    db = _num(raw.get("deadband_pct", 0))
    d["deadband_pct"] = db if db is not None and 0 <= db <= 50 else None
    if d["deadband_pct"] is None:
        errs.append("Deadband must be a percentage from 0 to 50.")

    trig = raw.get("trigger")
    groups: Dict[str, List[Dict[str, Any]]] = {"all": [], "any": []}
    if not isinstance(trig, dict):
        errs.append("Trigger must have 'all' and/or 'any' condition lists.")
    else:
        for g in ("all", "any"):
            for i, c in enumerate(trig.get(g, []) or [], 1):
                cond, e = validate_condition(c, f"Trigger {g} condition {i}")
                errs += e
                if cond:
                    groups[g].append(cond)
        if not groups["all"] and not groups["any"] and not errs:
            errs.append("A trigger needs at least one condition.")
        if len(groups["all"]) + len(groups["any"]) > 12:
            errs.append("A trigger can have at most 12 conditions.")
    d["trigger"] = groups

    va = raw.get("value_add", []) or []
    d["value_add"] = []
    if not isinstance(va, list) or len(va) > len(MEASURE_SLOTS):
        errs.append(f"Value-add metrics: a list of at most {len(MEASURE_SLOTS)} items.")
    else:
        for i, m in enumerate(va, 1):
            label = str(m.get("label", "")).strip() if isinstance(m, dict) else ""
            expr, fmt = (m.get("expression", ""), m.get("format", "number")) if isinstance(m, dict) else ("", "")
            if not 2 <= len(label) <= 60:
                errs.append(f"Value-add {i}: label must be 2 to 60 characters.")
            if fmt not in FORMATS:
                errs.append(f"Value-add {i}: format must be one of {sorted(FORMATS)}.")
            try:
                safe_expr.parse(expr, ALL_NAMES)
            except safe_expr.ExprError as exc:
                errs.append(f"Value-add {i} ('{label}'): {exc}")
            d["value_add"].append({"label": label, "expression": str(expr).strip(), "format": fmt})
    for key, limit in (("title", 120), ("callout", 600)):
        text = str(raw.get(key, "")).strip()
        d[key] = text
        if not text:
            errs.append(f"{key.capitalize()} template is required.")
        elif len(text) > limit:
            errs.append(f"{key.capitalize()} template is longer than {limit} characters.")
        else:
            try:
                render_template(text, {})
            except ValueError as exc:
                errs.append(f"{key.capitalize()}: {exc}")
    if "version" in raw:
        d["version"] = int(raw["version"]) if isinstance(raw["version"], (int, float)) else 1
    return (None, errs) if errs else (d, [])
