"""Single entry point: source tables in, immutable RunResult out.

``run_pipeline`` validates the inputs, builds an isolated in-memory DuckDB for
this run, asserts pipeline integrity, runs the causal estimates, audit, strict
lift and trust gated agents, and returns every output as DataFrames.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from agent_engine import build_facts, default_definitions, evaluate_agents, fingerprint
from causal_impact_runner import run_all
from config import HEADLINE_STRICT, PolicySettings
from database_manager import DATA_DIR, DatabaseManager
from governance_checker import run_audit
from validation import ValidationReport, validate_inputs

_REGISTRY: Any = None

ROOT = Path(__file__).resolve().parents[1]
TABLE_NAMES = ("RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS")
OUTPUT_VIEWS = ("STG_UNIFIED_MEASUREMENT", "ANALYTICS_MEASUREMENT_RECONCILIATION", "GOVERNANCE_CAMPAIGN_ALERTS",
                "GOVERNANCE_AUDIT_SUMMARY", "ROLLING_7D_PERFORMANCE")


class ValidationBlocked(ValueError):
    """Raised when input validation finds blockers; carries the report."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("Input validation failed: " + report.summary())
        self.report = report


def get_registry() -> Any:
    """The benchmark registry (loaded once), or None if the registry files are missing or invalid."""
    global _REGISTRY
    if _REGISTRY is None:
        try:
            from benchmark_registry import Registry
            _REGISTRY = Registry.load()
        except Exception:
            return None
    return _REGISTRY


def registry_in_use(settings: PolicySettings, declarations: Optional[Dict[str, Any]]) -> bool:
    """A run depends on the registry only when it uses an industry margin, seasonality or declared test geos."""
    return bool((settings.gross_margin is None and settings.margin_industry) or settings.seasonality_benchmark or (declarations or {}).get("test_geo_fips"))


def benchmark_version_for(settings: PolicySettings, declarations: Optional[Dict[str, Any]]) -> str:
    if not registry_in_use(settings, declarations):
        return ""
    reg = get_registry()
    return reg.version if reg is not None else "unavailable"


def code_fingerprint() -> str:
    """Short hash of the SQL and Python source, so runs record which code produced them."""
    h = hashlib.sha256()
    for f in sorted([*(ROOT / "sql").glob("*.sql"), *(ROOT / "python").glob("*.py")]):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


@dataclass
class SourceTables:
    """The four source tables (already mapped to the canonical column names)."""
    platform: pd.DataFrame
    mta: pd.DataFrame
    holdout: pd.DataFrame
    benchmarks: pd.DataFrame
    audience: Optional[Dict[str, pd.DataFrame]] = None  # optional aggregate audience layer (see audience_tiers.py)

    def as_dict(self) -> Dict[str, pd.DataFrame]:
        return dict(zip(TABLE_NAMES, (self.platform, self.mta, self.holdout, self.benchmarks)))

    def hashes(self) -> Dict[str, str]:
        """Content hash per table, independent of row order and index."""
        out = {}
        for name, df in self.as_dict().items():
            canon = df.reindex(sorted(df.columns), axis=1).sort_values(sorted(df.columns)).reset_index(drop=True)
            out[name] = hashlib.sha256(canon.to_csv(index=False).encode()).hexdigest()[:16]
        for name, df in sorted((self.audience or {}).items()):
            canon = df.reindex(sorted(df.columns), axis=1).sort_values(sorted(df.columns)).reset_index(drop=True)
            out[name] = hashlib.sha256(canon.to_csv(index=False).encode()).hexdigest()[:16]
        return out

    @classmethod
    def from_directory(cls, directory: Path = DATA_DIR, with_audience: bool = False) -> "SourceTables":
        d = Path(directory)
        t = cls(*(pd.read_csv(d / f"{n}.csv") for n in TABLE_NAMES))
        if with_audience:
            from audience_tiers import load_demo_audience
            t.audience = load_demo_audience()
        return t

    @classmethod
    def from_store(cls, load: Any) -> "SourceTables":
        """Rebuild the inputs of a stored run from a loader ``load(table_name)`` (used to re-run under another policy)."""
        t = cls(*(load(f"INPUT_{n}") for n in TABLE_NAMES))
        from schemas import AUDIENCE_TABLES
        try:
            t.audience = {n: load(f"INPUT_{n}") for n in AUDIENCE_TABLES}
        except Exception:
            t.audience = None
        return t


@dataclass
class RunResult:
    """Everything a run produces."""
    tables: Dict[str, pd.DataFrame]
    audit: Dict[str, Any]
    packets: List[Dict[str, Any]]
    validation: ValidationReport
    settings: PolicySettings
    declarations: Dict[str, Any] = field(default_factory=dict)
    code_version: str = ""


