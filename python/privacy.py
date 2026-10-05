"""Privacy guard for anything that leaves the app (prompts, exports).

Principles (see docs/PRIVACY_AND_GOVERNANCE.md):
  * Aggregate only. Prompts contain campaign and channel level totals, never rows, people, or identifiers.
  * Nothing the executive types is trusted: free text is scanned for personal data and the export is blocked or redacted.
  * Names can be replaced by reversible local aliases so an outside AI never sees real channel or campaign names.
This is a safeguard, not legal advice or a complete data loss prevention system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)")
SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")
IPV4 = re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\.?\d)")
LABELS = {"email": "email address", "phone": "phone number", "ssn": "government ID number", "card": "payment card number", "ip": "IP address"}
MARK = {"email": "[email removed]", "phone": "[phone removed]", "ssn": "[ID removed]", "card": "[card removed]", "ip": "[IP removed]"}
MAX_CONTEXT_CHARS = 2000

NOTICE = ("Data handling: this text contains aggregate marketing measurements only (channel and campaign totals). It contains no customer records, "
          "no personal data and no raw rows. Treat it as confidential company information and use only a company approved AI service.")


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0


@dataclass
class Finding:
    kind: str
    label: str
    start: int
    end: int


def scan_text(text: str) -> List[Finding]:
    """Personal data found in free text (email, phone, ID number, payment card with a valid check digit, IP address)."""
    out: List[Finding] = []
    taken: List[Tuple[int, int]] = []

    def add(kind: str, m: re.Match) -> None:
        if any(m.start() < e and s < m.end() for s, e in taken):
            return
        taken.append((m.start(), m.end()))
        out.append(Finding(kind, LABELS[kind], m.start(), m.end()))
    for m in EMAIL.finditer(text):
        add("email", m)
    for m in SSN.finditer(text):
        add("ssn", m)
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            add("card", m)
    for m in IPV4.finditer(text):
        add("ip", m)
    for m in PHONE.finditer(text):
        add("phone", m)
    return sorted(out, key=lambda f: f.start)


def redact_text(text: str) -> Tuple[str, List[Finding]]:
    """Text with personal data replaced by neutral markers, and what was found."""
    found = scan_text(text)
    for f in sorted(found, key=lambda f: f.start, reverse=True):
        text = text[:f.start] + MARK[f.kind] + text[f.end:]
    return text, found


@dataclass
class Aliaser:
    """Reversible local aliases (Channel A, Campaign 1). The mapping never leaves the app."""
    channels: Dict[str, str] = field(default_factory=dict)
    campaigns: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, channels: List[str], campaigns: List[str]) -> "Aliaser":
        a = cls()
        for i, c in enumerate(sorted(set(channels))):
            a.channels[c] = f"Channel {chr(65 + i % 26)}{'' if i < 26 else i // 26}"
        for i, c in enumerate(sorted(set(campaigns)), 1):
            a.campaigns[c] = f"Campaign {i}"
        return a

    def hide(self, text: str) -> str:
        for mapping in (self.campaigns, self.channels):  # campaign ids contain channel names, so replace those first
            for real, alias in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
                text = text.replace(real, alias)
        return text

    def reveal(self, text: str) -> str:
        for mapping in (self.channels, self.campaigns):
            for real, alias in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
                text = re.sub(re.escape(alias) + r"(?!\w)", real, text)
        return text

    def key_table(self) -> List[Tuple[str, str]]:
        return [(v, k) for k, v in {**self.channels, **self.campaigns}.items()]


def clean_context(text: Optional[str]) -> Tuple[str, List[Finding], bool]:
    """Executive supplied context: trimmed, personal data redacted, length capped. Returns (text, findings, was_truncated)."""
    text = (text or "").strip()
    truncated = len(text) > MAX_CONTEXT_CHARS
    text = text[:MAX_CONTEXT_CHARS]
    cleaned, found = redact_text(text)
    return cleaned, found, truncated


def assert_aggregate_only(rows_in_prompt: int) -> None:
    """Hard stop if code ever tries to place raw rows in a prompt."""
    if rows_in_prompt:
        raise ValueError("Raw data rows must never be placed in a prompt; only aggregate facts are allowed.")
