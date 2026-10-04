"""Two-tier input validation: blockers stop a run, warnings must be acknowledged.

Implements the validation rule catalog from the product plan against the
canonical contract in ``schemas.py``. Pure pandas, no database needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from config import PolicySettings
from schemas import KEY_COLUMNS, PII_HINTS, SCHEMAS

BLOCKER, WARNING, INFO = "BLOCKER", "WARNING", "INFO"


@dataclass
class Issue:
    severity: str
    rule: str
    table: str
    message: str
    examples: List[Any] = field(default_factory=list)


@dataclass
class ValidationReport:
    issues: List[Issue] = field(default_factory=list)
    coverage: Dict[str, float] = field(default_factory=dict)

    def add(self, severity: str, rule: str, table: str, message: str, examples: Optional[list] = None) -> None:
        self.issues.append(Issue(severity, rule, table, message, (examples or [])[:5]))

    @property
    def blockers(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == BLOCKER]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        """True when a run may start (warnings still need acknowledgement)."""
        return not self.blockers

    def summary(self) -> str:
        return f"{len(self.blockers)} blocker(s), {len(self.warnings)} warning(s)"

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "coverage": self.coverage,
                "issues": [i.__dict__ for i in self.issues]}


def _check_schema(table: str, df: pd.DataFrame, rep: ValidationReport) -> bool:
    """Validate columns, types, nulls, ranges and PII hints. Returns False if unusable."""
    cols = {c.lower() for c in df.columns}
    for hint in PII_HINTS:
        if any(hint in c for c in cols):
            rep.add(BLOCKER, "pii_column", table, f"Column looks like personal data ('{hint}'). Remove it before upload.")
    missing = [f.name for f in SCHEMAS[table] if f.required and f.name not in df.columns]
    if missing:
        rep.add(BLOCKER, "missing_column", table, f"Required column(s) missing or unmapped: {missing}")
        return False
    for f in SCHEMAS[table]:
        if f.name not in df.columns:
            continue
        s = df[f.name]
        if f.required and s.isna().any():
            rep.add(BLOCKER, "null_in_required", table, f"{f.name} has {int(s.isna().sum())} empty value(s).",
                    list(df.index[s.isna()][:5]))
        if f.kind == "date":
            parsed = pd.to_datetime(s, errors="coerce", format="mixed")
            bad = parsed.isna() & s.notna()
            if bad.any():
                rep.add(BLOCKER, "unparseable_date", table, f"{int(bad.sum())} unparseable date(s) in {f.name}.", list(s[bad][:5]))
        elif f.kind in ("int", "float"):
            num = pd.to_numeric(s, errors="coerce")
            bad = num.isna() & s.notna()
            if bad.any():
                rep.add(BLOCKER, "non_numeric", table, f"{f.name} has {int(bad.sum())} non-numeric value(s).", list(s[bad][:5]))
            elif f.min_value is not None and (num < f.min_value).any():
                rep.add(BLOCKER, "negative_value", table, f"{f.name} has {int((num < f.min_value).sum())} value(s) below {f.min_value}.",
                        list(s[num < f.min_value][:5]))
    return True


def validate_inputs(platform: pd.DataFrame, mta: pd.DataFrame, holdout: pd.DataFrame,
                    benchmarks: pd.DataFrame, settings: Optional[PolicySettings] = None,
                    declarations: Optional[Dict[str, Any]] = None) -> ValidationReport:
    """Validate the four source tables and return a report of blockers and warnings.

    ``declarations`` may carry ``currency`` (single ISO code); any ``currency``
    column in the data must match it.
    """
    settings = settings or PolicySettings()
    declarations = declarations or {}
    rep = ValidationReport()
    tables = {"RAW_PLATFORM_DATA": platform, "RAW_MTA_OUTPUT": mta,
              "RAW_HOLDOUT_DATA": holdout, "BUSINESS_BENCHMARKS": benchmarks}
    usable = {t: _check_schema(t, df, rep) for t, df in tables.items()}
    if not all(usable.values()) or rep.blockers:
        return rep  # cannot reason about relationships on broken tables

    # Currency: declared once; a data column with other values is a blocker.
    for t, df in tables.items():
        if "currency" in df.columns:
            found = set(df["currency"].dropna().astype(str).str.upper())
            declared = str(declarations.get("currency", "")).upper()
            if len(found) > 1:
                rep.add(BLOCKER, "mixed_currency", t, f"More than one currency in one run: {sorted(found)}.")
            elif declared and found and found != {declared}:
                rep.add(BLOCKER, "currency_mismatch", t, f"Data currency {sorted(found)} differs from declared {declared}.")

    # Duplicate keys.
    for t, keys in (("RAW_PLATFORM_DATA", KEY_COLUMNS), ("RAW_MTA_OUTPUT", KEY_COLUMNS)):
        dup = tables[t].duplicated(keys, keep=False)
        if dup.any():
            rep.add(BLOCKER, "duplicate_key", t, f"{int(dup.sum())} row(s) share the same {keys} key.",
                    tables[t][dup][keys].head(5).values.tolist())

    p = platform.copy()
    p["date"] = pd.to_datetime(p["date"], format="mixed")

    # Plausibility warnings.
    if (p["clicks"] > p["impressions"]).any():
        rep.add(WARNING, "clicks_gt_impressions", "RAW_PLATFORM_DATA", f"{int((p['clicks'] > p['impressions']).sum())} row(s) have clicks above impressions.")
    if (p["reported_conversions"] > p["clicks"]).any():
        rep.add(WARNING, "conversions_gt_clicks", "RAW_PLATFORM_DATA", f"{int((p['reported_conversions'] > p['clicks']).sum())} row(s) have conversions above clicks.")
    med = p.groupby("campaign_id")["spend"].median()
    if len(med) > 1 and med.median() > 0:
        odd = med[(med > 100 * med.median()) | (med < 0.01 * med.median())]
        if len(odd):
            rep.add(WARNING, "spend_unit_suspect", "RAW_PLATFORM_DATA",
                    "Spend for some campaigns is 100x off its peers (dollars vs cents?). Confirm the spend unit.", list(odd.index))
    conv = p["reported_conversions"].sum()
    if conv > 0:
        aov = p["reported_revenue"].sum() / conv
        if not settings.avg_order_value / 5 <= aov <= settings.avg_order_value * 5:
            rep.add(WARNING, "aov_implausible", "RAW_PLATFORM_DATA", f"Revenue per conversion is ${aov:,.2f} vs expected about ${settings.avg_order_value:,.2f}.")

    # Date gaps inside each campaign.
    gaps = []
    for cid, g in p.groupby("campaign_id"):
        expected = (g["date"].max() - g["date"].min()).days + 1
        if g["date"].nunique() < expected:
            gaps.append(cid)
    if gaps:
        rep.add(WARNING, "date_gaps", "RAW_PLATFORM_DATA", f"{len(gaps)} campaign(s) have missing days.", gaps)

    # Cross-source coverage.
    campaigns = set(p["campaign_id"])
    for name, df in (("mta", mta), ("holdout", holdout)):
        covered = campaigns & set(df["campaign_id"])
        pct = len(covered) / len(campaigns) if campaigns else 0.0
        rep.coverage[name] = round(pct, 3)
        if pct < 1.0:
            rep.add(WARNING, f"{name}_coverage_gap", name.upper(),
                    f"{len(campaigns) - len(covered)} platform campaign(s) have no {name} data (shown as unknown, not zero).",
                    sorted(campaigns - covered))
    unmatched = set(holdout["campaign_id"]) - campaigns
    if unmatched:
        rep.add(WARNING, "orphan_holdout_campaigns", "RAW_HOLDOUT_DATA", "Holdout campaigns not found in platform data.", sorted(unmatched))

    # Holdout design: control group, pre-period, sample size.
    groups = set(holdout["group_type"].astype(str).str.lower())
    if not {"control", "treatment"} <= groups:
        rep.add(BLOCKER, "holdout_groups", "RAW_HOLDOUT_DATA", "Holdout needs both 'control' and 'treatment' groups for causal results.")
    else:
        h = holdout.copy()
        h["date"] = pd.to_datetime(h["date"], format="mixed")
        start = h["date"].min()
        pre = h[h["treatment_flag"] == 0] if "treatment_flag" in h else h.iloc[0:0]
        test_days = h[h["treatment_flag"] == 1]["date"].nunique()
        pre_days = pre[pre["group_type"].str.lower() == "treatment"]["date"].nunique()
        if pre_days < settings.min_pre_period_days:
            rep.add(BLOCKER, "pre_period_short", "RAW_HOLDOUT_DATA", f"Pre-period is {pre_days} days; at least {settings.min_pre_period_days} needed for causal results.")
        if test_days < settings.min_test_days:
            rep.add(WARNING, "test_period_short", "RAW_HOLDOUT_DATA", f"Test period is {test_days} days; at least {settings.min_test_days} recommended. Trust tier will be lowered.")
        daily = h.groupby(["campaign_id", "date"])["conversions"].sum().groupby("campaign_id").mean() / 2
        low = daily[daily < settings.min_daily_conversions]
        if len(low):
            rep.add(WARNING, "low_volume", "RAW_HOLDOUT_DATA",
                    f"{len(low)} campaign(s) average under {settings.min_daily_conversions:g} holdout conversions per geo per day; results will be noisy.", list(low.index))
    return rep
