"""Memo workflow: draft, verify, retry with feedback, fall back to the template, human approval, export."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent_engine import build_facts
from config import HEADLINE_STRICT, PolicySettings
from memo_facts import FactSet, build_factset
from memo_verify import VerifyResult, clean_text, verify_memo
from memo_writer import Draft, MemoWriterError, TemplateMemoWriter

DAILY_AI_CAP = 50
MAX_AI_ATTEMPTS = 2


def draft_memo(store: Any, workspace_id: str, item: Dict[str, Any], facts: FactSet, run_id: str, ai_writer: Any = None,
               actor: str = "system", daily_cap: int = DAILY_AI_CAP) -> Dict[str, Any]:
    """Create and persist a memo for an inbox item. Never raises for writer failures; falls back to the template."""
    packet = item["packet"]
    fallback_reason: Optional[str] = None
    attempts: List[Dict[str, Any]] = []
    draft: Optional[Draft] = None
    result: Optional[VerifyResult] = None
    if ai_writer is not None and store.count_ai_memos_today(workspace_id) >= daily_cap:
        fallback_reason, ai_writer = f"Daily AI memo limit of {daily_cap} reached.", None
    if ai_writer is not None:
        feedback: Optional[List[str]] = None
        for n in range(1, MAX_AI_ATTEMPTS + 1):
            try:
                d = ai_writer.write(facts, packet, feedback)
            except MemoWriterError as exc:
                fallback_reason = str(exc)
                attempts.append({"attempt": n, "error": str(exc)})
                break
            r = verify_memo(d.text, facts)
            attempts.append({"attempt": n, "ok": r.ok, "issues": r.issues, "prompt_hash": d.prompt_hash, "usage": d.usage})
            if r.ok:
                draft, result = d, r
                break
            feedback = r.issues
        if draft is None and fallback_reason is None:
            fallback_reason = "The AI draft failed verification: " + "; ".join(attempts[-1]["issues"][:3])
    if draft is None:
        draft = TemplateMemoWriter().write(facts, packet)
        result = verify_memo(draft.text, facts)
        if not result.ok:  # a template that fails verification is a programming error
            raise RuntimeError("Template memo failed verification: " + "; ".join(result.issues))
    record = {
        "run_id": run_id, "item_id": item["id"], "writer": draft.writer, "model": draft.model, "ai_drafted": draft.writer != "template",
        "facts": [f.__dict__ for f in facts.facts], "facts_text": facts.text, "text_cited": draft.text, "text_clean": clean_text(draft.text),
        "verification": {"ok": result.ok, "issues": result.issues, "cited": result.cited, "numbers_checked": result.numbers_checked},
        "attempts": attempts, "fallback_reason": fallback_reason, "prompt_hash": draft.prompt_hash,
    }
    memo_id = store.create_memo(workspace_id, record, actor)
    return store.get_memo(workspace_id, memo_id)


def edit_memo(store: Any, workspace_id: str, memo_id: str, new_text: str, actor: str) -> Dict[str, Any]:
    """Human edit of the cited text. The edit must re-verify against the memo's facts; otherwise it is rejected."""
    memo = store.get_memo(workspace_id, memo_id)
    facts = FactSet([_fact(f) for f in memo["facts"]], memo["facts_text"])
    result = verify_memo(new_text, facts)
    if not result.ok:
        return {"ok": False, "issues": result.issues, "memo": memo}
    store.update_memo_text(workspace_id, memo_id, new_text, clean_text(new_text),
                           {"ok": True, "issues": [], "cited": result.cited, "numbers_checked": result.numbers_checked}, actor)
    return {"ok": True, "issues": [], "memo": store.get_memo(workspace_id, memo_id)}


def _fact(d: Dict[str, Any]):
    from memo_facts import Fact
    return Fact(**d)


def export_markdown(memo: Dict[str, Any]) -> str:
    """Markdown export; only approved memos can be exported."""
    if memo["status"] not in ("approved", "exported"):
        raise PermissionError("Only approved memos can be exported.")
    label = "AI drafted, human approved" if memo["ai_drafted"] else "Template drafted, human approved"
    return (f"# Measurement memo: {memo['facts_text'].get('campaign_id', '')}\n\n{memo['text_clean']}\n\n---\n"
            f"_{label} by {memo['approved_by']} on {memo['approved_at'][:10]}. Run {memo['run_id']}._\n")


def export_slack(memo: Dict[str, Any]) -> str:
    if memo["status"] not in ("approved", "exported"):
        raise PermissionError("Only approved memos can be exported.")
    label = "AI drafted, human approved" if memo["ai_drafted"] else "Template drafted, human approved"
    return f"*Measurement memo: {memo['facts_text'].get('campaign_id', '')}*\n{memo['text_clean']}\n_{label} by {memo['approved_by']}_"


def facts_for_item(store: Any, workspace_id: str, run_id: str, item: Dict[str, Any]) -> FactSet:
    """Rebuild the memo facts for an inbox item from the stored run (reconciliation, audit and the run's policy)."""
    run = store.get_run(workspace_id, run_id)
    strict = PolicySettings(**run["settings"]).headline_metric == HEADLINE_STRICT
    audit = store.load_audit(workspace_id, run_id)
    frame = build_facts(store.load_table(workspace_id, run_id, "ANALYTICS_MEASUREMENT_RECONCILIATION"), audit, strict)
    rows = frame[frame["campaign_id"] == item["packet"]["campaign_id"]]
    if rows.empty:
        raise ValueError("Campaign not found in this run")
    return build_factset(item["packet"], rows.iloc[0].to_dict(), audit["headline_label"], strict)
