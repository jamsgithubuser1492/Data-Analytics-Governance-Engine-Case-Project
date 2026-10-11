"""The calibration pack: priors, exclusions, widening, privacy and reproducibility."""
from __future__ import annotations

import copy
import math
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python")]

import calibration_pack as cp  # noqa: E402
import mmm_priors as mp  # noqa: E402
from config import PolicySettings  # noqa: E402
from pipeline import SourceTables, run_pipeline  # noqa: E402


@pytest.fixture(scope="module")
def run():
    return run_pipeline(SourceTables.from_directory(with_audience=True))


@pytest.fixture(scope="module")
def pack(run):
    return cp.build_pack(run.tables, run.audit, run.settings, run_id="r1")


def test_a_valid_pack_passes_its_own_checks(pack) -> None:
    assert cp.validate_pack(pack) == []
    assert pack["schema"] == cp.SCHEMA and pack["lineage"]["counting_basis"] == "strict_lift"
    assert pack["summary"]["records"] == len(pack["experiments"]) + len(pack["channels"]) + len(pack["audience_tiers"])


def test_every_record_is_listed_and_excluded_ones_say_why(pack) -> None:
    rows = pack["experiments"] + pack["channels"] + pack["audience_tiers"]
    assert all(r["included"] or r["exclusion_reason"] for r in rows)
    unjudged = [r for r in pack["audience_tiers"] if "not_enough_data" in r["quality_flags"]]
    assert unjudged and all(not r["included"] for r in unjudged)  # a tier with too little data never informs a model


def test_prior_reproduces_the_estimate_and_standard_error_when_nothing_is_widened(run) -> None:
    pol = cp.PriorPolicy(directional_widening=1.0, match_failed_widening=1.0, age_half_life_days=1e12, min_relative_se=0.0001)
    pack = cp.build_pack(run.tables, run.audit, run.settings, policy=pol)
    e = next(r for r in pack["experiments"] if r["included"] and r["evidence_level"] == "VERIFIED")
    se = mp.se_from_interval(e["lower95"], e["upper95"])
    mean = math.exp(e["prior"]["mu"] + e["prior"]["sigma"] ** 2 / 2)
    var = (math.exp(e["prior"]["sigma"] ** 2) - 1) * math.exp(2 * e["prior"]["mu"] + e["prior"]["sigma"] ** 2)
    assert mean == pytest.approx(e["estimate"], rel=1e-4) and math.sqrt(var) == pytest.approx(se, rel=1e-3)


def test_weaker_evidence_and_older_tests_widen_the_prior(run) -> None:
    base = cp.build_pack(run.tables, run.audit, run.settings, as_of=date(2026, 3, 1))
    later = cp.build_pack(run.tables, run.audit, run.settings, as_of=date(2027, 3, 1))
    pair = [(a, b) for a, b in zip(base["experiments"], later["experiments"]) if a["included"]]
    assert pair and all(b["prior"]["sd"] > a["prior"]["sd"] for a, b in pair)
    ch = {r["channel"]: r for r in base["channels"]}
    d = next(r for r in base["experiments"] if r["included"] and r["evidence_level"] == "DIRECTIONAL")
    v = next(r for r in base["experiments"] if r["included"] and r["evidence_level"] == "VERIFIED")
    assert d["widening"] >= 2.0 and v["widening"] < 1.5
    assert ch["Netflix Ads"]["evidence_level"] == "DIRECTIONAL"


def test_a_failed_control_match_widens_tier_priors(pack) -> None:
    tik = [r for r in pack["audience_tiers"] if r["channel"] == "TikTok Ads" and r["included"]]
    goo = [r for r in pack["audience_tiers"] if r["channel"] == "Google Ads" and r["included"]]
    assert tik and all("control_match_review_required" in r["quality_flags"] and r["widening"] >= 1.5 for r in tik)
    assert all("control_match_review_required" not in r["quality_flags"] for r in goo)
    assert all("overlaps_channel_level_evidence" in r["quality_flags"] for r in pack["audience_tiers"])


def test_unreliable_evidence_and_floors() -> None:
    pol = cp.PriorPolicy()
    assert not cp._prior(1.5, 1.0, 2.0, "NOT_DECISION_GRADE", True, 0, pol)["included"]
    assert not cp._prior(1.5, None, None, "VERIFIED", True, 0, pol)["included"]
    assert not cp._prior(-0.1, -0.5, 0.2, "VERIFIED", True, 0, pol)["included"]
    tight = cp._prior(2.0, 1.999, 2.001, "VERIFIED", True, 0, pol)
    assert tight["prior"]["sd"] == pytest.approx(0.05 * 2.0)  # never more certain than a share of its own estimate


def test_pack_is_deterministic_and_tamper_evident(run, pack) -> None:
    again = cp.build_pack(run.tables, run.audit, run.settings, run_id="r1")
    assert again["pack_hash"] == pack["pack_hash"]
    forged = copy.deepcopy(pack)
    forged["channels"][0]["estimate"] = 99.0
    assert any("hash" in e for e in cp.validate_pack(forged))


def test_included_records_must_be_strict_lift_and_reliable(pack) -> None:
    bad = copy.deepcopy(pack)
    r = next(x for x in bad["experiments"] if x["included"])
    r["basis"] = "reported_by_spec"
    bad["pack_hash"] = ""
    errs = cp.validate_pack(bad)
    assert any("strict lift" in e for e in errs)


def test_no_person_level_fields_and_flat_ledger_matches(pack) -> None:
    df = cp.to_frame(pack)
    assert len(df) == pack["summary"]["records"] and int(df["included"].sum()) == pack["summary"]["included"]
    assert not [c for c in df.columns if any(t in c.lower().split("_") for t in cp.FORBIDDEN_TOKENS)]
    assert df["run_id"].eq("r1").all()


def test_without_audience_data_the_pack_still_builds() -> None:
    r = run_pipeline(SourceTables.from_directory())
    p = cp.build_pack(r.tables, r.audit, r.settings)
    assert p["audience_tiers"] == [] and cp.validate_pack(p) == []


def test_the_architecture_guide_quotes_the_computed_example(pack) -> None:
    doc = (ROOT / "docs" / "MMM_INTEGRATION_ARCHITECTURE.md").read_text(encoding="utf-8")
    for c in pack["channels"]:
        assert f"| {c['channel']} | {c['estimate']:.3f} |" in doc, c["channel"]
        assert f"{c['prior']['sd']:.3f}" in doc
    for token in ("Built", "Designed", "Future", "design assumptions"):
        assert token in doc
    import re
    assert not re.search("[\U0001F000-\U0001FFFF☀-➿]", doc)
