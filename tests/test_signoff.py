"""The sign-off desk: every decision signed, nothing takes effect without a signature."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

import overrides as ov  # noqa: E402
import signoff as so  # noqa: E402
import strategy as sg  # noqa: E402
from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import LocalRunStore, StoreError  # noqa: E402
from runview import load_view  # noqa: E402

TICKS = [True] * 4
NOTE = "Reviewed with finance and agreed to proceed in stages"


@pytest.fixture()
def env():
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("t")
    runner = JobRunner(store, max_workers=1)
    cfg = store.latest_workspace_config(ws)
    rid = runner.submit(ws, SourceTables.from_directory(), cfg[0], cfg[1], "run")
    runner.wait(ws, rid, timeout=300)
    log = Path(tempfile.mkdtemp()) / "run_audit_log.json"
    yield store, ws, rid, log
    runner.shutdown()


def sign(env, item, outcome="APPROVED", **kw):
    store, ws, rid, log = env
    args = dict(trust_score=90, tier="VERIFIED", basis="Reported by spec", policy_version="abc123")
    args.update(kw)
    return so.sign(store, ws, item, outcome, NOTE, "cfo@example.com", "CFO / VP Finance", TICKS, log, **args)


def test_no_store_path_reaches_approved_executed_or_dismissed_without_a_signature(env) -> None:
    store, ws, rid, _ = env
    for item in store.list_inbox(ws, rid)[:3]:
        for status in ("approved", "dismissed", "executed"):
            with pytest.raises(StoreError):
                store.transition_inbox(ws, item["id"], status, "anyone", "trying to skip the gate")
        assert store.get_inbox_item(ws, item["id"])["status"] == "new"
    # even a perfect trust score gives no shortcut: reviewing is allowed, deciding is not
    top = store.list_inbox(ws, rid)[0]
    store.transition_inbox(ws, top["id"], "reviewed", "anyone")
    with pytest.raises(StoreError):
        store.transition_inbox(ws, top["id"], "approved", "anyone")


def test_signed_approval_moves_the_item_and_writes_a_verifiable_receipt(env) -> None:
    store, ws, rid, log = env
    item = store.list_inbox(ws, rid)[0]
    e = sign(env, item)
    assert store.get_inbox_item(ws, item["id"])["status"] == "approved"
    assert e["decision_outcome"] == "APPROVED" and e["authorizing_user"] == {"email": "cfo@example.com", "role": "CFO / VP Finance", "authentication": "self_asserted"}
    assert e["trust_score_at_signing"] == 90 and e["policy_version"] == "abc123" and e["counting_basis"] == "Reported by spec" and set(e["acknowledgements"]) == {k for k, _ in so.CHECKLIST}
    assert so.verify_signature(e) and ov.verify_log(log) == (True, "ok")
    sig = store.get_signoff(ws, item["id"])
    assert sig["outcome"] == "APPROVED" and sig["entry_hash"] == e["hash"]
    store.transition_inbox(ws, item["id"], "executed", "cfo@example.com", "dry run")  # execution follows a signed approval
    assert store.get_inbox_item(ws, item["id"])["status"] == "executed"


def test_override_and_reject_are_signed_too_and_dismiss_the_item(env) -> None:
    store, ws, rid, log = env
    a, b = store.list_inbox(ws, rid)[:2]
    sign(env, a, "OVERRIDDEN")
    sign(env, b, "REJECTED")
    assert store.get_inbox_item(ws, a["id"])["status"] == "dismissed" and store.get_inbox_item(ws, b["id"])["status"] == "dismissed"
    assert [e["decision_outcome"] for e in ov.read_log(log)] == ["OVERRIDDEN", "REJECTED"] and ov.verify_log(log)[0]


@pytest.mark.parametrize("kw,needle", [({"note": "short"}, "at least 10 characters"), ({"email": "nobody"}, "email"), ({"role": "Intern"}, "role"), ({"ticks": [True, True, True, False]}, "four acknowledgements")])
def test_incomplete_sign_offs_write_nothing(env, kw, needle) -> None:
    store, ws, rid, log = env
    item = store.list_inbox(ws, rid)[0]
    args = dict(note=NOTE, email="cfo@example.com", role="CFO / VP Finance", ticks=TICKS)
    args.update(kw)
    with pytest.raises(so.SignoffError, match=needle):
        so.sign(store, ws, item, "APPROVED", args["note"], args["email"], args["role"], args["ticks"], log, trust_score=90, tier="VERIFIED", basis="b", policy_version="p")
    assert not log.exists() and store.get_signoff(ws, item["id"]) is None and store.get_inbox_item(ws, item["id"])["status"] == "new"


def test_a_result_that_is_not_decision_grade_cannot_be_approved_but_can_be_rejected(env) -> None:
    store, ws, rid, log = env
    a, b = store.list_inbox(ws, rid)[:2]
    with pytest.raises(so.SignoffError, match="not decision grade"):
        sign(env, a, "APPROVED", tier="NOT_DECISION_GRADE", trust_score=30)
    assert not log.exists() and store.get_inbox_item(ws, a["id"])["status"] == "new"
    sign(env, b, "REJECTED", tier="NOT_DECISION_GRADE", trust_score=30)
    assert store.get_inbox_item(ws, b["id"])["status"] == "dismissed"


def test_an_item_can_only_be_signed_once(env) -> None:
    store, ws, rid, log = env
    item = store.list_inbox(ws, rid)[0]
    sign(env, item)
    with pytest.raises(so.SignoffError):
        sign(env, item, "REJECTED")
    assert len(ov.read_log(log)) == 1


def test_workspace_isolation(env) -> None:
    store, ws, rid, log = env
    other = store.get_or_create_workspace("intruder")
    item = store.list_inbox(ws, rid)[0]
    with pytest.raises(StoreError):
        store.sign_item(other, item["id"], "APPROVED", "x@y.com", "CFO / VP Finance", NOTE, "h")
    with pytest.raises(StoreError):
        store.get_inbox_item(other, item["id"])


def test_log_tampering_is_detected_and_the_signature_reproduces(env) -> None:
    store, ws, rid, log = env
    a, b = store.list_inbox(ws, rid)[:2]
    e1 = sign(env, a)
    sign(env, b, "REJECTED")
    lines = log.read_text().splitlines()
    forged = json.loads(lines[0])
    forged["decision_outcome"] = "REJECTED"
    log.write_text("\n".join([json.dumps(forged), lines[1]]) + "\n")
    ok, why = ov.verify_log(log)
    assert not ok and "altered" in why
    assert so.verify_signature(e1) and not so.verify_signature({**e1, "decision_outcome": "REJECTED"})


def test_scenarios_and_research_specs_enter_the_same_queue_and_need_the_same_signature(env) -> None:
    store, ws, rid, log = env
    v = load_view(store, ws, rid)
    plan = sg.plan_reallocation(v.ch, sg.default_moves(v.ch, v.breakeven))
    packet = sg.scenario_packet(v.ch, plan, sg.cost_of_delay(plan["net"], 60))
    assert packet["tier"] == "DIRECTIONAL" and packet["proposed_changes"] and packet["recommended_action"] == "REALLOCATE_BUDGET"  # Netflix is the weak link
    iid = store.add_inbox_item(ws, rid, packet, "tester")
    assert store.add_inbox_item(ws, rid, packet, "tester") == iid  # idempotent
    with pytest.raises(StoreError):
        store.transition_inbox(ws, iid, "approved", "tester")
    item = store.get_inbox_item(ws, iid)
    e = so.sign(store, ws, item, "APPROVED", NOTE, "cfo@example.com", "CFO / VP Finance", TICKS, log, trust_score=packet["trust_score"], tier=packet["tier"], basis="Reported by spec", policy_version="p")
    assert store.get_inbox_item(ws, iid)["status"] == "approved" and e["proposed_changes"][0]["entity"] in ("Netflix Ads", "Google Ads", "Meta Ads")
