"""MMGE executive dashboard: reads a stored run (Streamlit home page).

Run:  streamlit run app/app.py

Flow: perspective picker, an answer-first hero, one featured view per perspective, the three agent lenses with their evidence,
the full chart set (each with a Chart or Table toggle), decision cards with trust gating and sign-off overrides, a what-if,
and a sources and confidence section.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA_ROOT, demo_tables, get_runner, get_store, identity, page_setup, safe_page_link, succeeded_runs,  # noqa: E402
                    wait_for_run)

page_setup("Dashboard")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import charts  # noqa: E402
import council as cn  # noqa: E402
import dashdata as dd  # noqa: E402
import ui  # noqa: E402
import voice  # noqa: E402
from agent_engine import build_facts, default_definitions, evaluate_agents  # noqa: E402
from agent_orchestrator import PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM  # noqa: E402
from config import HEADLINE_SPEC, HEADLINE_STRICT, PolicySettings  # noqa: E402
from overrides import read_log, verify_log  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import StoreError  # noqa: E402

PERSPECTIVES = {"Everyone": (), "CFO / Finance": (PERSONA_CFO,), "CMO / Growth": (PERSONA_PLATFORM,), "Agency Director": (PERSONA_AGENCY,),
                "Platform Lead": (PERSONA_PLATFORM, PERSONA_AGENCY)}
LENS_IDS = ["CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT", "SCALE_OPPORTUNITY_AGENT"]
LENS_COPY = {
    "CAPITAL_PRESERVATION_AGENT": ("bad", "Capital preservation", "Brand CFO / Finance", "Finds campaigns that look profitable on the platform's own numbers but lose money once the test is applied."),
    "ATTRIBUTION_SHIELD_AGENT": ("warn", "Attribution shield", "Agency Director / Platform Lead", "Finds platforms that claim more credit than the evidence supports, so reporting can be corrected."),
    "SCALE_OPPORTUNITY_AGENT": ("ok", "Scale opportunity", "CMO / Growth VP", "Finds campaigns with strong, verified returns and little over-claiming that can take more budget."),
}
OLD_BASIS = {HEADLINE_SPEC: "All revenue in the test markets (reported by spec)", HEADLINE_STRICT: "Only revenue the ads caused (strict lift)"}

store, runner = get_store(), get_runner()
actor, ws = identity()
runs = succeeded_runs(ws)
theme = ui.tokens()
charts.use_theme(theme)


def money(v: float, sign: bool = False) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    return f"{'+' if sign and v > 0 else ('-' if v < 0 else '')}${abs(v):,.0f}"


def xfmt(v: float) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.2f}x"


def names(rows) -> str:
    rows = list(rows)
    return ", ".join(rows[:-1]) + (" and " if len(rows) > 1 else "") + rows[-1] if rows else ""


# ------------------------------------------------------------------------------ empty state (never a dead end)
if not runs:
    ui.hero("Media Measurement and Governance", "Know which channels truly earn back their spend.",
            "Bring your platform, attribution and holdout test data. In minutes you get a plain-language answer, the evidence behind it, "
            "and decision cards you can approve with confidence. Nothing runs until the data checks pass.")
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Try with demo data", type="primary", width="stretch"):
            cfg = store.latest_workspace_config(ws)
            rid = runner.submit(ws, demo_tables(), cfg[0], cfg[1], "Demo data")
            wait_for_run(ws, rid)
            st.rerun()
        st.caption("Loads a built-in 90 day example so you can explore every screen.")
    with c2:
        safe_page_link("pages/1_Upload.py", "Upload your own data", ":material/upload:")
        st.caption("Five guided steps with plain-language checks and row-level fixes.")
    with c3:
        safe_page_link("pages/6_Benchmarks.py", "See the benchmark sources", ":material/menu_book:")
        st.caption("Every outside reference is cited and verified.")
    st.stop()

# ------------------------------------------------------------------------------------------------ sidebar
st.sidebar.markdown("**Data run**")
labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')} · policy {r['settings_fingerprint'][:6]}" for r in runs}
if "pending_run" in st.session_state:  # set before the widget exists (Streamlit forbids changing it afterwards)
    st.session_state["run_select"] = st.session_state.pop("pending_run")
run_id = st.sidebar.selectbox("Showing run", list(labels), format_func=labels.get, key="run_select")
run = store.get_run(ws, run_id)
settings = PolicySettings(**run["settings"])
st.sidebar.markdown("**Counting basis**")
OPTIONS = {OLD_BASIS[HEADLINE_SPEC]: HEADLINE_SPEC, OLD_BASIS[HEADLINE_STRICT]: HEADLINE_STRICT}
current = next(k for k, v in OPTIONS.items() if v == settings.headline_metric)
choice = st.sidebar.radio("How to count the return", list(OPTIONS), index=list(OPTIONS).index(current))
if OPTIONS[choice] != settings.headline_metric:
    inputs = SourceTables(*(store.load_table(ws, run_id, f"INPUT_{n}") for n in ("RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS")))
    new_settings = PolicySettings(**{**settings.to_dict(), "headline_metric": OPTIONS[choice]})
    new_id = runner.submit(ws, inputs, new_settings, run["declarations"], (run["label"] or "Run") + " (view change)")
    wait_for_run(ws, new_id, "Re-running under the new counting basis...")
    st.session_state["pending_run"] = new_id  # an identical earlier run is reused, so point the picker at it explicitly
    st.rerun()
st.sidebar.caption("Counting only the revenue the ads caused is the more conservative and defensible choice. Both are always calculated; switching creates a new run so every number stays tied to how it was counted.")
st.sidebar.caption("Light or dark mode follows your system, or choose one from the menu at the top right.")


@st.cache_data(show_spinner=False)
def load(ws_id: str, rid: str):
    names_ = ("ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_AUDIT_SUMMARY", "ROLLING_7D_PERFORMANCE", "GOVERNANCE_CAMPAIGN_ALERTS")
    return {n: store.load_table(ws_id, rid, n) for n in names_}, store.load_audit(ws_id, rid)


tables, report = load(ws, run_id)
recon, audit, rolling, alerts = (tables[k] for k in ("ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_AUDIT_SUMMARY", "ROLLING_7D_PERFORMANCE", "GOVERNANCE_CAMPAIGN_ALERTS"))
camp = pd.DataFrame(report["campaigns"])
is_strict = settings.headline_metric == HEADLINE_STRICT
BASIS = "Strict lift" if is_strict else "Reported by spec"
PLAIN_BASIS = OLD_BASIS[settings.headline_metric]
econ = report.get("economics") or {}
BE = econ.get("breakeven_iroas") or 1.0
margin = econ.get("margin")
BE_LABEL = f"Breakeven {BE:.2f}x ({'profit at ' + format(margin, '.0%') + ' margin' if margin else 'revenue only, margin not set'})"

cd = dd.campaign_frame(recon, camp, is_strict, BE, margin)
cd["test_spend"] = cd["campaign_id"].map(camp.set_index("campaign_id")["test_period_spend"])
ch = dd.channel_frame(cd, audit, is_strict, BE)
tot = dd.portfolio_totals(cd, ch, is_strict)
ch = dd.with_actions(ch, BE, tot["proven"])
inbox = store.list_inbox(ws, run_id)
tier_of = camp.set_index("campaign_id")["tier"].to_dict()
score_of = camp.set_index("campaign_id")["trust_score"].to_dict()
days = int(rolling["date"].nunique()) if len(rolling) else 90
parallel_ok = all(c["status"] != "FAIL" for k in report["campaigns"] for c in k["checks"] if c["check_id"] == 1)
run_score = float(report["average_trust_score"])
run_tier = settings.trust_tier(run_score, parallel_ok)
run_gate = dd.gate(run_tier)
realloc = dd.recommended_reallocation(ch)
base_realloc = dd.reallocation(ch)
head = dd.headroom(ch, days)
div = dd.divergence(cd)

# --------------------------------------------------------------------------------------- perspective picker
bar_l, bar_r = st.columns([1, 4])
bar_l.markdown('<div class="kicker" style="padding-top:.55rem">Viewing as</div>', unsafe_allow_html=True)
with bar_r:
    persp = st.segmented_control("Perspective", list(PERSPECTIVES), default="Everyone", key="persp", label_visibility="collapsed") or "Everyone"
personas = PERSPECTIVES[persp]

# ------------------------------------------------------------------------------------------------- hero
ci_txt = f" (likely between {xfmt(tot['lower'])} and {xfmt(tot['upper'])})" if pd.notna(tot["lower"]) else ""
n_over = int((cd["overclaim_ratio"] > settings.inflation_moderate).sum()) if is_strict else int((recon["inflation_ratio"] > settings.inflation_moderate).sum())
n_low = int((cd["tier"] != "VERIFIED").sum())
n_above = int((ch["proven"] >= BE * 1.05).sum())
n_meas = int(ch["proven"].notna().sum())
spend_above = float(ch.loc[ch["proven"] >= BE * 1.05, "spend"].sum() / ch["spend"].sum()) if ch["spend"].sum() else 0.0
unearned_head = (f"{money(tot['unearned'])} of ad spend has not been earned back" if tot["unearned"] > 0 else "Every campaign earned back its ad spend on this basis")
sig_ids = {c["campaign_id"] for c in report["campaigns"] if any(k["check_id"] == 8 and k["status"] in ("PASS", "WARN") for k in c["checks"])}
n_sig, n_all = len(sig_ids), int(report["campaigns_audited"])
ready_ids = {c["campaign_id"] for c in report["campaigns"] if c["tier"] == "VERIFIED"}
n_ready = len(ready_ids)
need_test = [c["campaign_id"] for c in report["campaigns"] if c["campaign_id"] not in ready_ids]
if n_ready == n_all:
    ready_txt = f"All {n_all} campaigns have statistically significant evidence, enough to make a confident recommendation on each."
elif n_ready == 0:
    ready_txt = f"None of the {n_all} campaigns has strong enough evidence yet for a confident recommendation, so further testing comes first."
else:
    ready_txt = (f"{n_ready} out of {n_all} campaigns show enough statistically significant evidence to make a confident recommendation. "
                 f"The other {len(need_test)} ({names(need_test)}) need further testing before money moves.")
common_lede = (f"While platforms have self-reported revenue figures, our holdout tests reveal a <b>{money(tot['overclaim_revenue'])}</b> gap between what they claim and what our measurements support. "
               f"The portfolio returns <b>{xfmt(tot['proven'])}</b> for every $1 of ad spend (breakeven is {BE:.2f}x). {ready_txt}")
HEADLINES = {
    "Everyone": (unearned_head, common_lede),
    "CFO / Finance": (unearned_head, common_lede),
    "CMO / Growth": (f"{n_above} of {n_meas} measured channels return more than breakeven, holding {spend_above:.0%} of spend",
                     f"The portfolio returns <b>{xfmt(tot['proven'])}</b> for every $1 spent, against a breakeven of <b>{BE:.2f}x</b>. "
                     + (f"If today's return holds, adding a quarter more budget to {names(head['channels'])} would bring in about <b>{money(head['expected_monthly_revenue'])}</b> of revenue a month." if head["channels"] else "No channel earns enough yet to make a confident case for more budget.")),
    "Agency Director": (f"Platforms report {xfmt(audit['platform_roas'].mean())} on average; the test proves {xfmt(tot['proven'])}",
                        "Below, each channel shows what the platform reports next to what our tests prove, in terms you can take to a client."),
    "Platform Lead": (f"{n_over} of {report['campaigns_audited']} campaigns report more than {settings.inflation_moderate:g} times the results our tests confirm; {n_low} need more testing before they can be relied on",
                      "The tables below show where each platform's claims and our evidence stand, and how well each campaign is being measured."),
}
h1, lede = HEADLINES[persp]
ui.hero(f"Media Measurement and Governance &nbsp;·&nbsp; {html.escape(run['label'] or 'Run')} &nbsp;·&nbsp; {run['created_at'][:10]}", html.escape(h1), lede,
        [("The answer", "answer"), ("Advisory council", "council"), ("Evidence", "evidence"), ("Decisions", "decisions"), ("What if", "whatif"), ("Sources", "sources")])
st.write("")

# how sure we are: plain confidence strip, then the two counting methods note
cov_ = (run["validation"] or {}).get("coverage") or {}
kind = {"VERIFIED": "ok", "DIRECTIONAL": "warn", "NOT_DECISION_GRADE": "bad"}[run_tier]
ui.stat_row([dict(label="Confidence level", value="95%", sub="We are 95% sure the true return sits inside the ranges shown", kind="ok"),
             dict(label="Statistically significant", value=f"{n_sig} of {n_all}", sub="Campaigns where the lift is clearly more than zero", kind="ok" if n_sig == n_all else "warn"),
             dict(label="Ready for a confident decision", value=f"{n_ready} of {n_all}", sub="Strong enough evidence to move budget", kind="ok" if n_ready == n_all else "warn"),
             dict(label="Test coverage", value=f"{float(cov_.get('holdout', 1) or 0):.0%}", sub=f"Campaigns with a control test, over {days} days of data")], compact=True)
st.markdown(f'<div class="note"><b>What this means for your decision.</b> {html.escape(voice.conf_phrase(run_tier))}. '
            + (f"{n_ready} of {n_all} campaigns can move budget now. " if ready_ids and len(ready_ids) < n_all else "")
            + (f"Test further before moving money on {html.escape(names(need_test))}." if need_test else "Every campaign is ready for a decision.") + "</div>", unsafe_allow_html=True)
if len(div):
    st.write("")
    ui.callout(f"<b>The two ways of counting results disagree.</b> Counting all revenue in the test markets makes ads look up to "
               f"<b>{(div['spec_iroas'] / div['strict_iroas'].where(div['strict_iroas'] > 0)).max():.1f} times</b> better than counting only the extra revenue the ads actually caused. "
               f"This happens on {len(div)} of {len(cd)} campaigns. "
               + ("You are viewing the safer count, which credits ads only with revenue they caused." if is_strict else "The count of revenue the ads caused is the safer basis for budget decisions, so consider comparing both in the sidebar before moving money."), "warn")

# ---------------------------------------------------------------------------------------- headline stats
SPEC_NOTE = "" if is_strict else "No likely range is available when counting all test market revenue."
if persp == "CFO / Finance":
    cards = [dict(label="Spend not earned back", value=money(tot["unearned"]), sub="Ad spend the proven revenue did not repay", kind="bad", term="unearned"),
             dict(label="Claimed organic sales", value=money(tot["overclaim_revenue"]), sub="Revenue platforms claim that the test does not support", kind="warn", term="phantom"),
             dict(label="Proven return per $1", value=xfmt(tot["proven"]), sub=(f"95% sure it is between {xfmt(tot['lower'])} and {xfmt(tot['upper'])}" if is_strict else SPEC_NOTE), term="proven")]
elif persp == "CMO / Growth":
    cards = [dict(label="Portfolio proven return", value=xfmt(tot["proven"]), sub=f"Breakeven {BE:.2f}x" + (f" · 95% sure it is between {xfmt(tot['lower'])} and {xfmt(tot['upper'])}" if is_strict else ""), term="proven"),
             dict(label="Modeled value of moving Netflix spend", value=money(realloc["net"], True) if realloc else "n/a", sub=f"A scenario to {realloc['dest']} at proven returns, not a recommendation" if realloc else "No clear source and destination for a move"),
             dict(label="Growth headroom", value=money(head["added_monthly_spend"]) + " a month", sub=("Scale leaders: " + names(head["channels"])) if head["channels"] else "No channel qualifies yet", term="headroom")]
elif persp == "Agency Director":
    cards = [dict(label="Average claimed return", value=xfmt(audit["platform_roas"].mean()), sub="What the platforms report", term="claimed"),
             dict(label="Proven return per $1", value=xfmt(tot["proven"]), sub="What the holdout test confirms", kind="ok", term="proven"),
             dict(label="Typical over-claim", value=xfmt(cd["overclaim_ratio"].median()) if is_strict else xfmt(recon["inflation_ratio"].median()), sub="Claimed relative to proven", term="overclaim")]
elif persp == "Platform Lead":
    cov = (run["validation"] or {}).get("coverage") or {}
    cards = [dict(label="Campaigns over-claiming", value=f"{n_over} of {len(cd)}", sub=f"Above {settings.inflation_moderate:g}x the proven result", kind="warn" if n_over else "ok", term="overclaim"),
             dict(label="Campaigns needing stronger evidence", value=f"{n_low} of {len(cd)}", sub="Directional or not decision grade", kind="warn" if n_low else "ok", term="trust"),
             dict(label="Holdout coverage", value=f"{float(cov.get('holdout', 1)):.0%}", sub="Campaigns with a holdout test", term="holdout")]
else:
    cards = [dict(label="Total media spend", value=money(tot["spend"]), sub="All channels in this run" if not is_strict else "Test period spend"),
             dict(label="Revenue caused by ads", value=money(tot["proven_revenue"]), sub=PLAIN_BASIS, kind="ok"),
             dict(label="Proven return per $1", value=xfmt(tot["proven"]), sub=(f"95% sure it is between {xfmt(tot['lower'])} and {xfmt(tot['upper'])}" if is_strict else f"Breakeven {BE:.2f}x"), term="proven")]
open_items = [i for i in inbox if i["status"] in ("new", "reviewed", "approved")]
cards.append(dict(label="Decisions to review", value=str(len(open_items)), sub="Open items for your sign-off"))
ui.stat_row(cards)
st.markdown(f'<div class="note">Counting basis: <b>{html.escape(PLAIN_BASIS)}</b>. Breakeven {BE:.2f}x'
            + (f" at a {margin:.0%} margin ({'declared by you' if econ.get('source') == 'user' else 'industry proxy'})." if margin else " on revenue only; add a margin in Settings to see profit.")
            + "</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------------------- figure factories
def fig_returns():
    f = charts.returns_chart(ch, BE, BE_LABEL, charts.SERIES_NAMES["proven"], charts.returns_headline(ch, BE))
    t = ch[["channel", "claimed", "model", "proven", "lower", "upper", "tier"]].copy()
    t.columns = ["Channel", "Claimed return", "Attribution model", "Proven return", "Proven low (95%)", "Proven high (95%)", "Confidence"]
    t["Confidence"] = t["Confidence"].map(lambda v: ui.TIER_LABEL.get(v, (v,))[0])
    return f, t.round(3), "Source: platform exports, attribution model output and the geo holdout test for this run."


def fig_overclaim():
    if is_strict:
        inf = cd.rename(columns={"overclaim_ratio": "inflation_ratio"})[["channel", "campaign_id", "inflation_ratio"]]
        basis = "return"
    else:
        inf, basis = recon[["channel", "campaign_id", "inflation_ratio"]].copy(), "conversions"
    f = charts.overclaim_chart(inf, settings.inflation_moderate, settings.inflation_critical, charts.overclaim_headline(inf, settings.inflation_moderate, settings.inflation_critical), basis)
    t = inf.copy()
    t.columns = ["Channel", "Campaign", "Over-claim multiple"]
    return f, t.sort_values("Over-claim multiple", ascending=False).round(3), f"Thresholds from your policy: review above {settings.inflation_moderate:g}x, critical above {settings.inflation_critical:g}x."


def fig_trend():
    roll = dd.rolling_with_band(rolling)
    f = charts.trend_chart(roll, BE, BE_LABEL, charts.trend_headline(roll, BE))
    t = roll[["date", "channel", "iroas", "band_low", "band_high"]].copy()
    t["date"] = t["date"].astype(str).str[:10]
    t.columns = ["Date", "Channel", "7 day return", "Recent low", "Recent high"]
    return f, t.round(3), "Daily series counting all test market revenue; the stricter count needs the full test period."


def fig_waterfall():
    steps = dd.waterfall_steps(tot)
    f = charts.waterfall_chart(steps, charts.waterfall_headline(steps))
    return f, pd.DataFrame({"Step": [s[0] for s in steps], "Revenue": [round(s[1], 2) for s in steps]}), "Claimed revenue is the platforms' own report" + (", scaled to the test period by each campaign's spend share" if is_strict else "") + "; proven revenue comes from the holdout test."


def fig_portfolio():
    f = charts.portfolio_chart(ch, charts.portfolio_headline(ch))
    t = ch[["channel", "action", "spend_share", "revenue_share", "proven", "tier"]].copy()
    t.columns = ["Channel", "Position", "Share of spend", "Share of proven revenue", "Proven return", "Confidence"]
    t["Confidence"] = t["Confidence"].map(lambda v: ui.TIER_LABEL.get(v, (v,))[0])
    t["Position"] = t["Position"].map(lambda v: ui.ACTION_LABEL.get(v, v))
    return f, t.round(3), "Strong return means Verified evidence and a return of 1.5x the portfolio average or more; below breakeven means under 95% of breakeven."


FIGS = {"returns": fig_returns, "overclaim": fig_overclaim, "trend": fig_trend, "waterfall": fig_waterfall, "portfolio": fig_portfolio}
shown: set = set()


def card(key: str) -> None:
    f, t, src = FIGS[key]()
    basis, sub = BASIS, f.layout.meta["subtitle"]
    if key == "trend":  # a daily series exists only on the spec basis: stamp it truthfully
        basis = "Reported by spec"
        if is_strict:
            sub += " This daily view counts all test market revenue, which overstates returns, so read the direction rather than the level."
    ui.chart_card(key, f.layout.meta["headline"], sub, f, t, basis, src)
    shown.add(key)


def html_table(headers, rows) -> None:
    head_ = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr>{head_}</tr></thead><tbody>{body}</tbody></table></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------------- 01 the answer (by perspective)
ui.section("01", "The answer", {"Everyone": "What to do with the budget, and the proof.", "CFO / Finance": "Where capital is at risk, and how much of what platforms claim is real.",
                                "CMO / Growth": "How returns are trending and how much of the budget sits above breakeven.",
                                "Agency Director": "Reported versus proven, side by side, ready to explain to a client.",
                                "Platform Lead": "Which campaigns over-claim and whether the data behind them can be trusted."}[persp], "answer")
if persp in ("Everyone", "CMO / Growth"):
    if persp == "CMO / Growth":
        card("trend")
        card("portfolio")
        if head["channels"]:
            ui.callout(f"<b>Growth headroom.</b> A 25% rise in spend on {names(head['channels'])} would be about <b>{money(head['added_monthly_spend'])}</b> a month. At today's proven return that implies "
                       f"about <b>{money(head['expected_monthly_revenue'])}</b> of revenue a month"
                       + (f" (range {money(head['rev_low'])} to {money(head['rev_high'])})" if pd.notna(head["rev_low"]) else "") + ". Returns usually fall as spend grows, so consider confirming with a scaled test.", "ok")
    else:
        card("returns")
        html_table(["Channel", "Where the return stands", "Proven return", "Confidence"],
                   [[html.escape(r.channel), ui.action_pill(r.action), xfmt(r.proven) + (f" [{xfmt(r.lower)} to {xfmt(r.upper)}]" if pd.notna(r.lower) else ""), ui.tier_pill(r.tier)] for r in ch.sort_values("proven", ascending=False).itertuples()])
elif persp == "CFO / Finance":
    card("waterfall")
    st.markdown("##### Capital destruction leaderboard")
    st.caption("Campaigns ranked by spend not earned back. A campaign appears here only when its proven revenue does not repay the money spent.")
    lead = cd.sort_values("unearned", ascending=False)
    lead = lead[lead["unearned"] > 0].head(8)
    if lead.empty:
        ui.callout("No campaign has unearned spend on this basis.", "ok")
    else:
        html_table(["Campaign", "Spend", "Claimed return", "Proven return", "Spend not earned back", "Position"],
                   [[html.escape(r.campaign_id), money(r.spend), xfmt(r.claimed_roas), xfmt(r.proven) + (f" [{xfmt(r.lower)} to {xfmt(r.upper)}]" if pd.notna(r.lower) else ""), f"<b>{money(r.unearned)}</b>",
                     ui.action_pill("Cut" if dd.classify(r.proven, BE) == "below" else "Maintain")] for r in lead.itertuples()])
        ui.source_line("Spend not earned back = spend minus proven revenue" + (f" x {margin:.0%} margin" if margin else "") + f". Basis: {html.escape(PLAIN_BASIS)}.")
    if is_strict:
        worst = cd.sort_values("unearned", ascending=False).iloc[0]
        txt = dd.best_worst_case(worst, margin, BE)
        if txt:
            st.write("")
            ui.callout(f"<b>{html.escape(worst['campaign_id'])}</b>: {html.escape(txt)}", "warn")
elif persp == "Agency Director":
    st.markdown("##### Two ways of counting, side by side")
    st.caption("Both views are always computed. The spec view counts all revenue in test markets; strict lift counts only the gap the ads caused.")
    spec_by_ch = audit.set_index("channel")["incremental_roas"]
    both = cd.groupby("channel").apply(lambda g: pd.Series({"strict": (g["strict_iroas"] * g["test_spend"]).sum() / g["test_spend"].sum()}), include_groups=False).reset_index()
    both["spec"] = both["channel"].map(spec_by_ch)
    cols = st.columns(max(len(both), 1))
    for col, r in zip(cols, both.itertuples()):
        with col, st.container(border=True):
            st.markdown(f"**{html.escape(r.channel)}**")
            st.markdown(f'<div class="note">All test market revenue</div><div style="font-size:1.6rem;font-weight:720">{xfmt(r.spec)}</div>'
                        f'<div class="note" style="margin-top:8px">Only revenue the ads caused</div><div style="font-size:1.6rem;font-weight:720;color:{theme["proven"]}">{xfmt(r.strict)}</div>'
                        f'<div class="note" style="margin-top:8px">{ui.action_pill(ch.set_index("channel").loc[r.channel, "action"])}</div>', unsafe_allow_html=True)
    st.write("")
    card("returns")
    memo_md = "\n".join([f"# Client measurement note ({BASIS})", "", f"Run: {run['label'] or 'Run'} ({run['created_at'][:10]}). Counting basis: {PLAIN_BASIS}.", "",
                         f"Platforms report an average return of {xfmt(audit['platform_roas'].mean())}. The holdout test proves {xfmt(tot['proven'])}{ci_txt}.", "",
                         "| Channel | Claimed | Proven | Where the return stands |", "| --- | --- | --- | --- |"]
                        + [f"| {r.channel} | {xfmt(r.claimed)} | {xfmt(r.proven)} | {ui.ACTION_LABEL.get(r.action, r.action)} |" for r in ch.itertuples()]
                        + ["", f"Trust score {run_score:.0f} of 100 ({ui.TIER_LABEL[run_tier][0]}). Figures come from the verified run; none are estimated by an AI."])
    d1, d2 = st.columns(2)
    d1.download_button("Download client note (Markdown)", memo_md, "client_note.md", key="dl_md")
    d2.download_button("Download client note (HTML, print to PDF)", f"<html><body style='font-family:sans-serif;max-width:760px;margin:2rem auto'><pre style='white-space:pre-wrap'>{html.escape(memo_md)}</pre></body></html>", "client_note.html", key="dl_html")
    safe_page_link("pages/5_Memos.py", "Open the executive narrative generator", ":material/description:")
else:  # Platform Lead
    st.markdown("##### Over-claim alert table")
    st.caption("Every campaign, with the biggest gap between claimed and proven results first.")
    oc_series = cd["overclaim_ratio"] if is_strict else pd.Series(recon.set_index("campaign_id")["inflation_ratio"].reindex(cd["campaign_id"]).values, index=cd.index)
    tb = cd.assign(oc=oc_series).sort_values("oc", ascending=False, na_position="last")
    html_table(["Campaign", "Channel", "Claimed", "Proven", "Over-claim", "Status", "Trust"],
               [[html.escape(r.campaign_id), html.escape(r.channel), xfmt(r.claimed_roas), xfmt(r.proven), xfmt(r.oc),
                 ui.pill("Critical", "bad") if pd.notna(r.oc) and r.oc > settings.inflation_critical else (ui.pill("Review", "warn") if pd.notna(r.oc) and r.oc > settings.inflation_moderate else ui.pill("Normal", "ok")),
                 ui.tier_pill(r.tier) + f" {r.trust_score:.0f}"] for r in tb.itertuples()])
    low = cd[cd["tier"] != "VERIFIED"]
    if len(low):
        st.write("")
        ui.callout(f"<b>Low trust diagnostic.</b> {len(low)} campaign(s) are below Verified: {html.escape(names(low['campaign_id'].tolist()))}. "
                   "Money actions on these are limited until the evidence improves (longer test, more conversions or a cleaner control).", "warn")
    cov = (run["validation"] or {}).get("coverage") or {}
    st.write("")
    st.markdown("##### Data health")
    g1, g2 = st.columns(2)
    for col, key, label in ((g1, "mta", "Attribution model coverage"), (g2, "holdout", "Holdout test coverage")):
        v = float(cov.get(key, 0) or 0)
        col.progress(min(max(v, 0.0), 1.0), text=f"{label}: {v:.0%} of campaigns")

# ------------------------------------------------------------------------------------- 02 advisory council
ui.section("02", "The advisory council", "Four seasoned advisors look at the same results through their own priorities. Their suggestions are ideas to weigh, and the decision stays with you.", "council")
defs = {d["id"]: d for d in (store.get_agent_definitions(ws) or default_definitions())}
facts = build_facts(recon, report, is_strict)
council = cn.convene(ch, cd, tot, BE, is_strict, float(((run["validation"] or {}).get("coverage") or {}).get("holdout", 1) or 0))
ag, sp = st.columns(2)
with ag, st.container(border=True):
    st.markdown("##### Where the council agrees")
    for line in council.agree or ["No channel has full agreement."]:
        st.markdown(f"- {line}")
with sp, st.container(border=True):
    st.markdown("##### Where the council splits")
    for line in council.split or ["The advisors read every channel the same way."]:
        st.markdown(f"- {line}")
st.write("")
pc = st.columns(2)
for i, rd in enumerate(council.readings):
    pr = rd.persona
    with pc[i % 2], st.container(border=True):
        st.markdown(ui.lean_pill(pr.lean), unsafe_allow_html=True)
        st.markdown(f"#### {pr.name}")
        st.caption(pr.role)
        st.markdown(ui.esc(rd.headline))
        rows = "".join(f"<tr><td>{html.escape(c.channel)}</td><td>{ui.pill(voice.STANCE_WORDS[c.stance], ui.STANCE_KIND[c.stance])}</td></tr>" for c in rd.channels)
        st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Channel</th><th>Where they stand</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
        d = defs.get(pr.related_rule)
        fired = evaluate_agents([{**d, "enabled": True}], facts) if d else []
        with st.expander(f"Why they say this ({len(fired)} of {len(facts)} campaigns raised a concern)"):
            st.caption(dd.rule_in_words(d) if d else "")
            if not fired:
                st.caption("Nothing stands out under your current guardrail settings.")
            for pk in fired:
                ev = dd.evidence_for(pk["campaign_id"], report["campaigns"])
                row = cd.set_index("campaign_id").loc[pk["campaign_id"]]
                passed = sum(c["status"] == "PASS" for c in ev.checks)
                applicable = sum(c["status"] != "NA" for c in ev.checks)
                st.markdown(f"**{pk['campaign_id']}**: {voice.conf_phrase(ev.tier).lower()} ({passed} of {applicable} quality checks passed). "
                            f"The platform claims {xfmt(row['claimed_roas'])}; our tests prove {xfmt(row['proven'])}"
                            + (f", and we are 95% sure the true figure is between {xfmt(row['lower'])} and {xfmt(row['upper'])}" if pd.notna(row["lower"]) else "") + ".")
                txt = dd.best_worst_case(row, margin, BE)
                if txt:
                    st.caption(ui.esc(txt))
            st.caption(f"Source: control test results, {days} days of data, run {run_id[:8]}.")
safe_page_link("pages/4_Agents.py", "Open the full advisory council and set your guardrails", ":material/groups:")

# -------------------------------------------------------------------------------------------- 03 evidence
ui.section("03", "The evidence", "The charts behind the answer. Each one can be switched to a table you can copy into a spreadsheet.", "evidence")
for key in ("returns", "overclaim", "trend", "waterfall", "portfolio"):
    if key not in shown:
        card(key)

with st.expander("Benchmark context for these charts"):
    try:
        from pipeline import get_registry
        reg = get_registry()
        roi = reg.find("roi_interval_width").records
        dur = reg.find("test_duration_days").records
        st.markdown(f"- **Breakeven line**: {econ.get('note') or 'revenue breakeven of 1.00x because no margin was declared.'}\n"
                    + (f"- **How certain is any single test?** {roi[0]['definition']} (peer reviewed, confidence {roi[0]['confidence']}). Read returns as ranges, not exact points.\n" if roi else "")
                    + (f"- **Typical test length**: Meta geo tests in a large industry study ran about {dur[0]['value']:.1f} days on average (confidence {dur[0]['confidence']}).\n" if dur else "")
                    + "- **Industry comparison**: no channel return range is shown because no reliable, like for like range exists. See the Benchmarks page.")
    except Exception:
        st.caption("Benchmark registry unavailable for this view.")

# ------------------------------------------------------------------------------------------ 04 decisions
ui.section("04", "Decisions for your sign-off", "The system flags what deserves attention; people decide. Every decision, whether you approve, change or reject it, is signed by you on the Sign-off desk and kept in a permanent record.", "decisions")
visible = [i for i in inbox if not personas or i["packet"]["target_persona"] in personas]
if is_strict:
    st.caption("Dollar amounts here cover the test period only.")
if not visible:
    ui.callout("Nothing needs a decision for this view right now. Every channel is within your guardrails.", "ok")
log_path = Path(DATA_ROOT) / "workspaces" / ws / "run_audit_log.json"
for item in visible:
    p = item["packet"]
    t = tier_of.get(p["campaign_id"]) or p.get("tier")
    g = dd.gate(t)
    sev, sev_kind = ui.SEVERITY_LABEL.get(p["severity"], (p["severity"], "muted"))
    sig = store.get_signoff(ws, item["id"])
    with st.container(border=True):
        st.markdown(f"{ui.pill(sev, sev_kind)} {ui.tier_pill(t)} {ui.pill(item['status'].capitalize(), 'muted')}", unsafe_allow_html=True)
        st.markdown(f"#### {ui.scrub(p['title'])}")
        st.caption(f"Raised for {p['target_persona']} · {p['channel']} · {voice.conf_phrase(t)}")
        ui.stat_row([dict(label=ui.scrub(name), value=str(val)) for name, val in p["value_add_metrics"].items()], compact=True)
        st.markdown(f"**What this means:** {ui.safe(p['strategic_callout'])}")
        row = cd[cd["campaign_id"] == p["campaign_id"]]
        bw = dd.best_worst_case(row.iloc[0], margin, BE) if len(row) else None
        if bw:
            st.caption(ui.esc(bw))
        if sig:
            st.markdown(f"{ui.pill('Signed', 'ok')} {ui.esc(sig['outcome'].capitalize())} by {html.escape(sig['email'])} ({html.escape(sig['role'])}) on {sig['created_at'][:10]}.", unsafe_allow_html=True)
        elif not g["can_approve"]:
            st.caption(g["message"])
        b1, b2 = st.columns([2, 1.4])
        try:
            if item["status"] in ("new", "reviewed", "approved"):
                if b1.button("Review and sign" if item["status"] != "approved" else "Open in the sign-off desk", key=f"rs_{item['id']}", type="primary" if item["status"] != "approved" else "secondary"):
                    st.session_state["signoff_item"] = item["id"]
                    st.switch_page("pages/12_Signoff.py")
            if b2.button("Draft memo", key=f"mm_{item['id']}"):
                from memo_service import draft_memo, facts_for_item
                from memo_writer import configured_writer
                memo = draft_memo(store, ws, item, facts_for_item(store, ws, run_id, item), run_id, configured_writer(), actor)
                st.toast("Memo drafted and verified. Open the Memos page to review and approve it." + (" (AI draft replaced by template)" if memo["fallback_reason"] else ""))
        except StoreError as exc:
            st.error(str(exc))

# ------------------------------------------------------------------------------------------- 05 what if
ui.section("05", "Scenario: moving the Netflix budget", "An illustration at proven returns. It is a scenario, not a forecast and not a recommendation.", "whatif")
if base_realloc is None:
    ui.callout("The what-if needs Netflix, Google and Meta Ads data with holdout coverage. Upload data covering those channels to use it.")
else:
    s1, s2 = st.columns(2)
    shift = s1.slider("Netflix spend to move ($)", 0.0, float(base_realloc["spend"]), float(base_realloc["spend"]), step=1000.0)
    gp = s2.slider("Share sent to Google (the rest goes to Meta)", 0, 100, int(realloc["google_pct"]) if realloc else 50, step=5)
    r = dd.reallocation(ch, shift=shift, google_pct=float(gp))
    ui.stat_row([dict(label="Revenue expected from the new channels", value=money(r["gross"])), dict(label="Netflix revenue given up", value="-" + money(r["lost"])),
                 dict(label="Net revenue change", value=money(r["net"], True), kind="ok" if r["net"] >= 0 else "bad")])
    ui.callout(f"Moving {money(r['amount'])} out of Netflix would {'add' if r['net'] >= 0 else 'cost'} about <b>{money(abs(r['net']))}</b> in revenue at the proven returns "
               f"(Google {xfmt(r['a_iroas'])}, Meta {xfmt(r['b_iroas'])}, Netflix {xfmt(r['from_iroas'])}).", "ok" if r["net"] >= 0 else "bad")
    st.caption(f"Counting basis: {PLAIN_BASIS}. Assumes returns hold at the new spend level. Real returns usually fall as a channel saturates, so consider confirming with a scaled test before moving the full amount.")

# ------------------------------------------------------------------------------ 06 sources and confidence
ui.section("06", "Sources and how we know this is right", "Where every number comes from, how sure we are, and the checks behind each result.", "sources")
checks_all = [k for c in report["campaigns"] for k in c["checks"]]
passed_all, total_all = sum(k["status"] == "PASS" for k in checks_all), sum(k["status"] != "NA" for k in checks_all)
st.markdown(f"Three independent sources are reconciled: what the platforms report, what the attribution model credits, and what a controlled test in matched markets proves. "
            f"Results come from the controlled test, and we show a 95% likely range around each one. {n_sig} of {n_all} campaigns are statistically significant, meaning the lift is clearly more than zero, "
            f"and the campaigns passed {passed_all} of {total_all} quality checks overall.")
st.write("")
inputs_info = []
for tname, label_ in (("RAW_PLATFORM_DATA", "Platform reported performance"), ("RAW_MTA_OUTPUT", "Attribution model output"), ("RAW_HOLDOUT_DATA", "Geo holdout test")):
    try:
        df_ = store.load_table(ws, run_id, f"INPUT_{tname}")
        dates = pd.to_datetime(df_["date"], errors="coerce")
        inputs_info.append([label_, f"{len(df_):,}", f"{dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}", str((run.get("input_hashes") or {}).get(tname, ""))[:10]])
    except Exception:
        inputs_info.append([label_, "n/a", "n/a", ""])
st.markdown("##### Data sources")
html_table(["Source", "Rows", "Dates covered", "Content hash"], [[html.escape(c) for c in r] for r in inputs_info])
st.write("")
st.markdown("##### Quality checks by campaign")
st.caption("Six checks decide how far each result can be trusted: whether test and comparison markets behaved alike beforehand, whether the test was big enough, how narrow the likely range is, how the result compares with industry norms, whether seasonality is distorting it, and whether our sources agree. N/A means there was nothing reliable to compare against.")
check_names = {1: "Parallel trends", 2: "Sample size", 3: "Interval precision", 4: "Benchmark range", 5: "Seasonality", 6: "Sources agree"}
rows = []
for c in report["campaigns"]:
    st_ = {k["check_id"]: k["status"] for k in c["checks"]}
    rows.append([html.escape(c["campaign_id"]), ui.tier_pill(c["tier"]), f"{c['trust_score']:.0f}",
                 f"{xfmt(c['strict_iroas'])} [{xfmt(c['strict_iroas_lower'])} to {xfmt(c['strict_iroas_upper'])}]"] + [("N/A" if st_.get(i) in (None, "NA") else st_[i].title()) for i in check_names])
html_table(["Campaign", "Confidence", "Score", "Proven return (95% range)"] + list(check_names.values()), rows)
st.write("")
st.markdown("##### What each guardrail watches for")
rule_rows = []
for lid in LENS_IDS:
    d = defs.get(lid)
    if d:
        rule_rows.append([html.escape(d["name"]), f"v{d.get('version', 1)}", html.escape(dd.rule_in_words(d)), str(len(evaluate_agents([{**d, 'enabled': True}], facts)))])
html_table(["Guardrail", "Version", "Raises a concern when", "Campaigns"], rule_rows)
st.write("")
bctx = report.get("benchmark_context") or {}
sf = (run["validation"] or {}).get("scale_factor") or {}
st.markdown("##### Method")
st.markdown(f"- Counting basis **{PLAIN_BASIS}**; both are always computed.\n- Policy version **{report['settings_fingerprint']}**; code version **{str(run.get('code_version', ''))[:8]}**; run **{run_id[:8]}**.\n"
            + (f"- Benchmark registry version **{bctx['benchmark_set_version']}**.\n" if bctx.get("benchmark_set_version") else "- No outside benchmark version was used in scoring; the built in channel ranges are illustrative placeholders.\n")
            + (f"- Test market size check: the treatment markets hold {sf['census_share']:.1%} of the US population against a declared sample of {sf['declared_fraction']:.1%}.\n" if sf else "")
            + "- Confidence intervals are 95%. Channel intervals add the campaign bounds together, which is conservative (wider than strictly needed).")
issues = run["validation"]["issues"]
if issues:
    with st.expander(f"Data checks recorded for this run ({sum(i['severity'] == 'WARNING' for i in issues)} warnings)"):
        for i in issues:
            st.markdown(f"{ui.pill('Warning' if i['severity'] == 'WARNING' else 'Note', 'warn' if i['severity'] == 'WARNING' else 'info')} **{i['rule']}**: {i['message']}", unsafe_allow_html=True)
entries = read_log(log_path)
with st.expander(f"Signed decisions log ({len(entries)} entries)"):
    ok, why = verify_log(log_path)
    st.markdown(ui.pill("Log intact" if ok else "Log altered", "ok" if ok else "bad") + f" {html.escape(why if not ok else 'Every entry chains to the one before it.')}", unsafe_allow_html=True)
    if entries:
        view_ = pd.DataFrame([{"When": e.get("timestamp_utc", "")[:19], "Decision": e.get("decision_outcome", ""), "Rule": e.get("agent_rule_triggered", ""), "Signed by": (e.get("authorizing_user") or {}).get("email", ""),
                               "Role": (e.get("authorizing_user") or {}).get("role", ""), "Note": e.get("justification", ""), "Trust score": e.get("trust_score_at_signing", "")} for e in entries])
        st.dataframe(view_, hide_index=True, width="stretch")
with st.expander("Glossary: every term and formula"):
    for key, (label_, plain, formula) in ui.GLOSSARY.items():
        st.markdown(f"**{label_}.** {plain}" + (f" *Formula: {formula}.*" if formula else ""))
if econ.get("margin"):
    with st.expander("Profit view by campaign"):
        prof = cd[["campaign_id", "channel", "proven", "tier"]].copy()
        prof.columns = ["Campaign", "Channel", "Proven return per $1", "Confidence"]
        prof["Breakeven"] = BE
        prof["Profit per $1 of ad spend"] = prof["Proven return per $1"] * margin - 1.0
        prof["Confidence"] = prof["Confidence"].map(lambda v: ui.TIER_LABEL.get(v, (v,))[0])
        st.dataframe(prof.round(3), hide_index=True, width="stretch")
with st.expander("Raw tables"):
    st.dataframe(audit, width="stretch", hide_index=True)
    st.dataframe(alerts, width="stretch", hide_index=True)
