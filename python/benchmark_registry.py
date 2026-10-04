"""Benchmark registry: verified records with provenance, comparability rules and helpers.

Rules that keep benchmarks honest:
  * a record is loaded only if it has a source, a definition and (Tier B) a verbatim quote
  * a record is offered for one of OUR metrics only through the COMPARABILITY table, which says
    whether the definition matches exactly or is a labeled proxy; everything else is "not comparable"
  * every answer carries confidence, sample size, source and staleness, never a bare number
  * margins are an upper bound proxy, never silently applied
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from benchmark_sync import BENCH_DIR, registry_version

STALE_AFTER_DAYS = 548  # about 18 months: warn
EXCLUDE_AFTER_DAYS = 1095  # about 36 months: not offered
REQUIRED_COLUMNS = ["value_id", "tier", "source_id", "metric_id", "geography", "unit", "statistic", "definition_class", "definition", "verification", "confidence"]
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


class RegistryError(ValueError):
    """Raised when the registry files violate the loading rules."""


# our metric -> [(record metric_id, record definition_class, fit, caveat)]
COMPARABILITY: Dict[str, List[Tuple[str, str, str, str]]] = {
    "order_value": [("site_aov_median_usd", "site_aov", "proxy", "Site-wide Shopify median order value, not ad-attributed orders.")],
    "contribution_margin_upper_bound": [("gross_margin_aggregate", "aggregate_public_company_margin", "proxy",
                                         "Aggregate gross margin of US public companies in the industry. A brand's contribution margin is lower (shipping, fees, returns).")],
    "seasonal_index": [("retail_seasonal_index", "nsa_over_sa_ratio", "exact", "U.S. retail trade in aggregate, not your channel or category.")],
    "test_duration_days": [("test_duration_days", "design_parameter", "exact", "Average of Haus Meta geo tests (excluding the post-treatment window).")],
    "kpi_lift_pct": [("meta_lift_primary_kpi_pct", "lift_pct_on_primary_kpi", "proxy", "Meta only, primary business KPI, Haus customers (average spend about $14M a year).")],
    "roi_interval_width": [("roi_ci_width_pp_median", "uncertainty", "exact", "Peer reviewed field experiments with retailers and brokerages (2015).")],
    "ecommerce_share": [("ecommerce_share_of_retail_pct", "ecommerce_share", "exact", "National share of retail, context only.")],
}
# metrics we look for where NO verified record is comparable; used to explain why
NOT_COMPARABLE_NOTES: Dict[str, str] = {
    "ad_click_cvr": "Verified conversion rates are site-wide session conversion rates (Littledata). They are not click-to-purchase rates of paid ads, so they are not comparable.",
    "channel_roas": "No verified primary source for channel ROAS ranges was found. Vendor ranges conflict and publish no method (see excluded_claims.csv).",
    "incrementality_factor": "The only verified incrementality evidence gives relative multipliers and lift on a KPI, not an absolute factor by channel.",
    "cpm": "No verified primary CPM source was found.",
}


@dataclass
class MatchResult:
    our_metric: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    fit: str = "none"  # exact | proxy | none
    reasons: List[str] = field(default_factory=list)
    stale: bool = False

    @property
    def found(self) -> bool:
        return bool(self.records)


def _num(v: Any) -> Optional[float]:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


class Registry:
    def __init__(self, values: pd.DataFrame, sources: pd.DataFrame, evidence: Dict[str, Any], excluded: pd.DataFrame, root: Path, today: Optional[date] = None) -> None:
        self.values, self.sources, self.evidence, self.excluded, self.root = values, sources, evidence, excluded, Path(root)
        self.today = today or datetime.now(timezone.utc).date()
        self.version = registry_version(self.root)
        self._validate()
        self._src = self.sources.set_index("source_id").to_dict("index")
        self._states = self._counties = None

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, root: Path = BENCH_DIR, today: Optional[date] = None) -> "Registry":
        root = Path(root)
        try:
            values = pd.read_csv(root / "values.csv", keep_default_na=True)
            sources = pd.read_csv(root / "sources.csv")
            evidence = json.loads((root / "evidence.json").read_text(encoding="utf-8"))
            excluded = pd.read_csv(root / "excluded_claims.csv")
        except FileNotFoundError as exc:
            raise RegistryError(f"Registry file missing: {exc.filename}. Run python python/benchmark_sync.py sync") from exc
        return cls(values, sources, evidence, excluded, root, today)

    def _validate(self) -> None:
        v = self.values
        missing = [c for c in REQUIRED_COLUMNS if c not in v.columns]
        if missing:
            raise RegistryError(f"values.csv missing columns {missing}")
        if v["value_id"].duplicated().any():
            raise RegistryError("Duplicate value_id in values.csv")
        unknown = set(v["source_id"]) - set(self.sources["source_id"])
        if unknown:
            raise RegistryError(f"Values reference unknown sources: {sorted(unknown)}")
        for _, r in v.iterrows():
            if r["confidence"] not in CONFIDENCE_RANK:
                raise RegistryError(f"{r['value_id']}: invalid confidence '{r['confidence']}'")
            if not str(r["definition"]).strip() or not str(r["verification"]).strip():
                raise RegistryError(f"{r['value_id']}: definition and verification are required")
            if r["tier"] == "B" and (not isinstance(r.get("quote"), str) or len(r["quote"].strip()) < 20):
                raise RegistryError(f"{r['value_id']}: Tier B records need a verbatim quote")
            if isinstance(r.get("quote"), str) and len(r["quote"]) > 460:
                raise RegistryError(f"{r['value_id']}: quote longer than 460 characters (quote briefly)")
            if _num(r["value"]) is None and _num(r.get("low")) is None and r["statistic"] not in ("definition", "qualitative"):
                raise RegistryError(f"{r['value_id']}: no value and no lower bound")
        for _, s in self.sources.iterrows():
            if not str(s["url"]).startswith("http"):
                raise RegistryError(f"{s['source_id']}: url required")

    # ------------------------------------------------------------- record helpers
    def _age_days(self, rec: Dict[str, Any]) -> Optional[int]:
        stamp = rec.get("as_of")
        d: Optional[date] = None
        if isinstance(stamp, str) and stamp[:4].isdigit():
            try:
                d = pd.to_datetime(stamp[:10] if len(stamp) >= 10 else stamp[:7] + "-01").date()
            except (ValueError, TypeError):
                d = None
        if d is None:  # Tier B pages carry no verified date: age from retrieval
            ra = self._src.get(rec["source_id"], {}).get("retrieved_at")
            if isinstance(ra, str) and ra[:4].isdigit():
                d = pd.to_datetime(ra[:10]).date()
        return None if d is None else (self.today - d).days

    def record(self, rec: pd.Series) -> Dict[str, Any]:
        d = {k: (None if isinstance(x, float) and math.isnan(x) else x) for k, x in rec.to_dict().items()}
        s = self._src[d["source_id"]]
        d.update(source_title=s["title"], source_url=s["url"], source_publisher=s["publisher"], source_reliability=s["reliability"],
                 license_note=s["license_note"], age_days=self._age_days(d))
        d["stale"] = d["age_days"] is not None and d["age_days"] > STALE_AFTER_DAYS
        d["expired"] = d["age_days"] is not None and d["age_days"] > EXCLUDE_AFTER_DAYS
        return d

    def records(self, metric_id: Optional[str] = None, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        v = self.values
        if metric_id:
            v = v[v["metric_id"] == metric_id]
        if tier:
            v = v[v["tier"] == tier]
        return [self.record(r) for _, r in v.iterrows()]

    # ------------------------------------------------------- comparability lookup
    def find(self, our_metric: str, vertical: Optional[str] = None, channel: Optional[str] = None, min_confidence: str = "low") -> MatchResult:
        """Verified records that are legitimately comparable to ``our_metric`` (or an explanation of why none are)."""
        res = MatchResult(our_metric)
        rules = COMPARABILITY.get(our_metric)
        if not rules:
            res.reasons.append(NOT_COMPARABLE_NOTES.get(our_metric, f"No verified record is defined as comparable to '{our_metric}'."))
            return res
        floor = CONFIDENCE_RANK[min_confidence]
        for metric_id, dclass, fit, caveat in rules:
            for rec in self.records(metric_id):
                if rec["definition_class"] != dclass or rec["expired"] or CONFIDENCE_RANK[rec["confidence"]] < floor:
                    continue
                if channel and rec.get("channel") and rec["channel"] != channel:
                    continue
                if vertical and rec["vertical"] not in (vertical, "general", "ecommerce_all") and not str(rec["vertical"]).endswith(vertical):
                    continue
                rec["fit"], rec["caveat"] = fit, caveat
                res.records.append(rec)
        if res.records:
            res.fit = "exact" if all(r["fit"] == "exact" for r in res.records) else "proxy"
            res.stale = any(r["stale"] for r in res.records)
            res.reasons.append("Comparable by definition; see each record's caveat." if res.fit == "exact" else "Proxy only: see each record's caveat before relying on it.")
        else:
            res.reasons.append("No verified record matches this definition, vertical and channel.")
        return res

    def not_comparable_examples(self) -> List[Dict[str, str]]:
        """Records that look relevant by name but must not be compared to our metrics, with reasons."""
        out = []
        for key, why in NOT_COMPARABLE_NOTES.items():
            out.append({"our_metric": key, "why_not_comparable": why})
        return out

    # --------------------------------------------------------------- margins
    def industries(self) -> List[str]:
        return sorted(self.values[self.values["metric_id"] == "gross_margin_aggregate"]["entity"].tolist())

    def gross_margin(self, industry: str) -> Dict[str, Any]:
        v = self.values[(self.values["metric_id"] == "gross_margin_aggregate") & (self.values["entity"] == industry)]
        if v.empty:
            raise RegistryError(f"No margin record for industry '{industry}'")
        rec = self.record(v.iloc[0])
        rec["breakeven_iroas_lower_bound"] = 1.0 / rec["value"]
        return rec

    # ------------------------------------------------------------ population
    def _pop(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if self._states is None:
            s = pd.read_csv(self.root / "snapshots" / "census_pep2025_states.csv", encoding="latin-1")
            s = s[s["SUMLEV"] == 40].copy()
            s["fips"] = s["STATE"].astype(int).astype(str).str.zfill(2)
            self._states = s[s["fips"] != "72"][["fips", "NAME", "POPESTIMATE2025"]].rename(columns={"NAME": "name", "POPESTIMATE2025": "pop"})
            c = pd.read_csv(self.root / "snapshots" / "census_pep2025_counties.csv", dtype={"fips": str})
            c["fips"] = c["fips"].str.zfill(5)
            self._counties = c.rename(columns={"pop_2025": "pop"})
        return self._states, self._counties

    def us_population(self) -> int:
        return int(self.values[self.values["value_id"] == "PEP_US_POP_2025"].iloc[0]["value"])

    def population_share(self, fips: Sequence[str]) -> Dict[str, Any]:
        """Share of the US population in the given state (2 digit) and/or county (5 digit) FIPS codes.

        Errors (never guesses): empty list, unknown code, duplicate, or a state together with one of its counties.
        """
        states, counties = self._pop()
        errors: List[str] = []
        codes = [str(f).strip().zfill(2 if len(str(f).strip()) <= 2 else 5) for f in fips if str(f).strip()]
        if not codes:
            errors.append("No geographies given.")
        if len(set(codes)) != len(codes):
            errors.append("A code is listed twice.")
        rows, st_codes = [], set()
        for c in dict.fromkeys(codes):
            if len(c) == 2:
                m = states[states["fips"] == c]
                if m.empty:
                    errors.append(f"Unknown state FIPS '{c}'.")
                else:
                    rows.append((c, m.iloc[0]["name"], int(m.iloc[0]["pop"])))
                    st_codes.add(c)
            elif len(c) == 5:
                m = counties[counties["fips"] == c]
                if m.empty:
                    errors.append(f"Unknown county FIPS '{c}'.")
                else:
                    rows.append((c, f"{m.iloc[0]['county']}, {m.iloc[0]['state']}", int(m.iloc[0]["pop"])))
            else:
                errors.append(f"'{c}' is not a 2 digit state or 5 digit county FIPS code.")
        for c, _, _ in rows:
            if len(c) == 5 and c[:2] in st_codes:
                errors.append(f"County {c} is already inside state {c[:2]}; list one or the other.")
        total = sum(p for _, _, p in rows)
        share = total / self.us_population() if not errors else None
        return {"share": share, "population": total, "geos": [{"fips": c, "name": n, "population": p} for c, n, p in rows], "errors": errors,
                "us_population": self.us_population(), "vintage": "Census Vintage 2025 (July 1, 2025)"}

    # ------------------------------------------------------------ seasonality
    def seasonal_index(self, month: int) -> Dict[str, float]:
        v = self.values[(self.values["metric_id"] == "retail_seasonal_index") & (self.values["entity"] == f"month {month:02d}")]
        r = v.iloc[0]
        return {"mean": float(r["value"]), "low": float(r["low"]), "high": float(r["high"])}

    def _avg_index(self, start: date, end: date) -> float:
        days = pd.date_range(start, end, freq="D")
        return float(sum(self.seasonal_index(d.month)["mean"] for d in days) / len(days))

    def expected_seasonal_drift(self, pre_start: date, pre_end: date, test_start: date, test_end: date) -> Dict[str, Any]:
        """Expected relative change in unadjusted U.S. retail sales from the pre-period to the test period (percent)."""
        pre, test = self._avg_index(pre_start, pre_end), self._avg_index(test_start, test_end)
        return {"expected_drift_pct": (test / pre - 1.0) * 100.0, "pre_index": pre, "test_index": test}
