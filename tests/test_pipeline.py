"""Pytest suite for the MMGE pipeline."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "data"))

from agent_orchestrator import AgentOrchestrator  # noqa: E402
from database_manager import OUTPUT_VIEWS, DatabaseManager  # noqa: E402
from generate_synthetic_data import generate_all_data  # noqa: E402
from governance_checker import run_audit  # noqa: E402

DATA = ROOT / "data"
SCHEMAS = {
    "RAW_PLATFORM_DATA": (720, ["date", "channel", "campaign_id", "spend", "impressions", "clicks",
                                "reported_conversions", "reported_revenue"]),
    "RAW_MTA_OUTPUT": (720, ["date", "channel", "campaign_id", "mta_attributed_conversions",
                             "mta_attributed_revenue", "mta_attribution_weight", "model_version"]),
    "RAW_HOLDOUT_DATA": (1440, ["date", "experiment_id", "campaign_id", "geo_or_cohort_id", "group_type",
                                "treatment_flag", "population_size", "conversions", "revenue"]),
    "BUSINESS_BENCHMARKS": (4, ["channel", "expected_roas_min", "expected_roas_max", "expected_cvr_min",
                                "expected_cvr_max", "typical_incrementality_min", "typical_incrementality_max"]),
}


@pytest.fixture(scope="module")
def mgr() -> DatabaseManager:
    m = DatabaseManager().build()
    yield m
    m.close()


# ------------------------------------------------------------------ raw data
@pytest.mark.parametrize("table", list(SCHEMAS))
def test_raw_rows_and_schema(table: str) -> None:
    rows, cols = SCHEMAS[table]
    df = pd.read_csv(DATA / f"{table}.csv")
    assert len(df) == rows
    assert list(df.columns) == cols
    assert not df.isna().any().any()


def test_generator_matches_committed_data() -> None:
    platform, mta, holdout, _ = generate_all_data(42)
    pd.testing.assert_frame_equal(platform, pd.read_csv(DATA / "RAW_PLATFORM_DATA.csv"), check_dtype=False)
    pd.testing.assert_frame_equal(mta, pd.read_csv(DATA / "RAW_MTA_OUTPUT.csv"), check_dtype=False)
    pd.testing.assert_frame_equal(holdout, pd.read_csv(DATA / "RAW_HOLDOUT_DATA.csv"), check_dtype=False)


def test_experiment_structure() -> None:
    h = pd.read_csv(DATA / "RAW_HOLDOUT_DATA.csv")
    assert h["date"].nunique() == 90 and h["campaign_id"].nunique() == 8
    assert h[h["date"] < "2026-01-31"]["treatment_flag"].sum() == 0
    assert (h[(h["date"] >= "2026-01-31") & (h["group_type"] == "treatment")]["treatment_flag"] == 1).all()


# ------------------------------------------------------------- DuckDB views
@pytest.mark.parametrize("view", list(OUTPUT_VIEWS))
def test_views_execute_without_nulls(mgr: DatabaseManager, view: str) -> None:
    df = mgr.view(view)
    assert len(df) > 0
    assert not df.isna().any().any(), f"{view} contains NULLs"


def test_staging_grain_and_row_count(mgr: DatabaseManager) -> None:
    stg = mgr.view("STG_UNIFIED_MEASUREMENT")
    assert len(stg) == 720
    assert not stg.duplicated(["date", "channel", "campaign_id"]).any()
    assert (stg["has_holdout_coverage"] == 1).all()


def test_holdout_scaled_by_geo_sample(mgr: DatabaseManager) -> None:
    raw = pd.read_csv(DATA / "RAW_HOLDOUT_DATA.csv")
    expected = raw[raw["group_type"] == "treatment"]["conversions"].sum() / 0.40
    assert mgr.view("STG_UNIFIED_MEASUREMENT")["holdout_conversions"].sum() == pytest.approx(expected)


def test_roas_and_inflation_math(mgr: DatabaseManager) -> None:
    recon = mgr.view("ANALYTICS_MEASUREMENT_RECONCILIATION")
    plat = pd.read_csv(DATA / "RAW_PLATFORM_DATA.csv").groupby("campaign_id").sum(numeric_only=True)
    hold = pd.read_csv(DATA / "RAW_HOLDOUT_DATA.csv")
    hold = hold[hold["group_type"] == "treatment"].groupby("campaign_id").sum(numeric_only=True) / 0.40
    for _, r in recon.iterrows():
        c = r["campaign_id"]
        assert r["reported_roas"] == pytest.approx(plat.loc[c, "reported_revenue"] / plat.loc[c, "spend"], abs=0.006)
        assert r["incremental_roas"] == pytest.approx(hold.loc[c, "revenue"] / plat.loc[c, "spend"], abs=0.006)
        assert r["inflation_ratio"] == pytest.approx(
            plat.loc[c, "reported_conversions"] / hold.loc[c, "conversions"], abs=0.006)


def test_portfolio_totals_match_spec(mgr: DatabaseManager) -> None:
    a = mgr.view("GOVERNANCE_AUDIT_SUMMARY").set_index("channel")
    assert a["total_spend"].sum() == pytest.approx(748140.42, abs=0.05)
    assert a["total_holdout_revenue"].sum() == pytest.approx(2490562.50, abs=0.05)
    assert a.loc["Google Ads", "incremental_roas"] == 5.71
    assert a.loc["Meta Ads", "incremental_roas"] == 3.25
    assert a.loc["Netflix Ads", "governance_action"].startswith("UNPROFITABLE")


def test_rolling_window_is_seven_days(mgr: DatabaseManager) -> None:
    r = mgr.view("ROLLING_7D_PERFORMANCE")
    c = r[r["campaign_id"] == "META_ADS_CMP_01"].sort_values("date").reset_index(drop=True)
    assert c.loc[6, "rolling_7d_spend"] == pytest.approx(c.loc[:6, "daily_spend"].sum(), abs=0.05)
    assert c.loc[20, "rolling_7d_spend"] == pytest.approx(c.loc[14:20, "daily_spend"].sum(), abs=0.05)


@pytest.mark.parametrize("inflation,holdout,prefix", [
    (3.0, 100, "CRITICAL"), (2.99, 100, "MODERATE"), (1.5, 100, "MODERATE"),
    (1.49, 100, "PASS"), (1.0, 0, "NO_HOLDOUT"),
])
def test_governance_status_thresholds(inflation: float, holdout: int, prefix: str) -> None:
    db = DatabaseManager().build()
    db.con.execute(f"""CREATE OR REPLACE VIEW ANALYTICS_MEASUREMENT_RECONCILIATION AS SELECT
        'X' AS channel, 'X1' AS campaign_id, 1.0 AS total_spend, 1 AS total_platform_conversions,
        1 AS total_platform_revenue, 1 AS total_mta_conversions, 1 AS total_mta_revenue,
        {holdout} AS total_holdout_conversions, 1 AS total_holdout_revenue, 1 AS has_mta_coverage,
        1 AS has_holdout_coverage, 1 AS reported_roas,
        1 AS mta_roas, 1 AS incremental_roas, {inflation} AS inflation_ratio""")
    db._run_sql_file("04_governance_queries.sql")
    assert db.con.execute("SELECT governance_status FROM GOVERNANCE_CAMPAIGN_ALERTS").fetchone()[0].startswith(prefix)
    db.close()


def test_export_outputs(tmp_path: Path) -> None:
    db = DatabaseManager(output_dir=tmp_path).build()
    written = db.export_outputs()
    db.close()
    assert {p.name for p in written.values()} == set(OUTPUT_VIEWS.values())
    assert all(p.stat().st_size > 0 for p in written.values())


# ---------------------------------------------------------------- orchestrator
def _row(**kw) -> pd.DataFrame:
    base = dict(channel="Meta Ads", campaign_id="C1", total_spend=1000.0, total_platform_conversions=100.0,
                total_holdout_conversions=50.0, total_holdout_revenue=500.0, reported_roas=2.0,
                incremental_roas=1.5, inflation_ratio=1.0)
    base.update(kw)
    return pd.DataFrame([base])


def _agents(**kw):
    return [p["agent_id"] for p in AgentOrchestrator(_row(**kw)).evaluate_triggers()]


def test_capital_agent_boundaries() -> None:
    assert _agents(reported_roas=1.5, incremental_roas=0.99) == ["CAPITAL_PRESERVATION_AGENT"]
    assert _agents(reported_roas=1.49, incremental_roas=0.5) == []
    assert _agents(reported_roas=3.0, incremental_roas=1.0) == []


def test_shield_agent_boundaries() -> None:
    assert _agents(inflation_ratio=1.25) == []
    assert _agents(inflation_ratio=1.26) == ["ATTRIBUTION_SHIELD_AGENT"]
    assert _agents(inflation_ratio=3.0) == ["ATTRIBUTION_SHIELD_AGENT"]
    assert _agents(inflation_ratio=3.01) == []


def test_scale_agent_boundaries() -> None:
    assert _agents(incremental_roas=3.0, inflation_ratio=1.25) == ["SCALE_OPPORTUNITY_AGENT"]
    assert _agents(incremental_roas=2.99, inflation_ratio=1.0) == []
    assert _agents(incremental_roas=5.0, inflation_ratio=1.26) == ["ATTRIBUTION_SHIELD_AGENT"]


def test_multiple_agents_can_fire() -> None:
    assert set(_agents(reported_roas=2.0, incremental_roas=0.5, inflation_ratio=2.0)) == {
        "CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT"}


def test_null_and_zero_inputs_do_not_crash() -> None:
    assert _agents(inflation_ratio=float("nan"), incremental_roas=float("nan")) == []
    assert set(_agents(inflation_ratio=2.0, incremental_roas=0.0)) == {"CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT"}


def test_capital_packet_math() -> None:
    p = AgentOrchestrator(_row(reported_roas=2.0, incremental_roas=0.5, total_spend=1000.0,
                               total_holdout_revenue=500.0, total_platform_conversions=100.0,
                               total_holdout_conversions=40.0)).evaluate_triggers()[0]
    assert p["raw_metrics"]["cannibalization_pct"] == pytest.approx(60.0)
    assert p["raw_metrics"]["net_unrecouped_spend"] == pytest.approx(500.0)


def test_scale_packet_projects_25_percent() -> None:
    p = AgentOrchestrator(_row(incremental_roas=4.0, total_spend=1000.0)).evaluate_triggers()[0]
    assert p["raw_metrics"]["projected_gain"] == pytest.approx(1000.0)


def test_missing_columns_rejected() -> None:
    with pytest.raises(ValueError):
        AgentOrchestrator(pd.DataFrame({"channel": ["x"]}))


def test_action_log(tmp_path: Path) -> None:
    p = AgentOrchestrator(_row(incremental_roas=4.0)).evaluate_triggers()[0]
    rec = AgentOrchestrator.log_action(p, tmp_path / "log.jsonl")
    assert rec["snowflake_sql"].startswith("INSERT INTO") and (tmp_path / "log.jsonl").exists()


# ------------------------------------------------------------ governance audit
def test_audit_structure(mgr: DatabaseManager) -> None:
    report = run_audit(mgr)
    assert report["campaigns_audited"] == 8
    for c in report["campaigns"]:
        assert [k["check_id"] for k in c["checks"]] == list(range(1, 9))
        assert 0 <= c["trust_score"] <= 100
        assert all(k["status"] in {"PASS", "WARN", "FAIL", "NA"} for k in c["checks"])
        assert c["checks"][3]["status"] == "NA"  # the demo benchmark table is an unsourced placeholder, so check 4 makes no comparison
    netflix = next(c for c in report["campaigns"] if c["campaign_id"] == "NETFLIX_ADS_CMP_01")
    assert netflix["checks"][7]["status"] == "FAIL"  # lift interval includes zero
