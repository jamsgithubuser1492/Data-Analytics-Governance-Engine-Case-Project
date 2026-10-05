"""Public demo mode: auto loaded data, private per visitor workspaces, no uploads, clear disclaimer."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "python")]
T = 180


@pytest.fixture(autouse=True)
def demo_env(monkeypatch):
    monkeypatch.setenv("MMGE_DEMO_MODE", "1")
    monkeypatch.setenv("MMGE_DATA_DIR", tempfile.mkdtemp())
    import streamlit as st
    st.cache_resource.clear()
    sys.modules.pop("common", None)
    yield
    st.cache_resource.clear()
    sys.modules.pop("common", None)


def text(at):
    return " ".join(str(getattr(e, "value", "")) for k in ("markdown", "caption") for e in getattr(at, k))


def test_dashboard_loads_with_no_clicks_and_shows_the_notice():
    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "$105,158 of ad spend has not been earned back" in t
    assert "public demo on synthetic data" in t and "no affiliation" in t


def test_uploads_and_settings_are_read_only():
    for page, phrase in (("1_Upload.py", "Uploading is switched off"), ("3_Settings.py", "read only")):
        at = AppTest.from_file(str(ROOT / "app" / "pages" / page), default_timeout=T).run(timeout=T)
        assert not at.exception, [e.value for e in at.exception]
        assert phrase in text(at)


def test_each_visitor_session_gets_a_private_workspace():
    a = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)
    b = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)
    assert a.session_state["demo_session_id"] != b.session_state["demo_session_id"]


def test_demo_mode_off_by_default(monkeypatch):
    monkeypatch.delenv("MMGE_DEMO_MODE")
    import common
    importlib.reload(common)
    assert common.demo_mode() is False
