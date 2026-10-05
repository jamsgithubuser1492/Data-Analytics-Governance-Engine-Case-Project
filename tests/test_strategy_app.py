"""Strategy and AI brief pages."""
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


@pytest.fixture(scope="module", autouse=True)
def isolated_store():
    os.environ["MMGE_DATA_DIR"] = tempfile.mkdtemp()
    for m in [m for m in sys.modules if m == "common"]:
        del sys.modules[m]
    import streamlit as st
    st.cache_resource.clear()
    import common
    store, runner = common.get_store(), common.get_runner()
    _, ws = common.identity()
    cfg = store.latest_workspace_config(ws)
    runner.wait(ws, runner.submit(ws, common.demo_tables(), cfg[0], cfg[1], "Demo data"), timeout=300)
    yield
    st.cache_resource.clear()


def page(name: str) -> AppTest:
    return AppTest.from_file(str(ROOT / "app" / "pages" / name), default_timeout=T).run(timeout=T)


def text(at: AppTest) -> str:
    return " ".join(str(getattr(e, "value", "")) + " " + str(getattr(e, "label", "")) for k in ("markdown", "caption", "button", "metric", "checkbox", "expander", "error", "info", "warning") for e in getattr(at, k))


def test_strategy_page_states_the_scenario_as_a_finding_with_the_cost_of_delay() -> None:
    at = page("9_Strategy.py")
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "The question this answers" in t and "+$667,510" in t and "per week" in t and "modeled" in t
    assert "No interval on the spec basis" in t
    assert not EMOJI.search(t)
    assert "Scale Google" not in t and "Cut Netflix" not in t


def test_strategy_tabs_render_worksheet_change_plan_budget_and_monitor() -> None:
    at = page("9_Strategy.py")
    t = text(at)
    for fn in ("Finance and treasury", "Marketing and creative", "Agencies and media buying", "Data and engineering", "Legal and privacy"):
        assert fn in t
    assert any(i.label == "Commitment or penalty exposure ($)" for i in at.text_input)  # blank for the executive to fill
    assert all(i.value == "" for i in at.text_input if i.key.startswith("ws_"))
    assert "1. Align" in t and "3. Phase in" in t and any(c.key.startswith("cp_") for c in at.checkbox)
    assert "Core channels against a target of 70%" in t or "of spend is in Core" in t
    assert "Capital protection preview" in t and "NETFLIX_ADS_CMP_01" in t and "Information only" in t


def test_changing_the_scenario_updates_the_numbers() -> None:
    at = page("9_Strategy.py")
    at.multiselect(key="sc_targets_Netflix Ads").set_value(["Google Ads"]).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "+$667,510" not in t and "Net revenue change" in t


def test_budget_framework_rejects_targets_that_do_not_total_100() -> None:
    at = page("9_Strategy.py")
    at.number_input(key="lens_t1").set_value(60.0).run(timeout=T)
    assert any("need to total 100%" in e.value for e in at.error)


def test_ai_brief_is_gated_by_the_privacy_confirmation_then_shows_a_fact_grounded_prompt() -> None:
    at = page("10_AI_Brief.py")
    assert not at.exception, [e.value for e in at.exception]
    assert not at.code and "Confirm the privacy statement" in text(at)
    at.checkbox(key="brief_confirm").check().run(timeout=T)
    assert at.code, "the prompt should be shown once confirmed"
    prompt = at.code[0].value
    assert "[ROLE AND RULES]" in prompt and "$105,158" in prompt and "Do not instruct anyone to move money" in prompt and "Netflix Ads" in prompt
    assert not EMOJI.search(prompt)


def test_ai_brief_hides_names_and_redacts_personal_data() -> None:
    at = page("10_AI_Brief.py")
    at.checkbox(key="brief_confirm").check().run(timeout=T)
    at.checkbox(key="brief_alias").check().run(timeout=T)
    at.text_area(key="brief_ctx").set_value("Board prep. Reach me at cfo@example.com or 415-555-0123.").run(timeout=T)
    prompt = at.code[0].value
    assert "Netflix" not in prompt and "Channel A" in prompt
    assert "cfo@example.com" not in prompt and "415-555-0123" not in prompt and "[email removed]" in prompt
    assert any("Personal data was detected" in w.value for w in at.warning)


def test_answer_checker_flags_invented_numbers() -> None:
    at = page("10_AI_Brief.py")
    at.text_area(key="check_answer").set_value("Spend was $748,140 [F1]. Revenue will definitely reach $9,999,999 next quarter.").run(timeout=T)
    next(b for b in at.button if b.label == "Check the numbers").click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "Not in the facts" in t and "$9,999,999" in t and "Matches a fact" in t and "Certainty phrases" in t


def test_navigation_is_grouped_and_lists_the_new_pages() -> None:
    import common
    groups = dict(common.NAV_GROUPS)
    assert [n for _, n, _ in groups["Strategize"]] == ["Strategy", "AI brief"]
    assert set(groups) == {"Understand", "Interpret", "Strategize", "Reference"}
