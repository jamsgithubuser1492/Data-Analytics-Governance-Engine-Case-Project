"""Benchmark registry tests: schema, provenance, comparability, tamper detection, scale factor, margin, seasonality."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from benchmark_registry import COMPARABILITY, Registry, RegistryError  # noqa: E402
from benchmark_sync import CLAIMS, extract_quote, norm, numbers_in, registry_version  # noqa: E402
from benchmark_verify import expected_tier_a, verify_offline  # noqa: E402
from config import HEADLINE_STRICT, PolicySettings, SettingsError  # noqa: E402
from economics import breakeven_iroas, profit_per_dollar, resolve_economics  # noqa: E402
from pipeline import SourceTables, ValidationBlocked, benchmark_version_for, run_key, run_pipeline  # noqa: E402
from validation import validate_inputs  # noqa: E402

BENCH = ROOT / "benchmarks"


@pytest.fixture(scope="module")
def reg() -> Registry:
    return Registry.load(BENCH, today=date(2026, 10, 4))


@pytest.fixture()
def bench_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "benchmarks"
    shutil.copytree(BENCH, dest)
    return dest


# ------------------------------------------------------------ pinned facts from the primary files
def test_pinned_primary_values(reg) -> None:
    v = reg.values.set_index("value_id")
    assert v.loc["PEP_US_POP_2025", "value"] == 341_784_857
    assert v.loc["CENSUS_ECOM_PCT_LATEST", "value"] == 17.1 and v.loc["CENSUS_ECOM_SALES_LATEST", "value"] == pytest.approx(340_244e6)
    ad = reg.values[(reg.values["metric_id"] == "gross_margin_aggregate") & (reg.values["entity"] == "Advertising")].iloc[0]
    assert ad["value"] == pytest.approx(0.362429, abs=1e-6) and ad["n"] == 52 and ad["as_of"] == "2026-01-05"
    assert reg.gross_margin("Retail (Special Lines)")["value"] == pytest.approx(0.353039, abs=1e-6)
    assert v.loc["HAUS_TEST_DAYS", "value"] == 18.6 and v.loc["HAUS_META_LIFT", "value"] == 19.0 and v.loc["LITTLEDATA_CVR_FASHION", "value"] == 1.3
    assert v.loc["LITTLEDATA_N_STORES", "value"] == 421 and v.loc["LEWIS_ROI_CI", "low"] == 100.0


def test_every_record_has_provenance(reg) -> None:
    assert len(reg.values) >= 200
    for _, r in reg.values.iterrows():
        assert r["definition"] and r["verification"] and r["confidence"] in ("high", "medium", "low")
        rec = reg.record(r)
        assert rec["source_url"].startswith("http") and rec["source_title"]
        if r["tier"] == "B":
            assert isinstance(r["quote"], str) and len(r["quote"]) >= 20


def test_tier_b_quotes_contain_their_numbers(reg) -> None:
    spec = {c.claim_id: c for c in CLAIMS}
    for _, r in reg.values[reg.values["tier"] == "B"].iterrows():
        nums = numbers_in(r["quote"])
        for want in spec[r["value_id"]].check_numbers:
            assert any(abs(want - g) < 1e-9 for g in nums), (r["value_id"], want)


def test_unverified_claims_are_not_admitted(reg) -> None:
    ids = set(reg.values["value_id"])
    assert not any("PUBLISHED" in i or "NETFLIX" in i or "CPM" in i for i in ids)
    text = " ".join(reg.values["quote"].dropna()).lower() + " ".join(reg.values["definition"]).lower()
    assert "overestimat" not in text and "july 28" not in text and "2,800" not in text
    assert len(reg.excluded) >= 8 and reg.excluded["reason_excluded"].str.len().min() > 30


# --------------------------------------------------------------------- verification
def test_offline_verification_passes() -> None:
    res = verify_offline(BENCH)
    assert res and all(c.status == "PASS" for c in res), [(c.name, c.detail) for c in res if c.status != "PASS"]
    assert len(res) >= 20


def test_tampered_value_is_detected(bench_copy) -> None:
    v = pd.read_csv(bench_copy / "values.csv")
    v.loc[v["value_id"] == "CENSUS_ECOM_PCT_LATEST", "value"] = 19.9
    v.to_csv(bench_copy / "values.csv", index=False)
    bad = [c for c in verify_offline(bench_copy) if c.status == "FAIL"]
    assert any(c.name == "tier_a_rederived_from_snapshots" for c in bad)


def test_tampered_snapshot_is_detected(bench_copy) -> None:
    f = bench_copy / "snapshots" / "fred_ECOMPCTSA.csv"
    f.write_text(f.read_text() + "2026-07-01,99.9\n")
    assert any(c.name == "snapshot_hash_fred_ECOMPCTSA" and c.status == "FAIL" for c in verify_offline(bench_copy))


def test_hand_added_and_edited_tier_b_records_are_detected(bench_copy) -> None:
    v = pd.read_csv(bench_copy / "values.csv")
    row = v[v["value_id"] == "HAUS_META_LIFT"].iloc[0].copy()
    v.loc[v["value_id"] == "HAUS_META_LIFT", "value"] = 40.0  # a number the quote does not support
    extra = row.copy()
    extra["value_id"] = "MY_OWN_CLAIM"
    v = pd.concat([v, pd.DataFrame([extra])], ignore_index=True)
    v.to_csv(bench_copy / "values.csv", index=False)
    out = {c.name: c for c in verify_offline(bench_copy)}
    assert out["tier_b_claims_match_specs"].status == "FAIL" and "no claim spec" in out["tier_b_claims_match_specs"].detail


def test_registry_rejects_bad_files(bench_copy) -> None:
    v = pd.read_csv(bench_copy / "values.csv")
    broken = v.copy()
    broken.loc[broken["value_id"] == "HAUS_META_LIFT", "quote"] = ""
    broken.to_csv(bench_copy / "values.csv", index=False)
    with pytest.raises(RegistryError, match="verbatim quote"):
        Registry.load(bench_copy)
    for mutate, msg in ((lambda d: d.drop(columns=["definition"]), "missing columns"),
                        (lambda d: d.assign(source_id="NOPE"), "unknown sources"),
                        (lambda d: pd.concat([d, d.head(1)]), "Duplicate"),
                        (lambda d: d.assign(confidence="great"), "confidence")):
        mutate(v).to_csv(bench_copy / "values.csv", index=False)
        with pytest.raises(RegistryError, match=msg):
            Registry.load(bench_copy)
    shutil.rmtree(bench_copy / "snapshots")
    (bench_copy / "values.csv").unlink()
    with pytest.raises(RegistryError, match="missing"):
        Registry.load(bench_copy)


def test_extract_quote_is_verbatim_and_bounded() -> None:
    text = norm("Intro sentence here. The average advertiser in this study spends $14 million annually on Meta. Another sentence follows.")
    q = extract_quote(text, "$14 million annually")
    assert q == "The average advertiser in this study spends $14 million annually on Meta." and q in text
    assert extract_quote(text, "$14 million annually", start_at_anchor=True) == "$14 million annually on Meta."
    assert extract_quote(text, "not present") is None
    long = extract_quote("A " * 400 + "ANCHOR " + "B " * 400, "ANCHOR", 100)
    assert "ANCHOR" in long and len(long) <= 110 and long.startswith("...") and long.endswith("...")


# ---------------------------------------------------------------- comparability
def test_not_comparable_means_not_offered(reg) -> None:
    cvr = reg.find("ad_click_cvr")
    assert not cvr.found and cvr.fit == "none" and "not comparable" in cvr.reasons[0].lower()
    assert not reg.find("channel_roas").found and "excluded_claims" in reg.find("channel_roas").reasons[0]
    assert not reg.find("incrementality_factor").found and not reg.find("does_not_exist").found


def test_comparable_records_carry_caveats_and_vertical_filter(reg) -> None:
    aov = reg.find("order_value", vertical="fashion_apparel")
    assert aov.fit == "proxy" and {r["value"] for r in aov.records} == {98.0, 110.0}
    assert all(r["caveat"] and r["definition_class"] == "site_aov" for r in aov.records)
    assert {r["value"] for r in reg.find("order_value", vertical="beauty_skincare").records} == {66.0, 110.0}
    assert reg.find("seasonal_index").fit == "exact" and len(reg.find("seasonal_index").records) == 12
    assert reg.find("kpi_lift_pct", channel="Meta Ads").records and not reg.find("kpi_lift_pct", channel="TikTok Ads").records
    assert reg.find("order_value", vertical="beauty_skincare", min_confidence="medium").records[0]["value"] == 110.0  # low confidence filtered
    assert all(m in {"site_aov_median_usd", "gross_margin_aggregate", "retail_seasonal_index", "test_duration_days", "meta_lift_primary_kpi_pct",
                     "roi_ci_width_pp_median", "ecommerce_share_of_retail_pct"} for rules in COMPARABILITY.values() for m, *_ in rules)


def test_staleness_and_expiry() -> None:
    old = Registry.load(BENCH, today=date(2028, 6, 1))  # about 20 months after retrieval
    recs = old.records("test_duration_days")
    assert recs[0]["stale"] and not recs[0]["expired"] and old.find("test_duration_days").stale
    gone = Registry.load(BENCH, today=date(2031, 1, 1))
    assert gone.records("test_duration_days")[0]["expired"] and not gone.find("test_duration_days").found


# --------------------------------------------------------------------- margin
@pytest.mark.parametrize("m,be", [(0.5, 2.0), (1.0, 1.0), (0.25, 4.0)])
def test_breakeven_math(m, be) -> None:
    assert breakeven_iroas(m) == be and profit_per_dollar(be, m) == pytest.approx(0.0) and profit_per_dollar(2 * be, m) == pytest.approx(1.0)
    assert breakeven_iroas(None) is None and profit_per_dollar(3.0, None) is None and breakeven_iroas(0) is None


def test_margin_resolution_is_never_silent(reg) -> None:
    assert resolve_economics(PolicySettings())["margin"] is None
    user = resolve_economics(PolicySettings(gross_margin=0.4, margin_industry="Apparel"), reg)
    assert user["source"] == "user" and user["breakeven_iroas"] == pytest.approx(2.5)  # a declared margin always wins
    bench = resolve_economics(PolicySettings(margin_industry="Apparel"), reg)
    assert bench["source"] == "benchmark" and bench["margin"] == pytest.approx(0.5688, abs=1e-4) and "upper" not in bench["note"].lower() or "lower" in bench["note"].lower()
    assert bench["benchmark_set_version"] == reg.version and bench["record_id"].startswith("DAM_gross_margin_aggregate")
    with pytest.raises(Exception):
        resolve_economics(PolicySettings(margin_industry="Apparel"), None)
    with pytest.raises(Exception):
        reg.gross_margin("Online Pet Rocks")
    with pytest.raises(SettingsError):
        PolicySettings(gross_margin=0.0)
    with pytest.raises(SettingsError):
        PolicySettings(gross_margin=1.5)


# ------------------------------------------------------------------ scale factor
def test_population_share_math_and_errors(reg) -> None:
    s = reg.population_share(["06", "48"])
    assert s["share"] == pytest.approx((39_355_309 + 31_709_821) / 341_784_857) and s["population"] == 39_355_309 + 31_709_821
    assert reg.population_share(["06037", "06"])["errors"]  # county inside a listed state
    assert reg.population_share(["06", "06"])["errors"] and reg.population_share(["99"])["errors"] and reg.population_share([])["errors"]
    assert reg.population_share(["0603"])["errors"] and reg.population_share(["6"])["share"] is not None  # '6' is read as state 06
    a, b = reg.population_share(["06037"]), reg.population_share(["06"])
    assert 0 < a["share"] < b["share"]
    assert reg.population_share(["06", "53", "41"])["share"] == pytest.approx((39_355_309 + 8_001_020 + 4_273_586) / 341_784_857)


def test_scale_factor_validation_rules(reg) -> None:
    t = SourceTables.from_directory()
    args = (t.platform, t.mta, t.holdout, t.benchmarks)
    mismatch = validate_inputs(*args, PolicySettings(), {"test_geo_fips": ["06", "48", "12"]}, reg)  # about 27.7% vs declared 40%
    assert mismatch.ok and any(i.rule == "scale_factor_mismatch" for i in mismatch.warnings) and mismatch.scale_factor["census_share"] == pytest.approx(0.27657, abs=1e-4)
    # fraction matched to the census share: consistent
    s = reg.population_share(["06", "48", "12"])["share"]
    ok = validate_inputs(*args, PolicySettings(geo_sample_fraction=round(s, 2)), {"test_geo_fips": ["06", "48", "12"]}, reg)
    assert any(i.rule == "scale_factor_consistent" for i in ok.issues) and not any(i.rule == "scale_factor_mismatch" for i in ok.issues)
    # the gap is measured against the declared fraction (projected dollars are divided by it): 14.5% passes, 16% fails
    base = reg.population_share(["06", "48", "12"])["share"]
    flag = lambda mult: any(i.rule == "scale_factor_mismatch" for i in validate_inputs(*args, PolicySettings(geo_sample_fraction=base * mult), {"test_geo_fips": ["06", "48", "12"]}, reg).issues)  # noqa: E731
    assert not flag(1.17) and flag(1.19) and not flag(0.88) and flag(0.85)
    bad = validate_inputs(*args, PolicySettings(), {"test_geo_fips": ["99"]}, reg)
    assert not bad.ok and any(i.rule == "geo_fips_invalid" for i in bad.blockers)
    assert validate_inputs(*args, PolicySettings(), {}, reg).scale_factor == {}  # demo has no declared geos: nothing to flag
    nore = validate_inputs(*args, PolicySettings(), {"test_geo_fips": ["06"]}, None)
    assert any(i.rule == "scale_factor_unchecked" for i in nore.warnings)


# ---------------------------------------------------------------- seasonality
def test_expected_seasonal_drift(reg) -> None:
    d = reg.expected_seasonal_drift(date(2026, 1, 1), date(2026, 1, 30), date(2026, 1, 31), date(2026, 3, 31))
    assert d["expected_drift_pct"] == pytest.approx(4.94, abs=0.05) and d["test_index"] > d["pre_index"]
    same = reg.expected_seasonal_drift(date(2026, 5, 1), date(2026, 5, 31), date(2026, 5, 1), date(2026, 5, 31))
    assert same["expected_drift_pct"] == pytest.approx(0.0)
    assert reg.seasonal_index(12)["mean"] > 1.0 > reg.seasonal_index(1)["mean"]  # December peaks, January trough


# ------------------------------------------------------------ pipeline integration
@pytest.fixture(scope="module")
def tables() -> SourceTables:
    return SourceTables.from_directory()


def test_demo_benchmark_table_is_flagged_illustrative_and_check4_is_na(tables) -> None:
    r = run_pipeline(tables)
    assert r.audit["benchmark_context"]["illustrative_benchmark_table"] is True
    assert all(c["checks"][3]["status"] == "NA" for c in r.audit["campaigns"])
    assert all(c["trust_score"] == round(sum({"PASS": 1, "WARN": .5, "FAIL": 0}[k["status"]] for k in c["checks"] if k["status"] != "NA") / 7 * 100, 1) for c in r.audit["campaigns"])
    edited = tables.benchmarks.copy()
    edited.loc[0, "expected_roas_max"] = 9.0  # a user's own table
    r2 = run_pipeline(SourceTables(tables.platform, tables.mta, tables.holdout, edited))
    assert r2.audit["benchmark_context"]["illustrative_benchmark_table"] is False and r2.audit["campaigns"][0]["checks"][3]["status"] in ("PASS", "WARN")


def test_margin_flows_to_audit_facts_and_agents(tables, reg) -> None:
    from agent_engine import build_facts, evaluate_agents
    s = PolicySettings(gross_margin=0.5)
    r = run_pipeline(tables, s)
    assert r.audit["economics"]["breakeven_iroas"] == 2.0 and r.audit["benchmark_context"]["benchmark_set_version"] is None
    facts = build_facts(r.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], r.audit, False)
    row = facts[facts["campaign_id"] == "GOOGLE_ADS_CMP_01"].iloc[0]
    assert row["breakeven_iroas"] == 2.0 and row["profit_per_dollar"] == pytest.approx(row["iroas"] * 0.5 - 1.0)
    agent = {"id": "PROFIT_LEAK", "name": "Profit leak", "persona": "Marketing Agency Director", "severity": "WARNING", "action": "REVIEW_MEASUREMENT", "priority": 5,
             "trigger": {"all": [{"metric": "profit_per_dollar", "op": "<", "value": 0}], "any": []},
             "value_add": [{"label": "Profit per dollar", "expression": "profit_per_dollar", "format": "usd"}], "title": "Below breakeven {campaign_id}", "callout": "{channel} loses {m1} per ad dollar."}
    from agent_schema import validate_definition
    norm_def, errs = validate_definition(agent)
    assert not errs
    fired = {p["campaign_id"] for p in evaluate_agents([{**norm_def, "version": 1}], facts)}
    assert fired == set(facts[facts["profit_per_dollar"] < 0]["campaign_id"]) and "NETFLIX_ADS_CMP_01" in fired and "GOOGLE_ADS_CMP_01" not in fired
    none = build_facts(run_pipeline(tables).tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], run_pipeline(tables).audit, False)
    assert none["margin"].isna().all() and evaluate_agents([{**norm_def, "version": 1}], none) == []  # no margin declared: never guess


def test_industry_margin_and_seasonality_stamp_benchmark_version(tables, reg) -> None:
    r = run_pipeline(tables, PolicySettings(margin_industry="Apparel", seasonality_benchmark=True))
    assert r.audit["economics"]["source"] == "benchmark" and r.audit["benchmark_context"]["benchmark_set_version"] == reg.version
    assert r.audit["benchmark_context"]["seasonal_expectation"]["expected_drift_pct"] == pytest.approx(4.94, abs=0.05)
    assert "unexplained" in r.audit["campaigns"][0]["checks"][4]["detail"]
    plain = run_pipeline(tables)
    assert plain.audit["campaigns"][0]["checks"][4]["detail"].startswith("Unexposed control geo moved")


def test_run_key_includes_registry_version_only_when_used(tables, reg) -> None:
    plain, margin = PolicySettings(), PolicySettings(margin_industry="Apparel")
    assert benchmark_version_for(plain, {}) == "" and benchmark_version_for(margin, {}) == reg.version
    assert benchmark_version_for(plain, {"test_geo_fips": ["06"]}) == reg.version
    assert run_key(tables, margin, {}, "", "", "v1") != run_key(tables, margin, {}, "", "", "v2")
    assert run_key(tables, plain, {}, "", "", "") == run_key(tables, plain, {}, "", "", "")


def test_pipeline_blocks_invalid_geo_codes(tables) -> None:
    with pytest.raises(ValidationBlocked):
        run_pipeline(tables, PolicySettings(), {"test_geo_fips": ["99"]})


def test_registry_version_is_content_only(bench_copy) -> None:
    v1 = registry_version(bench_copy)
    s = pd.read_csv(bench_copy / "sources.csv")
    s["retrieved_at"] = "2030-01-01T00:00:00+00:00"
    s.to_csv(bench_copy / "sources.csv", index=False)
    assert registry_version(bench_copy) == v1  # retrieval timestamps do not change the version
    v = pd.read_csv(bench_copy / "values.csv")
    v.loc[0, "value"] = 0.123
    v.to_csv(bench_copy / "values.csv", index=False)
    assert registry_version(bench_copy) != v1


def test_expected_tier_a_covers_all_derivable_records(reg) -> None:
    exp = expected_tier_a(BENCH)
    tier_a = set(reg.values[reg.values["tier"] == "A"]["value_id"])
    assert set(exp) | {"CENSUS_ECOM_PCT_LATEST", "CENSUS_ECOM_SALES_LATEST"} >= tier_a - {"CENSUS_ECOM_PCT_LATEST", "CENSUS_ECOM_SALES_LATEST"}
