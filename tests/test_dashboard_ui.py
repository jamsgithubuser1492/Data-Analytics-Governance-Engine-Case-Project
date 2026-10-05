"""Dashboard UI: perspectives, chart or table toggle, trust gating, executive override and the no-emoji rule."""
from __future__ import annotations

import os
import re
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
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿←-⇿ℹ‍️]")
PERSPECTIVES = ["Everyone", "CFO / Finance", "CMO / Growth", "Agency Director", "Platform Lead"]


@pytest.fixture(scope="module", autouse=True)
def isolated_store():
    os.environ["MMGE_DATA_DIR"] = tempfile.mkdtemp()
    for m in [m for m in sys.modules if m == "common"]:
        del sys.modules[m]
    import streamlit as st
    st.cache_resource.clear()
    import common
    store, runner = common.get_store(), common.get_runner()
    actor, ws = common.identity()
    cfg = store.latest_workspace_config(ws)
    rid = runner.submit(ws, common.demo_tables(), cfg[0], cfg[1], "Demo data")
    runner.wait(ws, rid, timeout=300)
    yield
    st.cache_resource.clear()


def dash() -> AppTest:
    return AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)


def every_text(at: AppTest) -> str:
    parts = []
    for kind in ("markdown", "caption", "title", "header", "subheader", "success", "info", "warning", "error", "metric", "button"):
        for el in getattr(at, kind):
            parts.append(str(getattr(el, "value", "")) + " " + str(getattr(el, "label", "")))
    return " ".join(parts)


def persp(at: AppTest) -> object:
    return next(c for c in at.segmented_control if c.key == "persp")


@pytest.mark.parametrize("who", PERSPECTIVES)
def test_every_perspective_renders_in_both_bases(who: str) -> None:
    at = dash()
    persp(at).set_value(who).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    text = every_text(at)
    assert "The advisory council" in text and "Sources, confidence and method" in text
    assert "Trust score" in text and "Counting basis" in text
    assert not EMOJI.search(text), EMOJI.findall(text)


def test_strict_basis_shows_intervals_and_stamps_charts() -> None:
    at = dash()
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[1]).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    text = every_text(at)
    assert "95% CI" in text and "Strict lift" in text and "Divergence alert" in text
    assert not EMOJI.search(text)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=T)  # restore the spec view for later tests


def test_each_chart_card_has_a_table_toggle() -> None:
    at = dash()
    toggles = [c for c in at.segmented_control if c.key.startswith("view_")]
    assert {c.key for c in toggles} >= {"view_returns", "view_overclaim", "view_trend", "view_waterfall", "view_portfolio"}
    next(c for c in toggles if c.key == "view_returns").set_value("Table").run(timeout=T)
    assert not at.exception
    assert any("Claimed return" in getattr(d.value, "columns", []) for d in at.dataframe)


def test_trust_gating_limits_buttons_by_tier() -> None:
    at = dash()
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[1]).run(timeout=T)  # strict view makes Netflix Directional
    text = every_text(at)
    assert "Advisory only" in text or "Full actionability" in text
    approve = [b for b in at.button if b.label.startswith("Approve")]
    assert approve  # verified items can be approved
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=T)


def test_override_requires_justification_email_and_role_and_writes_audit_log() -> None:
    import common
    import overrides
    at = dash()
    text_areas = [t for t in at.text_area if t.key.startswith("or_")]
    emails = [t for t in at.text_input if t.key.startswith("oe_")]
    assert text_areas and emails
    key = text_areas[0].key.split("_", 1)[1]
    text_areas[0].set_value("too short")
    emails[0].set_value("cfo@example.com")
    next(b for b in at.button if b.key == f"ob_{key}").click().run(timeout=T)
    assert any("at least 10 characters" in e.value for e in at.error)
    at.text_area(key=f"or_{key}").set_value("Contract commitment runs until the Q3 renewal date").run(timeout=T)
    at.text_input(key=f"oe_{key}").set_value("cfo@example.com").run(timeout=T)
    next(b for b in at.button if b.key == f"ob_{key}").click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    actor, ws = common.identity()
    log = Path(common.DATA_ROOT) / "workspaces" / ws / "run_audit_log.json"
    entries = overrides.read_log(log)
    assert len(entries) == 1 and entries[0]["authorized_by"] == "cfo@example.com" and entries[0]["trust_tier"]
    assert overrides.verify_log(log) == (True, "ok")
    item = [i for i in common.get_store().list_inbox(ws) if i["id"] == key][0]
    assert item["status"] == "dismissed"


def test_legacy_emoji_in_stored_text_is_scrubbed_on_screen() -> None:
    import ui
    assert ui.scrub("\U0001F6A8 Capital Loss Detected: X ⚠️") == "Capital Loss Detected: X"
    assert ui.scrub(None) == ""


def test_switching_basis_back_and_forth_does_not_loop() -> None:
    at = dash()
    radio = at.sidebar.radio[0]
    radio.set_value(radio.options[1]).run(timeout=T)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=60)  # reuses the earlier spec run
    assert not at.exception and "Reported by spec" in every_text(at)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[1]).run(timeout=60)  # and the earlier strict run
    assert not at.exception and "Strict lift" in every_text(at)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=60)


def test_headline_is_an_objective_finding_not_an_instruction() -> None:
    at = dash()
    if "Strict lift (only" in at.sidebar.radio[0].value:  # earlier tests created a newer strict run; look at the spec basis
        at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=T)
    text = " ".join(m.value for m in at.markdown)
    assert "$105,158 of ad spend has not been earned back" in text
    for banned in ("Scale Google", "cut Netflix", "Cut Netflix", "maintain Meta"):
        assert banned not in text
    persp(at).set_value("CMO / Growth").run(timeout=T)
    assert "Modeled value of moving Netflix spend" in every_text(at) and "not a recommendation" in every_text(at)


def test_council_section_shows_four_personas_with_evidence() -> None:
    at = dash()
    text = every_text(at)
    for name in ("The Steward", "The Builder", "The Translator", "The Mechanic"):
        assert name in text
    assert "Where the council agrees" in text and "Where the council splits" in text and "Evidence and triggers" in " ".join(e.label for e in at.expander)
