"""Run history, comparison, agent inbox, audit log and exports."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import TIER_BADGE, get_store, identity, page_setup, safe_csv, succeeded_runs  # noqa: E402

page_setup("Runs",":material/history:")

import json  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from run_compare import compare_runs  # noqa: E402
from run_store import StoreError  # noqa: E402

store = get_store()
actor, ws = identity()
runs = store.list_runs(ws)

import ui  # noqa: E402

ui.page_head("History and audit", "Runs", "Every analysis is saved with the exact data, policy and code that produced it, so any number can be traced, compared and exported.")
if not runs:
    st.info("No runs yet. Upload data or load the demo from the Dashboard page.")
    st.stop()

tab_runs, tab_compare, tab_inbox, tab_audit = st.tabs(["Run history", "Compare runs", "Agent inbox", "Audit log"])

with tab_runs:
    rows = [{"Run": r["id"], "Label": r["label"], "Status": r["status"], "Created": r["created_at"], "Finished": r["finished_at"],
             "Policy": r["settings_fingerprint"], "Headline": r["settings"]["headline_metric"], "Error": r["error"] or ""} for r in runs]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    ok = [r for r in runs if r["status"] == "succeeded"]
    if ok:
        pick = st.selectbox("Export a run", [r["id"] for r in ok], format_func=lambda i: next(f"{r['label'] or 'Run'} · {r['created_at'][:16]}" for r in ok if r["id"] == i))
        audit = store.load_audit(ws, pick)
        tiers = audit["tier_counts"]
        st.caption(f"Trust tiers: {TIER_BADGE['VERIFIED']} {tiers['VERIFIED']} · {TIER_BADGE['DIRECTIONAL']} {tiers['DIRECTIONAL']} · "
                   f"{TIER_BADGE['NOT_DECISION_GRADE']} {tiers['NOT_DECISION_GRADE']}")
        c1, c2, c3 = st.columns(3)
        c1.download_button("Audit report (JSON)", json.dumps(audit, indent=2, default=str), f"audit_{pick}.json", "application/json")
        c2.download_button("Reconciliation (CSV)", safe_csv(store.load_table(ws, pick, "ANALYTICS_MEASUREMENT_RECONCILIATION")), f"reconciliation_{pick}.csv", "text/csv")
        c3.download_button("Governance alerts (CSV)", safe_csv(store.load_table(ws, pick, "GOVERNANCE_CAMPAIGN_ALERTS")), f"alerts_{pick}.csv", "text/csv")

with tab_compare:
    ok = [r for r in runs if r["status"] == "succeeded"]
    if len(ok) < 2:
        st.info("Compare needs at least two successful runs, for example this month and last month, or two policies on the same data.")
    else:
        fmt = lambda i: next(f"{r['label'] or 'Run'} · {r['created_at'][:16]} · policy {r['settings_fingerprint'][:6]}" for r in ok if r["id"] == i)  # noqa: E731
        a = st.selectbox("Baseline run (A)", [r["id"] for r in ok], index=len(ok) - 1, format_func=fmt)
        b = st.selectbox("Comparison run (B)", [r["id"] for r in ok], index=0, format_func=fmt)
        cmp = compare_runs(store, ws, a, b)
        show = cmp["campaigns"][["campaign_id", "channel", "total_spend_delta", "spec_iroas_a", "spec_iroas_b", "strict_iroas_a",
                                 "strict_iroas_b", "trust_score_delta", "tier_a", "tier_b"]]
        st.dataframe(show.round(3), width="stretch", hide_index=True)
        c1, c2 = st.columns(2)
        c1.markdown("**Agents newly fired in B**\n\n" + ("\n".join(f"* {x}" for x in cmp["agents_added"]) or "None"))
        c2.markdown("**Agents cleared in B**\n\n" + ("\n".join(f"* {x}" for x in cmp["agents_cleared"]) or "None"))

with tab_inbox:
    status = st.multiselect("Status", ["new", "reviewed", "approved", "executed", "dismissed", "superseded"], default=["new", "reviewed", "approved"])
    items = [i for i in store.list_inbox(ws) if i["status"] in status]
    if not items:
        st.info("Nothing in the inbox for these statuses.")
    for it in items:
        p = it["packet"]
        with st.container(border=True):
            st.markdown(f"**{ui.scrub(p['title'])}**  \nStatus **{it['status']}** · run `{it['run_id']}` · {p['agent_id']}")
            st.caption(p["strategic_callout"])
            sig = store.get_signoff(ws, it["id"])
            if sig:
                st.caption(f"Signed: {sig['outcome'].capitalize()} by {sig['email']} ({sig['role']}) on {sig['created_at'][:10]}.")
            elif it["status"] in ("new", "reviewed"):
                if st.button("Review and sign", key=f"rs{it['id']}"):
                    st.session_state["signoff_item"] = it["id"]
                    st.switch_page("pages/12_Signoff.py")

with tab_audit:
    ev = store.list_audit_events(ws)
    st.dataframe(pd.DataFrame(ev).drop(columns=["workspace_id"], errors="ignore"), width="stretch", hide_index=True) if ev else st.info("No events yet.")
