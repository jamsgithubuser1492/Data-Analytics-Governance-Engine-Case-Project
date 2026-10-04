"""Run store: workspaces, immutable runs, inbox, audit log, settings and mapping profiles.

Metadata lives in a SQL database; run artifacts (Parquet) live in an artifact
storage. ``LocalRunStore`` (SQLite WAL plus a local folder) is the default.
``PostgresRunStore`` is the same code against Postgres; it needs a connection
factory and has not been exercised against a live database yet.

Design rules: every query is scoped by workspace id; runs are written once and
committed atomically; the idempotent run key makes resubmission a no-op.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import duckdb
import pandas as pd

from agent_engine import default_definitions
from agent_schema import validate_definition
from config import PolicySettings
from pipeline import RunResult

QUEUED, RUNNING, SUCCEEDED, FAILED = "queued", "running", "succeeded", "failed"
INBOX_NEW, INBOX_REVIEWED, INBOX_APPROVED = "new", "reviewed", "approved"
INBOX_EXECUTED, INBOX_DISMISSED, INBOX_SUPERSEDED = "executed", "dismissed", "superseded"
TRANSITIONS = {
    INBOX_NEW: {INBOX_REVIEWED, INBOX_APPROVED, INBOX_DISMISSED},
    INBOX_REVIEWED: {INBOX_APPROVED, INBOX_DISMISSED},
    INBOX_APPROVED: {INBOX_EXECUTED, INBOX_DISMISSED},
}  # executed, dismissed and superseded are terminal; execution always requires prior approval


class StoreError(RuntimeError):
    """Raised for invalid store operations (unknown run, bad transition, cross workspace access)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _uid() -> str:
    return uuid.uuid4().hex[:16]


# ----------------------------------------------------------------- artifact storage
class ArtifactStorage(ABC):
    """Where Parquet run artifacts live (local folder now; object storage later)."""

    @abstractmethod
    def commit_run(self, workspace_id: str, run_id: str, tables: Dict[str, pd.DataFrame],
                   json_docs: Dict[str, Any]) -> List[str]:
        """Write all artifacts atomically; return the table names written."""

    @abstractmethod
    def read_table(self, workspace_id: str, run_id: str, name: str) -> pd.DataFrame: ...

    @abstractmethod
    def read_json(self, workspace_id: str, run_id: str, name: str) -> Any: ...


class LocalArtifactStorage(ArtifactStorage):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, workspace_id: str, run_id: str) -> Path:
        return self.root / "workspaces" / workspace_id / "runs" / run_id

    def commit_run(self, workspace_id, run_id, tables, json_docs):
        final = self._run_dir(workspace_id, run_id)
        tmp = final.parent / f".tmp-{run_id}-{_uid()}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            con = duckdb.connect(":memory:")
            for name, df in tables.items():
                con.register("_t", df)
                con.execute(f"COPY _t TO '{(tmp / (name + '.parquet')).as_posix()}' (FORMAT PARQUET)")
                con.unregister("_t")
            con.close()
            for name, doc in json_docs.items():
                (tmp / f"{name}.json").write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
            if final.exists():
                shutil.rmtree(final)
            os.replace(tmp, final)  # atomic commit
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return sorted(tables)

    def read_table(self, workspace_id, run_id, name):
        path = self._run_dir(workspace_id, run_id) / f"{name}.parquet"
        if not path.exists():
            raise StoreError(f"No table {name} for run {run_id}")
        return duckdb.connect(":memory:").execute(f"SELECT * FROM read_parquet('{path.as_posix()}')").fetchdf()

    def read_json(self, workspace_id, run_id, name):
        path = self._run_dir(workspace_id, run_id) / f"{name}.json"
        if not path.exists():
            raise StoreError(f"No document {name} for run {run_id}")
        return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------- SQL run store
