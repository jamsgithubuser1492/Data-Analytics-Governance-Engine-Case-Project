"""Shared Streamlit helpers: store, job runner, workspace identity, safe export, small UI pieces."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Tuple

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import SUCCEEDED, LocalRunStore  # noqa: E402



def demo_mode() -> bool:
    """True on a public demo host: every visitor gets a private, throwaway workspace on the verified demo data."""
    flag = os.environ.get("MMGE_DEMO_MODE", "")
    if not flag:
        try:
            flag = str(st.secrets.get("MMGE_DEMO_MODE", ""))
        except Exception:  # no secrets file
            flag = ""
    return flag.strip().lower() in ("1", "true", "yes", "on")


def _data_root() -> Path:
    explicit = os.environ.get("MMGE_DATA_DIR")
    if explicit:
        return Path(explicit)
    return Path(tempfile.gettempdir()) / "mmge_demo" if demo_mode() else ROOT / "var"


DATA_ROOT = _data_root()
DEMO_NOTICE = ("You are viewing a public demo on synthetic data. Platform names are illustrative labels with no affiliation. "
               "Signing and hand off are simulated, nothing is sent to an ad platform, and nothing you do here is saved or shared.")
import ui  # noqa: E402

TIER_BADGE = {k: v[0] for k, v in ui.TIER_LABEL.items()}
TIER_KIND = {k: v[1] for k, v in ui.TIER_LABEL.items()}
pill, takeaway = ui.pill, ui.callout

NAV_GROUPS = [
    ("Understand", [("app.py", "Dashboard", ":material/analytics:"), ("pages/1_Upload.py", "Upload data", ":material/upload:"),
                    ("pages/2_Runs.py", "Runs", ":material/history:"), ("pages/3_Settings.py", "Settings", ":material/tune:")]),
    ("Interpret", [("pages/4_Agents.py", "Advisory council", ":material/groups:")]),
    ("Strategize", [("pages/9_Strategy.py", "Strategy", ":material/account_tree:"), ("pages/10_AI_Brief.py", "AI brief", ":material/auto_awesome:"),
                    ("pages/11_Research.py", "Research next", ":material/science:")]),
    ("Decide", [("pages/12_Signoff.py", "Sign-off desk", ":material/draw:")]),
    ("Automate", [("pages/13_Automation.py", "Automation blueprint", ":material/hub:")]),
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
    if demo_mode() and not email:  # a private workspace per visitor session on a shared host
        sid = st.session_state.setdefault("demo_session_id", uuid.uuid4().hex[:12])
        return actor, get_store().get_or_create_workspace(f"public-demo-{sid}")
    return actor, get_store().get_or_create_workspace(email or "local-demo")


def auth_mode(actor: str) -> str:
    """'sso_verified' when a real login is active, otherwise 'self_asserted' (a typed email is not proof of identity)."""
    return "self_asserted" if actor == "local-demo-user" else "sso_verified"


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


def app_version() -> str:
    """Short commit and date of the running code, so anyone can tell which version they are on."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%h %cs"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=3)
        text = out.stdout.strip()
        return text if out.returncode == 0 and text else "unknown"
    except Exception:
        return "unknown"


def ensure_demo_run() -> None:
    """Public demo only: seed the verified demo data once per visitor so no page is ever empty."""
    if not demo_mode():
        return
    _, ws = identity()
    if not succeeded_runs(ws):
        store = get_store()
        cfg = store.latest_workspace_config(ws)
        rid = get_runner().submit(ws, demo_tables(), cfg[0], cfg[1], "Demo data")
        wait_for_run(ws, rid, "Loading the verified demo data...")


def page_setup(title: str, icon: str = ":material/analytics:") -> None:
    st.set_page_config(page_title=f"MMGE · {title}", page_icon=icon, layout="wide")
    ui.apply_theme()
    ensure_demo_run()
    with st.sidebar:
        st.markdown("**Media Measurement and Governance**")
        for group, items in NAV_GROUPS:
            st.markdown(f'<div class="kicker" style="margin:.9rem 0 .2rem">{group}</div>', unsafe_allow_html=True)
            for page, name, icon in items:
                safe_page_link(page, name, icon)
        st.divider()
        if demo_mode():
            st.caption("Public demo on synthetic data. Platform names are illustrative, with no affiliation. Signing is simulated.")
        st.caption(f"Version {app_version()}")


def safe_page_link(page: str, label: str, icon: str = "") -> None:
    """st.page_link that degrades to plain text when a page is not registered (for example in isolated tests)."""
    try:
        st.page_link(page, label=label, icon=icon or None)
    except Exception:  # StreamlitPageNotFoundError
        st.caption(label)
