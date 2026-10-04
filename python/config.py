"""Typed, validated policy settings for the MMGE (the governance policy layer).

Every value that used to be hardcoded (geo sample, pre-period, thresholds) lives
here with bounds, so settings can be edited by business users without code and
stamped on each run for traceability.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

HEADLINE_STRICT = "strict_lift"
HEADLINE_SPEC = "reported_by_spec"
HEADLINE_CHOICES = (HEADLINE_STRICT, HEADLINE_SPEC)

TIER_VERIFIED = "VERIFIED"
TIER_DIRECTIONAL = "DIRECTIONAL"
TIER_NOT_DECISION_GRADE = "NOT_DECISION_GRADE"


class SettingsError(ValueError):
    """Raised when a policy setting is outside its allowed range."""


@dataclass(frozen=True)
class PolicySettings:
    """Governance policy parameters with defaults matching the original spec."""
    geo_sample_fraction: float = 0.40
    pre_period_days: int = 30
    min_pre_period_days: int = 28
    min_test_days: int = 28
    min_daily_conversions: float = 5.0
    avg_order_value: float = 75.0
    inflation_moderate: float = 1.5
    inflation_critical: float = 3.0
    trust_verified_min: float = 75.0
    trust_directional_min: float = 50.0
    headline_metric: str = HEADLINE_SPEC  # user chosen; both views are always computed
    spec_vs_strict_warning_ratio: float = 1.5  # warn if spec iROAS exceeds strict by this multiple
    gross_margin: Optional[float] = None  # contribution margin the user declares (0 to 1); None means unknown
    margin_industry: str = ""  # Damodaran industry used as a labeled upper-bound proxy when gross_margin is None
    seasonality_benchmark: bool = False  # adjust the control geo drift check by U.S. retail seasonality (opt in)

    def __post_init__(self) -> None:
        def bound(name: str, lo: float, hi: float) -> None:
            v = getattr(self, name)
            if v is None and name == "gross_margin":
                return
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                raise SettingsError(f"{name} must be between {lo} and {hi}, got {v!r}")

        bound("geo_sample_fraction", 0.01, 1.0)
        bound("pre_period_days", 7, 365)
        bound("min_pre_period_days", 7, 365)
        bound("min_test_days", 7, 365)
        bound("min_daily_conversions", 0, 10_000)
        bound("avg_order_value", 0.01, 1_000_000)
        bound("inflation_moderate", 1.0, 10.0)
        bound("inflation_critical", 1.0, 20.0)
        bound("trust_verified_min", 1, 100)
        bound("trust_directional_min", 0, 100)
        bound("spec_vs_strict_warning_ratio", 1.0, 100.0)
        bound("gross_margin", 0.01, 1.0)
        if not isinstance(self.margin_industry, str) or not isinstance(self.seasonality_benchmark, bool):
            raise SettingsError("margin_industry must be text and seasonality_benchmark true or false")
        if self.inflation_moderate >= self.inflation_critical:
            raise SettingsError("inflation_moderate must be below inflation_critical")
        if self.trust_directional_min >= self.trust_verified_min:
            raise SettingsError("trust_directional_min must be below trust_verified_min")
        if self.headline_metric not in HEADLINE_CHOICES:
            raise SettingsError(f"headline_metric must be one of {HEADLINE_CHOICES}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable hash of the settings, stamped on each run."""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:12]

    def trust_tier(self, trust_score: float, parallel_trends_pass: bool) -> str:
        """Map a 0-100 trust score to a decision-grade tier."""
        if not parallel_trends_pass or trust_score < self.trust_directional_min:
            return TIER_NOT_DECISION_GRADE
        return TIER_VERIFIED if trust_score >= self.trust_verified_min else TIER_DIRECTIONAL

    @property
    def headline_label(self) -> str:
        return "Strict lift iROAS" if self.headline_metric == HEADLINE_STRICT else "Reported-by-spec iROAS"
