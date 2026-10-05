"""AI brief: a copy ready, fact grounded prompt for the company's own AI assistant, and a checker for what comes back."""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_store, identity, page_setup, safe_page_link, succeeded_runs  # noqa: E402

page_setup("AI brief", ":material/auto_awesome:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import council as cn  # noqa: E402
import privacy  # noqa: E402
import prompt_pack as pp  # noqa: E402
import strategy as sg  # noqa: E402
import ui  # noqa: E402
from runview import load_view  # noqa: E402

store = get_store()
actor, ws = identity()
runs = succeeded_runs(ws)

ui.page_head("Strategize", "Brief your own AI assistant",
             "Turn this run into a ready-to-paste prompt for your company's approved AI service. It carries only verified, aggregate facts, asks the assistant to stay even handed and to cite what it uses, "
             "and the second tab checks the numbers in whatever comes back.")

if not runs:
    ui.callout("A brief needs a measured run to draw on. Load the case study data from the Dashboard (choose Try with demo data) or upload your own files.")
    safe_page_link("app.py", "Go to the Dashboard", ":material/analytics:")
    st.stop()

labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
run_id = st.selectbox("Run to brief on", list(labels), format_func=labels.get, key="brief_run")
v = load_view(store, ws, run_id)
test_days = max(int(v.rolling["date"].nunique()) - int(v.settings.pre_period_days), 1) if len(v.rolling) else 60
moves = sg.default_moves(v.ch, v.breakeven)
plan = sg.plan_reallocation(v.ch, moves) if moves else None
sens = sg.saturation_sensitivity(v.ch, moves) if moves else None
delay = sg.cost_of_delay(plan["net"], test_days) if plan else None
council = cn.convene(v.ch, v.cd, v.tot, v.breakeven, v.is_strict, v.holdout_coverage)

tab_build, tab_check = st.tabs(["Build the brief", "Check an AI answer"])

# =============================================================================================== build the brief
with tab_build:
    left, right = st.columns([5, 6], gap="large")
    with left:
        ui.stepper(["Who and what", "Your context", "Privacy review", "Copy"], 1)
        st.markdown("##### 1. Who is it for, and what do you want?")
        audience = st.selectbox("The brief is written for", list(pp.AUDIENCES), key="brief_aud")
        task = st.selectbox("Ask the assistant to", list(pp.TASKS), key="brief_task", help=pp.TASKS["Executive memo"])
        st.caption(pp.TASKS[task])
        inc_scn = st.checkbox("Include the budget scenario from the Strategy page", value=bool(plan), disabled=not plan, key="brief_scn",
                              help="Moves the weakest channel's budget to the strongest measured channels. You can change it on the Strategy page.")
        inc_cou = st.checkbox("Include where the advisory council stands", value=True, key="brief_cou", help="The four personas' stance on each channel, labelled as interpretation.")
        aliases = st.checkbox("Hide channel and campaign names", value=False, key="brief_alias", help="Replaces real names with Channel A, Campaign 1 and so on. The key stays in this app.")
        st.markdown("##### 2. Anything the assistant should know?")
        ctx = st.text_area("Your context (optional)", key="brief_ctx", height=130,
                           placeholder="Example: Our Q4 plan is fixed until October. One contract has a minimum spend. We want a view for the board.",
                           help="Written by you and shown to the assistant as unverified. Personal data is replaced automatically.")
        _, found, trunc = privacy.clean_context(ctx)
        if found:
            st.warning("Personal data was detected (" + ", ".join(sorted({f.label for f in found})) + ") and will be replaced with markers in the brief. Consider removing it from your text.")
        if trunc:
            st.info(f"Your context is longer than {privacy.MAX_CONTEXT_CHARS} characters and will be shortened.")

    pack = pp.build_prompt(v, audience, task, plan=plan if inc_scn else None, delay=delay if inc_scn else None, haircut_be=(sens["break_even_haircut"] if (inc_scn and sens) else None),
                           council=council if inc_cou else None, context=ctx, use_aliases=aliases)

    with left:
        st.markdown("##### 3. Privacy review")
        with st.container(border=True):
            a, b = st.columns(2)
            a.markdown("**In this brief**\n" + "\n".join(f"- {x}" for x in pack.included))
            b.markdown("**Not in this brief**\n" + "\n".join(f"- {x}" for x in pack.excluded))
            for w in pack.warnings:
                st.caption(f"Note: {w}")
        ok = st.checkbox("I will paste this only into a company approved AI service.", key="brief_confirm")
        st.caption("Consider checking your company's AI policy first. See docs/PRIVACY_AND_GOVERNANCE.md in the repository.")

    with right:
        st.markdown("##### 4. Copy")
        if not ok:
            ui.callout("Confirm the privacy statement on the left to reveal the brief. This keeps the review from being skipped.")
        else:
            ui.stat_row([dict(label="Facts included", value=str(len(pack.facts))), dict(label="Approximate size", value=f"{pack.tokens_estimate:,} tokens"),
                         dict(label="Counting basis", value=v.basis)], compact=True)
            st.code(pack.text, language=None, wrap_lines=True, height=420)

            def log_export() -> None:
                store.log_event(ws, run_id, "prompt_exported", actor, {"sha256": pack.sha256, "audience": audience, "task": task, "aliases": aliases, "facts": len(pack.facts)})

            st.download_button("Download as a text file", pack.text.encode("utf-8"), "executive_brief_prompt.txt", "text/plain", on_click=log_export, key="brief_dl")
            st.caption(f"Content fingerprint {pack.sha256[:12]}. Exports are recorded in the audit trail by fingerprint only; the text itself is never stored. Use the copy icon at the top right of the box to copy.")
            if pack.aliaser:
                with st.expander("Alias key (keep private, do not paste into the assistant)"):
                    st.dataframe(pd.DataFrame(pack.aliaser.key_table(), columns=["Alias", "Real name"]), hide_index=True, width="stretch")
            with st.expander("The numbered facts, as a table"):
                st.dataframe(pd.DataFrame([{"Fact": f.id, "What it is": f.label, "Value": f.display} for f in pack.facts]), hide_index=True, width="stretch")

# ================================================================================================= check an answer
with tab_check:
    st.markdown("#### The question this answers")
    st.markdown("**Did the assistant stick to the facts, or did it add numbers of its own?**")
    st.caption("Paste the assistant's answer. Every figure is compared with the numbered facts in the brief. A figure that is not in the facts may be an assumption or an invention.")
    facts = pp.build_facts(v, plan if st.session_state.get("brief_scn") else None, delay if st.session_state.get("brief_scn") else None,
                           sens["break_even_haircut"] if (st.session_state.get("brief_scn") and sens) else None)
    answer = st.text_area("The assistant's answer", key="check_answer", height=220, placeholder="Paste the answer here")
    if st.button("Check the numbers", type="primary", disabled=len(answer.strip()) < 20):
        chk = pp.check_answer(answer, facts)
        kind = "ok" if chk.ok else ("warn" if chk.ungrounded <= 2 and not chk.certainty else "bad")
        ui.stat_row([dict(label="Figures that match a fact", value=str(chk.grounded), kind="ok"),
                     dict(label="Figures not found in the facts", value=str(chk.ungrounded), kind="bad" if chk.ungrounded else "ok"),
                     dict(label="Certainty phrases", value=str(len(chk.certainty)), kind="warn" if chk.certainty else "ok")])
        if chk.ok:
            ui.callout("Every figure matches a fact and no overconfident phrasing was found. Consider still reading the reasoning, since a check of numbers cannot judge the argument.", "ok")
        else:
            ui.callout("Some figures or phrases need a second look. In order to address this, we might want to think about asking the assistant to cite a fact id for each figure or to label it as an assumption.", kind)
        if chk.rows:
            kmap = {"grounded": ("Matches a fact", "ok"), "not_in_facts": ("Not in the facts", "bad"), "small_count": ("Small count, not checked", "muted")}
            by_id = {f.id: f for f in facts}
            rows = "".join(f"<tr><td>{html.escape(r.token)}</td><td>{ui.pill(*kmap[r.status])}</td><td>{html.escape((r.fact + ': ' + by_id[r.fact].label) if r.fact in by_id else '')}</td></tr>" for r in chk.rows)
            st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Figure</th><th>Result</th><th>Fact it matches</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
        if chk.certainty:
            st.markdown("**Phrases that sound more certain than the evidence allows**")
            for s in chk.certainty:
                st.markdown(f"- {ui.esc(s)}")
        st.caption("This check compares numbers with facts. It does not judge whether the reasoning is sound, and it only sees the facts that were in the brief.")
