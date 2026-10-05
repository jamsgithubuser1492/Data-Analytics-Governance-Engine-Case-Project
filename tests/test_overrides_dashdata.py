"""Executive overrides (audit chain) and the dashboard data layer."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

import dashdata as dd  # noqa: E402
import overrides as ov  # noqa: E402
from pipeline import SourceTables, run_pipeline  # noqa: E402
from run_store import LocalRunStore, StoreError  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return run_pipeline(SourceTables.from_directory())


# ---------------------------------------------------------------------------------- overrides
def test_override_validation_rules() -> None:
    assert ov.validate_override("too short", "a@b.co", "CFO / VP Finance") != []
    assert ov.validate_override("Legal hold on this budget line", "not-an-email", "CFO / VP Finance") != []
    assert ov.validate_override("Legal hold on this budget line", "a@b.co", "Intern") != []
    assert ov.validate_override("Legal hold on this budget line", "a@b.co", "CFO / VP Finance") == []


def test_log_tampering_is_detected() -> None:
    log = Path(tempfile.mkdtemp()) / "run_audit_log.json"
    for i in range(3):
        ov.append_entry(log, {"event": "x", "n": i})
    assert ov.verify_log(log)[0]
    lines = log.read_text().splitlines()
    forged = json.loads(lines[1]); forged["n"] = 99
    log.write_text("\n".join([lines[0], json.dumps(forged), lines[2]]) + "\n")
    ok, why = ov.verify_log(log)
    assert not ok and "altered" in why
    log.write_text("\n".join([lines[0], lines[2]]) + "\n")  # deleting an entry breaks the chain
    assert not ov.verify_log(log)[0]


# ------------------------------------------------------------------------------- data layer
def frames(result, strict: bool):
    recon = result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"]
    camp = pd.DataFrame(result.audit["campaigns"])
    cd = dd.campaign_frame(recon, camp, strict, 1.0, None)
    ch = dd.channel_frame(cd, result.tables["GOVERNANCE_AUDIT_SUMMARY"], strict, 1.0)
    return cd, ch


def test_spec_view_matches_the_known_golden_numbers(result) -> None:
    cd, ch = frames(result, False)
    t = dd.portfolio_totals(cd, ch, False)
    assert round(t["spend"], 2) == 748140.42 and round(t["proven"], 2) == 3.33
    assert round(t["platform_revenue"] - t["proven_revenue"]) == round(t["overclaim_revenue"], 0)
    nf = ch.set_index("channel").loc["Netflix Ads"]  # the PRD leaderboard figures are the Netflix channel totals
    assert round(nf["unearned"], 2) == 105158.01 and round(nf["spend"], 2) == 161595.51


def test_strict_view_has_intervals_and_conservative_channel_bounds(result) -> None:
    cd, ch = frames(result, True)
    assert cd["lower"].notna().all() and (cd["lower"] <= cd["proven"]).all() and (cd["proven"] <= cd["upper"]).all()
    assert (ch["lower"] <= ch["proven"]).all() and (ch["proven"] <= ch["upper"]).all()
    g = ch.set_index("channel").loc["Google Ads"]
    assert abs(g["proven"] - 1.0) < 0.05
    row = cd.iloc[0]
    s = dd.best_worst_case(row, None, 1.0)
    assert "lower bound" in s and "upper bound" in s and "net revenue" in s
    assert dd.best_worst_case(frames(result, False)[0].iloc[0], None, 1.0) is None  # no interval in the spec view


def test_portfolio_actions_follow_the_rules(result) -> None:
    cd, ch = frames(result, False)
    t = dd.portfolio_totals(cd, ch, False)
    a = dd.with_actions(ch, 1.0, t["proven"]).set_index("channel")["action"].to_dict()
    assert a == {"Google Ads": "Scale", "Meta Ads": "Maintain", "TikTok Ads": "Maintain", "Netflix Ads": "Cut"}  # the PRD example
    assert dd.portfolio_action(5.0, "NOT_DECISION_GRADE", 1.0, 3.0) == "Restructure"
    assert dd.portfolio_action(1.0, "VERIFIED", 1.0, 0.57) == "Maintain"  # at breakeven is not a loss and not a scale case
    assert dd.portfolio_action(0.5, "VERIFIED", 1.0, 0.57) == "Cut"
    assert dd.portfolio_action(float("nan"), "VERIFIED", 1.0, 1.0) == "Restructure"


def test_reallocation_and_headroom_match_the_golden_scenario(result) -> None:
    cd, ch = frames(result, False)
    t = dd.portfolio_totals(cd, ch, False)
    ch = dd.with_actions(ch, 1.0, t["proven"])
    r = dd.reallocation(ch)
    assert round(r["net"], 2) == 667510.38  # the +$667,510.38 net expansion from the spec
    h = dd.headroom(ch, days=90)
    assert h["channels"] == ["Google Ads"] and h["added_monthly_spend"] > 0
    assert dd.reallocation(ch[ch["channel"] != "Netflix Ads"]) is None


def test_gate_matches_the_tier_table() -> None:
    assert dd.gate("VERIFIED")["can_execute"] and dd.gate("VERIFIED")["can_approve"]
    assert dd.gate("DIRECTIONAL")["can_approve"] and not dd.gate("DIRECTIONAL")["can_execute"]
    assert not dd.gate("NOT_DECISION_GRADE")["can_approve"]


def test_divergence_flag_uses_the_15_percent_rule(result) -> None:
    cd, _ = frames(result, True)
    assert len(dd.divergence(cd)) == 8  # spec overstates strict for every demo campaign
    flat = cd.assign(spec_iroas=cd["strict_iroas"] * 1.10)
    assert dd.divergence(flat).empty


def test_rule_in_words_and_waterfall(result) -> None:
    from agent_presets import PRESETS
    txt = dd.rule_in_words(PRESETS[0])
    assert "claimed return at or above 1.5" in txt and "proven return below 1" in txt and " and " in txt
    cd, ch = frames(result, False)
    steps = dd.waterfall_steps(dd.portfolio_totals(cd, ch, False))
    assert steps[0][1] + steps[1][1] == pytest.approx(steps[2][1], rel=1e-6)


def test_rolling_band_is_descriptive_and_ordered(result) -> None:
    b = dd.rolling_with_band(result.tables["ROLLING_7D_PERFORMANCE"])
    ok = b.dropna(subset=["band_low", "band_high"])
    assert len(ok) > 0 and (ok["band_low"] <= ok["iroas"]).all() and (ok["iroas"] <= ok["band_high"]).all()


def test_recommended_reallocation_only_moves_money_to_channels_that_are_not_cuts(result) -> None:
    cd, ch = frames(result, False)
    ch = dd.with_actions(ch, 1.0, dd.portfolio_totals(cd, ch, False)["proven"])
    r = dd.recommended_reallocation(ch)
    assert r["dest"] == "Google and Meta" and r["google_pct"] == 50.0 and round(r["net"], 2) == 667510.38
    cd2, ch2 = frames(result, True)
    ch2 = dd.with_actions(ch2, 1.0, dd.portfolio_totals(cd2, ch2, True)["proven"])
    r2 = dd.recommended_reallocation(ch2)  # strict view: Meta is a Cut, so only Google may receive the money
    assert r2["dest"] == "Google" and r2["google_pct"] == 100.0
    assert dd.recommended_reallocation(ch2.assign(action="Cut")) is None


def test_definitions_saved_with_emoji_by_older_versions_are_returned_clean() -> None:
    from agent_presets import PRESETS
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("legacy")
    legacy = {**PRESETS[0], "title": "\U0001F6A8 Capital Loss Detected: {campaign_id}", "version": 2,
              "value_add": [{**PRESETS[0]["value_add"][0], "label": "⚠️ Spend Not Earned Back"}] + PRESETS[0]["value_add"][1:]}
    store.save_agent_definition(ws, legacy, "test")
    got = {d["id"]: d for d in store.get_agent_definitions(ws)}["CAPITAL_PRESERVATION_AGENT"]
    assert got["title"] == "Capital Loss Detected: {campaign_id}" and got["value_add"][0]["label"] == "Spend Not Earned Back"
