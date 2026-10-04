"""Agent builder UI flow tests (Streamlit AppTest)."""
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
    sys.modules.pop("common", None)
    import streamlit as st
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def page(name: str) -> AppTest:
    return AppTest.from_file(str(ROOT / "app" / name), default_timeout=T).run(timeout=T)


def clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


def w(at: AppTest, widgets, key: str):
    return next(x for x in widgets if x.key == key)


def test_1_builder_without_runs_shows_hint_and_validates() -> None:
    at = page("pages/4_Agents.py")
    clean(at)
    assert any("Create a run first" in i.value for i in at.info) and any("valid" in s.value for s in at.success)


def test_2_edit_preset_preview_and_save_new_version() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    app = page("app.py")
    next(b for b in app.button if b.label == "Try with demo data").click().run(timeout=T)
    clean(app)
    at = page("pages/4_Agents.py")
    at.selectbox[0].select("ATTRIBUTION_SHIELD_AGENT").run(timeout=T)
    clean(at)
    sid = "ATTRIBUTION_SHIELD_AGENT"
    assert any("Would fire on 2 of 8" in m.value for m in at.markdown)  # TikTok campaigns under the demo data
    w(at, at.text_input, f"{sid}_all0v").set_value("1.1").run(timeout=T)  # lower the lower bound from 1.25 to 1.1
    clean(at)
    assert any("Would fire on 6 of 8" in m.value for m in at.markdown)  # Google (1.10) is not above 1.1, the other six are
    next(b for b in at.button if b.label == "Save as new version").click().run(timeout=T)
    clean(at)
    saved = {d["id"]: d for d in store.get_agent_definitions(ws)}[sid]
    assert saved["version"] == 2 and saved["trigger"]["all"][0]["value"] == 1.1
    assert "agent_saved" in [e["event"] for e in store.list_audit_events(ws)]


def test_3_invalid_edit_blocks_save() -> None:
    at = page("pages/4_Agents.py")
    at.selectbox[0].select("SCALE_OPPORTUNITY_AGENT").run(timeout=T)
    w(at, at.text_input, "SCALE_OPPORTUNITY_AGENT_va0e").set_value("__import__('os').system('x')").run(timeout=T)
    clean(at)
    assert any("Value-add 1" in e.value for e in at.error)
    assert next(b for b in at.button if b.label == "Save as new version").disabled
    w(at, at.text_input, "SCALE_OPPORTUNITY_AGENT_all0v").set_value("not a number").run(timeout=T)
    assert any("not a valid value" in e.value for e in at.error)


def test_4_create_custom_agent_and_reevaluate_run() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    at = page("pages/4_Agents.py")
    at.selectbox[0].select("➕ New custom agent").run(timeout=T)
    n = "➕ New custom agent"
    w(at, at.text_input, f"{n}_id").set_value("TRUST_WATCH").run(timeout=T)
    w(at, at.text_input, f"{n}_name").set_value("Trust watch").run(timeout=T)
    w(at, at.text_input, f"{n}_all0v").set_value("1.0").run(timeout=T)  # the demo data's inflation ratios are all above 1.0
    clean(at)
    assert not at.error
    next(b for b in at.button if b.label == "Save as new version").click().run(timeout=T)
    clean(at)
    assert "TRUST_WATCH" in {d["id"] for d in store.get_agent_definitions(ws)}
    before = len(store.list_runs(ws))
    at2 = page("pages/4_Agents.py")
    next(b for b in at2.button if b.label.startswith("Re-evaluate")).click().run(timeout=T)
    clean(at2)
    assert len(store.list_runs(ws)) == before + 1
    newest = store.list_runs(ws)[0]
    assert any(i["packet"]["agent_id"] == "TRUST_WATCH" for i in store.list_inbox(ws, newest["id"]))


def test_5_dashboard_shows_custom_agent_packets() -> None:
    at = page("app.py")
    clean(at)
    assert any("Review" in m.value for m in at.markdown)
