"""Facts for memos: every number a memo may contain is a Fact the code produced.

A FactSet is built from an agent packet plus the campaign's facts row. The memo writer
(template or AI) may only cite these facts as [F1], [F2], ...; the verifier rejects any
number that does not match a fact cited in the same sentence.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_schema import ACTIONS

KINDS = ("multiple", "usd", "pct", "pct0", "number", "int")


@dataclass
class Fact:
    id: str
    key: str
    label: str
    value: float
    kind: str  # multiple (x), usd ($), pct (%), pct0 (% with no decimals), number, int
    display: str


@dataclass
class FactSet:
    facts: List[Fact]
    text: Dict[str, str]  # untrusted or descriptive strings: channel, campaign_id, tier, persona, action_label, headline_label
    by_key: Dict[str, Fact] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_key = {f.key: f for f in self.facts}

    def get(self, key: str) -> Optional[Fact]:
        return self.by_key.get(key)

    def by_id(self) -> Dict[str, Fact]:
        return {f.id: f for f in self.facts}

    def to_prompt(self) -> List[Dict[str, str]]:
        return [{"id": f.id, "label": f.label, "display": f.display} for f in self.facts]

    def allowed_text(self) -> List[str]:
        """Strings that may appear verbatim and contain digits (campaign ids, names)."""
        return [v for v in self.text.values() if v] + [f.label for f in self.facts]


_LINK = re.compile(r"https?://\S+|www\.\S+", re.I)


def sanitize_label(value: Any, limit: int = 80) -> str:
    """Make an untrusted name safe to show in a memo: no control characters, links, markup or brackets, bounded length."""
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    s = _LINK.sub("(link removed)", s)
    s = re.sub(r"[<>`\[\]()]", "", s) if "(link removed)" not in s else re.sub(r"[<>`\[\]]", "", s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def display(value: float, kind: str) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return {"multiple": f"{value:.2f}x", "usd": f"${value:,.2f}", "pct": f"{value:.1f}%", "pct0": f"{value:.0f}%",
            "number": f"{value:,.2f}", "int": f"{value:,.0f}"}[kind]


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def build_factset(packet: Dict[str, Any], row: Dict[str, Any], headline_label: str, strict_view: bool = False) -> FactSet:
    """Facts for one packet: core campaign metrics, the agent's value-add results, and policy percentages."""
    facts: List[Fact] = []

    def add(key: str, label: str, value: Any, kind: str) -> None:
        v = _num(value)
        if v is not None:
            facts.append(Fact(f"F{len(facts) + 1}", key, label, v, kind, display(v, kind)))

    add("total_spend", "Media spend" + (" (test period)" if strict_view else ""), row.get("total_spend"), "usd")
    add("reported_roas", "Platform reported return on ad spend", row.get("reported_roas"), "multiple")
    add("iroas", f"Measured incremental return ({headline_label})", row.get("iroas"), "multiple")
    add("inflation_ratio", "Platform claimed conversions divided by holdout conversions", row.get("inflation_ratio"), "multiple")
    add("trust_score", "Trust score out of 100", row.get("trust_score"), "number")
    if _num(row.get("margin")) is not None:
        add("margin", "Margin used for breakeven", _num(row["margin"]) * 100, "pct")
        add("breakeven_iroas", "Breakeven iROAS at that margin", row.get("breakeven_iroas"), "multiple")
        add("profit_per_dollar", "Profit per ad dollar at that margin", row.get("profit_per_dollar"), "usd")
    for m in packet.get("value_add_metrics", {}):
        raw = packet.get("raw_metrics", {}).get(m)
        kind = _kind_from_display(packet["value_add_metrics"][m])
        if _num(raw) is not None and kind:
            add(f"va:{m}", m, raw, kind)
    action = packet.get("recommended_action", "")
    for tok in ("50%", "25%"):
        if tok in action:
            add(f"policy:{tok}", f"Action size ({action})", float(tok.rstrip("%")), "pct0")
    label = ACTIONS.get(action, (action, False))[0]
    text = {"channel": sanitize_label(packet.get("channel", "")), "campaign_id": sanitize_label(packet.get("campaign_id", "")),
            "tier": str(packet.get("tier", "")).replace("_", " ").title(), "persona": str(packet.get("target_persona", "")),
            "action_label": label, "headline_label": headline_label, "agent_name": sanitize_label(packet.get("agent_name", packet.get("agent_id", "")))}
    return FactSet(facts, text)


def _kind_from_display(d: str) -> Optional[str]:
    if d.startswith("$"):
        return "usd"
    if d.endswith("%"):
        return "pct"
    if d.endswith("x"):
        return "multiple"
    return "number" if d and d[0].isdigit() or d[:1] == "-" else None
