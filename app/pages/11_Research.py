"""Research next: turn what a run leaves uncertain into the next tests to consider, with design tools."""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_store, identity, page_setup, safe_page_link, succeeded_runs  # noqa: E402

page_setup("Research next", ":material/science:")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

import charts  # noqa: E402
import mmm_priors as mp  # noqa: E402
import research_engine as rx  # noqa: E402
import synthetic_control as scm  # noqa: E402
import ui  # noqa: E402
from runview import load_view  # noqa: E402

store = get_store()
actor, ws = identity()
runs = succeeded_runs(ws)
charts.use_theme(ui.tokens())

ui.page_head("Strategize", "Research next",
             "A result is one measurement of one period. This page looks at what the run leaves uncertain and offers tests to consider, with a design computed from your own numbers. "
             "Ideas are offered to weigh; any test is authorized on the Sign-off desk.")

if not runs:
    ui.callout("Research ideas need a measured run to work from. Load the case study data from the Dashboard (choose Try with demo data) or upload your own files.")
    safe_page_link("app.py", "Go to the Dashboard", ":material/analytics:")
    st.stop()

labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
run_id = st.selectbox("Run to learn from", list(labels), format_func=labels.get, key="research_run")
v = load_view(store, ws, run_id)
st.markdown(f'<div class="note">Counting basis {ui.pill(v.basis, "info")} Breakeven {v.breakeven:.2f}x. Quantities are computed from this run; anything only your teams know is left blank.</div>', unsafe_allow_html=True)
st.write("")

tab_back, tab_scm, tab_mmm = st.tabs(["Ideas to consider", "Match test and control markets", "Media mix model priors"])

# ============================================================================================ the backlog
with tab_back:
    st.markdown("#### The question this answers")
    st.markdown("**Given what this run could and could not show, which tests would teach us the most?**")
    specs = rx.build_specs(v)
    if not specs:
        ui.callout("Every channel is measured to a Verified standard with no open questions this engine can see. Consider revisiting after the next run.", "ok")
    else:
        ui.stat_row([dict(label="Ideas to consider", value=str(len(specs))), dict(label="Highest priority", value=specs[0].channel, sub=rx.KIND_LABEL[specs[0].kind]),
                     dict(label="Channels covered", value=str(len({s.channel for s in specs})))], compact=True)
        st.caption(rx.FORMULA)
        rows = "".join(f"<tr><td>{s.priority:.0f}</td><td>{html.escape(s.channel)}</td><td>{html.escape(rx.KIND_LABEL[s.kind])}</td><td>{html.escape(s.method)}</td></tr>" for s in specs)
        st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Priority</th><th>Channel</th><th>What it would teach</th><th>Method to consider</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
        st.write("")
        for s in specs:
            with st.expander(f"{s.priority:.0f} · {s.title}"):
                st.markdown(f"{ui.pill(rx.KIND_LABEL[s.kind], 'info')} {ui.pill('Priority ' + format(s.priority, '.0f'), 'muted')}", unsafe_allow_html=True)
                st.caption(s.priority_note)
                st.markdown("**What the run showed**")
                for line in s.saw:
                    st.markdown(f"- {ui.esc(line)}")
                st.markdown("**Ideas to consider**")
                for line in s.consider:
                    st.markdown(f"- {ui.esc(line)}")
                st.markdown(f"**Objective.** {ui.esc(s.objective)}")
                st.markdown("**Design, computed from this run**")
                for k, val in s.design:
                    st.markdown(f"- **{k}:** {ui.esc(val)}")
                st.markdown("**For your teams to complete**")
                vals = {r: st.text_input(r, key=f"rs_{s.id}_{r}", placeholder="Your estimate") for r in s.resources}
                st.markdown("**How the result could guide the next step**")
                for k, outcome in s.decision_tree:
                    st.markdown(f"- {ui.esc(k)} {ui.esc(outcome)}")
                st.markdown("**Assumptions**")
                for a in s.assumptions:
                    st.markdown(f"- {ui.esc(a)}")
                b1, b2 = st.columns(2)
                b1.download_button("Download this specification", s.markdown(labels[run_id], v.basis), f"{s.id}.md", "text/markdown", key=f"dl_{s.id}")
                if b2.button("Send to the sign-off desk", key=f"send_{s.id}", help="Adds it to the decision queue. Nothing starts until a person signs."):
                    iid = store.add_inbox_item(ws, run_id, rx.spec_packet(s, v), actor)
                    st.session_state["signoff_item"] = iid
                    st.success("Added to the sign-off desk. Nothing starts until it is signed.")
                    safe_page_link("pages/12_Signoff.py", "Open the sign-off desk", ":material/draw:")
    st.caption("Sources and assumptions: this run's trust scores, intervals, sample size check, spend rate and the declared geo sample fraction. Test design choices such as cell sizes are defaults you can change.")

