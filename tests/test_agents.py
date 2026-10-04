"""Phase 4A tests: safe expressions, schema, engine, presets equivalence, store, job integration."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import safe_expr  # noqa: E402
from agent_engine import build_facts, default_definitions, evaluate_agents, fingerprint, sensitivity  # noqa: E402
from agent_orchestrator import AgentOrchestrator, PERSONA_AGENCY, PERSONA_CFO, PERSONA_PLATFORM  # noqa: E402
from agent_schema import render_template, validate_definition  # noqa: E402
from config import HEADLINE_STRICT, PolicySettings  # noqa: E402
from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables, run_key, run_pipeline  # noqa: E402
from run_store import LocalRunStore, SUCCEEDED  # noqa: E402

KEYS = ("agent_id", "target_persona", "campaign_id", "channel", "severity", "title", "value_add_metrics", "strategic_callout", "recommended_action")
DEFS = {d["id"]: d for d in default_definitions()}


# ------------------------------------------------------------------ safe_expr
@pytest.mark.parametrize("expr,expected", [("max(0, a - 3) * 2", 14.0), ("a / b", None), ("div(a, b)", 0), ("round(a / 3, 2)", 3.33),
                                           ("-a + 1", -9.0), ("a ** 2", 100.0), ("'hello'", "hello"), ("c + 1", None), ("min(a, 4)", 4.0)])
def test_safe_expr_values(expr, expected) -> None:
    assert safe_expr.evaluate(expr, {"a": 10.0, "b": 0.0, "c": None}) == expected


@pytest.mark.parametrize("bad", ["__import__('os').system('x')", "a.real", "[x for x in a]", "a if b else c", "open('f')", "a[0]",
                                 "lambda: 1", "a ** 99", "a ** b", "unknown + 1", "exec('1')", "min(a, key=abs)", "a; b", "x" * 300,
                                 "((((((((((a))))))))))" + "+1" * 70, "True", "None", "f'{a}'", "a is b"])
def test_safe_expr_rejects(bad) -> None:
    with pytest.raises(safe_expr.ExprError):
        safe_expr.evaluate(bad, {"a": 1.0, "b": 2.0, "c": 3.0})


def test_nan_and_inf_become_none() -> None:
    assert safe_expr.evaluate("a / b", {"a": float("nan"), "b": 1.0}) is None


# ------------------------------------------------------------------ schema
def good() -> dict:
    return copy.deepcopy(DEFS["ATTRIBUTION_SHIELD_AGENT"])


def test_presets_validate() -> None:
    assert set(DEFS) == {"CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT", "SCALE_OPPORTUNITY_AGENT"}


@pytest.mark.parametrize("mutate,fragment", [
    (lambda d: d.update(id="bad id"), "Agent id"), (lambda d: d.update(persona="CEO"), "Persona"),
    (lambda d: d.update(severity="LOUD"), "Severity"), (lambda d: d.update(action="DELETE_EVERYTHING"), "Action"),
    (lambda d: d.update(priority=0), "Priority"), (lambda d: d.update(deadband_pct=80), "Deadband"),
    (lambda d: d.update(min_spend=-1), "Minimum spend"), (lambda d: d.update(trigger={"all": [], "any": []}), "at least one condition"),
    (lambda d: d["trigger"]["all"].append({"metric": "secret_field", "op": ">", "value": 1}), "unknown metric"),
    (lambda d: d["trigger"]["all"].append({"metric": "inflation_ratio", "op": "contains", "value": 1}), "operator"),
    (lambda d: d["trigger"]["all"].append({"metric": "inflation_ratio", "op": ">", "value": 1e6}), "between"),
    (lambda d: d["trigger"]["all"].append({"metric": "tier", "op": "==", "value": "GOLD"}), "tier must be"),
    (lambda d: d["trigger"]["all"].append({"metric": "iroas", "op": "between", "value": [3, 1]}), "first number"),
    (lambda d: d["value_add"].append({"label": "Bad", "expression": "__import__('os')", "format": "text"}), "Value-add"),
    (lambda d: d["value_add"].append({"label": "Bad format", "expression": "iroas", "format": "hex"}), "format"),
    (lambda d: d.update(callout="{secret} and {channel.__class__}"), "not allowed"),
    (lambda d: d.update(callout="{iroas!r}"), "not allowed"), (lambda d: d.update(callout="{iroas:>20}"), "not allowed"),
    (lambda d: d.update(title=""), "required"),
])
def test_schema_rejects(mutate, fragment) -> None:
    d = good()
    mutate(d)
    norm, errs = validate_definition(d)
    assert norm is None and any(fragment.lower() in e.lower() for e in errs), errs


def test_money_action_forced_to_directional() -> None:
    d = copy.deepcopy(DEFS["SCALE_OPPORTUNITY_AGENT"])
    d["requires_min_tier"] = "NOT_DECISION_GRADE"
    norm, errs = validate_definition(d)
    assert not errs and norm["requires_min_tier"] == "DIRECTIONAL"


def test_render_template_safety() -> None:
    assert render_template("{iroas:.1f}x {{ok}} {channel}", {"iroas": 1.234, "channel": "Meta"}) == "1.2x {ok} Meta"
    assert render_template("{iroas}", {"iroas": None}) == "n/a"
    with pytest.raises(ValueError):
        render_template("{os}", {})


# ----------------------------------------------------------- equivalence
@pytest.fixture(scope="module")
def run_result():
    return run_pipeline(SourceTables.from_directory())


@pytest.mark.parametrize("strict", [False, True])
def test_presets_match_legacy_orchestrator_on_demo(run_result, strict) -> None:
    recon = run_result.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"]
    legacy = AgentOrchestrator.from_audit(recon, run_result.audit, use_strict=strict).evaluate_triggers()
    new = evaluate_agents(default_definitions(), build_facts(recon, run_result.audit, strict))
    assert [{k: p[k] for k in KEYS} for p in new] == [{k: p[k] for k in KEYS} for p in legacy]


def row(**kw) -> pd.DataFrame:
    base = dict(channel="Meta Ads", campaign_id="C1", total_spend=1000.0, total_platform_conversions=100.0, total_mta_conversions=90.0,
                total_holdout_conversions=50.0, total_platform_revenue=7500.0, total_mta_revenue=6750.0, total_holdout_revenue=500.0,
                reported_roas=2.0, mta_roas=1.8, incremental_roas=1.5, inflation_ratio=1.0, has_mta_coverage=1, has_holdout_coverage=1)
    base.update(kw)
    return pd.DataFrame([base])


def audit_for(tier="VERIFIED", cid="C1") -> dict:
    return {"campaigns": [{"campaign_id": cid, "tier": tier, "trust_score": 90.0, "spec_iroas": 1.5, "strict_iroas": 0.5,
                           "strict_incremental_revenue": 300.0, "test_period_spend": 700.0, "divergence_warning": True}]}


@pytest.mark.parametrize("kw", [dict(reported_roas=1.5, incremental_roas=0.99), dict(reported_roas=1.49, incremental_roas=0.5),
                                dict(reported_roas=3.0, incremental_roas=1.0), dict(inflation_ratio=1.25), dict(inflation_ratio=1.26),
                                dict(inflation_ratio=3.0), dict(inflation_ratio=3.01), dict(incremental_roas=3.0, inflation_ratio=1.25),
                                dict(incremental_roas=2.99, inflation_ratio=1.0), dict(incremental_roas=5.0, inflation_ratio=1.26),
                                dict(reported_roas=2.0, incremental_roas=0.5, inflation_ratio=2.0),
                                dict(inflation_ratio=float("nan"), incremental_roas=float("nan")),
                                dict(inflation_ratio=2.0, incremental_roas=0.0), dict(total_platform_conversions=0.0, reported_roas=2.0, incremental_roas=0.4)])
@pytest.mark.parametrize("tier", ["VERIFIED", "DIRECTIONAL", "NOT_DECISION_GRADE"])
def test_presets_match_legacy_at_boundaries(kw, tier) -> None:
    recon = row(**kw)
    legacy = AgentOrchestrator(recon, {"C1": tier}).evaluate_triggers()
    new = evaluate_agents(default_definitions(), build_facts(recon, audit_for(tier)))
    assert [{k: p[k] for k in KEYS} for p in new] == [{k: p[k] for k in KEYS} for p in legacy]


# --------------------------------------------------------------- engine rules
def custom(**over) -> dict:
    d = {"id": "LOW_TRUST_WATCH", "name": "Low trust watch", "persona": PERSONA_AGENCY, "severity": "INFO", "action": "RERUN_HOLDOUT",
         "priority": 40, "trigger": {"all": [{"metric": "trust_score", "op": "<", "value": 95}], "any": []},
         "value_add": [{"label": "Trust", "expression": "trust_score", "format": "number"}],
         "title": "Watch {campaign_id}", "callout": "{channel} trust is {m1}."}
    d.update(over)
    norm, errs = validate_definition(d)
    assert not errs, errs
    return {**norm, "version": 1}


def facts(tier="VERIFIED", **kw):
    return build_facts(row(**kw), audit_for(tier))


def test_custom_agent_fires_and_renders() -> None:
    p = evaluate_agents([custom()], facts())
    assert len(p) == 1 and p[0]["title"] == "Watch C1" and p[0]["strategic_callout"] == "Meta Ads trust is 90.00." and p[0]["agent_version"] == 1


def test_disabled_agents_do_not_fire() -> None:
    assert evaluate_agents([custom(enabled=False)], facts()) == []


def test_tier_gate_for_money_agents_and_requires_min_tier() -> None:
    money = custom(id="CUT_AGENT", action="REDUCE_BUDGET_50%", requires_min_tier="NOT_DECISION_GRADE")
    assert evaluate_agents([money], facts("NOT_DECISION_GRADE")) == []
    assert len(evaluate_agents([money], facts("DIRECTIONAL"))) == 1
    strict_only = custom(id="VERIFIED_ONLY", requires_min_tier="VERIFIED")
    assert evaluate_agents([strict_only], facts("DIRECTIONAL")) == [] and len(evaluate_agents([strict_only], facts("VERIFIED"))) == 1


def test_min_spend_floor() -> None:
    d = custom(min_spend=5000)
    assert evaluate_agents([d], facts(total_spend=1000.0)) == [] and len(evaluate_agents([d], facts(total_spend=6000.0))) == 1


def test_any_group_and_tier_condition() -> None:
    d = custom(trigger={"all": [], "any": [{"metric": "iroas", "op": ">", "value": 10}, {"metric": "tier", "op": "in", "value": ["VERIFIED"]}]})
    assert len(evaluate_agents([d], facts("VERIFIED"))) == 1 and evaluate_agents([d], facts("DIRECTIONAL")) == []


def test_between_operator() -> None:
    d = custom(trigger={"all": [{"metric": "iroas", "op": "between", "value": [1.0, 2.0]}], "any": []})
    assert len(evaluate_agents([d], facts(incremental_roas=1.5))) == 1 and evaluate_agents([d], facts(incremental_roas=2.5)) == []


def test_deadband_hysteresis_across_runs() -> None:
    d = custom(trigger={"all": [{"metric": "iroas", "op": ">=", "value": 3.0}], "any": []}, deadband_pct=10)
    just_below = facts(incremental_roas=2.8)  # within 10% of the threshold
    assert evaluate_agents([d], just_below) == []  # a fresh alert needs the full threshold
    assert len(evaluate_agents([d], just_below, {("LOW_TRUST_WATCH", "C1")})) == 1  # an active one stays on
    assert evaluate_agents([d], facts(incremental_roas=2.6), {("LOW_TRUST_WATCH", "C1")}) == []  # clears once clearly below
    low = custom(trigger={"all": [{"metric": "iroas", "op": "<", "value": 1.0}], "any": []}, deadband_pct=10)
    assert len(evaluate_agents([low], facts(incremental_roas=1.05), {("LOW_TRUST_WATCH", "C1")})) == 1


def test_opposing_money_actions_are_suppressed_by_priority() -> None:
    cut = custom(id="CUT_AGENT", action="REDUCE_BUDGET_50%", priority=10, requires_min_tier="DIRECTIONAL")
    grow = custom(id="GROW_AGENT", action="SCALE_BUDGET_25%", priority=20, requires_min_tier="DIRECTIONAL")
    out = evaluate_agents([grow, cut], facts())
    assert [p["agent_id"] for p in out] == ["CUT_AGENT"] and "Suppressed GROW_AGENT" in out[0]["notes"][0]


def test_priority_order_within_campaign() -> None:
    a, b = custom(id="AAA_LATE", priority=60), custom(id="ZZZ_EARLY", priority=5)
    assert [p["agent_id"] for p in evaluate_agents([a, b], facts())] == ["ZZZ_EARLY", "AAA_LATE"]


def test_sensitivity_flags_cliff_edges() -> None:
    d = custom(trigger={"all": [{"metric": "iroas", "op": ">=", "value": 3.0}], "any": []})
    f = pd.concat([facts(incremental_roas=3.1), facts(incremental_roas=3.0).assign(campaign_id="C2"),
                   facts(incremental_roas=9.0).assign(campaign_id="C3"), facts(incremental_roas=0.5).assign(campaign_id="C4")], ignore_index=True)
    s = sensitivity(d, f).set_index("campaign_id")
    assert bool(s.loc["C1", "cliff_edge"]) and bool(s.loc["C2", "cliff_edge"])
    assert not s.loc["C3", "cliff_edge"] and not s.loc["C4", "cliff_edge"] and bool(s.loc["C3", "fires_now"])


def test_fingerprint_changes_with_edits() -> None:
    base = default_definitions()
    edited = copy.deepcopy(base)
    edited[0]["trigger"]["all"][0]["value"] = 1.6
    assert fingerprint(base) != fingerprint(edited) and fingerprint(base) == fingerprint(list(reversed(base)))


# ------------------------------------------------------------ store + runner
@pytest.fixture()
def store(tmp_path):
    return LocalRunStore(tmp_path / "s")


def test_store_versions_presets_and_custom(store) -> None:
    ws = store.get_or_create_workspace("acme")
    assert [d["version"] for d in store.get_agent_definitions(ws)] == [1, 1, 1]
    edited = copy.deepcopy(DEFS["SCALE_OPPORTUNITY_AGENT"])
    edited["trigger"]["all"][0]["value"] = 4.0
    v, errs = store.save_agent_definition(ws, edited, "jim")
    assert v == 2 and not errs
    got = {d["id"]: d for d in store.get_agent_definitions(ws)}
    assert got["SCALE_OPPORTUNITY_AGENT"]["version"] == 2 and got["SCALE_OPPORTUNITY_AGENT"]["trigger"]["all"][0]["value"] == 4.0
    v2, _ = store.save_agent_definition(ws, custom(), "jim")
    assert v2 == 1 and len(store.get_agent_definitions(ws)) == 4
    bad = good()
    bad["action"] = "NOPE"
    assert store.save_agent_definition(ws, bad)[0] == 0
    assert [x["version"] for x in store.list_agent_versions(ws, "SCALE_OPPORTUNITY_AGENT")] == [2]
    assert "agent_saved" in [e["event"] for e in store.list_audit_events(ws)]
    other = store.get_or_create_workspace("other")
    assert {d["id"]: d for d in store.get_agent_definitions(other)}["SCALE_OPPORTUNITY_AGENT"]["version"] == 1  # isolated


def test_custom_agent_flows_through_a_run_and_new_definitions_make_a_new_run(store) -> None:
    ws, j, tables = store.get_or_create_workspace("acme"), JobRunner(store), SourceTables.from_directory()
    r1 = j.submit(ws, tables)
    assert j.wait(ws, r1) == SUCCEEDED and len(store.list_inbox(ws, r1)) == 6
    assert j.submit(ws, tables) == r1  # same definitions: same run
    store.save_agent_definition(ws, custom(trigger={"all": [{"metric": "trust_score", "op": ">=", "value": 0}], "any": []}), "jim")
    r2 = j.submit(ws, tables)
    assert r2 != r1 and j.wait(ws, r2) == SUCCEEDED
    items = store.list_inbox(ws, r2)
    assert len(items) == 6 + 8 and sum(i["packet"]["agent_id"] == "LOW_TRUST_WATCH" for i in items) == 8
    ctx = store.load_audit(ws, r2)["agent_context"]
    assert any(d["id"] == "LOW_TRUST_WATCH" for d in ctx["definitions"])
    j.shutdown()


def test_deadband_uses_history_and_changes_run_key(store) -> None:
    """Threshold 5.7 then 5.9 then 6.5 with a 10% deadband: an active alert stays on near the line and clears clearly past it."""
    ws, j, tables = store.get_or_create_workspace("acme"), JobRunner(store), SourceTables.from_directory()

    def hyst(threshold):
        return {**custom(id="HYST_AGENT"), "trigger": {"all": [{"metric": "iroas", "op": ">=", "value": threshold}], "any": []}, "deadband_pct": 10}

    def fired(run_id):
        return {i["campaign_id"] for i in store.list_inbox(ws, run_id) if i["packet"]["agent_id"] == "HYST_AGENT"}

    store.save_agent_definition(ws, hyst(5.7), "jim")
    r1 = j.submit(ws, tables)
    j.wait(ws, r1)
    assert fired(r1) == {"GOOGLE_ADS_CMP_02"}  # iROAS 5.76 clears 5.7; 5.67 does not
    store.save_agent_definition(ws, hyst(5.9), "jim")
    r2 = j.submit(ws, tables)
    j.wait(ws, r2)
    assert fired(r2) == {"GOOGLE_ADS_CMP_02"}  # was active, 5.76 is within 10% of 5.9, so it stays; 5.67 was never active
    prev = store.load_audit(ws, r2)["agent_context"]["previously_active"]
    assert "HYST_AGENT|GOOGLE_ADS_CMP_02" in prev and "HYST_AGENT|GOOGLE_ADS_CMP_01" not in prev
    store.save_agent_definition(ws, hyst(6.5), "jim")
    r3 = j.submit(ws, tables)
    j.wait(ws, r3)
    assert fired(r3) == set()  # 5.76 is below 6.5 by more than the 10% deadband, so it clears
    assert len({r1, r2, r3}) == 3
    j.shutdown()


def test_pipeline_defaults_to_presets_and_strict_view() -> None:
    r = run_pipeline(SourceTables.from_directory(), PolicySettings(headline_metric=HEADLINE_STRICT))
    assert {p["agent_id"] for p in r.packets} == {"CAPITAL_PRESERVATION_AGENT", "ATTRIBUTION_SHIELD_AGENT"} and r.audit["agent_context"]["fingerprint"]


def test_run_key_includes_agent_fingerprint() -> None:
    t, s = SourceTables.from_directory(), PolicySettings()
    assert run_key(t, s, None, "aaa") != run_key(t, s, None, "bbb") and run_key(t, s, None, "aaa", "r1") != run_key(t, s, None, "aaa", "r2")