SCHEMA = [
    "CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, name TEXT UNIQUE, created_at TEXT)",
    """CREATE TABLE IF NOT EXISTS workspace_config (workspace_id TEXT, version INTEGER, settings_json TEXT,
       declarations_json TEXT, created_at TEXT, PRIMARY KEY (workspace_id, version))""",
    """CREATE TABLE IF NOT EXISTS mapping_profiles (workspace_id TEXT, name TEXT, version INTEGER,
       mapping_json TEXT, created_at TEXT, PRIMARY KEY (workspace_id, name, version))""",
    """CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, workspace_id TEXT, run_key TEXT, label TEXT, status TEXT,
       error TEXT, settings_fingerprint TEXT, settings_json TEXT, declarations_json TEXT, input_hashes_json TEXT,
       validation_json TEXT, code_version TEXT, manifest_json TEXT, created_at TEXT, finished_at TEXT,
       UNIQUE (workspace_id, run_key))""",
    """CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, workspace_id TEXT, run_id TEXT, dedupe_key TEXT,
       agent_id TEXT, campaign_id TEXT, severity TEXT, packet_json TEXT, status TEXT, created_at TEXT,
       updated_at TEXT, UNIQUE (workspace_id, dedupe_key))""",
    """CREATE TABLE IF NOT EXISTS agent_definitions (workspace_id TEXT, agent_id TEXT, version INTEGER,
       definition_json TEXT, enabled INTEGER, actor TEXT, created_at TEXT, PRIMARY KEY (workspace_id, agent_id, version))""",
    """CREATE TABLE IF NOT EXISTS memos (id TEXT PRIMARY KEY, workspace_id TEXT, run_id TEXT, item_id TEXT, writer TEXT,
       model TEXT, ai_drafted INTEGER, status TEXT, facts_json TEXT, facts_text_json TEXT, text_cited TEXT, text_clean TEXT,
       verification_json TEXT, attempts_json TEXT, fallback_reason TEXT, prompt_hash TEXT, created_at TEXT, updated_at TEXT,
       approved_by TEXT, approved_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY, workspace_id TEXT, run_id TEXT, item_id TEXT,
       event TEXT, actor TEXT, detail_json TEXT, created_at TEXT)""",
]