# ================================================================================================ matcher
with tab_scm:
    st.markdown("#### The question this answers")
    st.markdown("**Which untreated markets, blended together, behave most like the test markets before launch?**")
    st.caption("A good match makes the test cleaner. Weights are zero or more and add up to 100%. The fit check asks whether the blend tracks the test markets within 5% of their average level before launch.")
    demo = st.session_state.get("scm_demo", False)
    c1, c2 = st.columns(2)
    if c1.button("Load an example (synthetic, for practice)"):
        st.session_state["scm_demo"] = True
        st.rerun()
    tmpl = "date,geo,value,treated\n2026-01-01,GEO_A,120,1\n2026-01-01,GEO_B,95,0\n2026-01-02,GEO_A,118,1\n2026-01-02,GEO_B,97,0\n"
    c2.download_button("Download a template (CSV)", tmpl, "geo_template.csv", "text/csv")
    up = st.file_uploader("Daily results by market for the pre-launch period (CSV with date, geo, value and treated, where treated is 1 for test markets)", type=["csv"], key="scm_file")
    df = None
    if up is not None:
        try:
            df = pd.read_csv(up)
        except Exception as exc:  # noqa: BLE001
            st.error(f"That file could not be read: {exc}")
    elif demo:
        rng = np.random.default_rng(7)
        days = pd.date_range("2026-01-01", periods=45)
        base = 100 + 8 * np.sin(np.arange(45) / 6)
        parts = [pd.DataFrame({"date": days, "geo": "TEST_MARKETS", "value": base + rng.normal(0, 1, 45), "treated": 1})]
        for i in range(9):
            parts.append(pd.DataFrame({"date": days, "geo": f"MARKET_{i + 1}", "value": base * rng.uniform(0.4, 2.5) * (1 + (0.4 if i == 3 else 0.0) * np.sin(np.arange(45) / 4)) + rng.normal(0, 2, 45), "treated": 0}))
        df = pd.concat(parts)
        st.caption("Example data: one test group and nine candidate markets over 45 days, generated for practice.")
    if df is None:
        ui.callout("Upload a file or load the example to see a match. The file needs four columns: date, geo, value and treated.")
    else:
        need = {"date", "geo", "value", "treated"}
        if not need <= set(df.columns):
            st.error(f"The file needs these columns: date, geo, value, treated. Missing: {', '.join(sorted(need - set(df.columns)))}.")
        else:
            wide = df.pivot_table(index="date", columns="geo", values="value", aggfunc="sum").sort_index()
            treated = sorted(df[df["treated"] == 1]["geo"].unique())
            donors = [g for g in wide.columns if g not in treated]
            if not treated or not donors:
                st.error("The file needs at least one test market (treated = 1) and one other market (treated = 0).")
            else:
                y = wide[treated].sum(axis=1).to_numpy()
                top_k = st.slider("Keep at most this many markets in the blend (0 keeps all)", 0, min(10, len(donors)), 0, key="scm_k")
                try:
                    fit = scm.fit_weights(y, wide[donors].to_numpy(), donors, top_k=top_k or None)
                except scm.SyntheticControlError as exc:
                    st.error(str(exc))
                else:
                    synth = scm.predict(fit, wide[donors].to_numpy(), y, wide[donors].to_numpy())
                    ui.stat_row([dict(label="Pre-launch fit error", value=f"{fit.relative_rmspe:.1%}", sub="Under 5% of the average level passes", kind="ok" if fit.fit_ok else "bad"),
                                 dict(label="Fit check", value="Passes" if fit.fit_ok else "Does not pass", kind="ok" if fit.fit_ok else "bad"),
                                 dict(label="Markets in the blend", value=str(len(fit.table())))], compact=True)
                    if not fit.fit_ok:
                        ui.callout("In order to address the weak match, we might want to think about adding more candidate markets or a longer pre-launch window before relying on this blend.", "warn")
                    t = ui.tokens()
                    f1 = go.Figure()
                    f1.add_scatter(x=wide.index, y=y, name="Test markets, actual", line=dict(color=t["proven"], width=3))
                    f1.add_scatter(x=wide.index, y=synth, name="Blend of other markets", line=dict(color=t["claimed"], width=3, dash="dash"))
                    f1.update_yaxes(title_text="Daily value")
                    f1 = charts._layout(f1, "How closely the blend follows the test markets before launch", "Two lines that sit on top of each other mean a good match.", 380)
                    ui.chart_card("scm_fit", "How closely the blend follows the test markets before launch", f1.layout.meta["subtitle"], f1,
                                  pd.DataFrame({"Date": wide.index.astype(str), "Test markets": y.round(2), "Blend": synth.round(2)}), "Pre-launch", "Source: your uploaded table. The blend is built only from markets that are not treated.")
                    wt = pd.DataFrame(fit.table(), columns=["Market", "Weight"])
                    f2 = go.Figure(go.Bar(x=wt["Weight"], y=wt["Market"], orientation="h", marker_color=t["proven"], text=wt["Weight"].map(lambda x: f"{x:.0%}"), textposition="outside", cliponaxis=False))
                    f2.update_xaxes(range=[0, max(1.0, wt["Weight"].max()) * 1.15], tickformat=".0%", title_text="Share of the blend")
                    f2.update_yaxes(autorange="reversed")
                    f2 = charts._layout(f2, "Which markets make up the blend", "Weights add up to 100%.", charts.bar_height(len(wt)), legend=False, bottom=60)
                    ui.chart_card("scm_w", "Which markets make up the blend", f2.layout.meta["subtitle"], f2, wt.round(4), "Pre-launch", "")
                    for note in fit.notes:
                        st.caption(note)
    st.caption("Assumptions: markets that are not treated are not affected by the campaign (no spillover), and the pre-launch pattern would have continued without it. Both are worth checking with your analysts.")

