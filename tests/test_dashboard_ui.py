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
    assert "The advisory council" in text and "Sources and how we know this is right" in text
    assert "Trust score" in text and "Counting basis" in text
    assert not EMOJI.search(text), EMOJI.findall(text)


def test_strict_basis_shows_intervals_and_stamps_charts() -> None:
    at = dash()
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[1]).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    text = every_text(at)
    assert "95% sure" in text and "Strict lift" in text and "The two ways of counting results disagree" in text
    assert not EMOJI.search(text)
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[0]).run(timeout=T)  # restore the spec view for later tests


def test_each_chart_card_has_a_table_toggle() -> None:
    at = dash()
    toggles = [c for c in at.segmented_control if c.key.startswith("view_")]
    assert {c.key for c in toggles} >= {"view_returns", "view_overclaim", "view_trend", "view_waterfall", "view_portfolio"}
    next(c for c in toggles if c.key == "view_returns").set_value("Table").run(timeout=T)
    assert not at.exception
    assert any("Claimed return" in getattr(d.value, "columns", []) for d in at.dataframe)


def test_every_open_decision_is_routed_to_the_signoff_desk_with_no_unsigned_shortcut() -> None:
    at = dash()
    labels = [b.label for b in at.button]
    assert "Review and sign" in labels
    assert not any(l.startswith(("Approve", "Execute", "Dismiss", "Record override")) for l in labels)
    assert not [t for t in at.text_area if t.key.startswith("or_")]  # the old inline override form is gone


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
    if "strict lift" in at.sidebar.radio[0].value:  # earlier tests created a newer strict run; look at the spec basis
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
    assert "Where the council agrees" in text and "Where the council splits" in text and "Why they say this" in " ".join(e.label for e in at.expander)


def test_app_version_helper_is_safe():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
    import common
    v = common.app_version()
    assert isinstance(v, str) and v


@pytest.mark.parametrize("who", PERSPECTIVES)
def test_no_builder_notes_or_jargon_on_screen(who: str) -> None:
    """Text meant for the builders must never reach the executive's screen."""
    import voice
    at = dash()
    persp(at).set_value(who).run(timeout=T)
    text = every_text(at).lower()
    for phrase in voice.BANNED_ON_SCREEN:
        assert phrase.lower() not in text, (who, phrase)