class SqlRunStore:
    """Run store over a DB-API connection factory (SQLite or Postgres)."""
    placeholder = "?"

    def __init__(self, connect: Callable[[], Any], artifacts: ArtifactStorage) -> None:
        self._connect = connect
        self.artifacts = artifacts
        self._lock = threading.Lock()
        with self._tx() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)

    # -- plumbing
    def _sql(self, sql: str) -> str:
        return sql.replace("?", self.placeholder) if self.placeholder != "?" else sql

    @contextmanager
    def _tx(self) -> Iterator[Any]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield _Cursor(cur, self)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- workspaces and config
    def get_or_create_workspace(self, name: str) -> str:
        with self._tx() as c:
            row = c.one("SELECT id FROM workspaces WHERE name = ?", (name,))
            if row:
                return row[0]
            wid = _uid()
            try:
                c.run("INSERT INTO workspaces (id, name, created_at) VALUES (?, ?, ?)", (wid, name, _now()))
            except Exception:  # lost a creation race
                row = c.one("SELECT id FROM workspaces WHERE name = ?", (name,))
                if row:
                    return row[0]
                raise
            return wid

    def save_workspace_config(self, workspace_id: str, settings: PolicySettings,
                              declarations: Dict[str, Any]) -> int:
        return _retry_on_conflict(lambda: self._save_workspace_config(workspace_id, settings, declarations))

    def _save_workspace_config(self, workspace_id: str, settings: PolicySettings,
                               declarations: Dict[str, Any]) -> int:
        with self._tx() as c:
            row = c.one("SELECT MAX(version) FROM workspace_config WHERE workspace_id = ?", (workspace_id,))
            version = (row[0] or 0) + 1
            c.run("INSERT INTO workspace_config VALUES (?, ?, ?, ?, ?)",
                  (workspace_id, version, json.dumps(settings.to_dict()), json.dumps(declarations), _now()))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, None, None, "config_saved", "system", json.dumps({"version": version}), _now()))
        return version

    def latest_workspace_config(self, workspace_id: str) -> Tuple[PolicySettings, Dict[str, Any], int]:
        with self._tx() as c:
            row = c.one("""SELECT settings_json, declarations_json, version FROM workspace_config
                           WHERE workspace_id = ? ORDER BY version DESC LIMIT 1""", (workspace_id,))
        if not row:
            return PolicySettings(), {}, 0
        return PolicySettings(**json.loads(row[0])), json.loads(row[1]), int(row[2])

    def save_mapping_profile(self, workspace_id: str, name: str, mapping: Dict[str, Any]) -> int:
        return _retry_on_conflict(lambda: self._save_mapping_profile(workspace_id, name, mapping))

    def _save_mapping_profile(self, workspace_id: str, name: str, mapping: Dict[str, Any]) -> int:
        with self._tx() as c:
            row = c.one("SELECT MAX(version) FROM mapping_profiles WHERE workspace_id = ? AND name = ?", (workspace_id, name))
            version = (row[0] or 0) + 1
            c.run("INSERT INTO mapping_profiles VALUES (?, ?, ?, ?, ?)",
                  (workspace_id, name, version, json.dumps(mapping), _now()))
        return version

    def get_mapping_profile(self, workspace_id: str, name: str) -> Optional[Dict[str, Any]]:
        with self._tx() as c:
            row = c.one("""SELECT mapping_json, version FROM mapping_profiles WHERE workspace_id = ? AND name = ?
                           ORDER BY version DESC LIMIT 1""", (workspace_id, name))
        return None if not row else {"mapping": json.loads(row[0]), "version": int(row[1])}

    # -- runs
    def get_or_create_run(self, workspace_id: str, key: str, settings: PolicySettings, declarations: Dict[str, Any],
                          input_hashes: Dict[str, str], validation: Dict[str, Any], code_version: str,
                          label: str = "") -> Tuple[str, bool]:
        """Return (run_id, created). Identical inputs reuse the existing run; failed runs are retried.

        Safe under concurrent submissions: a lost insert race re-reads the winner's row.
        """
        return _retry_on_conflict(lambda: self._get_or_create_run(
            workspace_id, key, settings, declarations, input_hashes, validation, code_version, label))

    def _get_or_create_run(self, workspace_id, key, settings, declarations, input_hashes, validation,
                           code_version, label):
        with self._tx() as c:
            row = c.one("SELECT id, status FROM runs WHERE workspace_id = ? AND run_key = ?", (workspace_id, key))
            if row:
                if row[1] == FAILED:
                    c.run("UPDATE runs SET status = ?, error = NULL, finished_at = NULL WHERE id = ?", (QUEUED, row[0]))
                    return row[0], True
                return row[0], False
            rid = _uid()
            c.run("""INSERT INTO runs (id, workspace_id, run_key, label, status, settings_fingerprint, settings_json,
                     declarations_json, input_hashes_json, validation_json, code_version, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (rid, workspace_id, key, label, QUEUED, settings.fingerprint(), json.dumps(settings.to_dict()),
                   json.dumps(declarations), json.dumps(input_hashes), json.dumps(validation, default=str),
                   code_version, _now()))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, rid, None, "run_created", "system", "{}", _now()))
        return rid, True

    def set_status(self, workspace_id: str, run_id: str, status: str, error: Optional[str] = None) -> None:
        with self._tx() as c:
            finished = _now() if status in (SUCCEEDED, FAILED) else None
            n = c.run("UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE id = ? AND workspace_id = ?",
                      (status, error, finished, run_id, workspace_id))
            if n == 0:
                raise StoreError(f"Run {run_id} not found in this workspace")

    def get_run(self, workspace_id: str, run_id: str) -> Dict[str, Any]:
        with self._tx() as c:
            rows = c.all("SELECT * FROM runs WHERE id = ? AND workspace_id = ?", (run_id, workspace_id))
            cols = c.columns
        if not rows:
            raise StoreError(f"Run {run_id} not found in this workspace")
        return self._run_dict(cols, rows[0])

    @staticmethod
    def _run_dict(cols: List[str], row: Any) -> Dict[str, Any]:
        d = dict(zip(cols, row))
        for k in ("settings_json", "declarations_json", "input_hashes_json", "validation_json", "manifest_json"):
            d[k[:-5]] = json.loads(d[k]) if d.get(k) else None
            d.pop(k, None)
        return d

    def list_runs(self, workspace_id: str) -> List[Dict[str, Any]]:
        with self._tx() as c:
            rows = c.all("SELECT * FROM runs WHERE workspace_id = ? ORDER BY created_at DESC, id", (workspace_id,))
            cols = c.columns
        return [self._run_dict(cols, r) for r in rows]

    def save_result(self, workspace_id: str, run_id: str, result: RunResult) -> None:
        """Commit artifacts atomically, then record the manifest, inbox items and SUCCEEDED status."""
        self.get_run(workspace_id, run_id)  # workspace check
        names = self.artifacts.commit_run(workspace_id, run_id, result.tables,
                                          {"audit": result.audit, "packets": result.packets})
        with self._tx() as c:
            c.run("UPDATE runs SET manifest_json = ? WHERE id = ? AND workspace_id = ?",
                  (json.dumps(names), run_id, workspace_id))
            for p in result.packets:
                dedupe = f"{p['agent_id']}|{p['campaign_id']}|{run_id}"
                if c.one("SELECT 1 FROM inbox WHERE workspace_id = ? AND dedupe_key = ?", (workspace_id, dedupe)):
                    continue
                # a newer run's packet supersedes older open ones for the same agent and campaign
                c.run("""UPDATE inbox SET status = ?, updated_at = ? WHERE workspace_id = ? AND agent_id = ? AND
                         campaign_id = ? AND status IN (?, ?) AND run_id <> ?""",
                      (INBOX_SUPERSEDED, _now(), workspace_id, p["agent_id"], p["campaign_id"], INBOX_NEW, INBOX_REVIEWED, run_id))
                c.run("INSERT INTO inbox VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (_uid(), workspace_id, run_id, dedupe, p["agent_id"], p["campaign_id"], p["severity"],
                       json.dumps(p, default=str), INBOX_NEW, _now(), _now()))
        self.set_status(workspace_id, run_id, SUCCEEDED)

    def load_table(self, workspace_id: str, run_id: str, name: str) -> pd.DataFrame:
        self.get_run(workspace_id, run_id)
        return self.artifacts.read_table(workspace_id, run_id, name)

    def load_audit(self, workspace_id: str, run_id: str) -> Dict[str, Any]:
        self.get_run(workspace_id, run_id)
        return self.artifacts.read_json(workspace_id, run_id, "audit")

    # -- agent definitions
    def save_agent_definition(self, workspace_id: str, definition: Dict[str, Any], actor: str = "system") -> Tuple[int, List[str]]:
        """Validate and save a new version. Returns (version, errors); version is 0 when rejected."""
        norm, errs = validate_definition(definition)
        if errs:
            return 0, errs
        version = _retry_on_conflict(lambda: self._save_agent_definition(workspace_id, norm, actor))
        return version, []

    def _save_agent_definition(self, workspace_id: str, d: Dict[str, Any], actor: str) -> int:
        with self._tx() as c:
            row = c.one("SELECT MAX(version) FROM agent_definitions WHERE workspace_id = ? AND agent_id = ?", (workspace_id, d["id"]))
            version = (row[0] or 0) + 1
            if version == 1 and d["id"] in {p["id"] for p in default_definitions()}:
                version = 2  # presets are version 1; the first saved edit is version 2
            stored = {**d, "version": version}
            c.run("INSERT INTO agent_definitions VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (workspace_id, d["id"], version, json.dumps(stored), 1 if d["enabled"] else 0, actor, _now()))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, None, d["id"], "agent_saved", actor, json.dumps({"version": version, "enabled": d["enabled"]}), _now()))
        return version

    def get_agent_definitions(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Latest version of every agent: workspace edits override presets; presets fill the rest."""
        with self._tx() as c:
            rows = c.all("""SELECT a.definition_json FROM agent_definitions a JOIN (
                              SELECT agent_id, MAX(version) AS v FROM agent_definitions WHERE workspace_id = ? GROUP BY agent_id) m
                            ON a.agent_id = m.agent_id AND a.version = m.v WHERE a.workspace_id = ?""", (workspace_id, workspace_id))
        saved = {json.loads(r[0])["id"]: json.loads(r[0]) for r in rows}
        merged = [saved.pop(p["id"], p) for p in default_definitions()]
        return merged + sorted(saved.values(), key=lambda d: (d["priority"], d["id"]))

    def list_agent_versions(self, workspace_id: str, agent_id: str) -> List[Dict[str, Any]]:
        with self._tx() as c:
            rows = c.all("SELECT definition_json, actor, created_at FROM agent_definitions WHERE workspace_id = ? AND agent_id = ? ORDER BY version",
                         (workspace_id, agent_id))
        return [{**json.loads(r[0]), "saved_by": r[1], "saved_at": r[2]} for r in rows]

    def latest_active_set(self, workspace_id: str) -> Tuple[Optional[str], set]:
        """(run_id, {(agent_id, campaign_id)}) for the most recent succeeded run; used for agent deadbands."""
        with self._tx() as c:
            row = c.one("SELECT id FROM runs WHERE workspace_id = ? AND status = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                        (workspace_id, SUCCEEDED))
            if not row:
                return None, set()
            rows = c.all("SELECT agent_id, campaign_id FROM inbox WHERE workspace_id = ? AND run_id = ?", (workspace_id, row[0]))
        return row[0], {(r[0], r[1]) for r in rows}

    # -- memos
    MEMO_TRANSITIONS = {"draft": {"approved"}, "approved": {"exported"}, "exported": {"exported"}}

    def create_memo(self, workspace_id: str, rec: Dict[str, Any], actor: str = "system") -> str:
        with self._tx() as c:
            if not c.one("SELECT 1 FROM runs WHERE id = ? AND workspace_id = ?", (rec["run_id"], workspace_id)):
                raise StoreError("Run not found in this workspace")
            if not c.one("SELECT 1 FROM inbox WHERE id = ? AND workspace_id = ?", (rec["item_id"], workspace_id)):
                raise StoreError("Inbox item not found in this workspace")
            mid, now = _uid(), _now()
            c.run("""INSERT INTO memos (id, workspace_id, run_id, item_id, writer, model, ai_drafted, status, facts_json, facts_text_json,
                     text_cited, text_clean, verification_json, attempts_json, fallback_reason, prompt_hash, created_at, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (mid, workspace_id, rec["run_id"], rec["item_id"], rec["writer"], rec.get("model"), 1 if rec["ai_drafted"] else 0, "draft",
                   json.dumps(rec["facts"]), json.dumps(rec["facts_text"]), rec["text_cited"], rec["text_clean"],
                   json.dumps(rec["verification"]), json.dumps(rec.get("attempts", []), default=str), rec.get("fallback_reason"),
                   rec.get("prompt_hash"), now, now))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, rec["run_id"], mid, "memo_drafted", actor,
                   json.dumps({"writer": rec["writer"], "verified": rec["verification"]["ok"], "fallback": rec.get("fallback_reason")}), now))
        return mid

    @staticmethod
    def _memo_dict(cols: List[str], row: Any) -> Dict[str, Any]:
        d = dict(zip(cols, row))
        for k, name in (("facts_json", "facts"), ("facts_text_json", "facts_text"), ("verification_json", "verification"), ("attempts_json", "attempts")):
            d[name] = json.loads(d.pop(k) or "null")
        d["ai_drafted"] = bool(d["ai_drafted"])
        return d

    def get_memo(self, workspace_id: str, memo_id: str) -> Dict[str, Any]:
        with self._tx() as c:
            rows = c.all("SELECT * FROM memos WHERE id = ? AND workspace_id = ?", (memo_id, workspace_id))
            cols = c.columns
        if not rows:
            raise StoreError("Memo not found in this workspace")
        return self._memo_dict(cols, rows[0])

    def list_memos(self, workspace_id: str, item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM memos WHERE workspace_id = ?", [workspace_id]
        if item_id:
            sql, args = sql + " AND item_id = ?", args + [item_id]
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY created_at DESC, id", tuple(args))
            cols = c.columns
        return [self._memo_dict(cols, r) for r in rows]

    def update_memo_text(self, workspace_id: str, memo_id: str, cited: str, clean: str, verification: Dict[str, Any], actor: str) -> None:
        with self._tx() as c:
            row = c.one("SELECT status, run_id FROM memos WHERE id = ? AND workspace_id = ?", (memo_id, workspace_id))
            if not row:
                raise StoreError("Memo not found in this workspace")
            if row[0] != "draft":
                raise StoreError("Only draft memos can be edited")
            c.run("UPDATE memos SET text_cited = ?, text_clean = ?, verification_json = ?, updated_at = ? WHERE id = ?",
                  (cited, clean, json.dumps(verification), _now(), memo_id))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, row[1], memo_id, "memo_edited", actor, "{}", _now()))

    def transition_memo(self, workspace_id: str, memo_id: str, new_status: str, actor: str) -> None:
        with self._tx() as c:
            row = c.one("SELECT status, run_id, verification_json FROM memos WHERE id = ? AND workspace_id = ?", (memo_id, workspace_id))
            if not row:
                raise StoreError("Memo not found in this workspace")
            if new_status not in self.MEMO_TRANSITIONS.get(row[0], set()):
                raise StoreError(f"Cannot move a memo from {row[0]} to {new_status}")
            if new_status == "approved" and not json.loads(row[2])["ok"]:
                raise StoreError("A memo that failed verification cannot be approved")
            now = _now()
            if new_status == "approved":
                c.run("UPDATE memos SET status = ?, approved_by = ?, approved_at = ?, updated_at = ? WHERE id = ?", (new_status, actor, now, now, memo_id))
            else:
                c.run("UPDATE memos SET status = ?, updated_at = ? WHERE id = ?", (new_status, now, memo_id))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, row[1], memo_id, f"memo_{new_status}", actor, "{}", now))

    def count_ai_memos_today(self, workspace_id: str) -> int:
        today = _now()[:10]
        with self._tx() as c:
            row = c.one("SELECT COUNT(*) FROM memos WHERE workspace_id = ? AND ai_drafted = 1 AND created_at LIKE ?", (workspace_id, today + "%"))
        return int(row[0])

    # -- inbox and audit log
    def list_inbox(self, workspace_id: str, run_id: Optional[str] = None,
                   status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM inbox WHERE workspace_id = ?", [workspace_id]
        if run_id:
            sql, args = sql + " AND run_id = ?", args + [run_id]
        if status:
            sql, args = sql + " AND status = ?", args + [status]
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY created_at, id", tuple(args))
            cols = c.columns
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d["packet"] = json.loads(d.pop("packet_json"))
            out.append(d)
        return out

    def transition_inbox(self, workspace_id: str, item_id: str, new_status: str, actor: str, note: str = "") -> None:
        with self._tx() as c:
            row = c.one("SELECT status, run_id FROM inbox WHERE id = ? AND workspace_id = ?", (item_id, workspace_id))
            if not row:
                raise StoreError("Inbox item not found in this workspace")
            if new_status not in TRANSITIONS.get(row[0], set()):
                raise StoreError(f"Cannot move inbox item from {row[0]} to {new_status}")
            c.run("UPDATE inbox SET status = ?, updated_at = ? WHERE id = ?", (new_status, _now(), item_id))
            c.run("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (_uid(), workspace_id, row[1], item_id, f"inbox_{new_status}", actor, json.dumps({"note": note}), _now()))

    def list_audit_events(self, workspace_id: str, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql, args = "SELECT * FROM audit_events WHERE workspace_id = ?", [workspace_id]
        if run_id:
            sql, args = sql + " AND run_id = ?", args + [run_id]
        with self._tx() as c:
            rows = c.all(sql + " ORDER BY created_at, id", tuple(args))
            cols = c.columns
        return [dict(zip(cols, r)) for r in rows]


def _retry_on_conflict(fn: Callable[[], Any], attempts: int = 4) -> Any:
    """Re-run a read-then-insert transaction when a concurrent writer wins the race."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if "IntegrityError" not in type(exc).__name__ and "UniqueViolation" not in type(exc).__name__ or i == attempts - 1:
                raise
    raise StoreError("unreachable")  # pragma: no cover


class _Cursor:
    """Tiny helper wrapping a DB-API cursor with placeholder translation."""

    def __init__(self, cur: Any, store: SqlRunStore) -> None:
        self.cur, self.store, self.columns = cur, store, []

    def run(self, sql: str, args: tuple = ()) -> int:
        self.cur.execute(self.store._sql(sql), args)
        return self.cur.rowcount

    def one(self, sql: str, args: tuple = ()) -> Any:
        self.run(sql, args)
        return self.cur.fetchone()

    def all(self, sql: str, args: tuple = ()) -> List[Any]:
        self.run(sql, args)
        self.columns = [d[0] for d in self.cur.description]
        return self.cur.fetchall()

    def execute(self, sql: str) -> None:
        self.cur.execute(sql)


class LocalRunStore(SqlRunStore):
    """SQLite (WAL) metadata plus a local artifact folder."""

    def __init__(self, root: Path) -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        db_path = root / "mmge_runs.sqlite"

        def connect() -> sqlite3.Connection:
            conn = sqlite3.connect(db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            return conn

        super().__init__(connect, LocalArtifactStorage(root / "artifacts"))


class PostgresRunStore(SqlRunStore):
    """Same store on Postgres. Needs a connection factory (psycopg) and an ArtifactStorage
    for object storage. NOT yet exercised against a live database."""
    placeholder = "%s"

    def __init__(self, connect: Callable[[], Any], artifacts: ArtifactStorage) -> None:
        super().__init__(connect, artifacts)
