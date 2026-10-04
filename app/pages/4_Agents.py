"""No-code agent builder: edit, preview, test sensitivity and save agent versions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_runner, get_store, identity, page_setup, succeeded_runs, wait_for_run  # noqa: E402

page_setup("Agents",":material/smart_toy:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from agent_engine import build_facts, evaluate_agents, sensitivity  # noqa: E402
from agent_schema import (ACTIONS, CONDITION_METRICS, FORMATS, MEASURE_SLOTS, NUMERIC_OPS, PERSONAS, SEVERITIES,  # noqa: E402
                          TIER_OPS, TIERS, validate_definition)
from config import HEADLINE_STRICT, PolicySettings  # noqa: E402
from pipeline import SourceTables  # noqa: E402

store, runner = get_store(), get_runner()
actor, ws = identity()
defs = store.get_agent_definitions(ws)
by_id = {d["id"]: d for d in defs}

st.title("Decision rules (agent builder)")
st.caption("Agents are rules, not code. Pick a metric, a condition, who it is for and what action it recommends. "
           "Money actions never fire on results that are not decision grade. Every save is a new version.")

st.dataframe(pd.DataFrame([{"Agent": d["id"], "Name": d["name"], "Version": d.get("version", 1), "Enabled": d.get("enabled", True),
                            "Persona": d["persona"], "Action": d["action"], "Priority": d["priority"]} for d in defs]),
             hide_index=True, width="stretch")

NEW = "New custom agent"
sel = st.selectbox("Edit agent", [d["id"] for d in defs] + [NEW])
base = by_id.get(sel) or {
    "id": "", "name": "", "description": "", "persona": PERSONAS[0], "severity": "INFO", "action": "REVIEW_MEASUREMENT", "enabled": True,
    "priority": 50, "requires_min_tier": "NOT_DECISION_GRADE", "min_spend": 0.0, "deadband_pct": 0.0,
    "trigger": {"all": [{"metric": "inflation_ratio", "op": ">", "value": 1.5}], "any": []},
    "value_add": [{"label": "Platform Over-Claim Multiplier", "expression": "inflation_ratio", "format": "x2"}],
    "title": "Review {campaign_id}", "callout": "{channel} needs review: platform claims {m1} of the verified conversions."}
k = lambda name: f"{sel}_{name}"  # noqa: E731  widget keys per selected agent so switching resets the form


def fmt_value(c: dict) -> str:
    v = c["value"]
    return ", ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def parse_value(metric: str, op: str, text: str):
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if metric == "tier":
        return parts if op == "in" else (parts[0] if parts else "")
    if op == "between":
        return [float(p) for p in parts]
    return float(parts[0])


c1, c2 = st.columns(2)
agent_id = c1.text_input("Agent id (capitals, digits, underscores)", base["id"], key=k("id"), disabled=bool(base["id"]))
name = c2.text_input("Name", base["name"], key=k("name"))
desc = st.text_input("What it is for", base.get("description", ""), key=k("desc"))
d1, d2, d3 = st.columns(3)
persona = d1.selectbox("Who it is for", PERSONAS, index=PERSONAS.index(base["persona"]), key=k("persona"))
severity = d2.selectbox("Severity", SEVERITIES, index=SEVERITIES.index(base["severity"]), key=k("sev"))
actions = list(ACTIONS)
action = d3.selectbox("Recommended action", actions, index=actions.index(base["action"]), key=k("action"),
                      format_func=lambda a: f"{ACTIONS[a][0]}{' (money action)' if ACTIONS[a][1] else ''}")
e1, e2, e3, e4, e5 = st.columns(5)
enabled = e1.checkbox("Enabled", base.get("enabled", True), key=k("en"))
priority = e2.number_input("Priority (1 first)", 1, 100, int(base["priority"]), key=k("pri"))
min_tier = e3.selectbox("Minimum trust tier", TIERS, index=TIERS.index(base["requires_min_tier"]), key=k("tier"),
                        help="Money actions are always at least Directional.")
min_spend = e4.number_input("Minimum spend ($)", 0.0, 1e9, float(base["min_spend"]), key=k("ms"))
deadband = e5.number_input("Deadband (%)", 0.0, 50.0, float(base["deadband_pct"]), key=k("db"),
                           help="An alert that was active last run stays active until the metric is this far past the threshold.")

st.markdown("**When it fires**")
raw_trigger = {"all": [], "any": []}
parse_errors = []
for group, label in (("all", "ALL of these must be true"), ("any", "ANY of these may be true")):
    existing = base["trigger"].get(group, [])
    n = st.number_input(f"{label}: number of conditions", 0, 6, len(existing), key=k(f"n_{group}"))
    for i in range(int(n)):
        cur = existing[i] if i < len(existing) else {"metric": "iroas", "op": ">", "value": 1.0}
        a, b, c = st.columns([3, 2, 3])
        metric = a.selectbox("Metric", CONDITION_METRICS, index=CONDITION_METRICS.index(cur["metric"]) if cur["metric"] in CONDITION_METRICS else 0, key=k(f"{group}{i}m"))
        ops = TIER_OPS if metric == "tier" else NUMERIC_OPS
        op = b.selectbox("Condition", ops, index=ops.index(cur["op"]) if cur["op"] in ops else 0, key=k(f"{group}{i}o"))
        text = c.text_input("Value (use a comma for between or in)", fmt_value(cur), key=k(f"{group}{i}v"))
        try:
            raw_trigger[group].append({"metric": metric, "op": op, "value": parse_value(metric, op, text)})
        except (ValueError, IndexError):
            parse_errors.append(f"{group.upper()} condition {i + 1}: '{text}' is not a valid value for {metric} {op}.")

st.markdown("**Numbers the agent shows (value-add metrics)**")
st.caption("Formulas can use any metric name, + - * / ** and min, max, abs, round, div(a, b, default). Nothing else is allowed.")
existing_va = base.get("value_add", [])
nva = st.number_input("Number of value-add metrics", 0, len(MEASURE_SLOTS), len(existing_va), key=k("nva"))
value_add = []
for i in range(int(nva)):
    cur = existing_va[i] if i < len(existing_va) else {"label": "", "expression": "iroas", "format": "x2"}
    a, b, c = st.columns([3, 5, 2])
    lab = a.text_input(f"Label {i + 1} (use {{m{i + 1}}} in the callout)", cur["label"], key=k(f"va{i}l"))
    expr = b.text_input("Formula", cur["expression"], key=k(f"va{i}e"))
    fmts = list(FORMATS)
    f = c.selectbox("Format", fmts, index=fmts.index(cur["format"]) if cur["format"] in fmts else 0, key=k(f"va{i}f"))
    value_add.append({"label": lab, "expression": expr, "format": f})

title = st.text_input("Card title", base["title"], key=k("title"), help="Placeholders: {campaign_id} {channel} {tier} and any metric name")
callout = st.text_area("Callout message", base["callout"], key=k("callout"), height=90,
                       help="Placeholders: any metric name, {m1} to {m5} for value-add results, {iroas:.2f} style formats.")

draft = {"id": agent_id.strip() or base["id"], "name": name, "description": desc, "persona": persona, "severity": severity, "action": action,
         "enabled": enabled, "priority": priority, "requires_min_tier": min_tier, "min_spend": min_spend, "deadband_pct": deadband,
         "trigger": raw_trigger, "value_add": value_add, "title": title, "callout": callout}
norm, errors = validate_definition(draft)
errors = parse_errors + errors
if errors:
    for e in errors:
        st.error(e)
else:
    st.success("This definition is valid.")

# ------------------------------------------------------------------ preview
st.subheader("Preview on a real run")
runs = succeeded_runs(ws)
if not runs:
    st.info("Create a run first (on the Dashboard, choose Try with demo data) to preview what this agent would do.")
elif norm is not None:
    labels = {r["id"]: f"{r['label'] or 'Run'} · {r['created_at'][:16].replace('T', ' ')}" for r in runs}
    run_id = st.selectbox("Run to test against", list(labels), format_func=labels.get, key="preview_run")
    run = store.get_run(ws, run_id)
    settings = PolicySettings(**run["settings"])
    facts = build_facts(store.load_table(ws, run_id, "ANALYTICS_MEASUREMENT_RECONCILIATION"), store.load_audit(ws, run_id),
                        settings.headline_metric == HEADLINE_STRICT)
    test_def = {**norm, "version": base.get("version", 0) + 1, "enabled": True}
    _, prev_active = store.latest_active_set(ws)
    prev = prev_active if norm["deadband_pct"] > 0 else set()
    fired = evaluate_agents([test_def], facts, prev)
    st.markdown(f"**Would fire on {len(fired)} of {len(facts)} campaigns** ({'strict lift' if settings.headline_metric == HEADLINE_STRICT else 'reported by spec'} view)")
    if fired:
        st.dataframe(pd.DataFrame([{"Campaign": p["campaign_id"], "Channel": p["channel"], "Tier": p["tier"], **p["value_add_metrics"]} for p in fired]),
                     hide_index=True, width="stretch")
        st.caption("Example message: " + fired[0]["strategic_callout"])
    sens = sensitivity(test_def, facts, prev)
    cliff = sens[sens["cliff_edge"]]
    st.markdown("**Sensitivity (thresholds moved 10% down and up)**")
    st.dataframe(sens, hide_index=True, width="stretch")
    if len(cliff):
        st.warning(f"{len(cliff)} campaign(s) sit on a cliff edge: {', '.join(cliff['campaign_id'])}. A small data change flips this alert. "
                   "Consider a deadband.")

# --------------------------------------------------------------------- save
s1, s2 = st.columns([1, 2])
if s1.button("Save as new version", type="primary", disabled=bool(errors)):
    version, errs = store.save_agent_definition(ws, draft, actor)
    if errs:
        st.error("; ".join(errs))
    else:
        st.success(f"Saved {draft['id']} as version {version}. New runs use it.")
        st.session_state["agent_saved"] = True
if runs and s2.button("Re-evaluate the selected run's data with the saved agents (creates a new run)"):
    rid = st.session_state.get("preview_run") or runs[0]["id"]
    run = store.get_run(ws, rid)
    inputs = SourceTables(*(store.load_table(ws, rid, f"INPUT_{n}") for n in ("RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS")))
    new_id = runner.submit(ws, inputs, PolicySettings(**run["settings"]), run["declarations"], (run["label"] or "Run") + " (agents updated)")
    status = wait_for_run(ws, new_id, "Re-evaluating agents...")
    st.success(f"Run {status}. Open the Dashboard to see the packets.") if status == "succeeded" else st.error(store.get_run(ws, new_id)["error"])
if base.get("version"):
    with st.expander("Version history"):
        st.dataframe(pd.DataFrame([{"Version": v.get("version"), "Saved by": v.get("saved_by"), "Saved at": v.get("saved_at"), "Enabled": v.get("enabled")}
                                   for v in store.list_agent_versions(ws, sel)]), hide_index=True)
