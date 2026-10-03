"""MMGE executive dashboard (Streamlit).

Run:  streamlit run app/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from agent_orchestrator import (PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM,  # noqa: E402
                                AgentOrchestrator)
from database_manager import OUTPUT_DIR, DatabaseManager  # noqa: E402

ROLES: Dict[str, str] = {
    "All Roles": "",
    "Brand CFO": PERSONA_CFO,
    "Agency Director": PERSONA_AGENCY,
    "Platform Lead": PERSONA_PLATFORM,
}
CHANNEL_COLORS = {"Meta Ads": "#2a78d6", "Google Ads": "#eb6834", "TikTok Ads": "#1baf7a", "Netflix Ads": "#eda100"}
SERIES_COLORS = {"Platform ROAS": "#2a78d6", "MTA ROAS": "#eb6834", "Incremental iROAS": "#1baf7a"}
SEVERITY_ICON = {"CRITICAL": "🔴", "WARNING": "🟡", "OPPORTUNITY": "🟢"}

st.set_page_config(page_title="MMGE Executive Dashboard", page_icon="🛡️", layout="wide")


@st.cache_data(show_spinner="Running measurement pipeline...")
def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, List[dict]]:
    """Load pipeline outputs (building them with DuckDB if absent) and run the agents."""
    needed = ["analytics_measurement_reconciliation.csv", "governance_audit_summary.csv",
              "rolling_7d_performance.csv", "view_governance_campaign_alerts.csv"]
    if not all((OUTPUT_DIR / f).exists() for f in needed):
        DatabaseManager().build().export_outputs()
    recon = pd.read_csv(OUTPUT_DIR / "analytics_measurement_reconciliation.csv")
    audit = pd.read_csv(OUTPUT_DIR / "governance_audit_summary.csv")
    rolling = pd.read_csv(OUTPUT_DIR / "rolling_7d_performance.csv", parse_dates=["date"])
    alerts = pd.read_csv(OUTPUT_DIR / "view_governance_campaign_alerts.csv")
    packets = AgentOrchestrator(recon).evaluate_triggers()
    return recon, audit, rolling, alerts, packets


def style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, template="plotly_white", legend_title_text="", margin=dict(t=60, b=40),
                      hovermode="x unified")
    return fig


recon, audit, rolling, alerts, packets = load_data()

# ------------------------------------------------------------------ header + sidebar
st.title("🛡️ Media Measurement & Governance Engine")
st.caption("Platform claims vs MTA vs geo holdout incrementality, with agent driven executive alerts.")
st.sidebar.header("🎯 Leadership Perspective")
role = st.sidebar.selectbox("Filter agent insights by role", list(ROLES))
st.sidebar.caption("Agents fire only when metrics cross decision thresholds, to avoid alert fatigue.")

# ------------------------------------------------------------------------ KPI cards
total_spend = float(audit["total_spend"].sum())
inc_revenue = float(audit["total_holdout_revenue"].sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Media Spend", f"${total_spend:,.0f}")
c2.metric("Total Incremental Revenue", f"${inc_revenue:,.0f}")
c3.metric("Blended iROAS", f"{inc_revenue / total_spend:.2f}x" if total_spend else "n/a")
c4.metric("Active Agent Packets", len(packets))
st.divider()

# -------------------------------------------------------------------- agent packets
st.subheader("🤖 Agent Software Packets")
visible = [p for p in packets if not ROLES[role] or p["target_persona"] == ROLES[role]]
if not visible:
    st.success("No threshold triggers are active for this role. All channels are within nominal parameters.")
for p in visible:
    with st.container(border=True):
        st.markdown(f"#### {SEVERITY_ICON[p['severity']]} {p['title']}")
        st.caption(f"Agent `{p['agent_id']}` · Target role: {p['target_persona']} · Channel: {p['channel']}")
        cols = st.columns(len(p["value_add_metrics"]))
        for col, (name, val) in zip(cols, p["value_add_metrics"].items()):
            col.metric(name, val)
        st.markdown(f"**Strategic callout:** {p['strategic_callout']}")
        if st.button(f"Execute Action: {p['recommended_action']}", key=p["packet_id"]):
            rec = AgentOrchestrator.log_action(p)
            st.toast("Action logged to the Snowflake governance queue (simulated).", icon="✅")
            st.code(rec["snowflake_sql"], language="sql")
st.divider()

# --------------------------------------------------------------------------- charts
st.subheader("📊 Measurement Reconciliation")
long = audit.melt(id_vars="channel", value_vars=["platform_roas", "mta_roas", "incremental_roas"],
                  var_name="source", value_name="roas")
long["source"] = long["source"].map({"platform_roas": "Platform ROAS", "mta_roas": "MTA ROAS",
                                     "incremental_roas": "Incremental iROAS"})
fig_roas = go.Figure()
for src, color in SERIES_COLORS.items():
    d = long[long["source"] == src]
    fig_roas.add_bar(x=d["channel"], y=d["roas"], name=src, marker_color=color,
                     text=d["roas"].map("{:.2f}x".format), textposition="outside")
fig_roas.add_hline(y=1.0, line_dash="dot", line_color="#52514e", annotation_text="Breakeven 1.0x")
fig_roas.update_layout(barmode="group", yaxis_title="Return on ad spend (x)")
st.plotly_chart(style(fig_roas, "Channel ROAS Comparison: Platform vs MTA vs Incremental"), width="stretch")

fig_infl = go.Figure()
for ch, color in CHANNEL_COLORS.items():
    d = recon[recon["channel"] == ch]
    fig_infl.add_bar(x=d["campaign_id"], y=d["inflation_ratio"], name=ch, marker_color=color,
                     text=d["inflation_ratio"].map("{:.2f}x".format), textposition="outside")
fig_infl.add_hline(y=1.5, line_dash="dash", line_color="#d03b3b", annotation_text="Warning threshold 1.5x")
fig_infl.update_layout(yaxis_title="Platform conversions / holdout conversions (x)", xaxis_tickangle=-30)
st.plotly_chart(style(fig_infl, "Campaign Inflation Multipliers"), width="stretch")

ch_roll = (rolling.groupby(["date", "channel"], as_index=False)[["rolling_7d_incremental_revenue", "rolling_7d_spend"]].sum())
ch_roll["iroas"] = ch_roll["rolling_7d_incremental_revenue"] / ch_roll["rolling_7d_spend"]
fig_roll = go.Figure()
for ch, color in CHANNEL_COLORS.items():
    d = ch_roll[ch_roll["channel"] == ch]
    fig_roll.add_scatter(x=d["date"], y=d["iroas"], name=ch, mode="lines", line=dict(color=color, width=2))
fig_roll.add_hline(y=1.0, line_dash="dot", line_color="#52514e", annotation_text="Breakeven 1.0x")
fig_roll.update_layout(yaxis_title="7 day rolling iROAS (x)")
st.plotly_chart(style(fig_roll, "7-Day Rolling iROAS by Channel"), width="stretch")

with st.expander("Table view of the charted data"):
    st.dataframe(audit, width="stretch", hide_index=True)
    st.dataframe(alerts, width="stretch", hide_index=True)
st.divider()

# ------------------------------------------------------------------- scenario simulator
st.subheader("🎛️ Budget Reallocation Scenario Simulator")
a = audit.set_index("channel")
nf_spend, nf_rev = float(a.loc["Netflix Ads", "total_spend"]), float(a.loc["Netflix Ads", "total_holdout_revenue"])
g_iroas, m_iroas = float(a.loc["Google Ads", "incremental_roas"]), float(a.loc["Meta Ads", "incremental_roas"])
s1, s2 = st.columns(2)
shift = s1.slider("Netflix spend to shift ($)", 0.0, nf_spend, nf_spend, step=1000.0)
google_pct = s2.slider("Share of shifted spend sent to Google (rest to Meta)", 0, 100, 50, step=5)
google_amt, meta_amt = shift * google_pct / 100, shift * (100 - google_pct) / 100
gross = google_amt * g_iroas + meta_amt * m_iroas
lost = nf_rev * (shift / nf_spend) if nf_spend else 0.0
net_gain = gross - lost
k1, k2, k3 = st.columns(3)
k1.metric("Projected revenue from reallocation", f"${gross:,.0f}")
k2.metric("Netflix revenue given up", f"-${lost:,.0f}")
k3.metric("Projected net revenue gain", f"${net_gain:+,.0f}")
st.caption(f"Google iROAS {g_iroas:.2f}x, Meta iROAS {m_iroas:.2f}x. Assumes average iROAS holds at the new spend "
           "level; real marginal returns fall as channels saturate, so validate with a scaled test first.")
