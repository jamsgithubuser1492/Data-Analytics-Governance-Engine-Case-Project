"""Advisory council and plain-language rule settings."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

import council as cn  # noqa: E402
import dashdata as dd  # noqa: E402
import stances as st_  # noqa: E402
from agent_engine import build_facts, default_definitions, evaluate_agents  # noqa: E402
from pipeline import SourceTables, run_pipeline  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return run_pipeline(SourceTables.from_directory())


def build(result, strict: bool):
    recon = result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"]
    camp = pd.DataFrame(result.audit["campaigns"])
    cd = dd.campaign_frame(recon, camp, strict, 1.0, None)
    ch = dd.channel_frame(cd, result.tables["GOVERNANCE_AUDIT_SUMMARY"], strict, 1.0)
    return cd, ch, dd.portfolio_totals(cd, ch, strict)


@pytest.mark.parametrize("strict", [False, True])
def test_every_recommendation_uses_only_the_allowed_tentative_forms(result, strict) -> None:
    cd, ch, tot = build(result, strict)
    council = cn.convene(ch, cd, tot, 1.0, strict)
    assert len(council.readings) == 4
    for rd in council.readings:
        for v in rd.channels:
            assert v.text.startswith(cn.ALLOWED_OPENERS) or v.text.startswith("Before cutting"), v.text
            assert not v.text.split()[0] in {"Scale", "Cut", "Reduce", "Pause", "Stop", "Increase"}
        for t in rd.portfolio:
            assert t.startswith(cn.ALLOWED_OPENERS), t


def test_personas_differ_by_lean_on_the_same_facts(result) -> None:
    cd, ch, tot = build(result, False)
    council = cn.convene(ch, cd, tot, 1.0, False)
    by = {rd.persona.id: {v.channel: v.stance for v in rd.channels} for rd in council.readings}
    assert by["BUILDER"]["Google Ads"] == "Lean in" and by["STEWARD"]["Meta Ads"] in ("Lean in", "Hold")
    assert by["STEWARD"]["Netflix Ads"] == "Get more evidence"  # Directional evidence is below the Steward's Verified bar
    assert by["BUILDER"]["Netflix Ads"] != by["STEWARD"]["Netflix Ads"]
    assert council.split and council.agree is not None


def test_conservative_persona_judges_by_the_pessimistic_end_of_the_interval(result) -> None:
    cd, ch, tot = build(result, True)
    steward = cn.PERSONA_BY_ID["STEWARD"]
    google = ch.set_index("channel").loc["Google Ads"]
    assert google["lower"] < 1.0 <= google["upper"] + 1e-9 or google["lower"] < 1.0
    assert cn.stance_for(steward, google, 1.0) == "Pull back"
    builder = cn.PERSONA_BY_ID["BUILDER"]
    assert cn.stance_for(builder, google, 1.0) in ("Hold", "Re-test")


def test_headlines_and_kpis_are_objective_facts_from_the_run(result) -> None:
    cd, ch, tot = build(result, False)
    council = cn.convene(ch, cd, tot, 1.0, False)
    steward = council.readings[0]
    assert "$105,158" in steward.headline and "$399,188" in steward.headline
    assert {k["label"] for k in steward.kpis} == {"Spend not earned back", "Claimed but unproven revenue", "Proven return per $1"}
    assert steward.kpis[0]["value"] == "$105,158"
    assert all(len(rd.kpis) == 3 and rd.persona.motivations for rd in council.readings)


def test_balanced_appetite_reproduces_the_shipped_rules_exactly(result) -> None:
    defs = {d["id"]: d for d in default_definitions()}
    balanced = st_.apply_appetite(defs, "Balanced")
    recon = result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"]
    facts = build_facts(recon, result.audit, False)
    base = evaluate_agents(list(defs.values()), facts)
    again = evaluate_agents(list(balanced.values()), facts)
    assert [(p["agent_id"], p["campaign_id"]) for p in base] == [(p["agent_id"], p["campaign_id"]) for p in again]
    assert len(base) == 6


def test_appetites_change_what_is_flagged_in_the_expected_direction(result) -> None:
    defs = {d["id"]: d for d in default_definitions()}
    facts = build_facts(result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], result.audit, False)

    def fired(app: str, rid: str) -> int:
        d = st_.apply_appetite(defs, app)[rid]
        return len(evaluate_agents([{**d, "enabled": True}], facts))
    assert fired("Aggressive", "SCALE_OPPORTUNITY_AGENT") >= fired("Balanced", "SCALE_OPPORTUNITY_AGENT") >= fired("Conservative", "SCALE_OPPORTUNITY_AGENT")
    assert fired("Conservative", "ATTRIBUTION_SHIELD_AGENT") >= fired("Balanced", "ATTRIBUTION_SHIELD_AGENT") >= fired("Aggressive", "ATTRIBUTION_SHIELD_AGENT")


def test_plain_settings_round_trip_and_validate() -> None:
    d = {x["id"]: x for x in default_definitions()}["ATTRIBUTION_SHIELD_AGENT"]
    s = st_.read_settings(d)
    assert s["overclaim_above"] == 1.25 and s["min_tier"] == "NOT_DECISION_GRADE"
    new, errs = st_.apply_settings(d, {"overclaim_above": 1.4, "min_spend": 5000.0, "min_tier": "VERIFIED"})
    assert not errs and st_.read_settings(new)["overclaim_above"] == 1.4 and new["min_spend"] == 5000.0 and new["requires_min_tier"] == "VERIFIED"
    assert "1.4" in st_.describe(new) and "$5,000" in st_.describe(new)
    bad, errs = st_.apply_settings(d, {"overclaim_above": 9999})
    assert bad is None and errs
