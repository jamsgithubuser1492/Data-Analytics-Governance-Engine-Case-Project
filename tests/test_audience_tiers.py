"""Audience tier arithmetic, sample guard, contract checks, SQL parity, data generation and pipeline wiring."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "app"), str(ROOT / "data"), str(ROOT / "tests")]

import audience_tiers as at  # noqa: E402
from config import PolicySettings, SettingsError  # noqa: E402
from helpers import sign_for_test  # noqa: E402
from pipeline import SourceTables, audience_packets, run_pipeline  # noqa: E402


def one_tier(**over):
    row = {"date": "2026-01-01", "channel": "Meta Ads", "campaign_id": "C1", "tier_name": "Tier 1 (High intent)", "tier_decile_start": 1, "tier_decile_end": 2,
           "spend": 50000.0, "reported_revenue": 410000.0, "treatment_conversions": 100000.0, "treatment_users": 1_000_000.0,
           "control_conversions": 94500.0, "control_users": 1_000_000.0}
    row.update(over)
    return pd.DataFrame([row])


@pytest.fixture(scope="module")
def demo():
    return at.load_demo_audience()


@pytest.fixture(scope="module")
def result():
    return run_pipeline(SourceTables.from_directory(with_audience=True))


# ------------------------------------------------------------------------------------------ the worked example
def test_the_50k_retargeting_example() -> None:
    r = at.tier_table(one_tier(), match_passed={"Meta Ads": True}).iloc[0]
    assert r["reported_roas"] == pytest.approx(8.2)
    assert r["strict_iroas"] == pytest.approx(0.45, abs=0.005)
    assert r["cannibalization_pct"] == pytest.approx(94.5)
    assert r["spend_for_organic_sales"] == pytest.approx(47250.0)  # "$47,250 of spend is paying for sales that would have happened anyway"
    assert r["spend_for_net_new_sales"] == pytest.approx(2750.0)
    assert r["status"] == at.STATUS_CRITICAL and r["action"] == at.ACTION_REDUCE


def test_identities_hold_on_every_tier(demo) -> None:
    t = at.tier_table(demo["AUDIENCE_TIER_PERFORMANCE"], match_passed={})
    assert np.allclose(t["strict_incremental_revenue"] + t["cannibalized_revenue"], t["reported_revenue"])
    assert np.allclose(t["spend_for_organic_sales"] + t["spend_for_net_new_sales"], t["spend"])
    assert (t["strict_iroas"] <= t["reported_roas"] + 1e-9).all()  # ads can never be credited with more than the platform claims
    assert ((t["lift_ratio"] >= 0) & (t["lift_ratio"] <= 1)).all()
    assert (t["lift_low"] <= t["lift_ratio"] + 1e-9).all() and (t["lift_ratio"] <= t["lift_high"] + 1e-9).all()


def test_lift_is_floored_at_zero_when_control_beats_test() -> None:
    r = at.tier_table(one_tier(control_conversions=110000.0), match_passed={"Meta Ads": True}).iloc[0]
    assert r["lift_ratio"] == 0 and r["cannibalization_pct"] == 100 and r["strict_iroas"] == 0


# ------------------------------------------------------------------------------------------ sample guard and evidence levels
def test_sparse_tiers_are_not_judged_and_recommend_nothing() -> None:
    sparse = one_tier(treatment_users=900.0, control_users=900.0, treatment_conversions=60.0, control_conversions=5.0)
    r = at.tier_table(sparse, match_passed={"Meta Ads": True}).iloc[0]
    assert r["evidence_tier"] == "NOT_DECISION_GRADE" and r["status"] == at.STATUS_NO_DATA and r["action"] == at.ACTION_NONE
    facts = at.tier_facts(at.tier_table(sparse, match_passed={"Meta Ads": True}))
    assert facts["cannibalization_pct"].isna().all()
    aud = {"AUDIENCE_TIER_RESULTS": at.tier_table(sparse, match_passed={"Meta Ads": True}), "AUDIENCE_MATCH_QUALITY": pd.DataFrame({"channel": ["Meta Ads"], "passed": [True]})}
    from agent_engine import default_definitions
    assert audience_packets(default_definitions(), aud, PolicySettings()) == []


def test_evidence_level_needs_a_firm_range_and_a_passed_match() -> None:
    firm = at.tier_table(one_tier(), match_passed={"Meta Ads": True}).iloc[0]
    assert firm["evidence_tier"] == "VERIFIED"
    unchecked = at.tier_table(one_tier(), match_passed={}).iloc[0]
    assert unchecked["evidence_tier"] == "DIRECTIONAL"  # sample is fine but the control match has not passed
    wide = at.tier_table(one_tier(treatment_users=10000.0, control_users=10000.0, treatment_conversions=120.0, control_conversions=108.0), match_passed={"Meta Ads": True}).iloc[0]
    assert wide["evidence_tier"] == "DIRECTIONAL" and wide["range_width"] > PolicySettings().tier_max_range_width


def test_small_spend_never_raises_a_money_recommendation() -> None:
    r = at.tier_table(one_tier(spend=5000.0, reported_revenue=41000.0), match_passed={"Meta Ads": True}).iloc[0]
    assert r["status"] == at.STATUS_CRITICAL and r["action"] == at.ACTION_SMALL


def test_thresholds_come_from_the_policy() -> None:
    lenient = PolicySettings(cannibalization_warning_threshold=60, cannibalization_critical_threshold=99)
    assert at.tier_table(one_tier(), lenient, match_passed={"Meta Ads": True}).iloc[0]["status"] == at.STATUS_REVIEW
    with pytest.raises(SettingsError):
        PolicySettings(cannibalization_warning_threshold=80, cannibalization_critical_threshold=70)


# ------------------------------------------------------------------------------------------ contract
def test_the_shipped_demo_audience_passes_the_contract(demo) -> None:
    rep = at.validate_audience(demo)
    assert rep.ok and not rep.warnings


def test_person_level_columns_and_bad_shapes_are_refused(demo) -> None:
    bad = {k: v.copy() for k, v in demo.items()}
    bad["AUDIENCE_TIER_PERFORMANCE"]["customer_id"] = "x"
    assert any(i.rule == "person_level_column" for i in at.validate_audience(bad).blockers)
    bad = {k: v.copy() for k, v in demo.items()}
    bad["AUDIENCE_DMA_PROPENSITY"].loc[0, "decile_1_pct"] += 0.2
    assert any(i.rule == "decile_mix_not_one" for i in at.validate_audience(bad).blockers)
    bad = {k: v.copy() for k, v in demo.items()}
    bad["AUDIENCE_TIER_PERFORMANCE"] = pd.concat([bad["AUDIENCE_TIER_PERFORMANCE"], bad["AUDIENCE_TIER_PERFORMANCE"].head(1)])
    assert any(i.rule == "duplicate_rows" for i in at.validate_audience(bad).blockers)
    bad = {k: v.copy() for k, v in demo.items()}
    bad["AUDIENCE_TIER_PERFORMANCE"].loc[0, "treatment_conversions"] = bad["AUDIENCE_TIER_PERFORMANCE"].loc[0, "treatment_users"] + 1
    assert any(i.rule == "conversions_exceed_users" for i in at.validate_audience(bad).blockers)
    assert any(i.rule == "missing_table" for i in at.validate_audience({}).blockers)


# ------------------------------------------------------------------------------------------ SQL parity and data
def test_sql_view_matches_the_python_engine(demo) -> None:
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    sql = (ROOT / "sql" / "audience_tier_views.sql").read_text()
    con.execute(sql.split("CREATE TABLE IF NOT EXISTS stg_audience_tier_performance")[0])
    tiers = demo["AUDIENCE_TIER_PERFORMANCE"].copy()
    tiers["date"] = pd.to_datetime(tiers["date"])
    con.register("tiers_df", tiers)
    ddl = "CREATE TABLE IF NOT EXISTS stg_audience_tier_performance" + sql.split("CREATE TABLE IF NOT EXISTS stg_audience_tier_performance")[1]
    con.execute(ddl.split("-- Share of credited")[0])
    con.execute("INSERT INTO stg_audience_tier_performance SELECT * FROM tiers_df")
    con.execute("CREATE OR REPLACE VIEW" + sql.split("CREATE OR REPLACE VIEW")[1])
    v = con.execute("SELECT * FROM view_audience_tier_disaggregation").df().set_index(["campaign_id", "tier_name"]).sort_index()
    p = at.tier_table(demo["AUDIENCE_TIER_PERFORMANCE"], match_passed={}).set_index(["campaign_id", "tier_name"]).sort_index()
    assert np.allclose(v["incremental_lift_ratio"], p["lift_ratio"]) and np.allclose(v["strict_iroas"], p["strict_iroas"])
    assert np.allclose(v["spend_for_organic_sales"], p["spend_for_organic_sales"])


def test_audience_data_is_deterministic_and_leaves_the_verified_files_alone() -> None:
    import generate_audience_data as gen
    out = Path(tempfile.mkdtemp())
    frames = gen.generate(out)
    for name, df in frames.items():
        shipped = pd.read_csv(ROOT / "data" / "audience" / f"{name}.csv")
        pd.testing.assert_frame_equal(pd.read_csv(out / f"{name}.csv"), shipped)
    import subprocess
    assert subprocess.run([sys.executable, str(ROOT / "python" / "verify_data.py")], capture_output=True).returncode == 0
    assert (ROOT / "data" / "audience" / "SYNTHETIC_DATA_NOTE.txt").exists()


def test_tier_spend_ties_back_to_the_platform_data(demo) -> None:
    plat = pd.read_csv(ROOT / "data" / "RAW_PLATFORM_DATA.csv")
    test_days = sorted(plat["date"].unique())[30:]
    expected = plat[plat["date"].isin(test_days)].groupby("campaign_id")["spend"].sum()
    got = demo["AUDIENCE_TIER_PERFORMANCE"].groupby("campaign_id")["spend"].sum()
    assert np.allclose(got, expected.reindex(got.index), atol=1.0)


# ------------------------------------------------------------------------------------------ pipeline wiring
def test_a_run_without_audience_data_is_unchanged() -> None:
    r = run_pipeline(SourceTables.from_directory())
    assert not any(k.startswith("AUDIENCE") for k in r.tables) and not any(p.get("audience_tier") for p in r.packets)
    assert "audience" not in r.audit


def test_a_run_with_audience_data_adds_tables_summary_and_gated_packets(result) -> None:
    assert {"AUDIENCE_TIER_RESULTS", "AUDIENCE_MATCH_QUALITY"} <= set(result.tables)
    tier_packets = [p for p in result.packets if p.get("audience_tier")]
    assert tier_packets and all(p["agent_id"] == "AUDIENCE_CANNIBALIZATION_AGENT" and p["recommended_action"] == "REDUCE_TIER_SPEND" for p in tier_packets)
    assert all(p["tier"] in ("VERIFIED", "DIRECTIONAL") for p in tier_packets)  # money actions never fire below Directional
    assert all(float(p["raw_metrics"]["Share of credited sales that ads did not cause"]) >= 75.0 for p in tier_packets)
    assert result.audit["audience"]["critical_tiers"] == len(tier_packets)
    assert all(p["strategic_callout"].split(",")[1].strip().startswith(("but", "given", "Given")) or "perhaps we should think about" in p["strategic_callout"] for p in tier_packets)


def test_raising_the_critical_threshold_removes_packets() -> None:
    r = run_pipeline(SourceTables.from_directory(with_audience=True), PolicySettings(cannibalization_critical_threshold=99.0))
    assert not [p for p in r.packets if p.get("audience_tier")]


def test_blocked_audience_files_block_the_run(demo) -> None:
    from pipeline import ValidationBlocked
    t = SourceTables.from_directory()
    t.audience = {k: v.copy() for k, v in demo.items()}
    t.audience["AUDIENCE_TIER_PERFORMANCE"]["email"] = "x"
    with pytest.raises(ValidationBlocked):
        run_pipeline(t)


def test_tier_decisions_flow_through_the_sign_off_store() -> None:
    from job_runner import JobRunner
    from run_store import LocalRunStore
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("acme")
    cfg = store.latest_workspace_config(ws)
    runner = JobRunner(store)
    rid = runner.submit(ws, SourceTables.from_directory(with_audience=True), cfg[0], cfg[1], "with audience")
    assert runner.wait(ws, rid, timeout=300) == "succeeded"
    items = [i for i in store.list_inbox(ws, rid) if i["packet"].get("audience_tier")]
    assert items and len({i["packet"]["campaign_id"] for i in items}) == len(items)
    with pytest.raises(Exception):
        store.transition_inbox(ws, items[0]["id"], "approved", "me")  # nothing is approved without a signature
    sign_for_test(store, ws, items[0]["id"])  # signing is what moves the item to approved
    assert store.get_inbox_item(ws, items[0]["id"])["status"] == "approved"
    runner.shutdown()
    rebuilt = SourceTables.from_store(lambda n: store.load_table(ws, rid, n))
    assert rebuilt.audience and set(rebuilt.audience) == set(at.AUDIENCE_TABLES)
