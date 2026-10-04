"""DuckDB pipeline runner for the MMGE.

Loads the raw CSVs into an in-memory DuckDB database, executes the SQL
pipeline in dependency order (01 -> 05) and exports each analytical view to
``outputs/`` as CSV. The same SQL files run unchanged on Snowflake.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Mapping

import duckdb
import pandas as pd

from config import PolicySettings

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SQL_DIR = ROOT / "sql"
OUTPUT_DIR = ROOT / "outputs"

RAW_TABLES: List[str] = ["RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS"]
SQL_PIPELINE: List[str] = [
    "01_raw_schema.sql",
    "02_staging_transforms.sql",
    "03_analytics_reconciliation.sql",
    "04_governance_queries.sql",
    "05_rolling_performance.sql",
]
# view name -> output CSV file name
OUTPUT_VIEWS: Dict[str, str] = {
    "STG_UNIFIED_MEASUREMENT": "stg_unified_measurement.csv",
    "ANALYTICS_MEASUREMENT_RECONCILIATION": "analytics_measurement_reconciliation.csv",
    "GOVERNANCE_CAMPAIGN_ALERTS": "view_governance_campaign_alerts.csv",
    "ROLLING_7D_PERFORMANCE": "rolling_7d_performance.csv",
    "GOVERNANCE_AUDIT_SUMMARY": "governance_audit_summary.csv",
}


class PipelineIntegrityError(RuntimeError):
    """Raised when a post-build integrity assertion fails."""


class DatabaseManager:
    """Builds and queries the MMGE warehouse in an in-memory DuckDB session."""

    def __init__(self, data_dir: Path = DATA_DIR, sql_dir: Path = SQL_DIR,
                 output_dir: Path = OUTPUT_DIR, settings: Optional[PolicySettings] = None,
                 frames: Optional[Mapping[str, pd.DataFrame]] = None) -> None:
        """``frames`` (table name -> DataFrame) loads uploaded data instead of CSV files."""
        self.settings = settings or PolicySettings()
        self.frames = dict(frames) if frames else None
        self.data_dir = Path(data_dir)
        self.sql_dir = Path(sql_dir)
        self.output_dir = Path(output_dir)
        self.con: duckdb.DuckDBPyConnection = duckdb.connect(database=":memory:")
        self._built = False

    # ------------------------------------------------------------------ build
    def build(self, check_integrity: bool = True) -> "DatabaseManager":
        """Create raw tables, apply policy settings, load CSVs and create all views.

        Raises PipelineIntegrityError if any post-build assertion fails.
        """
        self._run_sql_file(SQL_PIPELINE[0])
        self._apply_settings()
        self._load_raw_tables()
        for name in SQL_PIPELINE[1:]:
            self._run_sql_file(name)
        self._built = True
        if check_integrity:
            failures = self.integrity_failures()
            if failures:
                raise PipelineIntegrityError("; ".join(failures))
        return self

    def _apply_settings(self) -> None:
        s = self.settings
        self.con.execute("DELETE FROM POLICY_PARAMS")
        self.con.execute("INSERT INTO POLICY_PARAMS VALUES (?, ?, ?)",
                         [s.geo_sample_fraction, s.inflation_moderate, s.inflation_critical])

    def integrity_failures(self) -> List[str]:
        """Return human readable descriptions of any failed pipeline assertions."""
        q = lambda sql: self.con.execute(sql).fetchone()[0]  # noqa: E731
        fails: List[str] = []
        raw_rows, stg_rows = q("SELECT COUNT(*) FROM RAW_PLATFORM_DATA"), q("SELECT COUNT(*) FROM STG_UNIFIED_MEASUREMENT")
        if raw_rows != stg_rows:
            fails.append(f"Staging row count {stg_rows} differs from platform rows {raw_rows} (join fan-out or loss)")
        distinct = q("SELECT COUNT(*) FROM (SELECT DISTINCT date, channel, campaign_id FROM STG_UNIFIED_MEASUREMENT)")
        if distinct != stg_rows:
            fails.append("Staging grain (date, channel, campaign_id) is not unique")
        raw_spend, stg_spend = q("SELECT SUM(spend) FROM RAW_PLATFORM_DATA"), q("SELECT SUM(platform_spend) FROM STG_UNIFIED_MEASUREMENT")
        rec_spend = q("SELECT SUM(total_spend) FROM ANALYTICS_MEASUREMENT_RECONCILIATION")
        if raw_spend is not None and (abs(float(raw_spend) - float(stg_spend)) > 0.01 or abs(float(raw_spend) - float(rec_spend)) > 0.05 * max(1, q("SELECT COUNT(*) FROM ANALYTICS_MEASUREMENT_RECONCILIATION"))):
            fails.append("Spend total changed between raw, staging and reconciliation layers")
        if q("SELECT COUNT(*) FROM STG_UNIFIED_MEASUREMENT WHERE platform_spend < 0 OR platform_revenue < 0"):
            fails.append("Negative spend or revenue present in staging")
        return fails

    def _run_sql_file(self, file_name: str) -> None:
        path = self.sql_dir / file_name
        if not path.exists():
            raise FileNotFoundError(f"SQL file missing: {path}")
        # Drop full line comments so semicolons inside them cannot split statements.
        text = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                         if not l.strip().startswith("--"))
        for stmt in (s.strip() for s in text.split(";")):
            if stmt:
                self.con.execute(stmt)

    def _load_raw_tables(self) -> None:
        if self.frames is not None:
            for table in RAW_TABLES:
                if table not in self.frames:
                    raise ValueError(f"Missing source table: {table}")
                cols = [r[0] for r in self.con.execute(f"DESCRIBE {table}").fetchall()]
                df = self.frames[table]
                absent = [c for c in cols if c not in df.columns]
                if absent:
                    raise ValueError(f"{table} is missing columns {absent}")
                self.con.register("_incoming", df[cols])
                self.con.execute(f"INSERT INTO {table} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM _incoming")
                self.con.unregister("_incoming")
            return
        for table in RAW_TABLES:
            csv_path = self.data_dir / f"{table}.csv"
            if not csv_path.exists():
                raise FileNotFoundError(
                    f"Raw file missing: {csv_path}. Run python data/generate_synthetic_data.py")
            self.con.execute(
                f"INSERT INTO {table} SELECT * FROM read_csv('{csv_path.as_posix()}', header=true)")

    # ----------------------------------------------------------------- access
    def query(self, sql: str) -> pd.DataFrame:
        """Run SQL and return a DataFrame (builds the pipeline on first use)."""
        if not self._built:
            self.build()
        return self.con.execute(sql).fetchdf()

    def view_query(self, sql: str) -> pd.DataFrame:
        """Alias of :meth:`query` for ad hoc read-only SQL."""
        return self.query(sql)

    def view(self, name: str) -> pd.DataFrame:
        """Return an entire table or view by name."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid object name: {name!r}")
        return self.query(f"SELECT * FROM {name}")

    def export_outputs(self) -> Dict[str, Path]:
        """Write every pipeline view to ``outputs/`` and return the file paths."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, Path] = {}
        for view, file_name in OUTPUT_VIEWS.items():
            df = self.view(view)
            if view in ("STG_UNIFIED_MEASUREMENT", "ROLLING_7D_PERFORMANCE"):
                df = df.sort_values(["date", "campaign_id"]).reset_index(drop=True)
            else:
                df = df.sort_values(["channel"] + (["campaign_id"] if "campaign_id" in df else []))
                df = df.reset_index(drop=True)
            out = self.output_dir / file_name
            df.to_csv(out, index=False)
            written[view] = out
        return written

    def close(self) -> None:
        self.con.close()


def main(output_dir: Optional[Path] = None) -> None:
    """Build the warehouse, export outputs and print the governance alerts."""
    mgr = DatabaseManager(output_dir=output_dir or OUTPUT_DIR).build()
    for view, path in mgr.export_outputs().items():
        print(f"{view:<40} -> {path.relative_to(ROOT)}")
    print("\n=== GOVERNANCE CAMPAIGN ALERTS ===")
    print(mgr.view("GOVERNANCE_CAMPAIGN_ALERTS").to_string(index=False))
    mgr.close()


if __name__ == "__main__":
    main()
