"""Memo verifier: no number without a fact, no citation to a missing fact, no links or code.

Rules enforced on a draft that cites facts as [F1], [F2]:
  * every cited id exists
  * every number in a sentence matches (within its displayed precision, with matching unit) a fact cited in that sentence
  * no URLs, markdown links, code, HTML tags, or instruction-like text
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from memo_facts import Fact, FactSet

CITE = re.compile(r"\[F(\d+)\]")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LIST_NUM = re.compile(r"(?m)^\s*\d+[.)]\s+")
NUMBER = re.compile(r"(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suf>[kKmM](?![A-Za-z])|%|x(?![A-Za-z]))?")
URL = re.compile(r"https?://|www\.|\]\(|`|<[a-zA-Z/!][^>]*>", re.I)
INJECTION = re.compile(r"ignore (all|any|the|previous|prior|above)|disregard|you are now|system prompt|new instructions|override", re.I)
MAX_CHARS = 2500


@dataclass
class VerifyResult:
    ok: bool
    issues: List[str] = field(default_factory=list)
    cited: List[str] = field(default_factory=list)
    numbers_checked: int = 0


def _strip_allowed(text: str, allowed: List[str]) -> str:
    for a in sorted(allowed, key=len, reverse=True):
        if any(ch.isdigit() for ch in a):
            text = text.replace(a, " ")
    return text


def _remove_labels(text: str, allowed: List[str]) -> str:
    """Remove trusted label strings (names and fact labels) so rule scans only see the writer's own words."""
    for a in sorted(allowed, key=len, reverse=True):
        if len(a) >= 3:
            text = text.replace(a, " ")
    return text


def _matches(token: re.Match, fact: Fact) -> bool:
    cur, num, suf = token.group("cur"), token.group("num"), token.group("suf")
    raw = num.replace(",", "")
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    value = float(raw)
    unit = {"%": "pct", "x": "multiple"}.get(suf or "", None)
    if cur:
        unit = "usd"
    scale = 1.0
    fkind = {"pct0": "pct"}.get(fact.kind, fact.kind)
    if suf and suf.lower() in ("k", "m"):
        if unit not in (None, "usd") or fkind != "usd":
            return False
        scale = 1e3 if suf.lower() == "k" else 1e6
        unit = "usd"
    if unit == "usd" and fkind != "usd":
        return False
    if unit == "pct" and fkind != "pct":
        return False
    if unit == "multiple" and fkind != "multiple":
        return False
    tol = 0.5 * (10 ** -decimals) * scale + 1e-9
    return abs(value * scale - fact.value) <= tol


def verify_memo(text: str, facts: FactSet) -> VerifyResult:
    """Verify a cited draft against its facts."""
    res = VerifyResult(ok=True)
    by_id = facts.by_id()
    if not text or not text.strip():
        return VerifyResult(False, ["The memo is empty."])
    if len(text) > MAX_CHARS:
        res.issues.append(f"The memo is longer than {MAX_CHARS} characters.")
    if URL.search(text):
        res.issues.append("Links, code and markup are not allowed.")
    if INJECTION.search(_remove_labels(text, facts.allowed_text())):
        res.issues.append("The memo contains instruction-like text.")
    cited = sorted({f"F{n}" for n in CITE.findall(text)})
    res.cited = cited
    for c in cited:
        if c not in by_id:
            res.issues.append(f"Cites {c}, which does not exist.")
    body = ISO_DATE.sub(" ", text)
    body = LIST_NUM.sub("", body)
    body = _strip_allowed(body, facts.allowed_text())
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        ids = [f"F{n}" for n in CITE.findall(sentence)]
        cited_facts = [by_id[i] for i in ids if i in by_id]
        plain = CITE.sub(" ", sentence)
        for m in NUMBER.finditer(plain):
            res.numbers_checked += 1
            if not cited_facts:
                res.issues.append(f"The number '{m.group(0)}' has no fact citation in its sentence.")
            elif not any(_matches(m, f) for f in cited_facts):
                res.issues.append(f"The number '{m.group(0)}' does not match any fact cited in its sentence ({', '.join(ids)}).")
    res.ok = not res.issues
    return res


def clean_text(text: str) -> str:
    """Remove citation markers for human readable export."""
    return re.sub(r"\s+([.,;:])", r"\1", CITE.sub("", text)).replace("  ", " ").strip()
