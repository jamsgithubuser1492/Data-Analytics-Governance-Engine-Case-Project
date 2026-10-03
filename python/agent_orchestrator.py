"""Event-driven agent orchestrator for the MMGE.

Evaluates campaign reconciliation metrics against trigger ranges and dispatches
persona targeted "software packets" (plain dicts the Streamlit app renders).
Triggers are evaluated independently, so one campaign can fire several agents.

    CAPITAL_PRESERVATION_AGENT  reported_roas >= 1.5 AND incremental_roas < 1.0
    ATTRIBUTION_SHIELD_AGENT    1.25 < inflation_ratio <= 3.0
    SCALE_OPPORTUNITY_AGENT     incremental_roas >= 3.0 AND inflation_ratio <= 1.25
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECON = ROOT / "outputs" / "analytics_measurement_reconciliation.csv"
ACTION_LOG = ROOT / "outputs" / "snowflake_governance_action_log.jsonl"

PERSONA_CFO = "Brand CFO / Growth VP"
PERSONA_AGENCY = "Marketing Agency Director"
PERSONA_PLATFORM = "Tech Platform Lead / Growth Lead"

REQUIRED_COLUMNS = ["channel", "campaign_id", "total_spend", "total_platform_conversions",
                    "total_holdout_conversions", "total_holdout_revenue",
                    "reported_roas", "incremental_roas", "inflation_ratio"]

CAPITAL_MIN_REPORTED_ROAS = 1.5
CAPITAL_MAX_IROAS = 1.0
SHIELD_MIN_EXCLUSIVE = 1.25
SHIELD_MAX_INCLUSIVE = 3.0
SCALE_MIN_IROAS = 3.0
SCALE_MAX_INFLATION = 1.25
SCALE_SPEND_INCREASE = 0.25


def _valid(*values: Any) -> bool:
    """True when every value is a real (non-null, non-NaN) number."""
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in values)


class AgentOrchestrator:
    """Evaluates reconciliation rows and dispatches agent packets."""

    def __init__(self, recon_df: pd.DataFrame) -> None:
        missing = [c for c in REQUIRED_COLUMNS if c not in recon_df.columns]
        if missing:
            raise ValueError(f"Reconciliation data missing columns: {missing}")
        self.recon_df = recon_df.reset_index(drop=True)

    @classmethod
    def from_csv(cls, recon_filepath: Union[str, Path] = DEFAULT_RECON) -> "AgentOrchestrator":
        """Build an orchestrator from the exported reconciliation CSV."""
        path = Path(recon_filepath)
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run python python/database_manager.py first.")
        return cls(pd.read_csv(path))

    # ---------------------------------------------------------------- triggers
    @staticmethod
    def should_trigger_capital(reported_roas: float, iroas: float) -> bool:
        return _valid(reported_roas, iroas) and reported_roas >= CAPITAL_MIN_REPORTED_ROAS and iroas < CAPITAL_MAX_IROAS

    @staticmethod
    def should_trigger_shield(inflation: float) -> bool:
        return _valid(inflation) and SHIELD_MIN_EXCLUSIVE < inflation <= SHIELD_MAX_INCLUSIVE

    @staticmethod
    def should_trigger_scale(iroas: float, inflation: float) -> bool:
        return _valid(iroas, inflation) and iroas >= SCALE_MIN_IROAS and inflation <= SCALE_MAX_INFLATION

    def evaluate_triggers(self) -> List[Dict[str, Any]]:
        """Return a packet for every agent whose trigger condition is met."""
        packets: List[Dict[str, Any]] = []
        for _, row in self.recon_df.iterrows():
            roas, iroas, infl = row["reported_roas"], row["incremental_roas"], row["inflation_ratio"]
            if self.should_trigger_capital(roas, iroas):
                packets.append(self._capital_preservation_agent(row))
            if self.should_trigger_shield(infl):
                packets.append(self._attribution_shield_agent(row))
            if self.should_trigger_scale(iroas, infl):
                packets.append(self._scale_opportunity_agent(row))
        return packets

    # ------------------------------------------------------------------ agents
    @staticmethod
    def _capital_preservation_agent(row: pd.Series) -> Dict[str, Any]:
        spend, inc_rev = float(row["total_spend"]), float(row["total_holdout_revenue"])
        plat_conv, hold_conv = float(row["total_platform_conversions"]), float(row["total_holdout_conversions"])
        cannibalization = max(0.0, (plat_conv - hold_conv) / plat_conv * 100.0) if plat_conv > 0 else 0.0
        net_unrecouped = max(0.0, spend - inc_rev)
        return {
            "packet_id": f"CAPITAL_PRESERVATION_AGENT:{row['campaign_id']}",
            "agent_id": "CAPITAL_PRESERVATION_AGENT", "target_persona": PERSONA_CFO,
            "campaign_id": row["campaign_id"], "channel": row["channel"], "severity": "CRITICAL",
            "title": f"🚨 Capital Loss Detected: {row['campaign_id']}",
            "value_add_metrics": {
                "Unearned Organic Cannibalization": f"{cannibalization:.1f}%",
                "Net Unrecouped Spend": f"${net_unrecouped:,.2f}",
                "Marginal iROAS Gap": f"{float(row['reported_roas']) - float(row['incremental_roas']):.2f}x",
            },
            "raw_metrics": {"cannibalization_pct": cannibalization, "net_unrecouped_spend": net_unrecouped},
            "strategic_callout": (
                f"{row['channel']} claims {row['reported_roas']}x ROAS but randomized holdouts show only "
                f"{row['incremental_roas']}x. Reduce budget by 50% and reallocate ${net_unrecouped:,.2f} "
                "of unrecouped spend to proven channels."),
            "recommended_action": "REDUCE_BUDGET_50%",
        }

    @staticmethod
    def _attribution_shield_agent(row: pd.Series) -> Dict[str, Any]:
        roas, iroas = float(row["reported_roas"]), float(row["incremental_roas"])
        margin = (roas / iroas - 1.0) * 100.0 if iroas > 0 else float("inf")
        margin_txt = f"{margin:.1f}%" if math.isfinite(margin) else "n/a"
        return {
            "packet_id": f"ATTRIBUTION_SHIELD_AGENT:{row['campaign_id']}",
            "agent_id": "ATTRIBUTION_SHIELD_AGENT", "target_persona": PERSONA_AGENCY,
            "campaign_id": row["campaign_id"], "channel": row["channel"], "severity": "WARNING",
            "title": f"⚠️ Attribution Inflation Warning: {row['campaign_id']}",
            "value_add_metrics": {
                "Platform Over-Claim Multiplier": f"{float(row['inflation_ratio']):.2f}x",
                "Model Discrepancy Margin": margin_txt,
                "Audited True iROAS": f"{iroas:.2f}x",
            },
            "raw_metrics": {"over_claim_multiplier": float(row["inflation_ratio"]), "discrepancy_margin_pct": margin},
            "strategic_callout": (
                f"Client governance note: {row['channel']} reports {roas}x ROAS versus {iroas}x holdout "
                f"iROAS (platform claims {float(row['inflation_ratio']):.2f}x the verified conversions). "
                "Explain MTA deduplication and anchor reporting on holdout results."),
            "recommended_action": "CLIENT_GOVERNANCE_AUDIT",
        }

    @staticmethod
    def _scale_opportunity_agent(row: pd.Series) -> Dict[str, Any]:
        iroas, spend = float(row["incremental_roas"]), float(row["total_spend"])
        gain = spend * SCALE_SPEND_INCREASE * iroas
        return {
            "packet_id": f"SCALE_OPPORTUNITY_AGENT:{row['campaign_id']}",
            "agent_id": "SCALE_OPPORTUNITY_AGENT", "target_persona": PERSONA_PLATFORM,
            "campaign_id": row["campaign_id"], "channel": row["channel"], "severity": "OPPORTUNITY",
            "title": f"🚀 High-Incrementality Scale Target: {row['campaign_id']}",
            "value_add_metrics": {
                "Incremental Return": f"{iroas:.2f}x",
                "Platform Alignment Score": "High (Low Over-reporting)",
                "Est. Revenue Gain (+25% Spend)": f"${gain:,.2f}",
            },
            "raw_metrics": {"projected_gain": gain, "added_spend": spend * SCALE_SPEND_INCREASE},
            "strategic_callout": (
                f"{row['channel']} shows strong incrementality with minimal over-attribution. A 25% budget "
                f"increase projects ${gain:,.2f} of incremental revenue (assumes constant marginal iROAS)."),
            "recommended_action": "SCALE_BUDGET_25%",
        }

    # ------------------------------------------------------------- action log
    @staticmethod
    def log_action(packet: Dict[str, Any], log_path: Optional[Path] = None) -> Dict[str, Any]:
        """Simulate writing an executed action to the Snowflake governance queue.

        Appends a JSON line locally and returns the record including the
        INSERT statement that would run against Snowflake.
        """
        record = {
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "packet_id": packet["packet_id"], "agent_id": packet["agent_id"],
            "campaign_id": packet["campaign_id"], "action": packet["recommended_action"],
        }
        record["snowflake_sql"] = (
            "INSERT INTO MMGE_DB.GOVERNANCE.ACTION_QUEUE (executed_at, agent_id, campaign_id, action) "
            f"VALUES ('{record['executed_at']}', '{record['agent_id']}', "
            f"'{record['campaign_id']}', '{record['action']}');")
        path = Path(log_path) if log_path else ACTION_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return record


if __name__ == "__main__":
    for p in AgentOrchestrator.from_csv().evaluate_triggers():
        print(f"[{p['severity']:<11}] {p['agent_id']:<27} {p['campaign_id']:<20} {p['value_add_metrics']}")
