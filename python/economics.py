"""Profit aware returns: margin resolution, breakeven iROAS and profit per dollar.

Revenue return of 1.0x is breakeven only at a 100% margin. With a contribution margin m, a dollar of
incremental revenue earns m, so breakeven iROAS is 1 / m and profit per ad dollar is iROAS * m - 1.

A margin is never assumed silently: it is either declared by the user or taken from a labeled
industry proxy in the benchmark registry (an UPPER bound on a brand's contribution margin, hence a
LOWER bound on its true breakeven).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from config import PolicySettings


def breakeven_iroas(margin: Optional[float]) -> Optional[float]:
    return None if margin is None or margin <= 0 else 1.0 / margin


def profit_per_dollar(iroas: Optional[float], margin: Optional[float]) -> Optional[float]:
    if iroas is None or margin is None:
        return None
    return iroas * margin - 1.0


def resolve_economics(settings: PolicySettings, registry: Any = None) -> Dict[str, Any]:
    """Margin, its source and breakeven. ``source`` is 'user', 'benchmark' or None."""
    if settings.gross_margin is not None:
        m = float(settings.gross_margin)
        return {"margin": m, "source": "user", "industry": "", "breakeven_iroas": breakeven_iroas(m),
                "note": "Contribution margin declared by you.", "benchmark_set_version": None, "record_id": None}
    if settings.margin_industry:
        if registry is None:
            raise ValueError("A benchmark registry is required to use an industry margin")
        rec = registry.gross_margin(settings.margin_industry)
        m = float(rec["value"])
        return {"margin": m, "source": "benchmark", "industry": settings.margin_industry, "breakeven_iroas": breakeven_iroas(m),
                "note": (f"Industry proxy: aggregate gross margin of US public companies in '{settings.margin_industry}' "
                         f"({rec['source_publisher']}, updated {rec['as_of']}). Your contribution margin is lower, so your true breakeven is higher."),
                "benchmark_set_version": registry.version, "record_id": rec["value_id"]}
    return {"margin": None, "source": None, "industry": "", "breakeven_iroas": None, "note": "No margin declared: returns are shown as revenue returns only.",
            "benchmark_set_version": None, "record_id": None}
