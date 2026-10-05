"""The sign-off desk: the final human gate. No decision of any kind takes effect without a signed entry.

Every decision (approve, override or reject) needs a written note of 10 or more characters, the authorizing person's email and role,
and four acknowledgements. A signed entry is appended to ``run_audit_log.json`` (a hash chained log that reveals later edits or
deletions) and recorded in the store, which refuses to move an item to approved, executed or dismissed without it. A strong
statistical result never replaces the signature; a result that is not decision grade cannot be approved at all.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from overrides import EMAIL, EXEC_ROLES, MIN_REASON_CHARS, append_entry

OUTCOMES = {"APPROVED": "Approve as suggested", "OVERRIDDEN": "Override with my own decision", "REJECTED": "Reject"}
CHECKLIST: List[Tuple[str, str]] = [
    ("evidence", "I have reviewed the numbers and how sure we are about them."),
    ("impact", "I understand what this changes and which teams, clients or commitments it touches."),
    ("authority", "I have the authority to make this decision."),
    ("record", "I understand this signed record is permanent and cannot be edited."),
]
NOT_DECISION_GRADE = "NOT_DECISION_GRADE"


class SignoffError(ValueError):
    """Raised when a sign-off is incomplete or not allowed."""


def requirements(outcome: Optional[str], note: str, email: str, role: str, ticks: Sequence[bool], tier: str) -> List[str]:
    """Everything still needed before the decision can be signed, in plain words."""
    out: List[str] = []
    if outcome not in OUTCOMES:
        out.append("Choose what you decide.")
    elif outcome == "APPROVED" and tier == NOT_DECISION_GRADE:
        out.append("A result that is not decision grade cannot be approved. Choose Override or Reject.")
    if len((note or "").strip()) < MIN_REASON_CHARS:
        out.append(f"Write a note of at least {MIN_REASON_CHARS} characters explaining your decision.")
    if not EMAIL.match((email or "").strip()):
        out.append("Enter your email address.")
    if role not in EXEC_ROLES:
        out.append("Choose your executive role.")
    if len(ticks) != len(CHECKLIST) or not all(ticks):
        out.append("Tick all four acknowledgements.")
    return out


def _signature(entry: Dict[str, Any]) -> str:
    body = {k: entry[k] for k in ("run_id", "timestamp_utc", "recommendation_id", "decision_outcome")}
    body["email"] = entry["authorizing_user"]["email"]
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_entry(item: Dict[str, Any], outcome: str, note: str, email: str, role: str, ticks: Sequence[bool], *, trust_score: float, tier: str, basis: str,
                policy_version: str, authentication: str = "self_asserted") -> Dict[str, Any]:
    p = item["packet"]
    entry = {
        "audit_entry_id": str(uuid.uuid4()), "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "event": "signed_decision",
        "run_id": item["run_id"], "policy_version": policy_version, "counting_basis": basis, "trust_score_at_signing": int(round(float(trust_score))), "trust_tier": tier,
        "recommendation_id": item["id"], "agent_rule_triggered": p.get("agent_id", ""), "decision_outcome": outcome,
        "authorizing_user": {"email": email.strip(), "role": role, "authentication": authentication},
        "justification": note.strip(), "acknowledgements": {k: bool(t) for (k, _), t in zip(CHECKLIST, ticks)},
        "proposed_changes": p.get("proposed_changes") or [{"entity": p.get("campaign_id", ""), "change": p.get("recommended_action", "")}],
    }
    entry["signature_hash"] = _signature(entry)
    return entry


def verify_signature(entry: Dict[str, Any]) -> bool:
    return entry.get("signature_hash") == _signature(entry)


def sign(store: Any, workspace_id: str, item: Dict[str, Any], outcome: str, note: str, email: str, role: str, ticks: Sequence[bool], log_path: Path, *,
         trust_score: float, tier: str, basis: str, policy_version: str, authentication: str = "self_asserted") -> Dict[str, Any]:
    """Validate, record in the tamper evident log, then apply the decision to the item. Nothing is written if anything is missing."""
    problems = requirements(outcome, note, email, role, ticks, tier)
    if problems:
        raise SignoffError(" ".join(problems))
    fresh = store.get_inbox_item(workspace_id, item["id"])
    if store.get_signoff(workspace_id, item["id"]):
        raise SignoffError("This item has already been signed.")
    if fresh["status"] not in ("new", "reviewed"):
        raise SignoffError(f"Only open items can be signed; this one is {fresh['status']}.")
    entry = build_entry(fresh, outcome, note, email, role, ticks, trust_score=trust_score, tier=tier, basis=basis, policy_version=policy_version, authentication=authentication)
    written = append_entry(log_path, entry)
    store.sign_item(workspace_id, item["id"], outcome, email.strip(), role, note.strip(), written["hash"], authentication)
    return written


def receipt_json(entry: Dict[str, Any]) -> str:
    return json.dumps(entry, indent=2, sort_keys=True)
