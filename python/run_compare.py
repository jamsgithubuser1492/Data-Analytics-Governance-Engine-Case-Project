"""Compare two runs of the same workspace: per campaign deltas and agent changes."""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from run_store import SqlRunStore


def _campaign_frame(store: SqlRunStore, ws: str, run_id: str) -> pd.DataFrame:
    audit = store.load_audit(ws, run_id)
    c = pd.DataFrame(audit["campaigns"])[["campaign_id", "channel", "trust_score", "tier", "spec_iroas", "strict_iroas"]]
    recon = store.load_table(ws, run_id, "ANALYTICS_MEASUREMENT_RECONCILIATION")[["campaign_id", "total_spend"]]
    return c.merge(recon, on="campaign_id", how="left")


def compare_runs(store: SqlRunStore, workspace_id: str, run_a: str, run_b: str) -> Dict[str, Any]:
    """Return {'campaigns': DataFrame of deltas (b minus a), 'agents_added': [...], 'agents_cleared': [...]}."""
    a, b = _campaign_frame(store, workspace_id, run_a), _campaign_frame(store, workspace_id, run_b)
    m = a.merge(b, on="campaign_id", how="outer", suffixes=("_a", "_b"))
    out = pd.DataFrame({"campaign_id": m["campaign_id"], "channel": m["channel_b"].fillna(m["channel_a"])})
    for col in ("total_spend", "trust_score", "spec_iroas", "strict_iroas"):
        out[f"{col}_a"], out[f"{col}_b"] = m[f"{col}_a"], m[f"{col}_b"]
        out[f"{col}_delta"] = m[f"{col}_b"] - m[f"{col}_a"]
    out["tier_a"], out["tier_b"] = m["tier_a"], m["tier_b"]
    out["tier_changed"] = out["tier_a"] != out["tier_b"]
    pk = lambda rid: {i["packet"]["agent_id"] + "|" + i["packet"]["campaign_id"] for i in store.list_inbox(workspace_id, run_id=rid)}  # noqa: E731
    pa, pb = pk(run_a), pk(run_b)
    return {"campaigns": out.sort_values("campaign_id").reset_index(drop=True),
            "agents_added": sorted(pb - pa), "agents_cleared": sorted(pa - pb)}
