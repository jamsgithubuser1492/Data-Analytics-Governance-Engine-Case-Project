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
TIER_BADGE = {"VERIFIED": "Verified", "DIRECTIONAL": "Directional", "NOT_DECISION_GRADE": "Not decision grade"}
TIER_KIND = {"VERIFIED": "ok", "DIRECTIONAL": "warn", "NOT_DECISION_GRADE": "bad"}
SEVERITY_LABEL = {"CRITICAL": "Critical", "WARNING": "Warning", "OPPORTUNITY": "Opportunity", "INFO": "Info"}
SEVERITY_KIND = {"CRITICAL": "bad", "WARNING": "warn", "OPPORTUNITY": "ok", "INFO": "info"}

CSS = """
<style>
[data-testid="stSidebarNav"] {display: none;}
.block-container {padding-top: 2.2rem; max-width: 1280px;}
h1 {font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.1rem;}
h2, h3 {font-weight: 650; letter-spacing: -0.01em;}
[data-testid="stMetric"] {background: #f4f6fa; border: 1px solid #e3e8f0; border-radius: 12px; padding: 14px 16px;}
[data-testid="stMetricLabel"] {color: #4b586b;}
[data-testid="stMetricValue"] {font-weight: 700;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 12px;}
[data-testid="stSidebar"] {border-right: 1px solid #e3e8f0;}
.pill {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 600; line-height: 1.5; border: 1px solid transparent;}
.pill-ok {background: #e6f4ee; color: #146c47; border-color: #bfe3d2;}
.pill-warn {background: #fdf3df; color: #8a5a00; border-color: #f2dba6;}
.pill-bad {background: #fbe8e6; color: #a32619; border-color: #f0c3be;}
.pill-info {background: #e8eefb; color: #1d4ed8; border-color: #c5d3f5;}
.pill-muted {background: #eef0f4; color: #4b586b; border-color: #dde1e8;}
.takeaway {border-left: 4px solid #1d4ed8; background: #f4f7ff; padding: 14px 18px; border-radius: 8px; font-size: 1.05rem; line-height: 1.5;}
.takeaway.bad {border-left-color: #c0392b; background: #fdf4f3;}
.takeaway.ok {border-left-color: #1a7f5a; background: #f2faf6;}
.section-note {color: #4b586b; font-size: 0.95rem; margin: -0.3rem 0 0.6rem 0;}
</style>
"""


NAV = [("app.py", "Dashboard", ":material/analytics:"), ("pages/1_Upload.py", "Upload data", ":material/upload:"),
       ("pages/2_Runs.py", "Runs", ":material/history:"), ("pages/3_Settings.py", "Settings", ":material/tune:"),
       ("pages/4_Agents.py", "Decision rules", ":material/smart_toy:"), ("pages/5_Memos.py", "Memos", ":material/description:"),
       ("pages/6_Benchmarks.py", "Benchmarks", ":material/menu_book:")]


def pill(text: str, kind: str = "muted") -> str:
    """Small colored status label as HTML (always text, never color alone)."""
    return f'<span class="pill pill-{kind}">{text}</span>'


def takeaway(text: str, kind: str = "") -> None:
    st.markdown(f'<div class="takeaway {kind}">{text}</div>', unsafe_allow_html=True)


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
    st.markdown(CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("**Media Measurement and Governance**")
        for page, name, icon in NAV:
            safe_page_link(page, name, icon)
        st.divider()


def safe_page_link(page: str, label: str, icon: str = "") -> None:
    """st.page_link that degrades to plain text when a page is not registered (for example in isolated tests)."""
    try:
        st.page_link(page, label=label, icon=icon or None)
    except Exception:  # StreamlitPageNotFoundError
        st.caption(label)
