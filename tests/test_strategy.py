"""Strategy hub calculations."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

import dashdata as dd  # noqa: E402
import strategy as sg  # noqa: E402
from pipeline import SourceTables, run_pipeline  # noqa: E402


@pytest.fixture(scope="module")
def result():
    return run_pipeline(SourceTables.from_directory())


def view(result, strict: bool):
    camp = pd.DataFrame(result.audit["campaigns"])
    cd = dd.campaign_frame(result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], camp, strict, 1.0, None)
    ch = dd.channel_frame(cd, result.tables["GOVERNANCE_AUDIT_SUMMARY"], strict, 1.0)
    tot = dd.portfolio_totals(cd, ch, strict)
    return cd, dd.with_actions(ch, 1.0, tot["proven"]), tot


def moves(ch):
    amt = float(ch.set_index("channel").loc["Netflix Ads", "spend"])
    return [dict(source="Netflix Ads", target="Google Ads", amount=amt / 2), dict(source="Netflix Ads", target="Meta Ads", amount=amt / 2)]


def test_plan_matches_the_golden_reallocation_and_spend_is_conserved(result) -> None:
    cd, ch, tot = view(result, False)
    p = sg.plan_reallocation(ch, moves(ch))
    assert round(p["net"], 2) == 667510.38
    assert p["table"]["change"].sum() == pytest.approx(0.0) and p["table"]["spend_after"].sum() == pytest.approx(ch["spend"].sum())
    assert np.isnan(p["net_low"])  # the spec basis has no interval, so no best and worst case


def test_best_and_worst_case_exist_only_on_the_strict_basis_and_bracket_the_estimate(result) -> None:
    cd, ch, _ = view(result, True)
    p = sg.plan_reallocation(ch, moves(ch))
    assert p["net_low"] <= p["net"] <= p["net_high"]


def test_cannot_move_more_than_a_channel_spends_and_unknown_channels_fail(result) -> None:
    cd, ch, _ = view(result, False)
    p = sg.plan_reallocation(ch, [dict(source="Netflix Ads", target="Google Ads", amount=1e12)])
    assert p["moved"] == pytest.approx(float(ch.set_index("channel").loc["Netflix Ads", "spend"]))
    with pytest.raises(KeyError):
        sg.plan_reallocation(ch, [dict(source="Nope", target="Google Ads", amount=1)])


def test_cost_of_delay_arithmetic() -> None:
    d = sg.cost_of_delay(70000.0, 56)  # 8 weeks
    assert d["per_week"] == pytest.approx(8750.0) and d["weeks"] == pytest.approx(8.0) and d["per_30_days"] == pytest.approx(8750 * 30 / 7)


def test_break_even_haircut_is_where_net_is_zero(result) -> None:
    cd, ch, _ = view(result, False)
    s = sg.saturation_sensitivity(ch, moves(ch))
    h = s["break_even_haircut"]
    assert 0 < h < 1 and sg.plan_reallocation(ch, moves(ch), h)["net"] == pytest.approx(0.0, abs=1e-6)
    assert list(s["table"]["net"]) == sorted(s["table"]["net"], reverse=True)  # more saturation never helps


def test_implications_cover_five_functions_with_computed_changes_and_blank_estimates(result) -> None:
    cd, ch, _ = view(result, False)
    rows = sg.implications(ch, sg.plan_reallocation(ch, moves(ch)))
    assert [r["function"] for r in rows] == sg.FUNCTIONS
    assert "Netflix Ads" in rows[0]["what_changes"] and "$161,596" in rows[0]["what_changes"]
    assert all(r["questions"] and r["fields"] for r in rows)
    assert not any(ch_ in "".join(r["fields"]) for r in rows for ch_ in "0123456789")  # no invented numbers in worksheet fields


def test_change_plan_is_fact_triggered_and_tentative(result) -> None:
    cd, ch, tot = view(result, False)
    cp = sg.change_plan(tot, ch, len(dd.divergence(cd)), len(cd), False, "VERIFIED", 1.0)
    assert len(cp["stakeholders"]) == 4 and [p[0] for p in cp["phases"]] == ["Align", "Prove", "Phase in", "Embed"]
    text = " ".join(i for _, items in cp["phases"] for i in items) + " ".join(s["consider"] for s in cp["stakeholders"])
    assert "Netflix Ads" in text and "$105,158" in cp["stakeholders"][0]["evidence"]
    for _, items in cp["phases"]:
        assert all(i.startswith(("Consider", "Given that", "In order to address")) for i in items), items


def test_allocation_lens_shares_sum_to_one(result) -> None:
    cd, ch, _ = view(result, False)
    lens = sg.allocation_lens(ch)
    assert lens["table"]["share"].sum() == pytest.approx(1.0)
    by = lens["by_channel"].set_index("channel")["lens"].to_dict()
    assert by["Google Ads"] == "Core" and by["Meta Ads"] == "Core" and by["Netflix Ads"] == "Below threshold"
    assert sg.allocation_lens(ch, core_min=10.0)["by_channel"].set_index("channel").loc["Google Ads", "lens"] == "Validation"


def test_decay_monitor_flags_falling_and_below_floor_series() -> None:
    d = pd.date_range("2026-03-01", periods=15)
    roll = pd.concat([pd.DataFrame({"date": d, "channel": "Falling", "iroas": np.linspace(3.0, 2.0, 15)}),
                      pd.DataFrame({"date": d, "channel": "Flat", "iroas": np.full(15, 2.5)}),
                      pd.DataFrame({"date": d, "channel": "Low", "iroas": np.full(15, 0.6)}),
                      pd.DataFrame({"date": d[:3], "channel": "Short", "iroas": [1, 1, 1]})])
    r = sg.decay_monitor(roll).set_index("channel")
    assert r.loc["Falling", "status"] == "Falling" and r.loc["Flat", "status"] == "Stable" and r.loc["Low", "status"] == "Below floor" and r.loc["Short", "status"] == "Not enough days"
    assert "fell 33%" in r.loc["Falling", "note"]


def test_capital_protection_preview_uses_the_editable_rule(result) -> None:
    cd, ch, _ = view(result, False)
    p = sg.capital_protection_preview(cd)
    assert set(p["channel"]) == {"Netflix Ads"}
    assert sg.capital_protection_preview(cd, spend_min=1e9).empty and len(sg.capital_protection_preview(cd, floor=3.0)) > len(p)


def test_default_moves_pick_the_weakest_source_and_strongest_targets(result) -> None:
    cd, ch, _ = view(result, False)
    m = sg.default_moves(ch, 1.0)
    assert [x["source"] for x in m] == ["Netflix Ads", "Netflix Ads"] and [x["target"] for x in m] == ["Google Ads", "Meta Ads"]
    assert round(sg.plan_reallocation(ch, m)["net"], 2) == 667510.38
    assert sg.default_moves(ch.assign(proven=5.0), 1.0) == []  # nothing below breakeven, so no suggested source
