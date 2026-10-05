"""Advisory council page: personas, guardrail presets in plain language, custom watch, guide, data integrity."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "data"))

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import verify_data  # noqa: E402

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


def council() -> AppTest:
    return AppTest.from_file(str(ROOT / "app" / "pages" / "4_Agents.py"), default_timeout=T).run(timeout=T)


def alltext(at: AppTest) -> str:
    return " ".join(str(getattr(e, "value", "")) + " " + str(getattr(e, "label", "")) for k in ("markdown", "caption", "button", "metric", "radio", "expander") for e in getattr(at, k))


def test_council_page_renders_every_persona_view_without_emoji() -> None:
    at = council()
    assert not at.exception, [e.value for e in at.exception]
    text = alltext(at)
    assert "Where the council agrees" in text and "Leans conservative" in text and "Leans aggressive" in text
    for name in ("The Steward", "The Builder", "The Translator", "The Mechanic"):
        seg = next(c for c in at.segmented_control if c.key == "council_who")
        seg.set_value(name).run(timeout=T)
        assert not at.exception, [e.value for e in at.exception]
        t = alltext(at)
        assert "What would change my mind" in " ".join(m.value for m in at.markdown) or "What would change my mind" in t
        assert name in t and not EMOJI.search(t)


def test_risk_appetite_is_saved_as_new_versions_and_detected() -> None:
    import common
    import stances
    at = council()
    at.radio(key="appetite").set_value("Aggressive").run(timeout=T)
    next(b for b in at.button if b.label.startswith("Apply Aggressive")).click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    store, (_, ws) = common.get_store(), common.identity()
    defs = {d["id"]: d for d in store.get_agent_definitions(ws)}
    assert stances.detect_appetite(defs) == "Aggressive" and defs["SCALE_OPPORTUNITY_AGENT"]["version"] >= 2
    at2 = council()
    assert at2.radio(key="appetite").value == "Aggressive"
    at2.radio(key="appetite").set_value("Balanced").run(timeout=T)
    next(b for b in at2.button if b.label.startswith("Apply Balanced")).click().run(timeout=T)
    assert stances.detect_appetite({d["id"]: d for d in store.get_agent_definitions(ws)}) == "Balanced"


def test_a_guardrail_can_be_tuned_in_plain_terms_with_a_live_preview() -> None:
    at = council()
    box = at.number_input(key="ATTRIBUTION_SHIELD_AGENT_overclaim_above")
    box.set_value(1.1).run(timeout=T)
    assert any("Would flag" in m.value for m in at.markdown)
    save = next(b for b in at.button if b.key == "save_ATTRIBUTION_SHIELD_AGENT")
    assert not save.disabled
    save.click().run(timeout=T)
    import common, stances
    _, ws = common.identity()
    d = {x["id"]: x for x in common.get_store().get_agent_definitions(ws)}["ATTRIBUTION_SHIELD_AGENT"]
    assert stances.read_settings(d)["overclaim_above"] == pytest.approx(1.1)
    box = council().number_input(key="ATTRIBUTION_SHIELD_AGENT_overclaim_above")
    assert box.value == pytest.approx(1.1)


def test_guide_page_and_methodology_file_are_in_sync() -> None:
    import guide_content
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "7_Guide.py"), default_timeout=T).run(timeout=T)
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "holdout" in text.lower() and "trust score" in text.lower() and "Strict lift" in text
    assert (ROOT / "docs" / "METHODOLOGY.md").read_text(encoding="utf-8").strip() == guide_content.to_markdown().strip()
    assert not EMOJI.search(guide_content.to_markdown())


def test_advanced_editor_remains_available_to_analysts() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "8_Advanced_rules.py"), default_timeout=T).run(timeout=T)
    assert not at.exception and any("Advanced rule editor" in m.value for m in at.markdown)


# ---------------------------------------------------------------------------------- verified data
def test_case_study_files_match_the_recorded_checksums() -> None:
    assert verify_data.all_verified(), verify_data.verify()
    assert all(ok for _, ok, _ in verify_data.verify())


def test_a_changed_file_is_detected(tmp_path) -> None:
    for n in verify_data.FILES:
        (tmp_path / n).write_bytes((ROOT / "data" / n).read_bytes())
    assert verify_data.all_verified(tmp_path)
    p = tmp_path / "RAW_MTA_OUTPUT.csv"
    p.write_text(p.read_text() + "\n2026-01-01,X,Y,1,1,0.5,v\n")
    res = {n: ok for n, ok, _ in verify_data.verify(tmp_path)}
    assert res["RAW_MTA_OUTPUT.csv"] is False and res["RAW_PLATFORM_DATA.csv"] is True


def test_generator_defaults_to_a_separate_folder_and_reproduces_the_verified_values(tmp_path) -> None:
    import subprocess
    import pandas as pd
    r = subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic_data.py"), "--out-dir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0
    for n in verify_data.FILES:
        pd.testing.assert_frame_equal(pd.read_csv(tmp_path / n), pd.read_csv(ROOT / "data" / n), check_exact=False, rtol=1e-9)
    refuse = subprocess.run([sys.executable, str(ROOT / "data" / "generate_synthetic_data.py"), "--out-dir", str(ROOT / "data")], capture_output=True, text=True)
    assert refuse.returncode != 0 and "Refusing to overwrite" in (refuse.stderr + refuse.stdout)
    assert verify_data.all_verified()


def test_upload_page_offers_verified_data_and_in_memory_generation() -> None:
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "1_Upload.py"), default_timeout=T).run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    assert any("verified demo data" in b.label for b in at.button) and any("checksums" in c.value for c in at.caption)
    before = {n: hashlib.sha256((ROOT / "data" / n).read_bytes()).hexdigest() for n in verify_data.FILES}
    next(b for b in at.button if b.key == "gen_go").click().run(timeout=T)
    assert not at.exception, [e.value for e in at.exception]
    assert before == {n: hashlib.sha256((ROOT / "data" / n).read_bytes()).hexdigest() for n in verify_data.FILES}  # verified files untouched


def test_dollar_amounts_are_escaped_so_markdown_does_not_turn_them_into_formulas() -> None:
    import ui
    assert ui.esc("$1,000 and $2,000") == "\\$1,000 and \\$2,000"
    at = council()
    heads = [m.value for m in at.markdown if "has not been earned back" in m.value]
    assert heads and all("\\$" in h for h in heads), heads
