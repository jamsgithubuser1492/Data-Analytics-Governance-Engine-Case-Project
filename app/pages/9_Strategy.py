"""Business strategy: from measured results to company level decisions (trade-offs, implications, change plan, budget lens, monitoring)."""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_store, identity, page_setup, safe_page_link, succeeded_runs  # noqa: E402

page_setup("Strategy", ":material/account_tree:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import charts  # noqa: E402
import dashdata as dd  # noqa: E402
import strategy as sg  # noqa: E402
import ui  # noqa: E402
from runview import load_view  # noqa: E402

store = get_store()
actor, ws = identity()
runs = succeeded_runs(ws)
charts.use_theme(ui.tokens())

ui.page_head("Strategize", "Business strategy",
             "The dashboard shows what the data says. This page helps with what it could mean for the company: what moving money would change, who is affected, how to bring people along, "
             "how to budget going forward and what to keep watching. Findings are facts; ideas are offered to consider, and the decision stays with you.")

if not runs:
    ui.callout("Strategy needs a measured run to work from. Load the case study data from the Dashboard (choose Try with demo data) or upload your own files.")
    safe_page_link("app.py", "Go to the Dashboard", ":material/analytics:")
    st.stop()


def money(v: float, sign: bool = False) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    return f"{'+' if sign and v > 0 else ('-' if v < 0 else '')}${abs(v):,.0f}"


labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
run_id = st.selectbox("Run to work from", list(labels), format_func=labels.get, key="strategy_run")
v = load_view(store, ws, run_id)
ch, BE = v.ch, v.breakeven
test_days = max(int(v.rolling["date"].nunique()) - int(v.settings.pre_period_days), 1) if len(v.rolling) else 60
st.markdown(f'<div class="note">Counting basis {ui.pill(v.basis, "info")} Breakeven {BE:.2f}x. Every figure comes from this run; assumptions are labelled.</div>', unsafe_allow_html=True)
st.write("")

t_trade, t_impl, t_change, t_budget, t_watch = st.tabs(["Trade-offs", "Implications", "Change plan", "Budget framework", "Monitor"])

# ================================================================================================= trade-offs
with t_trade:
    st.markdown("#### The question this answers")
    st.markdown("**If budget moved from one channel to others, what would it change, how sure are we, and what does waiting cost?**")
    default = sg.default_moves(ch, BE)
    measured = ch.dropna(subset=["proven"])["channel"].tolist()
    src_default = default[0]["source"] if default else measured[0]
    c1, c2 = st.columns([1, 1])
    source = c1.selectbox("Move budget out of", measured, index=measured.index(src_default), key="sc_source")
    src_spend = float(ch.set_index("channel").loc[source, "spend"])
    amount = c2.slider("Amount to move ($)", 0.0, src_spend, src_spend, step=1000.0, format="$%.0f", key=f"sc_amount_{source}")
    others = [c for c in measured if c != source]
    tdefault = [m["target"] for m in default if m["source"] == source] or others[:1]
    targets = st.multiselect("Into", others, default=[t for t in tdefault if t in others], key=f"sc_targets_{source}")
    if len(targets) == 2:
        share = st.slider(f"Share sent to {targets[0]} (the rest goes to {targets[1]})", 0, 100, 50, 5, key="sc_share")
        weights = [share / 100, 1 - share / 100]
    else:
        weights = [1 / len(targets)] * len(targets) if targets else []
        if len(targets) > 2:
            st.caption("Money is split evenly across the receiving channels.")
    moves = [dict(source=source, target=t, amount=amount * w) for t, w in zip(targets, weights)]
    if not moves or amount <= 0:
        ui.callout("Choose a channel to move budget out of and at least one to receive it.")
        plan = sg.plan_reallocation(ch, [])
    else:
        plan = sg.plan_reallocation(ch, moves)
        delay = sg.cost_of_delay(plan["net"], test_days)
        sens = sg.saturation_sensitivity(ch, moves)
        cards = [dict(label="Budget moved", value=money(plan["moved"]), sub="Total spend does not change"),
                 dict(label="Revenue expected from receiving channels", value=money(plan["gross"]), sub="At their proven average returns"),
                 dict(label="Revenue given up", value="-" + money(plan["lost"]), sub=f"From {source}"),
                 dict(label="Net revenue change", value=money(plan["net"], True), kind="ok" if plan["net"] >= 0 else "bad",
                      sub=(f"Worst to best case {money(plan['net_low'], True)} to {money(plan['net_high'], True)}" if pd.notna(plan["net_low"]) else "No interval on the spec basis"))]
        ui.stat_row(cards)
        ui.callout(f"Moving {money(plan['moved'])} out of {source} would change revenue by about <b>{money(plan['net'], True)}</b> at proven average returns. "
                   f"Spread over the {test_days} day test period, that is a modeled <b>{money(delay['per_week'], True)} per week</b>, so each week of delay has a modeled cost of about that amount. "
                   "Given that returns usually fall as spend rises, perhaps we should think about the sensitivity below before acting.", "ok" if plan["net"] >= 0 else "bad")
        st.write("")
        sh = charts.spend_shift_chart(plan["table"], "Spend by channel, today and in the scenario")
        ui.chart_card("shift", sh.layout.meta["headline"], sh.layout.meta["subtitle"], sh,
                      plan["table"].rename(columns={"channel": "Channel", "spend_before": "Spend today", "change": "Change", "spend_after": "Spend in the scenario", "change_pct": "Change as share of today"}).round(3),
                      v.basis, "Source: this run's channel spend. The scenario is an illustration, not a forecast and not a recommendation.")
        be = sens["break_even_haircut"]
        head = (f"The net gain stays positive until the return on the new money is {be:.0%} below its average" if pd.notna(be) and be < 1 else "The scenario adds nothing on a net basis")
        sc = charts.sensitivity_chart(sens["table"], be, head)
        ui.chart_card("sens", head, sc.layout.meta["subtitle"], sc, sens["table"].rename(columns={"haircut": "Return on new money below its average", "net": "Net revenue change"}).round(3),
                      v.basis, "Assumption: the return on new money falls by the percentage shown. This is a sensitivity, not a prediction.")
        st.caption(ui.esc("Sources and assumptions: average proven returns from the holdout test; interval bounds from the 95% confidence interval where the strict basis provides one; "
                          f"weekly value divided over a {test_days} day test period. Returns usually fall as spend rises, so consider confirming with a scaled test."))

# ============================================================================================== implications
with t_impl:
    st.markdown("#### The question this answers")
    st.markdown("**Who inside the company would feel this move, and what would we need to find out first?**")
    st.markdown('<div class="note">The system computes what changes. The estimates that only your teams know (cost, hours, contract terms) are blank for you to fill in. The system does not supply them.</div>', unsafe_allow_html=True)
    rows = sg.implications(ch, plan)
    out_rows = []
    cols = st.columns(2)
    for i, r in enumerate(rows):
        with cols[i % 2], st.container(border=True):
            st.markdown(f"##### {r['function']}")
            st.markdown(ui.esc(f"**What changes.** {r['what_changes']}"))
            st.markdown("**Questions to answer**")
            for q in r["questions"]:
                st.markdown(f"- {q}")
            vals = {}
            for fld in r["fields"]:
                vals[fld] = st.text_input(fld, key=f"ws_{i}_{fld}", placeholder="Your estimate")
            out_rows.append({"Function": r["function"], "What changes": r["what_changes"], **vals})
    ws_df = pd.DataFrame(out_rows).fillna("")
    st.download_button("Download this worksheet (CSV)", ws_df.to_csv(index=False).encode("utf-8"), "implications_worksheet.csv", "text/csv", key="dl_ws")
    st.caption("Sources and assumptions: spend figures from the scenario above; evidence levels from this run. Nothing in the blank fields is estimated by the system.")

# ================================================================================================ change plan
with t_change:
    st.markdown("#### The question this answers")
    st.markdown("**How could the organization be brought along, in what order, and what will each group want to see?**")
    div = len(dd.divergence(v.cd))
    run_tier = v.settings.trust_tier(float(v.report["average_trust_score"]), True)
    cp = sg.change_plan(v.tot, ch, div, len(v.cd), v.is_strict, run_tier, BE)
    st.markdown("##### What each group may care about")
    sc_cols = st.columns(2)
    for i, s in enumerate(cp["stakeholders"]):
        with sc_cols[i % 2], st.container(border=True):
            st.markdown(f"**{s['group']}**")
            st.caption(f"May worry about: {s['worries']}")
            st.markdown(ui.esc(f"**What the evidence offers.** {s['evidence']}"))
            st.markdown(ui.esc(s["consider"]))
    st.markdown("##### A phased path to consider")
    ph = st.columns(2)
    total, done = 0, 0
    for i, (name, items) in enumerate(cp["phases"]):
        with ph[i % 2], st.container(border=True):
            st.markdown(f"**{i + 1}. {name}**")
            for j, it in enumerate(items):
                total += 1
                done += int(st.checkbox(ui.esc(it), key=f"cp_{i}_{j}"))
    st.progress(done / total if total else 0.0, text=f"{done} of {total} items ticked off")
    st.caption("Sources and assumptions: stakeholder concerns are common patterns, not findings about your organization. Evidence lines are computed from this run.")

# ============================================================================================ budget framework
with t_budget:
    st.markdown("#### The question this answers")
    st.markdown("**How is today's spend spread across proven, promising and unproven channels, and how does that compare with the mix we want?**")
    st.markdown('<div class="note">This is an optional policy lens. The thresholds and the target mix are yours to set; they are not facts and not recommendations.</div>', unsafe_allow_html=True)
    b1, b2 = st.columns(2)
    core_min = b1.number_input("Core: proven return at least (x), with Verified evidence", 0.5, 20.0, 2.0, 0.1, key="lens_core")
    val_min = b2.number_input("Validation: proven return at least (x)", 0.0, 20.0, float(round(BE, 2)), 0.05, key="lens_val")
    t1, t2, t3 = st.columns(3)
    tc = t1.number_input("Target share in Core (%)", 0.0, 100.0, 70.0, 5.0, key="lens_t1")
    tv = t2.number_input("Target share in Validation (%)", 0.0, 100.0, 20.0, 5.0, key="lens_t2")
    ts = t3.number_input("Target share in Sandbox (%)", 0.0, 100.0, 10.0, 5.0, key="lens_t3")
    if abs(tc + tv + ts - 100.0) > 1e-6:
        st.error(f"The target shares add up to {tc + tv + ts:.0f}%. They need to total 100%.")
    else:
        lens = sg.allocation_lens(ch, core_min, val_min, (tc, tv, ts))
        tb = lens["table"]
        core_row = tb[tb["tier"] == "Core"].iloc[0]
        ui.callout(f"{core_row['share']:.0%} of spend is in Core channels against a target of {tc:.0f}%, a gap of {abs(core_row['gap']) * 100:.0f} points. "
                   + ("Given that some spend sits below the threshold, perhaps we should think about what evidence would justify it staying there." if tb[tb["tier"] == "Below threshold"].iloc[0]["share"] > 0 else "No spend sits below the threshold."))
        st.write("")
        figa = charts.allocation_chart(tb, f"{core_row['share']:.0%} of spend is in Core, against a {tc:.0f}% target")
        ui.chart_card("alloc", figa.layout.meta["headline"], figa.layout.meta["subtitle"], figa,
                      tb.rename(columns={"tier": "Tier", "share": "Current share", "target": "Target", "gap": "Gap", "channels": "Channels"}).round(3), v.basis,
                      "Core: Verified evidence and a return at or above the Core level. Validation: at or above the Validation level. Sandbox: no holdout evidence yet.")
        bc = lens["by_channel"].copy()
        bc["tier"] = bc["tier"].map(lambda x: ui.TIER_LABEL.get(x, (x,))[0])
        bc.columns = ["Channel", "Spend", "Proven return", "Evidence", "Tier"]
        st.dataframe(bc.round(3), hide_index=True, width="stretch")
    st.caption("Sources and assumptions: spend and returns from this run. A tiered mix is one way to balance proven and unproven spend; your finance policy may differ.")

# ===================================================================================================== monitor
with t_watch:
    st.markdown("#### The question this answers")
    st.markdown("**Is performance holding as time passes, and which campaigns would deserve a second look?**")
    m1, m2 = st.columns(2)
    floor = m1.number_input("Return floor (x)", 0.0, 20.0, float(round(BE, 2)), 0.05, key="mon_floor", help="A channel whose latest 7 day return is under this level is flagged.")
    window = m2.slider("Look back (days)", 7, 30, 14, key="mon_window")
    roll = dd.rolling_with_band(v.rolling)
    mon = sg.decay_monitor(roll, window, floor)
    kind = {"Stable": "ok", "Falling": "warn", "Below floor": "bad", "Not enough days": "muted"}
    rows_html = "".join(f"<tr><td>{html.escape(r.channel)}</td><td>{ui.pill(r.status, kind[r.status])}</td><td>{html.escape(r.note)}</td></tr>" for r in mon.itertuples())
    st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Channel</th><th>Status</th><th>What the recent days show</th></tr></thead><tbody>{rows_html}</tbody></table></div>', unsafe_allow_html=True)
    figm = charts.trend_chart(roll, floor, f"Return floor {floor:.2f}x", charts.trend_headline(roll, floor))
    ui.chart_card("monitor", figm.layout.meta["headline"], figm.layout.meta["subtitle"], figm,
                  roll[["date", "channel", "iroas"]].assign(date=lambda d: d["date"].astype(str).str[:10]).rename(columns={"date": "Date", "channel": "Channel", "iroas": "7 day return"}).round(3),
                  "Reported by spec", "Daily series on the spec basis, which overstates returns; read direction rather than level.")
    st.markdown("##### Capital protection preview")
    p1, p2 = st.columns(2)
    spend_min = p1.number_input("Spend at least ($)", 0.0, 10_000_000.0, 10000.0, 1000.0, key="cap_spend")
    cap_floor = p2.number_input("Proven return below (x)", 0.0, 20.0, 1.0, 0.05, key="cap_floor")
    cap = sg.capital_protection_preview(v.cd, spend_min, cap_floor)
    if cap.empty:
        ui.callout("No campaign meets both conditions on this basis.", "ok")
    else:
        rws = "".join(f"<tr><td>{html.escape(r.campaign_id)}</td><td>{money(r.spend)}</td><td>{r.proven:.2f}x</td><td>{ui.tier_pill(r.tier)}</td></tr>" for r in cap.itertuples())
        st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Campaign</th><th>Spend</th><th>Proven return</th><th>Evidence</th></tr></thead><tbody>{rws}</tbody></table></div>', unsafe_allow_html=True)
        st.caption(f"{len(cap)} campaign(s) meet the rule. Given that this is a preview, perhaps we should think about whether a review step should be required for these before any budget change.")
    st.caption("Information only: nothing is paused, staged or changed. Sources and assumptions: this run's rolling return and campaign totals; the thresholds are yours.")