def audience_packets(definitions: List[Dict[str, Any]], aud: Dict[str, pd.DataFrame], settings: PolicySettings,
                     previously_active: Optional[Set[Tuple[str, str]]] = None) -> List[Dict[str, Any]]:
    """Guardrail packets for audience tiers. Thresholds come from the policy settings so Settings is the single source of truth."""
    import copy
    from agent_presets import AUDIENCE_RULE_IDS
    from audience_tiers import tier_facts
    defs = []
    for d in definitions:
        if d["id"] in AUDIENCE_RULE_IDS:
            d = copy.deepcopy(d)
            d["min_spend"] = settings.tier_min_spend
            for c in d["trigger"]["all"]:
                if c["metric"] == "cannibalization_pct":
                    c["value"] = settings.cannibalization_critical_threshold
            defs.append(d)
    table = aud["AUDIENCE_TIER_RESULTS"]
    if not defs or table.empty:
        return []
    out = evaluate_agents(defs, tier_facts(table), previously_active)
    keyed = table.assign(_key=table["campaign_id"] + "|" + table["tier_name"]).set_index("_key")
    for p in out:
        r = keyed.loc[p["campaign_id"]]
        match = aud["AUDIENCE_MATCH_QUALITY"]
        mrow = match[match["channel"] == r["channel"]]
        p["tier_name"], p["audience_tier"], p["campaign_ref"] = r["tier_name"], True, r["campaign_id"]
        p["audience_checks"] = [
            ["Enough people and conversions were measured in both the test and control markets", bool(r["sample_ok"])],
            ["The share caused by ads is known within a narrow range", bool(r["range_width"] <= settings.tier_max_range_width)],
            ["The control markets match the test markets on sales history and audience mix", bool(len(mrow) and mrow.iloc[0]["passed"])],
            ["Spend is large enough to be worth acting on", bool(r["spend"] >= settings.tier_min_spend)]]
        p["audience_range"] = [float(r["strict_iroas_low"]), float(r["strict_iroas_high"])]
        p["reported_roas"], p["strict_iroas"] = float(r["reported_roas"]), float(r["strict_iroas"])
    return out


def run_key(inputs: SourceTables, settings: PolicySettings, declarations: Optional[Dict[str, Any]] = None,
            agents_fingerprint: str = "", previous_run_id: str = "", benchmark_version: str = "") -> str:
    """Deterministic key: same inputs, settings, declarations, agent definitions and code give the same run.

    ``previous_run_id`` is only supplied when an agent uses a deadband (its result then depends on history).
    """
    payload = json.dumps({"inputs": inputs.hashes(), "settings": settings.to_dict(), "declarations": declarations or {},
                          "code": code_fingerprint(), "agents": agents_fingerprint, "previous": previous_run_id, "benchmarks": benchmark_version}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def run_pipeline(inputs: SourceTables, settings: Optional[PolicySettings] = None,
                 declarations: Optional[Dict[str, Any]] = None,
                 agent_definitions: Optional[List[Dict[str, Any]]] = None,
                 previously_active: Optional[Set[Tuple[str, str]]] = None,
                 registry: Any = None) -> RunResult:
    """Validate, build, audit and gate. Raises ValidationBlocked if blockers exist.

    ``agent_definitions`` defaults to the built-in presets; ``previously_active`` feeds agent deadbands.
    """
    settings = settings or PolicySettings()
    declarations = declarations or {}
    if registry is None and registry_in_use(settings, declarations):
        registry = get_registry()
        if registry is None and settings.margin_industry and settings.gross_margin is None:
            raise ValueError("An industry margin was requested but the benchmark registry is not available. Run python python/benchmark_sync.py sync")
    report = validate_inputs(inputs.platform, inputs.mta, inputs.holdout, inputs.benchmarks, settings, declarations, registry)
    if not report.ok:
        raise ValidationBlocked(report)
    mgr = DatabaseManager(settings=settings, frames=inputs.as_dict()).build()
    try:
        tables = {name: mgr.view(name) for name in OUTPUT_VIEWS}
        tables.update({f"INPUT_{k}": v for k, v in inputs.as_dict().items()})  # kept so a run can be re-run under another policy
        tables["CAUSAL_IMPACT"] = run_all(mgr.view("RAW_HOLDOUT_DATA"), settings.pre_period_days)
        audit = run_audit(mgr, settings, registry, declarations)
        definitions = agent_definitions if agent_definitions is not None else default_definitions()
        facts = build_facts(tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], audit, settings.headline_metric == HEADLINE_STRICT)
        packets = evaluate_agents(definitions, facts, previously_active)
        if inputs.audience:
            from audience_tiers import compute, summary, tier_facts, validate_audience
            arep = validate_audience(inputs.audience, settings)
            if not arep.ok:
                raise ValidationBlocked(arep)
            report.issues.extend(arep.issues)
            econ = audit.get("economics") or {}
            aud = compute(inputs.audience, settings, econ.get("breakeven_iroas") or 1.0)
            tables.update(aud)
            tables.update({f"INPUT_{k}": v for k, v in inputs.audience.items()})
            audit["audience"] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in summary(aud["AUDIENCE_TIER_RESULTS"], settings).items() if k != "top"}
            packets = packets + audience_packets(definitions, aud, settings, previously_active)
    finally:
        mgr.close()
    audit["agent_context"] = {"fingerprint": fingerprint(definitions),
                              "definitions": [{"id": d["id"], "version": d.get("version", 1), "enabled": d.get("enabled", True)} for d in definitions],
                              "previously_active": sorted(f"{a}|{c}" for a, c in (previously_active or set()))}
    audit["declarations"] = declarations
    audit["validation"] = report.to_dict()
    return RunResult(tables, audit, packets, report, settings, declarations, code_fingerprint())
