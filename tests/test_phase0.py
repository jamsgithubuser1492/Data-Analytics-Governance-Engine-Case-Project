"""Phase 0 trust foundation tests: settings, validation, NULL semantics, gating, strict lift."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from agent_orchestrator import AgentOrchestrator  # noqa: E402
from config import HEADLINE_STRICT, PolicySettings, SettingsError  # noqa: E402
from database_manager import DatabaseManager, PipelineIntegrityError  # noqa: E402
from governance_checker import run_audit  # noqa: E402
from strict_lift import divergence_warning, headline_iroas  # noqa: E402
from validation import validate_inputs  # noqa: E402

DATA = ROOT / "data"


def load():
    return (pd.read_csv(DATA / "RAW_PLATFORM_DATA.csv"), pd.read_csv(DATA / "RAW_MTA_OUTPUT.csv"),
            pd.read_csv(DATA / "RAW_HOLDOUT_DATA.csv"), pd.read_csv(DATA / "BUSINESS_BENCHMARKS.csv"))


def rules(rep, severity=None):
    return {i.rule for i in rep.issues if severity is None or i.severity == severity}


@pytest.fixture()
def data_copy(tmp_path: Path) -> Path:
    for f in DATA.glob("*.csv"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


# ------------------------------------------------------------------ settings
def test_defaults_match_spec() -> None:
    s = PolicySettings()
    assert (s.geo_sample_fraction, s.inflation_moderate, s.inflation_critical) == (0.40, 1.5, 3.0)


@pytest.mark.parametrize("kw", [dict(geo_sample_fraction=0), dict(geo_sample_fraction=1.5),
                                dict(inflation_moderate=3.0, inflation_critical=3.0),
                                dict(trust_directional_min=80), dict(headline_metric="vibes")])
def test_invalid_settings_rejected(kw) -> None:
    with pytest.raises(SettingsError):
        PolicySettings(**kw)


def test_fingerprint_changes_with_settings() -> None:
    assert PolicySettings().fingerprint() != PolicySettings(geo_sample_fraction=0.5).fingerprint()


def test_sample_fraction_flows_into_sql() -> None:
    a = DatabaseManager().build().view("ANALYTICS_MEASUREMENT_RECONCILIATION")
    b = DatabaseManager(settings=PolicySettings(geo_sample_fraction=0.8)).build().view("ANALYTICS_MEASUREMENT_RECONCILIATION")
    ratio = (a["total_holdout_revenue"].sum() / b["total_holdout_revenue"].sum())
    assert ratio == pytest.approx(2.0)


def test_thresholds_flow_into_governance_status() -> None:
    db = DatabaseManager(settings=PolicySettings(inflation_moderate=1.05, inflation_critical=1.2)).build()
    statuses = db.view("GOVERNANCE_CAMPAIGN_ALERTS")["governance_status"]
    assert statuses.str.startswith("CRITICAL").any()


# ---------------------------------------------------------------- validation
def test_demo_data_has_no_blockers() -> None:
    rep = validate_inputs(*load())
    assert rep.ok, [i.message for i in rep.blockers]
    assert rep.coverage == {"mta": 1.0, "holdout": 1.0}


def test_missing_column_blocks() -> None:
    p, m, h, b = load()
    assert "missing_column" in rules(validate_inputs(p.drop(columns=["spend"]), m, h, b), "BLOCKER")


def test_negative_spend_blocks() -> None:
    p, m, h, b = load()
    p.loc[0, "spend"] = -5
    assert "negative_value" in rules(validate_inputs(p, m, h, b), "BLOCKER")


def test_unparseable_date_blocks() -> None:
    p, m, h, b = load()
    p.loc[0, "date"] = "not a date"
    assert "unparseable_date" in rules(validate_inputs(p, m, h, b), "BLOCKER")


def test_duplicate_key_blocks() -> None:
    p, m, h, b = load()
    assert "duplicate_key" in rules(validate_inputs(pd.concat([p, p.head(3)]), m, h, b), "BLOCKER")


def test_mixed_currency_blocks() -> None:
    p, m, h, b = load()
    p["currency"] = "USD"
    p.loc[0, "currency"] = "EUR"
    assert "mixed_currency" in rules(validate_inputs(p, m, h, b, declarations={"currency": "USD"}), "BLOCKER")


def test_currency_mismatch_with_declaration_blocks() -> None:
    p, m, h, b = load()
    p["currency"] = "EUR"
    assert "currency_mismatch" in rules(validate_inputs(p, m, h, b, declarations={"currency": "USD"}), "BLOCKER")


def test_pii_column_blocks() -> None:
    p, m, h, b = load()
    p["customer_email"] = "x@y.com"
    assert "pii_column" in rules(validate_inputs(p, m, h, b), "BLOCKER")


def test_cents_instead_of_dollars_warns() -> None:
    p, m, h, b = load()
    p.loc[p["campaign_id"] == "META_ADS_CMP_01", "spend"] *= 100
    assert "spend_unit_suspect" in rules(validate_inputs(p, m, h, b), "WARNING")


def test_missing_holdout_campaign_is_coverage_warning() -> None:
    p, m, h, b = load()
    rep = validate_inputs(p, m, h[h["campaign_id"] != "META_ADS_CMP_01"], b)
    assert rep.ok and "holdout_coverage_gap" in rules(rep, "WARNING") and rep.coverage["holdout"] == 0.875


def test_short_pre_period_blocks() -> None:
    p, m, h, b = load()
    h = h.copy()
    h.loc[(h["date"] < "2026-01-31") & (h["date"] > "2026-01-10"), "treatment_flag"] = 1
    assert "pre_period_short" in rules(validate_inputs(p, m, h, b), "BLOCKER")


def test_gap_and_low_volume_warn() -> None:
    p, m, h, b = load()
    rep = validate_inputs(p[p["date"] != "2026-02-10"].copy(), m, h, b)
    assert "date_gaps" in rules(rep, "WARNING")
    assert "low_volume" in rules(validate_inputs(*load()), "WARNING")  # Netflix is tiny


# ------------------------------------------------- NULL not zero + integrity
def test_missing_holdout_is_null_not_zero(data_copy: Path) -> None:
    h = pd.read_csv(data_copy / "RAW_HOLDOUT_DATA.csv")
    h[h["campaign_id"] != "META_ADS_CMP_01"].to_csv(data_copy / "RAW_HOLDOUT_DATA.csv", index=False)
    db = DatabaseManager(data_dir=data_copy).build()
    r = db.view("ANALYTICS_MEASUREMENT_RECONCILIATION").set_index("campaign_id").loc["META_ADS_CMP_01"]
    assert pd.isna(r["total_holdout_revenue"]) and pd.isna(r["incremental_roas"]) and r["has_holdout_coverage"] == 0
    alerts = db.view("GOVERNANCE_CAMPAIGN_ALERTS").set_index("campaign_id")
    assert alerts.loc["META_ADS_CMP_01", "governance_status"].startswith("NO_HOLDOUT")
    meta = db.view("GOVERNANCE_AUDIT_SUMMARY").set_index("channel").loc["Meta Ads"]
    assert meta["holdout_covered_spend"] < meta["total_spend"]  # iROAS uses covered spend only
    assert meta["incremental_roas"] == pytest.approx(
        db.view("ANALYTICS_MEASUREMENT_RECONCILIATION").set_index("campaign_id").loc["META_ADS_CMP_02", "incremental_roas"], abs=0.01)


def test_audit_handles_uncovered_campaign(data_copy: Path) -> None:
    h = pd.read_csv(data_copy / "RAW_HOLDOUT_DATA.csv")
    h[h["campaign_id"] != "META_ADS_CMP_01"].to_csv(data_copy / "RAW_HOLDOUT_DATA.csv", index=False)
    rep = run_audit(DatabaseManager(data_dir=data_copy).build())
    c = next(c for c in rep["campaigns"] if c["campaign_id"] == "META_ADS_CMP_01")
    assert c["tier"] == "NOT_DECISION_GRADE" and c["recommendation"].startswith("HOLD") and c["checks"] == []


def test_integrity_assertion_catches_fanout(data_copy: Path) -> None:
    m = pd.read_csv(data_copy / "RAW_MTA_OUTPUT.csv")
    m.loc[0, "channel"] = "Meta Ads"
    # corrupt platform: a negative spend row must fail the integrity check
    p = pd.read_csv(data_copy / "RAW_PLATFORM_DATA.csv")
    p.loc[0, "spend"] = -10
    p.to_csv(data_copy / "RAW_PLATFORM_DATA.csv", index=False)
    with pytest.raises(PipelineIntegrityError):
        DatabaseManager(data_dir=data_copy).build()


def test_demo_passes_integrity() -> None:
    assert DatabaseManager().build().integrity_failures() == []


# --------------------------------------------------------- strict lift, tiers
def test_strict_lift_is_below_spec_and_diverges() -> None:
    rep = run_audit(DatabaseManager().build())
    for c in rep["campaigns"]:
        assert c["strict_iroas"] < c["spec_iroas"]
        assert c["divergence_warning"] is True
    g = next(c for c in rep["campaigns"] if c["campaign_id"] == "GOOGLE_ADS_CMP_01")
    assert g["strict_iroas"] == pytest.approx(1.0, abs=0.05)  # about breakeven under strict lift
    assert g["strict_iroas_lower"] < g["strict_iroas"] < g["strict_iroas_upper"]


def test_headline_follows_setting() -> None:
    assert headline_iroas(5.0, 1.0, PolicySettings()) == 5.0
    assert headline_iroas(5.0, 1.0, PolicySettings(headline_metric=HEADLINE_STRICT)) == 1.0
    rep = run_audit(DatabaseManager(settings=PolicySettings(headline_metric=HEADLINE_STRICT)).build())
    assert all(c["headline_iroas"] == c["strict_iroas"] for c in rep["campaigns"])
    assert not any(c["recommendation"].startswith("SCALE") for c in rep["campaigns"])  # strict never scales here


def test_divergence_warning_logic() -> None:
    s = PolicySettings()
    assert divergence_warning(3.0, 1.0, s) and not divergence_warning(1.2, 1.0, s)
    assert divergence_warning(1.0, 0.0, s) and not divergence_warning(float("nan"), 1.0, s)


def test_tier_rules() -> None:
    s = PolicySettings()
    assert s.trust_tier(90, True) == "VERIFIED" and s.trust_tier(60, True) == "DIRECTIONAL"
    assert s.trust_tier(40, True) == "NOT_DECISION_GRADE" and s.trust_tier(95, False) == "NOT_DECISION_GRADE"


def test_diverging_pre_trends_downgrade_tier(data_copy: Path) -> None:
    h = pd.read_csv(data_copy / "RAW_HOLDOUT_DATA.csv")
    mask = (h["campaign_id"] == "GOOGLE_ADS_CMP_01") & (h["group_type"] == "treatment") & (h["date"] < "2026-01-31")
    day = pd.to_datetime(h.loc[mask, "date"]).dt.day
    h.loc[mask, "conversions"] = (h.loc[mask, "conversions"] * (1 + day * 0.15)).round().astype(int)
    h.to_csv(data_copy / "RAW_HOLDOUT_DATA.csv", index=False)
    c = next(c for c in run_audit(DatabaseManager(data_dir=data_copy).build())["campaigns"] if c["campaign_id"] == "GOOGLE_ADS_CMP_01")
    assert c["checks"][0]["status"] == "FAIL" and c["tier"] == "NOT_DECISION_GRADE" and c["recommendation"].startswith("HOLD")


def test_money_agents_gated_by_tier() -> None:
    recon = pd.DataFrame([dict(channel="Google Ads", campaign_id="G1", total_spend=1000.0, total_platform_conversions=100.0,
                               total_holdout_conversions=90.0, total_holdout_revenue=4000.0, reported_roas=5.0,
                               incremental_roas=4.0, inflation_ratio=1.1)])
    assert [p["agent_id"] for p in AgentOrchestrator(recon).evaluate_triggers()] == ["SCALE_OPPORTUNITY_AGENT"]
    assert AgentOrchestrator(recon, {"G1": "NOT_DECISION_GRADE"}).evaluate_triggers() == []
    assert len(AgentOrchestrator(recon, {"G1": "DIRECTIONAL"}).evaluate_triggers()) == 1
    shield = recon.assign(inflation_ratio=2.0, incremental_roas=0.5)
    ids = [p["agent_id"] for p in AgentOrchestrator(shield, {"G1": "NOT_DECISION_GRADE"}).evaluate_triggers()]
    assert ids == ["ATTRIBUTION_SHIELD_AGENT"]  # governance memos are not money actions


def test_strict_mode_agents_use_causal_numbers() -> None:
    db = DatabaseManager().build()
    recon, rep = db.view("ANALYTICS_MEASUREMENT_RECONCILIATION"), run_audit(db)
    spec_ids = {p["agent_id"] for p in AgentOrchestrator.from_audit(recon, rep).evaluate_triggers()}
    strict = AgentOrchestrator.from_audit(recon, rep, use_strict=True).evaluate_triggers()
    assert "SCALE_OPPORTUNITY_AGENT" in spec_ids
    assert not any(p["agent_id"] == "SCALE_OPPORTUNITY_AGENT" for p in strict)  # nothing scales under strict lift
    capital = [p for p in strict if p["agent_id"] == "CAPITAL_PRESERVATION_AGENT"]
    assert {p["channel"] for p in capital} >= {"Meta Ads", "TikTok Ads"}  # platform looks great, strict return below 1x
