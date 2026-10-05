"""Test helper: sign an inbox item so low level store tests can move it through its lifecycle legitimately."""
from __future__ import annotations

from typing import Any


def sign_for_test(store: Any, ws: str, item_id: str, outcome: str = "APPROVED", email: str = "exec@example.com") -> str:
    return store.sign_item(ws, item_id, outcome, email, "CFO / VP Finance", "Signed by the test helper for lifecycle checks", "0" * 64)
