"""Automation blueprint: how AI models could connect to the engine through MCP while a person signs every decision."""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import page_setup  # noqa: E402

page_setup("Automation blueprint", ":material/hub:")

import streamlit as st  # noqa: E402

import blueprint as bp  # noqa: E402
import ui  # noqa: E402

KIND = {"Built": "ok", "Designed": "info", "Future": "muted"}
CHEV = '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" style="flex:none;color:var(--mm-muted)"><path d="M6 3l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

ui.page_head("Automate", "Automation blueprint", bp.INTRO)
counts = {k: sum(1 for c in bp.COMPONENTS if c["status"] == k) for k in KIND}
ui.stat_row([dict(label="Built and tested", value=str(counts["Built"]), kind="ok", sub=bp.STATUS_NOTE["Built"]), dict(label="Designed, not built", value=str(counts["Designed"]), sub=bp.STATUS_NOTE["Designed"]),
             dict(label="Depends on your choices", value=str(counts["Future"]), sub=bp.STATUS_NOTE["Future"])], compact=True)

t_big, t_tools, t_safe, t_week, t_roll = st.tabs(["The big picture", "What a model can and cannot do", "Safety rules", "The weekly rhythm", "Rollout"])

with t_big:
    st.markdown("#### The question this answers")
    st.markdown("**How could AI models help every week without ever deciding for us?**")
    st.markdown("Think of three roles. **The engine** measures and flags. **A model** reads the verified facts, tries ideas and queues proposals. **A person** signs. The model has no way to approve or act; the only door to a change is the Sign-off desk.")
    for layer in bp.LAYER_ORDER:
        comps = [c for c in bp.COMPONENTS if c["layer"] == layer]
        st.markdown(f"**{layer}**")
        cols = st.columns(len(comps))
        for col, c in zip(cols, comps):
            with col, st.container(border=True):
                st.markdown(f"{ui.pill(c['status'], KIND[c['status']])}", unsafe_allow_html=True)
                st.markdown(f"**{c['name']}**")
                st.caption(c["does"])
    st.caption("Status is shown with a shape and a word. Only the items marked Built exist today.")

with t_tools:
    st.markdown("#### The question this answers")
    st.markdown("**What exactly could a connected model do, and what is it prevented from doing?**")
    st.markdown("Six narrow tools. Five only read. One stages a proposal that does nothing until a person signs it. **There is no approve tool and no execute tool.** "
                "A model can never pass in a trust score, evidence level or counting outcome; the server reads those from the stored run.")
    for tool in bp.TOOLS:
        with st.container(border=True):
            st.markdown(f"{ui.pill(tool['access'], 'ok' if tool['access'] == 'Read' else 'warn')} &nbsp; **`{tool['name']}`**", unsafe_allow_html=True)
            st.markdown(tool["plain"])
            st.markdown("**It cannot**\n" + "\n".join(f"- {c}" for c in tool["cannot"]))
            with st.expander("Technical detail for your engineers"):
                st.caption(f"Backed by {tool['maps_to']}")
                st.code(json.dumps(tool["schema"], indent=2), language="json")
    st.caption("Also offered: " + "; ".join(bp.RESOURCES) + ". Prompt: " + "; ".join(bp.PROMPTS) + ".")

with t_safe:
    st.markdown("#### The question this answers")
    st.markdown("**What stops automation from doing something it should not?**")
    rows = "".join(f"<tr><td>{html.escape(g['rule'])}</td><td>{html.escape(g['how'])}</td><td>{ui.pill(g['status'], KIND[g['status']])}</td></tr>" for g in bp.GUARDRAILS)
    st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>Rule</th><th>How it is enforced</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>', unsafe_allow_html=True)
    st.markdown("##### The path of a decision")
    flow = "".join(f'<span class="chip" style="cursor:default">{html.escape(s)}</span>' + (CHEV if i < len(bp.STATES) - 1 else "") for i, s in enumerate(["Staged", "Approved", "Executed"]))
    st.markdown(f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0">{flow}</div>', unsafe_allow_html=True)
    erows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{ui.pill(w, 'warn' if 'Human' in w and 'model' not in w else 'muted')}</td><td>{html.escape(m)}</td></tr>" for a, b, w, m in bp.EDGES)
    st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>From</th><th>To</th><th>Who</th><th>What it means</th></tr></thead><tbody>{erows}</tbody></table></div>', unsafe_allow_html=True)
    st.markdown("**Never allowed**\n" + "\n".join(f"- {f}" for f in bp.FORBIDDEN))

with t_week:
    st.markdown("#### The question this answers")
    st.markdown("**What would a normal week look like once this is running?**")
    cols = st.columns(2)
    for i, p in enumerate(bp.PIPELINE):
        with cols[i % 2], st.container(border=True):
            st.markdown(f"{ui.pill(p['status'], KIND[p['status']])} &nbsp; **{i + 1}. {p['step']}**", unsafe_allow_html=True)
            st.markdown(p["what"])
            st.caption(f"By {p['by']} · {p['cadence']}")
    st.markdown("##### When things go wrong")
    frows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>" for a, b, c in bp.FAILURES)
    st.markdown(f'<div class="tblwrap"><table class="mm"><thead><tr><th>If this happens</th><th>What it affects</th><th>The safe behavior</th></tr></thead><tbody>{frows}</tbody></table></div>', unsafe_allow_html=True)

with t_roll:
    st.markdown("#### The question this answers")
    st.markdown("**In what order could this be adopted, with a clear test before each step?**")
    for r in bp.ROLLOUT:
        with st.container(border=True):
            st.markdown(f"**{r['phase']}**")
            st.markdown(r["delivers"])
            st.caption(f"Ready to move on when: {r['exit']}")
    st.markdown("##### Where it could run")
    for a, b in bp.DEPLOYMENT:
        st.markdown(f"- **{a}.** {b}")
    st.caption("The full design, including every tool schema, is in docs/ARCHITECTURE_MCP.md. Privacy and governance: docs/PRIVACY_AND_GOVERNANCE.md. This is a design and not legal advice.")
