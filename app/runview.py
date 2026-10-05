"""Load one stored run into the frames every page needs (shared by the dashboard and the advisory council)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

import dashdata as dd
from config import HEADLINE_STRICT, PolicySettings


@dataclass
class RunView:
    run: Dict[str, Any]
    settings: PolicySettings
    report: Dict[str, Any]
    recon: pd.DataFrame
    audit: pd.DataFrame
    rolling: pd.DataFrame
    alerts: pd.DataFrame
    camp: pd.DataFrame
    cd: pd.DataFrame
    ch: pd.DataFrame
    tot: Dict[str, Any]
    breakeven: float
    margin: Optional[float]
    econ: Dict[str, Any]
    is_strict: bool
    holdout_coverage: float

    @property
    def basis(self) -> str:
        return "Strict lift" if self.is_strict else "Reported by spec"


def build_view(run: Dict[str, Any], tables: Dict[str, pd.DataFrame], report: Dict[str, Any]) -> RunView:
    settings = PolicySettings(**run["settings"])
    is_strict = settings.headline_metric == HEADLINE_STRICT
    econ = report.get("economics") or {}
    be = econ.get("breakeven_iroas") or 1.0
    margin = econ.get("margin")
    recon, audit = tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], tables["GOVERNANCE_AUDIT_SUMMARY"]
    camp = pd.DataFrame(report["campaigns"])
    cd = dd.campaign_frame(recon, camp, is_strict, be, margin)
    cd["test_spend"] = cd["campaign_id"].map(camp.set_index("campaign_id")["test_period_spend"])
    ch = dd.channel_frame(cd, audit, is_strict, be)
    tot = dd.portfolio_totals(cd, ch, is_strict)
    ch = dd.with_actions(ch, be, tot["proven"])
    cov = ((run.get("validation") or {}).get("coverage") or {})
    return RunView(run, settings, report, recon, audit, tables["ROLLING_7D_PERFORMANCE"], tables["GOVERNANCE_CAMPAIGN_ALERTS"], camp, cd, ch, tot, be, margin, econ,
                   is_strict, float(cov.get("holdout", 1.0) or 0.0))


def load_view(store: Any, ws: str, run_id: str) -> RunView:
    names = ("ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_AUDIT_SUMMARY", "ROLLING_7D_PERFORMANCE", "GOVERNANCE_CAMPAIGN_ALERTS")
    return build_view(store.get_run(ws, run_id), {n: store.load_table(ws, run_id, n) for n in names}, store.load_audit(ws, run_id))
