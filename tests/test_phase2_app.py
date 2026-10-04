"""Streamlit flow tests (AppTest): upload with demo data, run, dashboard, inbox actions, settings."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

T = 300


@pytest.fixture(scope="module", autouse=True)
def isolated_store():
    os.environ["MMGE_DATA_DIR"] = tempfile.mkdtemp()
    for m in [m for m in sys.modules if m == "common"]:
        del sys.modules[m]
    import streamlit as st
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def page(name: str) -> AppTest:
    return AppTest.from_file(str(ROOT / "app" / name), default_timeout=T).run(timeout=T)


def clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


def test_1_empty_state_then_demo_run_from_dashboard() -> None:
    at = page("app.py")
    clean(at)
    assert any("Know which channels truly earn back" in m.value for m in at.markdown)  # empty state is never a dead end
    next(b for b in at.button if b.label == "Try with demo data").click().run(timeout=T)
    clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "$748,140" in text and "3.33x" in text and "Decisions to review" in text and "Trust score 89 of 100" in text
    assert "Scale Google Ads" in text and "+$667,510" in text  # answer first headline


def test_2_policy_switch_creates_strict_run() -> None:
    at = page("app.py")
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[1]).run(timeout=T)
    clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "0.57x" in text and "Strict lift" in text
    import common
    assert len(common.get_store().list_runs(common.identity()[1])) >= 2


def test_3_upload_flow_requires_ack_and_runs() -> None:
    at = page("pages/1_Upload.py")
    clean(at)
    next(b for b in at.button if "demo" in b.label).click().run(timeout=T)
    clean(at)
    run_btn = next(b for b in at.button if b.label == "Run measurement")
    assert run_btn.disabled  # demo has a low volume warning that must be acknowledged
    next(c for c in at.checkbox if c.key == "ack").check().run(timeout=T)
    next(b for b in at.button if b.label == "Run measurement").click().run(timeout=T)
    clean(at)
    assert any("Run complete" in s.value for s in at.success)


def test_4_inbox_approve_then_execute_writes_audit_log() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    at = page("app.py")
    next(b for b in at.button if b.label.startswith("Approve")).click().run(timeout=T)
    clean(at)
    assert any(i["status"] == "approved" for i in store.list_inbox(ws))
    next(b for b in at.button if b.label.startswith("Execute")).click().run(timeout=T)
    clean(at)
    events = [e["event"] for e in store.list_audit_events(ws)]
    assert "inbox_approved" in events and "inbox_executed" in events


def test_5_role_filter_hides_other_personas() -> None:
    at = page("app.py")
    next(c for c in at.segmented_control if c.key == "persp").set_value("CFO / Finance").run(timeout=T)
    clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "No decision rule is triggered" in text and "has not been earned back" in text  # no capital loss packets under spec view


def test_6_runs_page_and_compare() -> None:
    at = page("pages/2_Runs.py")
    clean(at)
    assert len(at.tabs) == 4


def test_7_settings_save_versions_and_validation() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    at = page("pages/3_Settings.py")
    clean(at)
    next(r for r in at.radio if "Headline" in r.label).set_value("strict_lift")
    next(b for b in at.button if b.label == "Save new version").click().run(timeout=T)
    clean(at)
    s, d, v = store.latest_workspace_config(ws)
    assert v == 1 and s.headline_metric == "strict_lift" and d["currency"] == "USD"
    # invalid ordering is rejected, no new version saved
    next(n for n in at.number_input if n.label == "Inflation: moderate at").set_value(5.0)
    next(n for n in at.number_input if n.label == "Inflation: critical at").set_value(2.0)
    next(b for b in at.button if b.label == "Save new version").click().run(timeout=T)
    assert any("below inflation_critical" in e.value for e in at.error) and store.latest_workspace_config(ws)[2] == 1
