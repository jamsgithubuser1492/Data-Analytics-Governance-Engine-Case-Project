"""Automation blueprint invariants: the design itself must not allow a model to decide or act."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import blueprint as bp  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿←-⇿ℹ‍️]")
CALLER_MUST_NOT_SUPPLY = {"trust_score", "tier", "trust_tier", "outcome", "decision_outcome", "approved", "signature", "email", "role", "policy_version"}


def test_there_is_no_approve_execute_sign_or_reject_tool() -> None:
    assert bp.forbidden_tool_names() == []
    assert [t["name"] for t in bp.TOOLS] == ["get_verified_run_facts", "evaluate_governance_rules", "simulate_reallocation", "recommend_experiments", "stage_decision_packet", "get_audit_status"]


def test_no_tool_lets_the_caller_supply_trust_evidence_or_outcome() -> None:
    for t in bp.TOOLS:
        assert not (set(bp.tool_parameters(t["name"])) & CALLER_MUST_NOT_SUPPLY), t["name"]
        assert t["schema"]["additionalProperties"] is False  # unknown parameters are rejected


def test_only_one_tool_writes_and_it_only_stages() -> None:
    writers = [t for t in bp.TOOLS if t["access"] != "Read"]
    assert [t["name"] for t in writers] == ["stage_decision_packet"] and writers[0]["access"] == "Stage only"
    assert any("Approve, reject or execute" in c for c in writers[0]["cannot"])


def test_every_path_to_executed_goes_through_a_human_signature() -> None:
    assert bp.can_reach_executed_without_human()
    edges = {(a, b): who for a, b, who, _ in bp.EDGES}
    assert edges[("Staged", "Approved")] == "Human only" and edges[("Approved", "Executed")] == "Human only"
    assert ("Staged", "Executed") not in edges and ("Trust gated", "Approved") not in edges
    assert all(b != "Approved" or who == "Human only" for (a, b), who in edges.items())


def test_schemas_are_well_formed_json_and_statuses_are_known() -> None:
    for t in bp.TOOLS:
        json.dumps(t["schema"])
        assert t["schema"]["type"] == "object" and t["plain"] and t["cannot"] and t["maps_to"]
    for c in bp.COMPONENTS:
        assert c["status"] in bp.STATUS_NOTE and c["layer"] in bp.LAYER_ORDER
    assert {g["status"] for g in bp.GUARDRAILS} <= set(bp.STATUS_NOTE)
    # honesty: the MCP server itself is a design, not code
    assert next(c for c in bp.COMPONENTS if c["name"] == "MCP server")["status"] == "Designed"
    assert not (ROOT / "mcp_server").exists()


def test_the_architecture_document_matches_the_module_and_is_clean() -> None:
    doc = (ROOT / "docs" / "ARCHITECTURE_MCP.md").read_text(encoding="utf-8")
    assert doc.strip() == bp.to_markdown().strip()
    assert not EMOJI.search(doc) and "—" not in doc and "–" not in doc
    assert "There is deliberately no approve tool and no execute tool." in doc and "stateDiagram-v2" in doc


def test_a_real_run_store_enforces_what_the_blueprint_promises() -> None:
    """The store invariant the Sign-off guardrail relies on: staging is fine, deciding needs a signature."""
    import tempfile
    from job_runner import JobRunner
    from pipeline import SourceTables
    from run_store import LocalRunStore, StoreError
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("t")
    runner = JobRunner(store, max_workers=1)
    cfg = store.latest_workspace_config(ws)
    rid = runner.submit(ws, SourceTables.from_directory(), cfg[0], cfg[1], "run")
    runner.wait(ws, rid, timeout=300)
    iid = store.add_inbox_item(ws, rid, {"packet_id": "x", "agent_id": "STRATEGY_SCENARIO", "campaign_id": "S1", "severity": "INFO", "title": "t", "channel": "Multiple"}, "model")
    for status in ("approved", "executed", "dismissed"):
        try:
            store.transition_inbox(ws, iid, status, "model")
        except StoreError:
            continue
        raise AssertionError(f"a model-staged item reached {status} without a signature")
    runner.shutdown()
