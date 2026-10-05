"""The three built-in agents, expressed as data (no code). They reproduce the original
AgentOrchestrator behavior exactly; users can duplicate and edit them."""
from __future__ import annotations

from typing import Any, Dict, List

from agent_orchestrator import PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM

PRESETS: List[Dict[str, Any]] = [
    {
        "id": "CAPITAL_PRESERVATION_AGENT", "name": "Capital preservation", "persona": PERSONA_CFO, "severity": "CRITICAL",
        "description": "Platform looks profitable but the holdout return is below breakeven (false positive profitability).",
        "priority": 10, "action": "REDUCE_BUDGET_50%", "requires_min_tier": "DIRECTIONAL",
        "trigger": {"all": [{"metric": "reported_roas", "op": ">=", "value": 1.5}, {"metric": "iroas", "op": "<", "value": 1.0}]},
        "value_add": [
            {"label": "Sales credited to ads that they did not cause", "format": "pct1",
             "expression": "max(0, div(total_platform_conversions - total_holdout_conversions, total_platform_conversions) * 100)"},
            {"label": "Spend Not Earned Back", "format": "usd", "expression": "max(0, total_spend - total_holdout_revenue)"},
            {"label": "Claimed return minus proven return", "format": "x2", "expression": "reported_roas - iroas"},
        ],
        "title": "{campaign_id}: {m2} spent has not been earned back",
        "callout": ("{channel} reports a {reported_roas}x return, but our control tests show only {iroas}x. "
                    "Given that {m2} of spend has not been earned back, perhaps we should think about cutting this budget in half until a fresh test says otherwise."),
    },
    {
        "id": "ATTRIBUTION_SHIELD_AGENT", "name": "Attribution shield", "persona": PERSONA_AGENCY, "severity": "WARNING",
        "description": "Platform over-claims conversions relative to the holdout; prepare a client governance note.",
        "priority": 20, "action": "CLIENT_GOVERNANCE_AUDIT", "requires_min_tier": "NOT_DECISION_GRADE",
        "trigger": {"all": [{"metric": "inflation_ratio", "op": ">", "value": 1.25}, {"metric": "inflation_ratio", "op": "<=", "value": 3.0}]},
        "value_add": [
            {"label": "How many times the platform overstates results", "format": "x2", "expression": "inflation_ratio"},
            {"label": "How far the claim sits above the proven return", "format": "pct1", "expression": "(reported_roas / iroas - 1) * 100"},
            {"label": "Proven Return", "format": "x2", "expression": "iroas"},
        ],
        "title": "{campaign_id}: the platform claims more than our tests support",
        "callout": ("{channel} reports a {reported_roas}x return, while our tests prove {iroas}x. The platform is claiming {inflation_ratio:.2f} times the conversions we can confirm. "
                    "In order to address the gap, we might want to think about explaining to the client how overlapping credit is counted and anchoring reporting on the test results."),
    },
    {
        "id": "SCALE_OPPORTUNITY_AGENT", "name": "Scale opportunity", "persona": PERSONA_PLATFORM, "severity": "OPPORTUNITY",
        "description": "High incremental return with low over-attribution: room to scale spend.",
        "priority": 30, "action": "SCALE_BUDGET_25%", "requires_min_tier": "DIRECTIONAL",
        "trigger": {"all": [{"metric": "iroas", "op": ">=", "value": 3.0}, {"metric": "inflation_ratio", "op": "<=", "value": 1.25}]},
        "value_add": [
            {"label": "Proven Return", "format": "x2", "expression": "iroas"},
            {"label": "How closely the platform matches our tests", "format": "text", "expression": "'Close match'"},
            {"label": "Revenue a quarter more budget could add", "format": "usd", "expression": "total_spend * 0.25 * iroas"},
        ],
        "title": "{campaign_id}: a strong, proven return",
        "callout": ("{channel} earns a strong return, and the platform's own numbers line up with our tests. Given that, perhaps we should think about raising this budget by a quarter, "
                    "which would add about {m3} of revenue if today's return holds."),
    },
]


def preset_ids() -> List[str]:
    return [p["id"] for p in PRESETS]
