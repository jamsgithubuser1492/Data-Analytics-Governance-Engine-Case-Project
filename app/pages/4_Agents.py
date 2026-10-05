"""Advisory council and guardrails: personas interpret the facts, and rules are set in plain business language."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_store, identity, page_setup, safe_page_link, succeeded_runs  # noqa: E402

page_setup("Advisory council", ":material/groups:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import council as cn  # noqa: E402
import guide_content  # noqa: E402
import stances as sx  # noqa: E402
import ui  # noqa: E402
from agent_engine import build_facts, default_definitions, evaluate_agents  # noqa: E402
from agent_schema import ACTIONS, PERSONAS as RULE_PERSONAS  # noqa: E402
from runview import load_view  # noqa: E402

store = get_store()
actor, ws = identity()
runs = succeeded_runs(ws)

ui.page_head("Interpretation", "Advisory council",
             "Four advisors read the same verified facts through different motivations and risk appetites. They offer ideas to consider, never instructions. "
             "Set your own guardrails in plain business terms, and see how each choice changes what gets flagged.")

if not runs:
    ui.callout("There is nothing to interpret yet. Load the case study data from the Dashboard (choose Try with demo data) or upload your own files, then return here.")
    safe_page_link("app.py", "Go to the Dashboard", ":material/analytics:")
    st.stop()

labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
run_id = st.selectbox("Run to interpret", list(labels), format_func=labels.get, key="council_run")
v = load_view(store, ws, run_id)
facts = build_facts(v.recon, v.report, v.is_strict)
defs = {d["id"]: d for d in (store.get_agent_definitions(ws) or default_definitions())}
council = cn.convene(v.ch, v.cd, v.tot, v.breakeven, v.is_strict, v.holdout_coverage)

STANCE_KIND = ui.STANCE_KIND


def lean_pill(p: cn.Persona) -> str:
    return ui.lean_pill(p.lean)


def bar_text(p: cn.Persona) -> str:
    return (f"Wants {cn.TIER_WORDS[p.evidence_floor]} evidence before backing a money move, "
            f"{'judges a channel by the cautious end of its interval' if p.uses_lower_bound else 'judges a channel by its central estimate'}, "
            f"treats {p.clearance:g}x breakeven as clearly profitable, and tolerates platforms claiming up to {p.overclaim_tolerance:g}x what the test confirms.")


tab_council, tab_rules, tab_how = st.tabs(["The council", "Your guardrails", "How it works"])

# ============================================================================================== the council
with tab_council:
    st.markdown(f'<div class="note">Counting basis {ui.pill(v.basis, "info")} Breakeven {v.breakeven:.2f}x. Every number below is computed from this run; the advisors add interpretation only.</div>', unsafe_allow_html=True)
    who = st.segmented_control("Show", ["Whole council"] + [p.name for p in cn.PERSONAS], default="Whole council", key="council_who", label_visibility="collapsed") or "Whole council"
    st.write("")

    if who == "Whole council":
        a, s = st.columns(2)
        with a, st.container(border=True):
            st.markdown("##### Where the council agrees")
            for line in council.agree or ["No channel has full agreement. See the split on the right."]:
                st.markdown(f"- {line}")
        with s, st.container(border=True):
            st.markdown("##### Where the council splits")
            st.caption("A split shows where judgement and risk appetite, not the data, decide.")
            for line in council.split or ["The advisors read every channel the same way."]:
                st.markdown(f"- {line}")
        st.write("")
        cols = st.columns(2)
        for i, rd in enumerate(council.readings):
            p = rd.persona
            with cols[i % 2], st.container(border=True):
                st.markdown(f"{lean_pill(p)}", unsafe_allow_html=True)
                st.markdown(f"#### {p.name}")
                st.caption(p.role)
                st.markdown(ui.esc(rd.headline))
                ui.stat_row(rd.kpis, compact=True)
                rows = "".join(f"<tr><td>{html.escape(c.channel)}</td><td>{ui.pill(c.stance, STANCE_KIND[c.stance])}</td></tr>" for c in rd.channels)
                st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Channel</th><th>Where {html.escape(p.name)} stands</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
                st.caption(f"First question: {p.first_question}")
        st.caption("Choose an advisor above for their full reading, the facts behind each view and what would change their mind.")
    else:
        rd = next(r for r in council.readings if r.persona.name == who)
        p = rd.persona
        with st.container(border=True):
            st.markdown(f"{lean_pill(p)}", unsafe_allow_html=True)
            st.markdown(f"### {p.name}, {p.role}")
            c1, c2 = st.columns(2)
            c1.markdown(f"**Background.** {p.background}")
            c1.markdown(f"**Personality.** {p.personality}")
            c2.markdown("**Motivations**\n" + "\n".join(f"- {m}" for m in p.motivations))
            c2.markdown(f"**First question.** {p.first_question}")
            st.caption(bar_text(p))
        st.markdown("##### What the facts say, in their terms")
        st.markdown(ui.esc(rd.headline))
        ui.stat_row(rd.kpis, compact=True)
        st.markdown("##### Their view, channel by channel")
        for c in rd.channels:
            with st.container(border=True):
                st.markdown(f"{ui.pill(c.stance, STANCE_KIND[c.stance])} &nbsp; **{html.escape(c.channel)}**", unsafe_allow_html=True)
                st.markdown(ui.esc(c.text))
                with st.expander("The facts behind this and what would change their mind"):
                    st.markdown(ui.esc(f"**Facts.** {c.facts}."))
                    st.markdown(ui.esc(f"**What would change my mind.** {c.change_my_mind}."))
        if rd.portfolio:
            st.markdown("##### Across the portfolio")
            for t in rd.portfolio:
                st.markdown(f"- {ui.esc(t)}")
        related = defs.get(p.related_rule)
        if related:
            fired = evaluate_agents([{**related, "enabled": True}], facts)
            with st.expander(f"Evidence from the '{related['name']}' guardrail ({len(fired)} of {len(facts)} campaigns flagged)"):
                st.caption(ui.esc(sx.describe(related)) if related["id"] in sx.RULE_IDS else "")
                if not fired:
                    st.caption("Nothing flagged under the current guardrail settings.")
                camp = v.camp.set_index("campaign_id")
                for pk in fired:
                    r = camp.loc[pk["campaign_id"]]
                    st.markdown(ui.esc(f"**{pk['campaign_id']}**: trust score {r['trust_score']:.0f} ({cn.TIER_WORDS[r['tier']]}), "
                                + ", ".join(f"{ui.scrub(a)} {b}" for a, b in pk["value_add_metrics"].items())))
        st.caption("Sources: this run's platform, attribution and holdout data. Intervals are 95%.")

# ================================================================================================ guardrails
with tab_rules:
    st.markdown("#### Choose how cautious the whole system should be")
    st.caption("A risk appetite sets all three guardrails at once. Balanced is the standard case study setting. Your choice is saved as a new version and can be changed back at any time.")
    current = sx.detect_appetite(defs)
    names = list(sx.APPETITES)
    choice = st.radio("Risk appetite", names, index=names.index(current) if current in names else 1, horizontal=True, key="appetite")
    st.caption(sx.APPETITES[choice]["blurb"] + (f" Your guardrails currently match: {current}." if current != "Custom" else " Your guardrails are currently tuned individually (Custom)."))

    # what each appetite would flag on THIS run
    rows = []
    for rid, title in (("CAPITAL_PRESERVATION_AGENT", "Money not earned back"), ("ATTRIBUTION_SHIELD_AGENT", "Platforms claiming more than proven"), ("SCALE_OPPORTUNITY_AGENT", "Room to grow")):
        cells = []
        for ap in names:
            d, _ = sx.apply_settings(defs[rid], sx.APPETITES[ap][rid])
            n = len(evaluate_agents([{**d, "enabled": True}], facts)) if d else 0
            cells.append(f"<b>{n}</b> of {len(facts)}" if ap == choice else f"{n} of {len(facts)}")
        rows.append(f"<tr><td>{title}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    st.markdown("**What each appetite would flag on this run**")
    st.markdown('<div class="tblwrap"><table class="mm"><thead><tr><th>Guardrail</th>' + "".join(f"<th>{n}</th>" for n in names) + f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)
    if st.button(f"Apply {choice} to all three guardrails", type="primary", disabled=choice == current):
        try:
            for rid, d in sx.apply_appetite(defs, choice).items():
                store.save_agent_definition(ws, {**defs[rid], **d}, actor)
            st.toast(f"{choice} saved as a new version of each guardrail.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.divider()
    st.markdown("#### Fine tune each guardrail")
    st.caption("Each guardrail is a plain question. Change an answer and the preview shows what it would flag on this run before you save.")
    GUARDS = [
        ("CAPITAL_PRESERVATION_AGENT", "Money not earned back", "For the CFO. Catches campaigns that look profitable in the platform's own numbers but lose money once the test is applied.",
         [("claimed_at_least", "Alert when a platform claims a return of at least", 1.0, 10.0, 0.05, "x"), ("proven_below", "but the test proves less than", 0.0, 5.0, 0.05, "x")]),
        ("ATTRIBUTION_SHIELD_AGENT", "Platforms claiming more than proven", "For agencies and platform leads. Catches platforms taking more credit than the evidence supports.",
         [("overclaim_above", "Alert when a platform claims more than this many times what the test confirms", 1.0, 5.0, 0.05, "x")]),
        ("SCALE_OPPORTUNITY_AGENT", "Room to grow", "For the CMO. Catches strong, well measured campaigns that could take more budget.",
         [("proven_at_least", "Alert when the proven return is at least", 0.5, 20.0, 0.1, "x"), ("overclaim_at_most", "and platforms claim no more than this many times what the test confirms", 1.0, 5.0, 0.05, "x")]),
    ]
    for rid, title, blurb, fields in GUARDS:
        base = defs[rid]
        cur = sx.read_settings(base)
        with st.container(border=True):
            top_l, top_r = st.columns([4, 1])
            top_l.markdown(f"##### {title}")
            top_l.caption(blurb)
            enabled = top_r.toggle("Watching", value=bool(base.get("enabled", True)), key=f"en_{rid}")
            st.markdown(f"**Right now:** {ui.esc(sx.describe(base))}")
            vals = {}
            cols = st.columns(len(fields))
            for col, (key, label, lo, hi, step, unit) in zip(cols, fields):
                vals[key] = col.number_input(f"{label} ({unit})", lo, hi, float(min(max(cur[key], lo), hi)), step, key=f"{rid}_{key}")
            c1, c2 = st.columns(2)
            vals["min_spend"] = c1.number_input("Only when at least this much is being spent ($)", 0.0, 10_000_000.0, float(cur["min_spend"]), 1000.0, key=f"{rid}_spend",
                                                help="Small campaigns create noisy alerts. A floor keeps the guardrail focused on money that matters.")
            tier_label = c2.selectbox("Evidence level needed", list(sx.TIER_CHOICES), index=list(sx.TIER_CHOICES.values()).index(cur["min_tier"]), key=f"{rid}_tier",
                                      help="Verified results passed every quality check. Directional results are informative but weaker.")
            vals["min_tier"] = sx.TIER_CHOICES[tier_label]
            cand, errs = sx.apply_settings(base, vals)
            if errs:
                st.error(" ".join(errs))
            else:
                fired = evaluate_agents([{**cand, "enabled": True}], facts)
                st.markdown(f'{ui.pill("Preview", "info")} Would flag <b>{len(fired)} of {len(facts)}</b> campaigns on this run'
                            + (": " + ", ".join(p["campaign_id"] for p in fired) if fired else "."), unsafe_allow_html=True)
                changed = any(abs(float(cur.get(k, 0)) - float(vals[k])) > 1e-9 for k in vals if k != "min_tier") or cur["min_tier"] != vals["min_tier"] or enabled != bool(base.get("enabled", True))
                if st.button("Save this guardrail", key=f"save_{rid}", disabled=not changed):
                    _, e2 = store.save_agent_definition(ws, {**cand, "enabled": enabled}, actor)
                    st.toast("Saved as a new version." if not e2 else " ".join(e2))
                    st.rerun()

    st.divider()
    with st.expander("Add a watch of your own"):
        st.caption("Say it as a sentence: tell me when a measure goes above or below a level. The same safety rules apply, and every save is a new version.")
        MEASURES = {"Proven return per $1": ("iroas", "x2", 0.0, 20.0), "Claimed return per $1": ("reported_roas", "x2", 0.0, 50.0), "Over-claim multiple": ("inflation_ratio", "x2", 0.0, 20.0),
                    "Trust score (0 to 100)": ("trust_score", "number", 0.0, 100.0), "Spend ($)": ("total_spend", "usd", 0.0, 5_000_000.0)}
        n1, n2 = st.columns(2)
        wname = n1.text_input("Name this watch", placeholder="Example: Low proven return")
        who_sees = n2.selectbox("Who should see it", RULE_PERSONAS)
        m1, m2, m3 = st.columns([3, 1.4, 1.6])
        measure = m1.selectbox("Tell me when", list(MEASURES))
        mkey, mfmt, mlo, mhi = MEASURES[measure]
        op = m2.selectbox("is", ["above", "below"])
        level = m3.number_input("this level", mlo, mhi, min(max(1.0, mlo), mhi), 0.05 if mhi <= 50 else 1000.0)
        action_labels = {"Just flag it for review": "REVIEW_MEASUREMENT", **{lbl: code for code, (lbl, _) in ACTIONS.items() if code != "REVIEW_MEASUREMENT"}}
        action = st.selectbox("and suggest", list(action_labels))
        wid = re.sub(r"[^A-Z0-9]+", "_", ("WATCH_" + wname.upper()).strip("_"))[:40].strip("_")
        if st.button("Save watch", disabled=len(wname.strip()) < 3):
            new = {"id": wid, "name": wname.strip(), "description": f"{measure} {op} {level:g}", "persona": who_sees, "severity": "WARNING", "action": action_labels[action], "enabled": True,
                   "priority": 50, "requires_min_tier": "NOT_DECISION_GRADE", "min_spend": 0.0, "deadband_pct": 0.0,
                   "trigger": {"all": [{"metric": mkey, "op": ">" if op == "above" else "<", "value": float(level)}], "any": []},
                   "value_add": [{"label": measure, "expression": mkey, "format": mfmt}], "title": f"{wname.strip()}: " + "{campaign_id}",
                   "callout": "Consider reviewing {channel}: " + f"{measure.lower()} is " + "{m1}, which is " + f"{op} the level you set ({level:g})."}
            ver, errs = store.save_agent_definition(ws, new, actor)
            st.success(f"Saved as version {ver}.") if not errs else st.error(" ".join(errs))
    safe_page_link("pages/8_Advanced_rules.py", "Open the advanced rule editor (for analysts)", ":material/code:")

# ================================================================================================ how it works
with tab_how:
    st.markdown("#### The short version")
    st.markdown("Three guardrails watch every result. A risk appetite sets how sensitive they are. Four advisors then interpret what was flagged, each from their own motivations, "
                "and offer ideas to consider. The facts never change with the advisor; only the interpretation does.")
    wanted = {"The trust score and the three trust levels", "Guardrails: the rules that watch your results", "Risk appetite: Conservative, Balanced or Aggressive", "The advisory council"}
    for title, body in guide_content.SECTIONS:
        if title in wanted:
            with st.expander(title):
                st.markdown(body)
    safe_page_link("pages/7_Guide.py", "Read the full methodology guide", ":material/help:")
