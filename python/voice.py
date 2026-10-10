"""Shared wording for executive facing text: business terms first, technical names only in the sources section."""
from __future__ import annotations

# What each advisor stance means for a budget owner (internal keys stay stable for logic and tests).
STANCE_WORDS = {"Lean in": "Put more behind it", "Hold": "Keep as is", "Re-test": "Test again before deciding",
                "Pull back": "Reduce spend", "Get more evidence": "Prove it before deciding"}
# Short phrase used inside sentences ("would put more behind Google Ads").
STANCE_VERB = {"Lean in": "put more behind", "Hold": "keep as is", "Re-test": "test again before deciding on",
               "Pull back": "reduce spend on", "Get more evidence": "want more proof before deciding on"}

ACTION_WORDS = {"REDUCE_BUDGET_50%": "Reduce the budget by half", "SCALE_BUDGET_25%": "Increase the budget by a quarter",
                "CLIENT_GOVERNANCE_AUDIT": "Review the reporting with the client", "HOLD_SCALE_REQUESTS": "Pause requests to spend more",
                "RERUN_HOLDOUT": "Run a longer test", "REVIEW_MEASUREMENT": "Review how results are being measured",
                "REDUCE_TIER_SPEND": "Reduce spend on this audience tier", "REALLOCATE_BUDGET": "Move budget between channels", "AUTHORIZE_RESEARCH": "Approve a research test"}

# Phrases that describe how the product was built. They must never appear on screen.
BANNED_ON_SCREEN = ("screen reader", "shape and", "shape plus", "REQ-", "FR-", "design principle", "never an AI", "persona", "deliberately do not",
                    "self_asserted", "iROAS", "MDE", "spec basis", "cannibaliz", "propensity", "decile", "donor", "RMSPE")


def conf_phrase(tier: str) -> str:
    """How sure we are, in one plain phrase."""
    return {"VERIFIED": "Confident: strong enough to act on", "DIRECTIONAL": "Leaning one way: worth testing further before big moves",
            "NOT_DECISION_GRADE": "Not yet reliable: more testing needed first"}.get(tier, "Not yet rated")


def join_names(names, last="and") -> str:
    names = [str(n) for n in names]
    return names[0] if len(names) == 1 else (", ".join(names[:-1]) + f" {last} " + names[-1] if names else "")
