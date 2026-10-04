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

    def as_dict(self) -> Dict[str, pd.DataFrame]:
        return dict(zip(TABLE_NAMES, (self.platform, self.mta, self.holdout, self.benchmarks)))

    def hashes(self) -> Dict[str, str]:
        """Content hash per table, independent of row order and index."""
        out = {}
        for name, df in self.as_dict().items():
            canon = df.reindex(sorted(df.columns), axis=1).sort_values(sorted(df.columns)).reset_index(drop=True)
            out[name] = hashlib.sha256(canon.to_csv(index=False).encode()).hexdigest()[:16]
        return out

    @classmethod
    def from_directory(cls, directory: Path = DATA_DIR) -> "SourceTables":
        d = Path(directory)
        return cls(*(pd.read_csv(d / f"{n}.csv") for n in TABLE_NAMES))


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
    finally:
        mgr.close()
    audit["agent_context"] = {"fingerprint": fingerprint(definitions),
                              "definitions": [{"id": d["id"], "version": d.get("version", 1), "enabled": d.get("enabled", True)} for d in definitions],
                              "previously_active": sorted(f"{a}|{c}" for a, c in (previously_active or set()))}
    audit["declarations"] = declarations
    audit["validation"] = report.to_dict()
    return RunResult(tables, audit, packets, report, settings, declarations, code_fingerprint())