# ================================================================================================= MMM priors
with tab_mmm:
    st.markdown("#### The question this answers")
    st.markdown("**If we build a media mix model, how can the test results keep it honest?**")
    st.caption("Models that learn only from history tend to give platforms the credit they claim. A test result with its margin of error can be turned into a starting belief for the model, called a prior.")
    pt = mp.priors_table(v.ch)
    if not v.is_strict:
        ui.callout("Priors need a confidence interval, and the Reported by spec basis does not have one. Switch the counting basis to Strict lift on the Dashboard, then return here.", "warn")
    show = pt.copy()
    show["Usable"] = show["usable"].map({True: "Yes", False: "No"})
    st.dataframe(show[["channel", "proven", "lower", "upper", "se", "mu", "sigma", "Usable", "reason"]].rename(columns={"channel": "Channel", "proven": "Proven return", "lower": "Low (95%)", "upper": "High (95%)",
                 "se": "Standard error", "mu": "Prior mu", "sigma": "Prior sigma", "reason": "Why not"}).round(3), hide_index=True, width="stretch")
    if pt["usable"].any():
        code = mp.pymc_snippet(pt)
        st.markdown("**Code your analysts can adapt (PyMC)**")
        st.code(code, language="python", wrap_lines=True)
        st.download_button("Download the code", code, "mmm_priors.py", "text/x-python", key="dl_priors")
    st.caption("Assumption: the test's standard error is taken from its 95% interval, and the return is positive. Carry over and saturation curves still need to be chosen for each channel (see the reference functions in the code).")
