"""Automation blueprint: how models could connect to the engine through the Model Context Protocol (MCP) without removing human control.

This is a design, not a server. One structured source feeds the in-app page and docs/ARCHITECTURE_MCP.md (a test keeps them in sync).
Statuses are honest: Built means code exists in this repository, Designed means specified here but not built, Future means depends on
choices that belong to your organization (credentials, vendors, sign-in).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

TITLE = "Automation blueprint: connecting AI models to the engine safely"
INTRO = ("The engine can run continuously and let AI models read verified facts, test ideas and queue proposals, while a named person still signs every decision. "
         "This page is the design. The model never approves, never executes and never supplies its own trust score. Nothing described as Designed or Future exists yet.")

STATUS_NOTE = {"Built": "Code exists in this repository and is tested.", "Designed": "Specified here; no code yet.", "Future": "Depends on your organization's choices (credentials, vendors, sign-in)."}

# ---------------------------------------------------------------------------------------------------- components
COMPONENTS: List[Dict[str, str]] = [
    dict(layer="Data in", name="File upload and validation", status="Built", does="Accepts CSV or Excel, maps columns, blocks personal data columns, checks dates, duplicates and coverage."),
    dict(layer="Data in", name="Scheduled warehouse pulls", status="Designed", does="Pulls new aggregate data on a schedule from the company warehouse or platform exports."),
    dict(layer="Measure", name="Measurement engine", status="Built", does="Reconciles platform, attribution and holdout results; strict lift and spec bases; trust scores and levels."),
    dict(layer="Measure", name="Run store and audit trail", status="Built", does="Immutable runs, versioned policy, a signed decisions log that reveals edits."),
    dict(layer="Think", name="Guardrails and advisory council", status="Built", does="Rules flag results; four personas interpret them in tentative language."),
    dict(layer="Think", name="Research engine", status="Built", does="Ranks tests worth considering with designs computed from the run."),
    dict(layer="Connect", name="MCP server", status="Designed", does="Exposes six narrow tools, read only plus one staging tool, over a standard protocol."),
    dict(layer="Connect", name="Agent orchestration", status="Designed", does="A model calls the tools on a schedule or on request and prepares proposals for people."),
    dict(layer="Connect", name="Scheduler and notifications", status="Designed", does="Triggers runs, then tells the right person that something awaits their signature."),
    dict(layer="Decide", name="Sign-off desk", status="Built", does="Every decision is signed with a note, email, role and checklist; the store refuses unsigned changes."),
    dict(layer="Act", name="Execution connectors", status="Future", does="Applies a signed change in an ad platform through a scoped service account inside a change window."),
    dict(layer="Learn", name="Monitor and feedback", status="Built", does="Watches whether returns hold after a change and suggests retests."),
]
LAYER_ORDER = ["Data in", "Measure", "Think", "Connect", "Decide", "Act", "Learn"]

# -------------------------------------------------------------------------------------------------------- tools
TOOLS: List[Dict[str, Any]] = [
    dict(name="get_verified_run_facts", access="Read", plain="Returns the numbered facts for a run: spend, proven return, trust, evidence level, interval where one exists.",
         maps_to="app/prompt_pack.py build_facts", schema={"type": "object", "properties": {"run_id": {"type": "string"}, "counting_basis": {"type": "string", "enum": ["strict_lift", "reported_by_spec"], "description": "Which view to read. Both are always computed."},
                "level": {"type": "string", "enum": ["portfolio", "channel", "campaign"], "default": "channel"}, "use_aliases": {"type": "boolean", "default": False}}, "required": ["run_id"], "additionalProperties": False},
         cannot=["Return raw rows", "Return personal data", "Accept a trust score or evidence level from the caller"]),
    dict(name="evaluate_governance_rules", access="Read", plain="Runs the saved guardrails against a run and returns what they flag, with the evidence.",
         maps_to="python/agent_engine.py evaluate_agents", schema={"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
         cannot=["Change thresholds (they come from the saved, versioned policy)", "Create or edit rules"]),
    dict(name="simulate_reallocation", access="Read", plain="Models moving budget between channels at proven returns, with a best and worst case where an interval exists.",
         maps_to="app/strategy.py plan_reallocation", schema={"type": "object", "properties": {"run_id": {"type": "string"}, "moves": {"type": "array", "items": {"type": "object", "properties": {"source": {"type": "string"},
                "target": {"type": "string"}, "amount": {"type": "number", "minimum": 0}}, "required": ["source", "target", "amount"], "additionalProperties": False}, "maxItems": 10},
                "return_haircut": {"type": "number", "minimum": 0, "maximum": 0.5, "default": 0}}, "required": ["run_id", "moves"], "additionalProperties": False},
         cannot=["Change any budget", "Move more than a channel spends"]),
    dict(name="recommend_experiments", access="Read", plain="Returns ranked research ideas with designs computed from the run.",
         maps_to="app/research_engine.py build_specs", schema={"type": "object", "properties": {"run_id": {"type": "string"}, "channel": {"type": "string"}}, "required": ["run_id"], "additionalProperties": False},
         cannot=["Start a test", "Spend anything"]),
    dict(name="stage_decision_packet", access="Stage only", plain="Puts a budget scenario or a research idea in the sign-off queue as an open item. It does nothing until a person signs it.",
         maps_to="python/run_store.py add_inbox_item", schema={"type": "object", "properties": {"run_id": {"type": "string"}, "packet_type": {"type": "string", "enum": ["budget_scenario", "research_spec"]},
                "moves": {"type": "array", "items": {"type": "object", "properties": {"source": {"type": "string"}, "target": {"type": "string"}, "amount": {"type": "number", "minimum": 0}},
                "required": ["source", "target", "amount"], "additionalProperties": False}, "maxItems": 10}, "spec_id": {"type": "string"}, "rationale": {"type": "string", "maxLength": 500}},
                "required": ["run_id", "packet_type"], "additionalProperties": False},
         cannot=["Approve, reject or execute anything", "Set the trust score, evidence level, counting basis or outcome (the server derives them from the stored run)",
                 "Stage a budget scenario whose evidence is not decision grade"]),
    dict(name="get_audit_status", access="Read", plain="Reports whether the signed decisions log is intact and how many items await a signature, as counts only.",
         maps_to="python/overrides.py verify_log", schema={"type": "object", "properties": {"run_id": {"type": "string"}}, "required": [], "additionalProperties": False},
         cannot=["Return names or emails of signers", "Write to the log"]),
]
RESOURCES = ["methodology (the how it works guide)", "glossary of terms and formulas", "run summaries (aggregate only)"]
PROMPTS = ["executive_brief: the AI brief prompt for a chosen audience and task, built by the same fact numbering as the app"]

# -------------------------------------------------------------------------------------------------- state machine
STATES = ["Ingested", "Validated", "Computed", "Trust gated", "Staged", "Approved", "Dismissed", "Executed"]
# (from, to, who, plain meaning)
EDGES: List[Tuple[str, str, str, str]] = [
    ("Ingested", "Validated", "System", "Data passes the onboarding checks, or is stopped with a plain explanation."),
    ("Validated", "Computed", "System", "A run is created: measurement, trust scores, guardrails, research ideas."),
    ("Computed", "Trust gated", "System", "Each result gets an evidence level that decides what may be proposed."),
    ("Trust gated", "Staged", "System or model", "A proposal is queued as an open item. Not decision grade results cannot be staged as budget moves."),
    ("Staged", "Approved", "Human only", "A named person signs with a note, email, role and checklist."),
    ("Staged", "Dismissed", "Human only", "A person signs an override or a rejection. A newer run can also replace an open item."),
    ("Approved", "Executed", "Human only", "A dry run today; an outside connector later, after the signed approval."),
]
FORBIDDEN = ["Staged to Executed without Approved", "Any model or system actor reaching Approved, Dismissed by decision or Executed", "Approving a result that is not decision grade",
             "Signing the same item twice", "Editing or deleting a signed entry without the log showing it"]

# ------------------------------------------------------------------------------------------------------ guardrails
GUARDRAILS: List[Dict[str, str]] = [
    dict(rule="There is no approve tool and no execute tool.", how="Design of the tool catalog; a test asserts no tool name contains approve or execute.", status="Designed"),
    dict(rule="The model cannot supply trust, evidence level, counting basis or outcome.", how="Tool schemas have no such parameters; the server reads them from the stored run.", status="Designed"),
    dict(rule="No decision takes effect without a signed entry.", how="The store refuses approved, executed and dismissed without a signature, and the log is hash chained.", status="Built"),
    dict(rule="Results that are not decision grade cannot be approved.", how="Checked in the sign-off logic and shown on the desk.", status="Built"),
    dict(rule="Aggregate data only; personal data never leaves.", how="Schema blocks personal columns; free text is scanned and redacted; aliases hide names.", status="Built"),
    dict(rule="Read only by default, scoped to one workspace.", how="Per workspace credentials and an allowlist of tools; staging is a separate scope.", status="Designed"),
    dict(rule="Every tool call is logged by content hash.", how="Same pattern as prompt exports; text is never stored.", status="Designed"),
    dict(rule="Limits and a kill switch.", how="Rate and size limits per call; staging can be switched off per workspace at any time.", status="Designed"),
    dict(rule="Signatures come from verified people in production.", how="Single sign-on provides the email and role; today the email is self asserted and recorded as such.", status="Future"),
    dict(rule="Ad platform credentials never sit in the model layer.", how="Execution runs in a separate service with a scoped account and change windows.", status="Future"),
]

# ------------------------------------------------------------------------------------------------------- pipeline
PIPELINE: List[Dict[str, str]] = [
    dict(step="Pull", what="Scheduled job fetches new aggregate data and stores it with a content hash.", by="Scheduler", cadence="Daily or weekly", status="Designed"),
    dict(step="Validate", what="Onboarding checks run; blockers stop the pipeline and notify the data owner.", by="Engine", cadence="Each pull", status="Built"),
    dict(step="Measure", what="A run is created with both counting bases, trust scores and intervals.", by="Engine", cadence="Each valid pull", status="Built"),
    dict(step="Flag", what="Guardrails flag results; the research engine ranks questions.", by="Engine", cadence="Each run", status="Built"),
    dict(step="Prepare", what="A model reads facts through the tools and drafts a proposal or a research idea.", by="Model through MCP", cadence="Each run", status="Designed"),
    dict(step="Stage", what="The proposal is queued as an open item with its evidence.", by="Model or system", cadence="As needed", status="Designed"),
    dict(step="Notify", what="The right executive is told that something awaits a signature.", by="Notifier", cadence="On staging", status="Designed"),
    dict(step="Decide", what="A named person signs: approve, override or reject.", by="Human", cadence="On their schedule", status="Built"),
    dict(step="Act", what="A signed approval is handed to the team or an execution connector inside a change window.", by="Human, then connector", cadence="After signing", status="Future"),
    dict(step="Learn", what="The monitor checks whether the return held and suggests retests.", by="Engine", cadence="Weekly", status="Built"),
]

FAILURES: List[Tuple[str, str, str]] = [
    ("Data fails validation", "No run is created.", "Stop, tell the data owner what to fix. Nothing is staged."),
    ("Run succeeds but evidence is weak", "Results are Directional or not decision grade.", "Advisory only, or blocked from budget proposals; research ideas are offered instead."),
    ("Model is unavailable or returns nonsense", "No proposals are prepared.", "Pipeline still produces runs and guardrail flags; people use the dashboard as today."),
    ("Model proposes something outside its tools", "The call is rejected.", "Schema validation fails the call; the attempt is logged."),
    ("Notification is missed", "An item waits.", "Items stay open and visible on the sign-off desk and are re-surfaced; nothing happens by default."),
    ("Signed log is edited", "Chain verification fails.", "The desk shows 'Log altered' and decisions are paused until investigated."),
    ("Execution connector fails", "A signed change is not applied.", "The item stays approved, not executed, and the failure is logged for a person to retry."),
]
DEPLOYMENT = [
    ("Local, single user", "The MCP server runs on the same machine over standard input and output. Good for trying tools with a desktop assistant. No network exposure."),
    ("Company hosted", "The server runs behind the company gateway over HTTP with single sign-on, per workspace scopes, rate limits and logging. Recommended for shared use."),
    ("Warehouse integrated", "Scheduled pulls land aggregate data in the run store; the server reads only from the run store, never from the warehouse directly."),
]
ROLLOUT: List[Dict[str, str]] = [
    dict(phase="0. Today", delivers="Measurement, guardrails, council, strategy, AI brief, research ideas, sign-off desk with a tamper evident log.", exit="Already in place."),
    dict(phase="1. Read only tools", delivers="MCP server with four read tools and the audit status tool over local standard input and output.", exit="Tool schemas validated; a test proves no tool can change anything."),
    dict(phase="2. Staging", delivers="The stage tool plus notifications to the signer; company hosted with sign-in and scopes.", exit="Staged items appear on the desk; verified identity recorded on every signature."),
    dict(phase="3. Always on", delivers="Scheduled pulls, automatic runs, model prepared proposals each cycle.", exit="Failure handling exercised; weekly review of staged versus signed items."),
    dict(phase="4. Execution connectors", delivers="Scoped service accounts that apply signed changes inside change windows, one platform at a time.", exit="Dry run parity, rollback tested, finance approval of the process."),
]

# ------------------------------------------------------------------------------------------------------- invariants
def can_reach_executed_without_human() -> bool:
    """Graph check: is there any path to Executed whose edges are not all Human only after Staged?"""
    human_gates = {(a, b) for a, b, who, _ in EDGES if who == "Human only"}
    return not any(b == "Executed" and (a, b) not in human_gates for a, b, _, _ in EDGES)


def forbidden_tool_names() -> List[str]:
    return [t["name"] for t in TOOLS if any(w in t["name"] for w in ("approve", "execute", "sign", "reject"))]


def tool_parameters(name: str) -> List[str]:
    return list(next(t for t in TOOLS if t["name"] == name)["schema"]["properties"])


# ------------------------------------------------------------------------------------------------------- markdown
def to_markdown() -> str:
    import json
    L: List[str] = [f"# {TITLE}", "", INTRO, "", "## Status key", ""]
    L += [f"* **{k}**: {v}" for k, v in STATUS_NOTE.items()]
    L += ["", "## 1. The layers", "", "| Layer | Component | Status | What it does |", "| --- | --- | --- | --- |"]
    for layer in LAYER_ORDER:
        for c in [c for c in COMPONENTS if c["layer"] == layer]:
            L.append(f"| {layer} | {c['name']} | {c['status']} | {c['does']} |")
    L += ["", "```text", "  Company data and platform exports", "            |", "            v", "  [ Ingestion and validation ]  -->  [ Measurement engine ]  -->  [ Guardrails, council, research ]",
          "                                                                    |", "                                                                    v",
          "                 [ MCP server: six narrow tools ]  <--- reads facts, simulates, recommends", "                                |  stage only", "                                v",
          "                 [ Sign-off desk: a named person signs ]  --->  [ Signed log, hash chained ]", "                                |  signed approval only", "                                v",
          "                 [ Execution connector (future, scoped, change windows) ]", "```", "", "## 2. The six tools", "",
          "There is deliberately no approve tool and no execute tool. No tool accepts a trust score, evidence level, counting basis or outcome from the caller; the server derives them from the stored run.", ""]
    for t in TOOLS:
        L += [f"### {t['name']} ({t['access']})", "", t["plain"], "", f"Backed by: `{t['maps_to']}`", "", "It cannot:", ""] + [f"* {c}" for c in t["cannot"]]
        L += ["", "```json", json.dumps(t["schema"], indent=2), "```", ""]
    L += ["Resources: " + "; ".join(RESOURCES) + ".", "", "Prompts: " + "; ".join(PROMPTS) + ".", "", "## 3. The decision state machine", "", "```mermaid", "stateDiagram-v2"]
    L += [f"    {a.replace(' ', '')} --> {b.replace(' ', '')}: {who}" for a, b, who, _ in EDGES]
    L += ["```", "", "| From | To | Who | What it means |", "| --- | --- | --- | --- |"] + [f"| {a} | {b} | {who} | {m} |" for a, b, who, m in EDGES]
    L += ["", "Never allowed:", ""] + [f"* {f}" for f in FORBIDDEN]
    L += ["", "## 4. Safety rules", "", "| Rule | How it is enforced | Status |", "| --- | --- | --- |"] + [f"| {g['rule']} | {g['how']} | {g['status']} |" for g in GUARDRAILS]
    L += ["", "## 5. The always on pipeline", "", "| Step | What happens | By | How often | Status |", "| --- | --- | --- | --- | --- |"] + [f"| {p['step']} | {p['what']} | {p['by']} | {p['cadence']} | {p['status']} |" for p in PIPELINE]
    L += ["", "## 6. When things go wrong", "", "| Failure | Effect | Safe behavior |", "| --- | --- | --- |"] + [f"| {a} | {b} | {c} |" for a, b, c in FAILURES]
    L += ["", "## 7. Where it could run", ""] + [f"* **{a}.** {b}" for a, b in DEPLOYMENT]
    L += ["", "## 8. Rollout", "", "| Phase | Delivers | Exit test |", "| --- | --- | --- |"] + [f"| {r['phase']} | {r['delivers']} | {r['exit']} |" for r in ROLLOUT]
    L += ["", "## 9. Privacy", "", "Only aggregate marketing measurements move through the tools. Free text is scanned for personal data, names can be replaced with aliases, calls are logged by content hash only, "
          "and signer identities are never returned by a tool. See `docs/PRIVACY_AND_GOVERNANCE.md`. This is a design, not legal advice.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    print(to_markdown())
