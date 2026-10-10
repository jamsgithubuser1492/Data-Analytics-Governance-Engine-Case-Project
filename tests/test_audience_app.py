"""Audience tier screens: dashboard section, advisors, Sign-off desk, Settings and Upload."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "app")]

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


def text(at) -> str:
    return " ".join(str(getattr(e, "value", "")) + " " + str(getattr(e, "label", "")) for k in ("markdown", "caption", "button", "metric", "expander", "number_input", "slider", "file_uploader", "checkbox")
                    for e in getattr(at, k))


def test_dashboard_leads_with_dollars_and_stamps_the_basis() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "Audience tiers: who the money actually reaches" in t
    assert re.search(r"\$[\d,]+ of spend in \d+ audience tiers? is paying for sales that would have happened anyway", t)
    assert "Strict lift" in t and "Match passed" in t and "Review required" in t
    assert "How well the control markets match the test markets" in t and "What each advisor sees in the audience tiers" in t
    assert not EMOJI.search(t)
    assert t.index("Audience tiers: who the money") < t.index("The advisory council") < t.index("Decisions for your sign-off")


@pytest.mark.parametrize("who", ["CFO / Finance", "CMO / Growth", "Agency Director", "Platform Lead"])
def test_each_perspective_gets_its_own_first_sentence(who: str) -> None:
    at = AppTest.from_file(str(ROOT / "app" / "app.py"), default_timeout=T).run(timeout=T)
    next(c for c in at.segmented_control if c.key == "persp").set_value(who).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    key = {"CFO / Finance": "is paying for sales that would have happened anyway", "CMO / Growth": "modeled value of moving", "Agency Director": "difference is where client and platform reports will disagree",
           "Platform Lead": "cannot be judged yet"}[who]
    assert key in t


def test_advisor_suggestions_use_the_allowed_forms_and_facts_do_not() -> None:
    import audience_tiers as aud
    import council as cn
    from pipeline import SourceTables, run_pipeline
    r = run_pipeline(SourceTables.from_directory(with_audience=True))
    tab, match = r.tables["AUDIENCE_TIER_RESULTS"], r.tables["AUDIENCE_MATCH_QUALITY"]
    out = cn.tier_readings(tab, match, aud.summary(tab), aud.shift_scenario(tab), 75.0)
    assert [o["persona"] for o in out] == ["STEWARD", "BUILDER", "TRANSLATOR", "MECHANIC"]
    assert all(o["suggestion"].startswith(cn.ALLOWED_OPENERS) for o in out)
    assert not any(o["headline"].startswith(cn.ALLOWED_OPENERS) for o in out)
    assert not EMOJI.search(" ".join(o["headline"] + o["suggestion"] for o in out))


def test_sign_off_desk_shows_checks_and_the_basis_for_a_tier_decision() -> None:
    import common
    store = common.get_store()
    _, ws = common.identity()
    item = next(i for i in store.list_inbox(ws) if i["packet"].get("audience_tier") and i["status"] in ("new", "reviewed"))
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "12_Signoff.py"), default_timeout=T)
    at.session_state["signoff_item"] = item["id"]
    at.run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    assert "Governance checks" in t and "Platform credit per $1" in t and "Caused by the ads per $1" in t
    assert "Audience tiers always count only the extra conversions the ads caused" in t
    assert "Reduce spend on this audience tier" in t
    assert not EMOJI.search(t)


def test_settings_page_exposes_the_audience_policy() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "3_Settings.py"), default_timeout=T).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    t = text(at)
    for label in ("Weight on matching the audience mix", "Recommend reducing tier spend at this share not caused by ads (%)", "Minimum people reached per arm", "Control match: minimum audience mix overlap"):
        assert label in t, label


def test_upload_page_offers_the_optional_aggregate_audience_files() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "1_Upload.py"), default_timeout=T).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    assert "Optional: add audience tier data" in " ".join(e.label for e in at.expander) or "Optional: add audience tier data" in text(at)
