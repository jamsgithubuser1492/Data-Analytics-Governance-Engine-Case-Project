"""Sign-off desk page, research page and automation blueprint page."""
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
NOTE = "Agreed with finance to proceed in stages"


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
    return " ".join(str(getattr(e, "value", "")) + " " + str(getattr(e, "label", "")) for k in ("markdown", "caption", "button", "metric", "checkbox", "expander", "error", "info", "warning", "success") for e in getattr(at, k))


def fill_and_sign(at: AppTest, outcome: str, note: str = NOTE) -> AppTest:
    at.radio[0].set_value(outcome).run(timeout=T)
    next(t for t in at.text_area if t.key.startswith("so_note")).set_value(note).run(timeout=T)
    next(t for t in at.text_input if t.key.startswith("so_email")).set_value("cfo@example.com").run(timeout=T)
    next(s for s in at.selectbox if s.key.startswith("so_role")).select("CFO / VP Finance").run(timeout=T)
    for c in [c for c in at.checkbox if c.key.startswith("so_tick")]:
        c.check()
    at.run(timeout=T)
    return at


def test_the_desk_shows_the_queue_and_blocks_signing_until_everything_is_complete() -> None:
    at = page("12_Signoff.py")
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "Awaiting your signature" in t and "Your decision" in t and "Still needed" in t
    go = next(b for b in at.button if b.label == "Sign and record this decision")
    assert go.disabled and not EMOJI.search(t)
    assert [o for o in at.radio[0].options] == list(["APPROVED", "OVERRIDDEN", "REJECTED"]) or len(at.radio[0].options) == 3


def test_signing_an_approval_through_the_ui_writes_the_log_and_unlocks_the_dry_run() -> None:
    import common
    import overrides
    store, (_, ws) = common.get_store(), common.identity()
    at = page("12_Signoff.py")
    item_id = at.selectbox(key="so_pick").value
    fill_and_sign(at, "APPROVED")
    go = next(b for b in at.button if b.label == "Sign and record this decision")
    assert not go.disabled
    go.click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    assert store.get_inbox_item(ws, item_id)["status"] == "approved"
    log = Path(common.DATA_ROOT) / "workspaces" / ws / "run_audit_log.json"
    entries = overrides.read_log(log)
    assert len(entries) == 1 and entries[0]["decision_outcome"] == "APPROVED" and entries[0]["authorizing_user"]["authentication"] == "self_asserted" and overrides.verify_log(log)[0]
    at2 = page("12_Signoff.py")
    at2.segmented_control(key="so_filter").set_value("Approved").run(timeout=T)
    assert "Signed: Approve as suggested" in text(at2) and any(b.label == "Record the dry run" for b in at2.button)
    next(b for b in at2.button if b.label == "Record the dry run").click().run(timeout=T)
    assert store.get_inbox_item(ws, item_id)["status"] == "executed"


def test_reject_and_override_are_signed_and_dismiss() -> None:
    import common
    store, (_, ws) = common.get_store(), common.identity()
    at = page("12_Signoff.py")
    item_id = at.selectbox(key="so_pick").value
    fill_and_sign(at, "REJECTED")
    next(b for b in at.button if b.label == "Sign and record this decision").click().run(timeout=T)
    assert store.get_inbox_item(ws, item_id)["status"] == "dismissed" and store.get_signoff(ws, item_id)["outcome"] == "REJECTED"


def test_a_strategy_scenario_and_a_research_spec_can_be_sent_to_the_desk() -> None:
    import common
    store, (_, ws) = common.get_store(), common.identity()
    s = page("9_Strategy.py")
    next(b for b in s.button if b.key == "send_scn").click().run(timeout=T)
    assert not s.exception, [e.value for e in s.exception]
    assert any(i["agent_id"] == "STRATEGY_SCENARIO" and i["status"] == "new" for i in store.list_inbox(ws))
    r = page("11_Research.py")
    assert not r.exception, [e.value for e in r.exception]
    btn = next(b for b in r.button if b.key.startswith("send_SPEC-"))
    btn.click().run(timeout=T)
    assert any(i["agent_id"] == "RESEARCH_SPEC" and i["status"] == "new" for i in store.list_inbox(ws))
    at = page("12_Signoff.py")
    assert any("Authorize research" in o or "budget scenario" in o for o in at.selectbox(key="so_pick").options)


def test_research_page_lists_ranked_ideas_with_blank_resources_and_tools() -> None:
    at = page("11_Research.py")
    t = text(at)
    assert "The question this answers" in t and "Ideas to consider" in t and "Priority = spend at stake" in t
    assert any(i.key.startswith("rs_SPEC-") and i.value == "" for i in at.text_input)
    assert "Match test and control markets" in " ".join(tab.label for tab in at.tabs)
    assert not EMOJI.search(t)


def test_synthetic_control_tool_loads_an_example_and_reports_fit() -> None:
    at = page("11_Research.py")
    next(b for b in at.button if b.label.startswith("Load an example")).click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "Pre-launch fit error" in t or "Fit check" in t or any("Pre-launch fit error" in str(getattr(m, "label", "")) for m in at.markdown)


def test_automation_page_renders_and_states_the_boundaries() -> None:
    at = page("13_Automation.py")
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "no approve tool and no execute tool" in t and "Built and tested" in t and "Never allowed" in t
    assert not EMOJI.search(t)
