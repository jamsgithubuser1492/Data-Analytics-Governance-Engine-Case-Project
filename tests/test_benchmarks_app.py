"""Benchmarks and economics UI flow tests (Streamlit AppTest)."""
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


def test_1_benchmarks_page_answers_comparability() -> None:
    at = page("pages/6_Benchmarks.py")
    clean(at)
    assert {m.label: m.value for m in at.metric}["Verified records"] == "234"
    at.selectbox[0].select("ad_click_cvr").run(timeout=T)
    assert any("Not comparable" in w.value for w in at.warning)
    at.selectbox[0].select("channel_roas").run(timeout=T)
    assert any("Not comparable" in w.value for w in at.warning)
    at.selectbox[0].select("order_value").run(timeout=T)
    assert any("proxy" in s.value for s in at.success)


def test_2_offline_verification_button() -> None:
    at = page("pages/6_Benchmarks.py")
    next(b for b in at.button if b.label == "Run offline verification").click().run(timeout=T)
    clean(at)
    rows = [d for d in at.dataframe if "Check" in getattr(d.value, "columns", [])]
    assert rows and (rows[0].value["Status"].str.contains("PASS").all())


def test_3_settings_margin_and_geos_flow_to_the_dashboard() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    s = page("pages/3_Settings.py")
    clean(s)
    next(c for c in s.checkbox if c.label.startswith("I know")).check()
    next(n for n in s.number_input if n.label.startswith("Contribution margin")).set_value(50.0)
    next(t for t in s.text_area if "Treatment geo" in t.label).set_value("06, 48, 12")
    next(b for b in s.button if b.label == "Save new version").click().run(timeout=T)
    clean(s)
    cfg, decl, v = store.latest_workspace_config(ws)
    assert cfg.gross_margin == 0.5 and decl["test_geo_fips"] == ["06", "48", "12"] and v == 1
    assert any("2.00x" in i.value for i in s.info) and any("27.7%" in w.value for w in s.warning)
    d = page("app.py")
    next(b for b in d.button if b.label == "Try with demo data").click().run(timeout=T)
    clean(d)
    assert any("Breakeven 2.00x at a 50% margin" in m.value for m in d.markdown)
    run = store.list_runs(ws)[0]
    audit = store.load_audit(ws, run["id"])
    assert audit["economics"]["breakeven_iroas"] == 2.0
    assert any(i["rule"] == "scale_factor_mismatch" for i in run["validation"]["issues"])
    assert run["validation"]["scale_factor"]["census_share"] == pytest.approx(0.27657, abs=1e-4)


def test_4_invalid_geo_codes_are_rejected_on_save() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    before = store.latest_workspace_config(ws)[2]
    s = page("pages/3_Settings.py")
    next(t for t in s.text_area if "Treatment geo" in t.label).set_value("99, 06037, 06")
    next(b for b in s.button if b.label == "Save new version").click().run(timeout=T)
    clean(s)
    assert any("Treatment geo codes" in e.value for e in s.error) and store.latest_workspace_config(ws)[2] == before


def test_5_industry_proxy_is_labeled_as_proxy() -> None:
    import common
    store, (actor, ws) = common.get_store(), common.identity()
    s = page("pages/3_Settings.py")
    next(c for c in s.checkbox if c.label.startswith("I know")).uncheck()
    next(sb for sb in s.selectbox if sb.label.startswith("Or use an industry proxy")).select("Apparel")
    next(t for t in s.text_area if "Treatment geo" in t.label).set_value("")
    next(b for b in s.button if b.label == "Save new version").click().run(timeout=T)
    clean(s)
    assert store.latest_workspace_config(ws)[0].margin_industry == "Apparel"
    assert any("Industry proxy" in i.value and "higher" in i.value for i in s.info)
