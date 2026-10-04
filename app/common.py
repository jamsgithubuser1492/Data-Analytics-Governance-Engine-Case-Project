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
TIER_BADGE = {"VERIFIED": "🟢 Verified", "DIRECTIONAL": "🟡 Directional", "NOT_DECISION_GRADE": "🔴 Not decision grade"}
SEVERITY_ICON = {"CRITICAL": "🔴", "WARNING": "🟡", "OPPORTUNITY": "🟢"}


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


def page_setup(title: str, icon: str) -> None:
    st.set_page_config(page_title=f"MMGE · {title}", page_icon=icon, layout="wide")


def safe_page_link(page: str, label: str, icon: str = "") -> None:
    """st.page_link that degrades to plain text when a page is not registered (for example in isolated tests)."""
    try:
        st.page_link(page, label=label, icon=icon or None)
    except Exception:  # StreamlitPageNotFoundError
        st.caption(f"{icon} {label}")
