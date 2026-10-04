"""Canonical data contract for the four MMGE source tables.

Each field has a type, a null policy and an allowed range; the validation
engine uses this contract so uploaded data is checked against explicit rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

KEY_COLUMNS = ["date", "channel", "campaign_id"]


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # "date" | "str" | "int" | "float"
    required: bool = True
    min_value: Optional[float] = None


SCHEMAS: Dict[str, List[Field]] = {
    "RAW_PLATFORM_DATA": [
        Field("date", "date"), Field("channel", "str"), Field("campaign_id", "str"),
        Field("spend", "float", min_value=0), Field("impressions", "int", min_value=0),
        Field("clicks", "int", min_value=0), Field("reported_conversions", "int", min_value=0),
        Field("reported_revenue", "float", min_value=0),
    ],
    "RAW_MTA_OUTPUT": [
        Field("date", "date"), Field("channel", "str"), Field("campaign_id", "str"),
        Field("mta_attributed_conversions", "int", min_value=0),
        Field("mta_attributed_revenue", "float", min_value=0),
        Field("mta_attribution_weight", "float", required=False, min_value=0),
        Field("model_version", "str", required=False),
    ],
    "RAW_HOLDOUT_DATA": [
        Field("date", "date"), Field("experiment_id", "str"), Field("campaign_id", "str"),
        Field("geo_or_cohort_id", "str"), Field("group_type", "str"),
        Field("treatment_flag", "int", min_value=0), Field("population_size", "int", required=False, min_value=0),
        Field("conversions", "int", min_value=0), Field("revenue", "float", min_value=0),
    ],
    "BUSINESS_BENCHMARKS": [
        Field("channel", "str"), Field("expected_roas_min", "float", min_value=0),
        Field("expected_roas_max", "float", min_value=0), Field("expected_cvr_min", "float", min_value=0),
        Field("expected_cvr_max", "float", min_value=0),
        Field("typical_incrementality_min", "float", min_value=0),
        Field("typical_incrementality_max", "float", min_value=0),
    ],
}

# Columns that look like personal data and must never be uploaded.
PII_HINTS = ("email", "phone", "first_name", "last_name", "address", "ssn", "ip_address")
