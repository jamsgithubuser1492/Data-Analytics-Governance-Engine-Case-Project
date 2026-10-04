"""MMGE executive dashboard: reads a stored run (Streamlit home page).

Run:  streamlit run app/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (SEVERITY_ICON, TIER_BADGE, demo_tables, get_runner, get_store, identity, page_setup,  # noqa: E402
                    succeeded_runs, wait_for_run, safe_page_link)

page_setup("Dashboard", "🛡️")

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from agent_orchestrator import PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM  # noqa: E402
from config import HEADLINE_SPEC, HEADLINE_STRICT, PolicySettings  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import StoreError  # noqa: E402

ROLES = {"All Roles": "", "Brand CFO": PERSONA_CFO, "Agency Director": PERSONA_AGENCY, "Platform Lead": PERSONA_PLATFORM}
CHANNEL_COLORS = {"Meta Ads": "#2a78d6", "Google Ads": "#eb6834", "TikTok Ads": "#1baf7a", "Netflix Ads": "#eda100"}
SERIES_COLORS = {"Platform ROAS": "#2a78d6", "MTA ROAS": "#eb6834", "Incremental iROAS": "#1baf7a"}

store, runner = get_store(), get_runner()
actor, ws = identity()
runs = succeeded_runs(ws)

st.title("🛡️ Media Measurement & Governance Engine")
st.caption("Platform claims vs MTA vs geo holdout incrementality, with trust gated agent alerts.")

# ------------------------------------------------------------------ empty state
if not runs:
    st.info("No runs yet in this workspace. Upload your data, or explore with the built in demo data.")
    c1, c2 = st.columns(2)
    if c1.button("Try with demo data", type="primary"):
        rid = runner.submit(ws, demo_tables(), store.latest_workspace_config(ws)[0], store.latest_workspace_config(ws)[1], "Demo data")
        wait_for_run(ws, rid)
        st.rerun()
    with c2:
        safe_page_link("pages/1_Upload.py", "Upload your own data", "📤")
    st.stop()

# -------------------------------------------------------------------- sidebar
st.sidebar.header("🗂️ Run")
labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')} · policy {r['settings_fingerprint'][:6]}" for r in runs}
run_id = st.sidebar.selectbox("Showing run", list(labels), format_func=labels.get)
run = store.get_run(ws, run_id)
settings = PolicySettings(**run["settings"])

st.sidebar.header("🎯 Leadership Perspective")
role = st.sidebar.selectbox("Filter agent insights by role", list(ROLES))

st.sidebar.header("⚙️ Policy")
OPTIONS = {"Reported by spec (all treatment geo revenue)": HEADLINE_SPEC, "Strict lift (causal gap only)": HEADLINE_STRICT}
current = next(k for k, v in OPTIONS.items() if v == settings.headline_metric)
choice = st.sidebar.radio("Headline incrementality metric", list(OPTIONS), index=list(OPTIONS).index(current))
if OPTIONS[choice] != settings.headline_metric:
    inputs = SourceTables(*(store.load_table(ws, run_id, f"INPUT_{n}") for n in
                            ("RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS")))
    new_settings = PolicySettings(**{**settings.to_dict(), "headline_metric": OPTIONS[choice]})
    new_id = runner.submit(ws, inputs, new_settings, run["declarations"], (run["label"] or "Run") + " (view change)")
    wait_for_run(ws, new_id, "Re-running under the new policy...")
    st.rerun()
st.sidebar.caption("Both views are always computed. Changing the headline creates a new run with that policy, so every number "
                   "stays tied to the policy that produced it.")


@st.cache_data(show_spinner=False)
def load(ws_id: str, rid: str):
    t = {n: store.load_table(ws_id, rid, n) for n in ("ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_AUDIT_SUMMARY",
                                                      "ROLLING_7D_PERFORMANCE", "GOVERNANCE_CAMPAIGN_ALERTS")}
    return t, store.load_audit(ws_id, rid)


tables, report = load(ws, run_id)
recon, audit, rolling, alerts = (tables[k] for k in ("ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_AUDIT_SUMMARY",
                                                      "ROLLING_7D_PERFORMANCE", "GOVERNANCE_CAMPAIGN_ALERTS"))
camp = pd.DataFrame(report["campaigns"])
is_strict = settings.headline_metric == HEADLINE_STRICT
label = report["headline_label"]

# ------------------------------------------------------------ plain English briefing
by_ch = camp.groupby("channel").apply(lambda g: pd.Series({
    "iroas": (g["strict_incremental_revenue"].sum() / g["test_period_spend"].sum()) if is_strict
    else g["spec_iroas"].mean(), "tier": g["tier"].iloc[0]}), include_groups=False)
by_ch = by_ch.dropna()
tiers = report["tier_counts"]
if len(by_ch):
    best, worst = by_ch["iroas"].idxmax(), by_ch["iroas"].idxmin()
    st.success(f"**{best}** returns the most at **{by_ch.loc[best, 'iroas']:.2f}x**; **{worst}** returns the least at "
               f"**{by_ch.loc[worst, 'iroas']:.2f}x** ({label}). {tiers['VERIFIED']} of {report['campaigns_audited']} campaigns "
               "are verified, decision grade results.")

# ------------------------------------------------------------------------ KPI cards
total_spend = float(audit["total_spend"].sum())
if is_strict:
    inc_revenue, denom = float(camp["strict_incremental_revenue"].sum()), float(camp["test_period_spend"].sum())
else:
    inc_revenue, denom = float(audit["total_holdout_revenue"].sum()), float(audit["holdout_covered_spend"].sum())
inbox = store.list_inbox(ws, run_id)
open_items = [i for i in inbox if i["status"] in ("new", "reviewed", "approved")]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Media Spend", f"${total_spend:,.0f}")
c2.metric("Total Incremental Revenue", f"${inc_revenue:,.0f}", help=label + (" (test period only)" if is_strict else ""))
c3.metric(f"Blended iROAS ({'strict' if is_strict else 'spec'})", f"{inc_revenue / denom:.2f}x" if denom else "n/a")
c4.metric("Open Agent Packets", len(open_items))
st.caption(f"Headline metric: **{label}** · Trust tiers: {tiers['VERIFIED']} verified, {tiers['DIRECTIONAL']} directional, "
           f"{tiers['NOT_DECISION_GRADE']} not decision grade · Policy v{report['settings_fingerprint']}")
if not is_strict and bool(camp["divergence_warning"].any()):
    st.warning("Reported by spec counts all treatment geo revenue as incremental. The strict causal view is much lower for "
               f"{int(camp['divergence_warning'].sum())} campaign(s). Switch the headline metric in the sidebar to compare.")
if run["validation"]["issues"]:
    with st.expander(f"Data checks recorded for this run ({sum(i['severity'] == 'WARNING' for i in run['validation']['issues'])} warnings)"):
        for i in run["validation"]["issues"]:
            st.write(f"{'🟡' if i['severity'] == 'WARNING' else 'ℹ️'} **{i['rule']}**: {i['message']}")
st.divider()

# -------------------------------------------------------------------- agent packets
st.subheader("🤖 Agent Software Packets")
if is_strict:
    st.caption("Strict lift view: dollar amounts in packets cover the test period only.")
visible = [i for i in inbox if not ROLES[role] or i["packet"]["target_persona"] == ROLES[role]]
if not visible:
    st.success("No threshold triggers are active for this role. All channels are within nominal parameters.")
tier_of = camp.set_index("campaign_id")["tier"].to_dict()
for item in visible:
    p = item["packet"]
    with st.container(border=True):
        st.markdown(f"#### {SEVERITY_ICON[p['severity']]} {p['title']}")
        st.caption(f"Agent `{p['agent_id']}` · Target role: {p['target_persona']} · Channel: {p['channel']} · "
                   f"{TIER_BADGE.get(tier_of.get(p['campaign_id']), '')} · Status: **{item['status']}**")
        cols = st.columns(len(p["value_add_metrics"]))
        for col, (name, val) in zip(cols, p["value_add_metrics"].items()):
            col.metric(name, val)
        st.markdown(f"**Strategic callout:** {p['strategic_callout']}")
        b1, b2, b3 = st.columns([2, 1, 4])
        try:
            if item["status"] in ("new", "reviewed"):
                if b1.button(f"Approve: {p['recommended_action']}", key=f"ap_{item['id']}"):
                    store.transition_inbox(ws, item["id"], "approved", actor, "approved from dashboard")
                    st.rerun()
            elif item["status"] == "approved":
                if b1.button(f"Execute: {p['recommended_action']}", key=f"ex_{item['id']}", type="primary"):
                    store.transition_inbox(ws, item["id"], "executed", actor, "dry run: logged to simulated Snowflake queue")
                    st.toast("Action logged to the governance audit trail (simulated Snowflake queue).", icon="✅")
                    st.rerun()
            if item["status"] in ("new", "reviewed", "approved") and b2.button("Dismiss", key=f"dm_{item['id']}"):
                store.transition_inbox(ws, item["id"], "dismissed", actor)
                st.rerun()
        except StoreError as exc:
            st.error(str(exc))
st.divider()

# --------------------------------------------------------------------------- charts
st.subheader("📊 Measurement Reconciliation")


def style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, template="plotly_white", legend_title_text="", margin=dict(t=60, b=40), hovermode="x unified")
    return fig


long = audit.melt(id_vars="channel", value_vars=["platform_roas", "mta_roas", "incremental_roas"], var_name="source", value_name="roas")
long["source"] = long["source"].map({"platform_roas": "Platform ROAS", "mta_roas": "MTA ROAS", "incremental_roas": "Incremental iROAS"})
fig_roas = go.Figure()
for src, color in SERIES_COLORS.items():
    d = long[long["source"] == src]
    fig_roas.add_bar(x=d["channel"], y=d["roas"], name=src, marker_color=color, text=d["roas"].map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}x"), textposition="outside")
fig_roas.add_hline(y=1.0, line_dash="dot", line_color="#52514e", annotation_text="Breakeven 1.0x")
fig_roas.update_layout(barmode="group", yaxis_title="Return on ad spend (x)")
st.plotly_chart(style(fig_roas, "Channel ROAS Comparison: Platform vs MTA vs Incremental (spec view)"), width="stretch")

fig_infl = go.Figure()
for ch, color in CHANNEL_COLORS.items():
    d = recon[recon["channel"] == ch]
    if len(d):
        fig_infl.add_bar(x=d["campaign_id"], y=d["inflation_ratio"], name=ch, marker_color=color,
                         text=d["inflation_ratio"].map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}x"), textposition="outside")
fig_infl.add_hline(y=settings.inflation_moderate, line_dash="dash", line_color="#d03b3b",
                   annotation_text=f"Warning threshold {settings.inflation_moderate:g}x")
fig_infl.update_layout(yaxis_title="Platform conversions / holdout conversions (x)", xaxis_tickangle=-30)
st.plotly_chart(style(fig_infl, "Campaign Inflation Multipliers"), width="stretch")

ch_roll = rolling.groupby(["date", "channel"], as_index=False)[["rolling_7d_incremental_revenue", "rolling_7d_covered_spend"]].sum()
ch_roll["iroas"] = ch_roll["rolling_7d_incremental_revenue"] / ch_roll["rolling_7d_covered_spend"].where(ch_roll["rolling_7d_covered_spend"] > 0)
fig_roll = go.Figure()
for ch, color in CHANNEL_COLORS.items():
    d = ch_roll[ch_roll["channel"] == ch]
    if len(d):
        fig_roll.add_scatter(x=d["date"], y=d["iroas"], name=ch, mode="lines", line=dict(color=color, width=2))
fig_roll.add_hline(y=1.0, line_dash="dot", line_color="#52514e", annotation_text="Breakeven 1.0x")
fig_roll.update_layout(yaxis_title="7 day rolling iROAS, spec view (x)")
st.plotly_chart(style(fig_roll, "7-Day Rolling iROAS by Channel"), width="stretch")

with st.expander("Table view of the charted data"):
    st.dataframe(audit, width="stretch", hide_index=True)
    st.dataframe(alerts, width="stretch", hide_index=True)
st.divider()

# ------------------------------------------------------------------- scenario simulator
st.subheader("🎛️ Budget Reallocation Scenario Simulator")
a = audit.set_index("channel")
needed = {"Netflix Ads", "Google Ads", "Meta Ads"}
if not needed <= set(a.index) or a.loc[list(needed), "incremental_roas"].isna().any():
    st.info("The simulator needs Netflix, Google and Meta Ads data with holdout coverage. Upload data covering those channels to use it.")
else:
    nf_spend, nf_rev = float(a.loc["Netflix Ads", "total_spend"]), float(a.loc["Netflix Ads", "total_holdout_revenue"])
    g_iroas, m_iroas = float(a.loc["Google Ads", "incremental_roas"]), float(a.loc["Meta Ads", "incremental_roas"])
    if is_strict:
        grp = camp.groupby("channel")[["strict_incremental_revenue", "test_period_spend"]].sum()
        s = (grp["strict_incremental_revenue"] / grp["test_period_spend"]).to_dict()
        g_iroas, m_iroas, nf_rev = s["Google Ads"], s["Meta Ads"], s["Netflix Ads"] * nf_spend
    s1, s2 = st.columns(2)
    shift = s1.slider("Netflix spend to shift ($)", 0.0, nf_spend, nf_spend, step=1000.0)
    google_pct = s2.slider("Share of shifted spend sent to Google (rest to Meta)", 0, 100, 50, step=5)
    gross = shift * google_pct / 100 * g_iroas + shift * (100 - google_pct) / 100 * m_iroas
    lost = nf_rev * (shift / nf_spend) if nf_spend else 0.0
    k1, k2, k3 = st.columns(3)
    k1.metric("Projected revenue from reallocation", f"${gross:,.0f}")
    k2.metric("Netflix revenue given up", f"-${lost:,.0f}")
    k3.metric("Projected net revenue gain", f"${gross - lost:+,.0f}")
    st.caption(f"Metric: {label}. Google iROAS {g_iroas:.2f}x, Meta iROAS {m_iroas:.2f}x. Assumes average iROAS holds at the new "
               "spend level; real marginal returns fall as channels saturate, so validate with a scaled test first.")
