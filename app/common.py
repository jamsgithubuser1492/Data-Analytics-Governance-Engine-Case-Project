"""Shared Streamlit helpers: store, job runner, workspace identity, safe export, small UI pieces."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import SUCCEEDED, LocalRunStore  # noqa: E402

DATA_ROOT = Path(os.environ.get("MMGE_DATA_DIR", ROOT / "var"))
import ui  # noqa: E402

TIER_BADGE = {k: v[0] for k, v in ui.TIER_LABEL.items()}
TIER_KIND = {k: v[1] for k, v in ui.TIER_LABEL.items()}
pill, takeaway = ui.pill, ui.callout

NAV_GROUPS = [
    ("Understand", [("app.py", "Dashboard", ":material/analytics:"), ("pages/1_Upload.py", "Upload data", ":material/upload:"),
                    ("pages/2_Runs.py", "Runs", ":material/history:"), ("pages/3_Settings.py", "Settings", ":material/tune:")]),
    ("Interpret", [("pages/4_Agents.py", "Advisory council", ":material/groups:")]),
    ("Strategize", [("pages/9_Strategy.py", "Strategy", ":material/account_tree:"), ("pages/10_AI_Brief.py", "AI brief", ":material/auto_awesome:")]),
    ("Reference", [("pages/5_Memos.py", "Memos", ":material/description:"), ("pages/6_Benchmarks.py", "Benchmarks", ":material/menu_book:"),
                   ("pages/7_Guide.py", "How it works", ":material/help:")]),
]
NAV = [item for _, items in NAV_GROUPS for item in items]


@st.cache_resource
def get_store() -> LocalRunStore:
    return LocalRunStore(DATA_ROOT)


@st.cache_resource
def get_runner() -> JobRunner:
    return JobRunner(get_store(), max_workers=2)


def identity() -> Tuple[str, str]:
    """Return (actor, workspace_id). Uses Streamlit login when configured, else a local demo workspace."""
    email = None
    try:
        user = st.user
        if getattr(user, "is_logged_in", False):
            email = user.get("email")
    except Exception:  # login not configured
        pass
    actor = email or "local-demo-user"
    return actor, get_store().get_or_create_workspace(email or "local-demo")


def safe_csv(df: pd.DataFrame) -> bytes:
    """CSV bytes with spreadsheet formula injection neutralized (cells starting with = + - @)."""
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object or str(out[c].dtype).startswith("string"):
            out[c] = out[c].map(lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v)
    return out.to_csv(index=False).encode("utf-8")


def demo_tables() -> SourceTables:
    return SourceTables.from_directory()


def wait_for_run(workspace_id: str, run_id: str, label: str = "Running the measurement pipeline...") -> str:
    with st.spinner(label):
        return get_runner().wait(workspace_id, run_id, timeout=300)


def succeeded_runs(workspace_id: str) -> list:
    return [r for r in get_store().list_runs(workspace_id) if r["status"] == SUCCEEDED]


def page_setup(title: str, icon: str = ":material/analytics:") -> None:
    st.set_page_config(page_title=f"MMGE · {title}", page_icon=icon, layout="wide")
    ui.apply_theme()
    with st.sidebar:
        st.markdown("**Media Measurement and Governance**")
        for group, items in NAV_GROUPS:
            st.markdown(f'<div class="kicker" style="margin:.9rem 0 .2rem">{group}</div>', unsafe_allow_html=True)
            for page, name, icon in items:
                safe_page_link(page, name, icon)
        st.divider()


def safe_page_link(page: str, label: str, icon: str = "") -> None:
    """st.page_link that degrades to plain text when a page is not registered (for example in isolated tests)."""
    try:
        st.page_link(page, label=label, icon=icon or None)
    except Exception:  # StreamlitPageNotFoundError
        st.caption(label)
