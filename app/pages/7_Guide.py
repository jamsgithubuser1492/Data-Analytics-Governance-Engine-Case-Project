"""Plain-English methodology guide for people who have never seen the model."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import page_setup  # noqa: E402

page_setup("How it works", ":material/help:")

import streamlit as st  # noqa: E402

import guide_content as g  # noqa: E402
import ui  # noqa: E402

ui.page_head("Methodology", "How it works", g.INTRO)
chips = "".join(f'<a class="chip" href="#s{i}">{i}. {t}</a>' for i, (t, _) in enumerate(g.SECTIONS, 1))
st.markdown(f'<div class="chips">{chips}</div>', unsafe_allow_html=True)
for i, (title, body) in enumerate(g.SECTIONS, 1):
    ui.section(f"{i:02d}", title, "", f"s{i}")
    st.markdown(body)
st.divider()
with st.expander("Glossary: every term and formula"):
    for key, (label, plain, formula) in ui.GLOSSARY.items():
        st.markdown(f"**{label}.** {plain}" + (f" *Formula: {formula}.*" if formula else ""))
st.caption("The same text is in docs/METHODOLOGY.md in the repository.")
