"""Executive overrides with a tamper evident audit log (FR-AG01).

Overriding a recommendation needs a written business justification (at least 10 characters), the authorizing
person's email and executive role. Each override is appended to ``run_audit_log.json`` (JSON Lines) with a hash
that chains to the previous entry, so any later edit or deletion is detectable by ``verify_log``. The same event is
also written to the run store's audit trail.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

MIN_REASON_CHARS = 10
EXEC_ROLES = ["CFO / VP Finance", "CMO / Growth VP", "Agency Director", "Platform Lead", "Other executive"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENESIS = "0" * 64


class OverrideError(ValueError):
    """Raised when the sign-off panel input is incomplete."""


def validate_override(reason: str, email: str, role: str) -> List[str]:
    problems = []
    if len((reason or "").strip()) < MIN_REASON_CHARS:
        problems.append(f"Write a business justification of at least {MIN_REASON_CHARS} characters.")
    if not EMAIL.match((email or "").strip()):
        problems.append("Enter the authorizing person's email address.")
    if role not in EXEC_ROLES:
        problems.append("Choose the authorizing executive role.")
    return problems


def _digest(entry: Dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_log(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_entry(path: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
    entries = read_log(path)
    entry = {**entry, "prev_hash": entries[-1]["hash"] if entries else GENESIS}
    entry["hash"] = _digest(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # append only
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify_log(path: Path) -> Tuple[bool, str]:
    """(True, 'ok') when every entry hashes correctly and chains to the one before it."""
    prev = GENESIS
    for i, e in enumerate(read_log(path), 1):
        if e.get("prev_hash") != prev:
            return False, f"Entry {i} does not chain to the entry before it."
        if _digest(e) != e.get("hash"):
            return False, f"Entry {i} was altered after it was written."
        prev = e["hash"]
    return True, "ok"


def record_override(store: Any, workspace_id: str, item: Dict[str, Any], reason: str, email: str, role: str,
                    trust_score: float, tier: str, log_path: Path) -> Dict[str, Any]:
    problems = validate_override(reason, email, role)
    if problems:
        raise OverrideError(" ".join(problems))
    p = item["packet"]
    entry = append_entry(log_path, {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"), "event": "override_default_recommendation",
        "run_id": item["run_id"], "inbox_item": item["id"], "campaign_id": p["campaign_id"], "agent_id": p["agent_id"],
        "recommended_action": p["recommended_action"], "authorized_by": email.strip(), "role": role,
        "rationale": reason.strip(), "trust_score": trust_score, "trust_tier": tier})
    store.transition_inbox(workspace_id, item["id"], "dismissed", email.strip(), f"OVERRIDE ({role}): {reason.strip()}")
    return entry
