"""MMGE executive dashboard: reads a stored run (Streamlit home page).

Run:  streamlit run app/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (SEVERITY_KIND, SEVERITY_LABEL, TIER_BADGE, TIER_KIND, demo_tables, get_runner, get_store,  # noqa: E402
                    identity, page_setup, pill, safe_page_link, succeeded_runs, takeaway, wait_for_run)

page_setup("Dashboard", ":material/analytics:")

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import charts  # noqa: E402

from agent_orchestrator import PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM  # noqa: E402
from config import HEADLINE_SPEC, HEADLINE_STRICT, PolicySettings  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import StoreError  # noqa: E402

ROLES = {"All Roles": "", "Brand CFO": PERSONA_CFO, "Agency Director": PERSONA_AGENCY, "Platform Lead": PERSONA_PLATFORM}

store, runner = get_store(), get_runner()
actor, ws = identity()
runs = succeeded_runs(ws)

st.title("Media Investment Scorecard")
st.caption("Which channels truly earn back their spend, where platforms over-claim, and what to do about it.")

# ------------------------------------------------------------------ empty state
if not runs:
    st.info("No runs yet in this workspace. Upload your data, or explore with the built in demo data.")
    c1, c2 = st.columns(2)
    if c1.button("Try with demo data", type="primary"):
        rid = runner.submit(ws, demo_tables(), store.latest_workspace_config(ws)[0], store.latest_workspace_config(ws)[1], "Demo data")
        wait_for_run(ws, rid)
        st.rerun()
    with c2:
        safe_page_link("pages/1_Upload.py", "Upload your own data", ":material/upload:")
    st.stop()

# -------------------------------------------------------------------- sidebar
st.sidebar.header("Data run")
labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')} · policy {r['settings_fingerprint'][:6]}" for r in runs}
run_id = st.sidebar.selectbox("Showing run", list(labels), format_func=labels.get)
run = store.get_run(ws, run_id)
settings = PolicySettings(**run["settings"])

st.sidebar.header("Audience")
role = st.sidebar.selectbox("Show recommendations for", list(ROLES))

st.sidebar.header("Measurement basis")
OPTIONS = {"Reported by spec (all revenue in the test markets)": HEADLINE_SPEC, "Strict lift (only the gap the ads caused)": HEADLINE_STRICT}
current = next(k for k, v in OPTIONS.items() if v == settings.headline_metric)
choice = st.sidebar.radio("How to count the return", list(OPTIONS), index=list(OPTIONS).index(current))
if OPTIONS[choice] != settings.headline_metric:
    inputs = SourceTables(*(store.load_table(ws, run_id, f"INPUT_{n}") for n in
                            ("RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS")))
    new_settings = PolicySettings(**{**settings.to_dict(), "headline_metric": OPTIONS[choice]})
    new_id = runner.submit(ws, inputs, new_settings, run["declarations"], (run["label"] or "Run") + " (view change)")
    wait_for_run(ws, new_id, "Re-running under the new policy...")
    st.rerun()
st.sidebar.caption("Strict lift is the more conservative and defensible basis. Both are always computed; switching creates a new run "
                   "so every number stays tied to the basis that produced it.")


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


# ------------------------------------------------------------------ channel level view of the evidence
econ = report.get("economics") or {}
BE = econ.get("breakeven_iroas") or 1.0
if econ.get("margin"):
    BE_LABEL = f"Breakeven {BE:.2f}x (profit, {econ['margin']:.0%} margin)"
    PROVEN_NAME = "Proven by the holdout test"
else:
    BE_LABEL = f"Breakeven {BE:.2f}x (revenue only, margin not set)"
    PROVEN_NAME = "Proven by the holdout test"

PLAIN_BASIS = "Strict lift (only the gap the ads caused)" if is_strict else "Reported by spec (all revenue in the test markets)"
ch = audit[["channel", "total_spend", "platform_roas", "mta_roas", "incremental_roas"]].rename(
    columns={"platform_roas": "claimed", "mta_roas": "model", "incremental_roas": "proven"}).set_index("channel")
if is_strict:
    grp = camp.groupby("channel")[["strict_incremental_revenue", "test_period_spend"]].sum()
    ch["proven"] = (grp["strict_incremental_revenue"] / grp["test_period_spend"].where(grp["test_period_spend"] > 0)).reindex(ch.index)
ch["tier"] = camp.groupby("channel")["tier"].first().reindex(ch.index)
ch = ch.reset_index()
tiers = report["tier_counts"]
measured = ch.dropna(subset=["proven"])

# ------------------------------------------------------------------ executive summary
def money(v: float) -> str:
    return f"${v:,.0f}"


if len(measured):
    status = measured["proven"].map(lambda v: charts.classify(v, BE))
    earn, even, short = (measured[status == k] for k in ("above", "at", "below"))
    parts = []
    if len(earn):
        parts.append(f"<b>{', '.join(earn['channel'])}</b> {'earns' if len(earn) == 1 else 'earn'} a profit "
                     f"(proven {', '.join(f'{v:.2f}x' for v in earn['proven'])} against a {BE:.2f}x breakeven).")
    if len(even):
        parts.append(f"<b>{', '.join(even['channel'])}</b> {'sits' if len(even) == 1 else 'sit'} right at breakeven "
                     f"({', '.join(f'{v:.2f}x' for v in even['proven'])}): it pays for itself but adds no profit.")
    if len(short):
        gap = ", ".join(f"{r.channel} claims {r.claimed:.2f}x but proves {r.proven:.2f}x" for r in short.itertuples() if pd.notna(r.claimed))
        parts.append(f"<b>{', '.join(short['channel'])}</b> {'falls' if len(short) == 1 else 'fall'} below breakeven. {gap}. "
                     f"{money(float(short['total_spend'].sum()))} of spend sits in {'this channel' if len(short) == 1 else 'these channels'}.")
    parts.append(f"{tiers['VERIFIED']} of {report['campaigns_audited']} campaigns have verified, decision grade results; "
                 f"{tiers['DIRECTIONAL']} are directional and {tiers['NOT_DECISION_GRADE']} are not yet decision grade.")
    takeaway("<b>The bottom line.</b> " + " ".join(parts), "bad" if len(short) and not len(earn) else ("ok" if not len(short) else ""))
else:
    takeaway("No channel has holdout evidence in this run, so returns cannot be proven yet. Add a holdout test to unlock the scorecard.")
st.write("")

# ------------------------------------------------------------------------ KPI cards
total_spend = float(audit["total_spend"].sum())
if is_strict:
    inc_revenue, denom = float(camp["strict_incremental_revenue"].sum()), float(camp["test_period_spend"].sum())
else:
    inc_revenue, denom = float(audit["total_holdout_revenue"].sum()), float(audit["holdout_covered_spend"].sum())
inbox = store.list_inbox(ws, run_id)
open_items = [i for i in inbox if i["status"] in ("new", "reviewed", "approved")]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total media spend", f"${total_spend:,.0f}", help="All spend across every channel and campaign in this run.")
c2.metric("Revenue caused by ads", f"${inc_revenue:,.0f}",
          help=PLAIN_BASIS + (", test period only" if is_strict else "") + ". Revenue that the holdout test attributes to advertising.")
c3.metric("Proven return per $1", f"{inc_revenue / denom:.2f}x" if denom else "n/a",
          help="Revenue caused by ads divided by the spend in tested markets. Compare it with the breakeven line.")
c4.metric("Recommendations to review", len(open_items), help="Open items from your decision rules. See Recommended actions below.")
st.caption(f"Counting basis: **{PLAIN_BASIS}**. Breakeven is {BE:.2f}x"
           + (f" at a {econ['margin']:.0%} margin ({'declared by you' if econ.get('source') == 'user' else 'industry proxy'})." if econ.get("margin")
              else " on revenue only; add a margin in Settings to see profit.")
           + f" Policy version {report['settings_fingerprint']}.")
if not is_strict and bool(camp["divergence_warning"].any()):
    st.warning("This counting basis treats all revenue in the test markets as caused by ads. The strict view, which counts only the gap "
               f"versus the control markets, is much lower for {int(camp['divergence_warning'].sum())} campaign(s). "
               "Switch the basis in the sidebar to compare before making budget decisions.")

with st.expander("How to read this scorecard (plain language definitions)"):
    st.markdown(
        "- **Claimed return**: revenue each ad platform says it generated per $1 of spend. Platforms grade their own homework, so this tends to run high.\n"
        "- **Attribution model estimate**: the same question answered by our attribution model, which removes double counting between platforms.\n"
        "- **Proven return**: revenue per $1 that a holdout test shows the ads actually caused. In a holdout test some markets see ads and similar markets do not; "
        "the difference is the proof.\n"
        "- **Breakeven**: the return needed to cover the cost of advertising. At a 50% margin you need $2 of revenue for every $1 spent, so breakeven is 2.00x.\n"
        "- **Over-claim multiple**: how many times more conversions a platform claims than the holdout test confirms. 1.0x means they agree.\n"
        "- **Trust level**: Verified results passed our quality checks and can support budget moves. Directional results are informative but should be "
        "confirmed. Not decision grade results should not be used to move money.")
st.divider()

# -------------------------------------------------------------------------- charts
st.subheader("Where advertising pays off")
st.markdown('<div class="section-note">Each chart leads with its finding. Reference lines come from your own margin and policy settings.</div>',
            unsafe_allow_html=True)
def show(fig: go.Figure) -> None:
    """Render a chart under its finding (headline) and reading guide (subtitle)."""
    meta = fig.layout.meta or {}
    st.markdown(f"##### {meta.get('headline', '')}")
    st.caption(meta.get("subtitle", ""))
    st.plotly_chart(fig, width="stretch", theme=None)


show(charts.returns_chart(ch, BE, BE_LABEL, PROVEN_NAME, charts.returns_headline(ch, BE)))
st.caption("How to use this: move budget toward channels whose green bar clears the red line, and ask platforms with a large gap between "
           "the grey and green bars to justify their reporting.")

if is_strict:
    # Under the strict basis, compare the return each platform claims with the return the test proves.
    cl = recon.set_index("campaign_id")["reported_roas"]
    sc = camp.set_index("campaign_id")
    inf = pd.DataFrame({"campaign_id": sc.index, "channel": sc["channel"].values,
                        "inflation_ratio": (cl.reindex(sc.index) / sc["strict_iroas"].where(sc["strict_iroas"] > 0)).values})
    basis = "return"
else:
    inf = recon[["channel", "campaign_id", "inflation_ratio"]].copy()
    basis = "conversions"
n_unmeasured = int(inf["inflation_ratio"].isna().sum())
show(charts.overclaim_chart(inf, settings.inflation_moderate, settings.inflation_critical,
                            charts.overclaim_headline(inf, settings.inflation_moderate, settings.inflation_critical), basis))
st.caption("How to use this: campaigns in amber or red report more than the test can confirm. Anchor reporting on the proven result."
           + (f" {n_unmeasured} campaign(s) cannot be measured (no holdout, or no positive proven lift) and are not shown." if n_unmeasured else ""))

ch_roll = rolling.groupby(["date", "channel"], as_index=False)[["rolling_7d_incremental_revenue", "rolling_7d_covered_spend"]].sum()
ch_roll["iroas"] = ch_roll["rolling_7d_incremental_revenue"] / ch_roll["rolling_7d_covered_spend"].where(ch_roll["rolling_7d_covered_spend"] > 0)
show(charts.trend_chart(ch_roll, BE, BE_LABEL, charts.trend_headline(ch_roll, BE)))
st.caption("This trend uses the reported by spec basis because it is a daily series; the strict view needs the full test period. "
           "Treat single days as noisy and look at direction.")

with st.expander("Benchmark context for these charts"):
    try:
        from pipeline import get_registry
        reg = get_registry()
        roi = reg.find("roi_interval_width").records
        dur = reg.find("test_duration_days").records
        st.markdown(
            f"- **Breakeven line**: {econ.get('note') or 'revenue breakeven of 1.00x because no margin was declared.'}\n"
            + (f"- **How certain is any single test?** {roi[0]['definition']} (peer reviewed, confidence {roi[0]['confidence']}). "
               "Read returns as ranges, not exact points.\n" if roi else "")
            + (f"- **Typical test length**: Meta geo tests in a large industry study ran about {dur[0]['value']:.1f} days on average "
               f"(confidence {dur[0]['confidence']}).\n" if dur else "")
            + "- **What we deliberately do not draw**: a benchmark band for channel return. No verified, comparable channel return range exists in the "
              "registry, and vendor ranges conflict, so adding one would imply precision we cannot support. See the Benchmarks page.")
    except Exception:  # registry is optional context, never block the dashboard
        st.caption("Benchmark registry unavailable for this view.")
bctx = report.get("benchmark_context") or {}
if bctx.get("illustrative_benchmark_table"):
    st.caption("The built in channel ranges are illustrative placeholders, so no governance score is based on them.")
st.divider()

# -------------------------------------------------------------------- recommended actions
st.subheader("Recommended actions")
st.markdown('<div class="section-note">Each recommendation comes from a decision rule you can edit on the Agents page. '
            'Nothing is executed without your approval.</div>', unsafe_allow_html=True)
if is_strict:
    st.caption("Strict lift view: dollar amounts cover the test period only.")
visible = [i for i in inbox if not ROLES[role] or i["packet"]["target_persona"] == ROLES[role]]
if not visible:
    st.success("No threshold triggers are active for this audience. All channels are within nominal parameters.")
tier_of = camp.set_index("campaign_id")["tier"].to_dict()
for item in visible:
    p = item["packet"]
    t = tier_of.get(p["campaign_id"])
    with st.container(border=True):
        st.markdown(f"{pill(SEVERITY_LABEL.get(p['severity'], p['severity']), SEVERITY_KIND.get(p['severity'], 'muted'))} "
                    f"{pill(TIER_BADGE.get(t, 'Unrated'), TIER_KIND.get(t, 'muted'))} "
                    f"{pill(item['status'].capitalize(), 'muted')}", unsafe_allow_html=True)
        st.markdown(f"#### {p['title']}")
        st.caption(f"For {p['target_persona']} · {p['channel']} · rule {p['agent_id']}")
        cols = st.columns(len(p["value_add_metrics"]))
        for col, (name, val) in zip(cols, p["value_add_metrics"].items()):
            col.metric(name, val)
        st.markdown(f"**Recommendation:** {p['strategic_callout']}")
        b1, b2, b3 = st.columns([2, 1, 4])
        try:
            if item["status"] in ("new", "reviewed"):
                if b1.button(f"Approve: {p['recommended_action']}", key=f"ap_{item['id']}"):
                    store.transition_inbox(ws, item["id"], "approved", actor, "approved from dashboard")
                    st.rerun()
            elif item["status"] == "approved":
                if b1.button(f"Execute: {p['recommended_action']}", key=f"ex_{item['id']}", type="primary"):
                    store.transition_inbox(ws, item["id"], "executed", actor, "dry run: logged to simulated Snowflake queue")
                    st.toast("Action logged to the governance audit trail (simulated Snowflake queue).")
                    st.rerun()
            if item["status"] in ("new", "reviewed", "approved") and b2.button("Dismiss", key=f"dm_{item['id']}"):
                store.transition_inbox(ws, item["id"], "dismissed", actor)
                st.rerun()
            if b3.button("Draft memo", key=f"mm_{item['id']}"):
                from memo_service import draft_memo, facts_for_item
                from memo_writer import configured_writer
                memo = draft_memo(store, ws, item, facts_for_item(store, ws, run_id, item), run_id, configured_writer(), actor)
                st.toast("Memo drafted and verified. Open the Memos page to review and approve it." + (" (AI draft replaced by template)" if memo["fallback_reason"] else ""))
        except StoreError as exc:
            st.error(str(exc))
st.divider()

# ------------------------------------------------------------------- scenario simulator
st.subheader("What if we moved the Netflix budget?")
st.markdown('<div class="section-note">A simple what-if using the proven returns above. It is an estimate, not a forecast.</div>', unsafe_allow_html=True)
a = audit.set_index("channel")
needed = {"Netflix Ads", "Google Ads", "Meta Ads"}
if not needed <= set(a.index) or ch.set_index("channel").loc[list(needed), "proven"].isna().any():
    st.info("The what-if needs Netflix, Google and Meta Ads data with holdout coverage. Upload data covering those channels to use it.")
else:
    pr = ch.set_index("channel")["proven"]
    nf_spend = float(a.loc["Netflix Ads", "total_spend"])
    g_iroas, m_iroas, nf_iroas = float(pr["Google Ads"]), float(pr["Meta Ads"]), float(pr["Netflix Ads"])
    nf_rev = nf_iroas * nf_spend
    s1, s2 = st.columns(2)
    shift = s1.slider("Netflix spend to move ($)", 0.0, nf_spend, nf_spend, step=1000.0)
    google_pct = s2.slider("Share sent to Google (the rest goes to Meta)", 0, 100, 50, step=5)
    gross = shift * google_pct / 100 * g_iroas + shift * (100 - google_pct) / 100 * m_iroas
    lost = nf_rev * (shift / nf_spend) if nf_spend else 0.0
    net = gross - lost
    k1, k2, k3 = st.columns(3)
    k1.metric("Revenue expected from the new channels", f"${gross:,.0f}")
    k2.metric("Netflix revenue given up", f"-${lost:,.0f}")
    k3.metric("Net revenue change", f"${net:+,.0f}")
    takeaway(f"Moving {money(shift)} out of Netflix is projected to {'add' if net >= 0 else 'cost'} <b>{money(abs(net))}</b> in revenue "
             f"at the proven returns (Google {g_iroas:.2f}x, Meta {m_iroas:.2f}x, Netflix {nf_iroas:.2f}x).", "ok" if net >= 0 else "bad")
    st.caption(f"Counting basis: {PLAIN_BASIS}. Assumes returns hold at the new spend level. Real returns usually fall as a channel saturates, "
               "so confirm with a scaled test before moving the full amount.")
st.divider()

# -------------------------------------------------------------------- evidence and data quality
st.subheader("Evidence and data quality")
sf = (run["validation"] or {}).get("scale_factor") or {}
if sf:
    st.caption(f"Test market size check: the treatment markets hold {sf['census_share']:.1%} of the US population, against a declared sample of {sf['declared_fraction']:.1%}.")
if bctx.get("benchmark_set_version"):
    st.caption(f"Benchmark registry version {bctx['benchmark_set_version']} was used in this run.")
issues = run["validation"]["issues"]
if issues:
    with st.expander(f"Data checks recorded for this run ({sum(i['severity'] == 'WARNING' for i in issues)} warnings)"):
        for i in issues:
            st.markdown(f"{pill('Warning' if i['severity'] == 'WARNING' else 'Note', 'warn' if i['severity'] == 'WARNING' else 'info')} "
                        f"**{i['rule']}**: {i['message']}", unsafe_allow_html=True)
if econ.get("margin"):
    with st.expander("Profit view by campaign"):
        prof = camp[["campaign_id", "channel", "headline_iroas", "tier"]].copy()
        prof.columns = ["Campaign", "Channel", "Proven return per $1", "Trust level"]
        prof["Breakeven"] = BE
        prof["Profit per $1 of ad spend"] = prof["Proven return per $1"] * econ["margin"] - 1.0
        prof["Trust level"] = prof["Trust level"].map(TIER_BADGE)
        st.dataframe(prof.round(3), hide_index=True, width="stretch")
with st.expander("Table view of the charted data"):
    st.dataframe(audit, width="stretch", hide_index=True)
    st.dataframe(alerts, width="stretch", hide_index=True)
