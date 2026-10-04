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
            {"label": "Unearned Organic Cannibalization", "format": "pct1",
             "expression": "max(0, div(total_platform_conversions - total_holdout_conversions, total_platform_conversions) * 100)"},
            {"label": "Net Unrecouped Spend", "format": "usd", "expression": "max(0, total_spend - total_holdout_revenue)"},
            {"label": "Marginal iROAS Gap", "format": "x2", "expression": "reported_roas - iroas"},
        ],
        "title": "🚨 Capital Loss Detected: {campaign_id}",
        "callout": ("{channel} claims {reported_roas}x ROAS but randomized holdouts show only {iroas}x. "
                    "Reduce budget by 50% and reallocate {m2} of unrecouped spend to proven channels."),
    },
    {
        "id": "ATTRIBUTION_SHIELD_AGENT", "name": "Attribution shield", "persona": PERSONA_AGENCY, "severity": "WARNING",
        "description": "Platform over-claims conversions relative to the holdout; prepare a client governance note.",
        "priority": 20, "action": "CLIENT_GOVERNANCE_AUDIT", "requires_min_tier": "NOT_DECISION_GRADE",
        "trigger": {"all": [{"metric": "inflation_ratio", "op": ">", "value": 1.25}, {"metric": "inflation_ratio", "op": "<=", "value": 3.0}]},
        "value_add": [
            {"label": "Platform Over-Claim Multiplier", "format": "x2", "expression": "inflation_ratio"},
            {"label": "Model Discrepancy Margin", "format": "pct1", "expression": "(reported_roas / iroas - 1) * 100"},
            {"label": "Audited True iROAS", "format": "x2", "expression": "iroas"},
        ],
        "title": "⚠️ Attribution Inflation Warning: {campaign_id}",
        "callout": ("Client governance note: {channel} reports {reported_roas}x ROAS versus {iroas}x holdout iROAS "
                    "(platform claims {inflation_ratio:.2f}x the verified conversions). "
                    "Explain MTA deduplication and anchor reporting on holdout results."),
    },
    {
        "id": "SCALE_OPPORTUNITY_AGENT", "name": "Scale opportunity", "persona": PERSONA_PLATFORM, "severity": "OPPORTUNITY",
        "description": "High incremental return with low over-attribution: room to scale spend.",
        "priority": 30, "action": "SCALE_BUDGET_25%", "requires_min_tier": "DIRECTIONAL",
        "trigger": {"all": [{"metric": "iroas", "op": ">=", "value": 3.0}, {"metric": "inflation_ratio", "op": "<=", "value": 1.25}]},
        "value_add": [
            {"label": "Incremental Return", "format": "x2", "expression": "iroas"},
            {"label": "Platform Alignment Score", "format": "text", "expression": "'High (Low Over-reporting)'"},
            {"label": "Est. Revenue Gain (+25% Spend)", "format": "usd", "expression": "total_spend * 0.25 * iroas"},
        ],
        "title": "🚀 High-Incrementality Scale Target: {campaign_id}",
        "callout": ("{channel} shows strong incrementality with minimal over-attribution. A 25% budget increase "
                    "projects {m3} of incremental revenue (assumes constant marginal iROAS)."),
    },
]


def preset_ids() -> List[str]:
    return [p["id"] for p in PRESETS]
