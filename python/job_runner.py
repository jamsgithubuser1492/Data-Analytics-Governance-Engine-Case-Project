"""Background job runner: submit, poll, wait. Concurrency limited, never inline.

Runs execute in a small thread pool (Stage A). The store holds the status
(queued, running, succeeded, failed) so the UI only ever polls by run id.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, Optional

from config import PolicySettings
from pipeline import SourceTables, ValidationBlocked, code_fingerprint, run_key, run_pipeline
from run_store import FAILED, QUEUED, RUNNING, SUCCEEDED, SqlRunStore
from validation import validate_inputs


class JobRunner:
    def __init__(self, store: SqlRunStore, max_workers: int = 1) -> None:
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="mmge-run")
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()

    def submit(self, workspace_id: str, inputs: SourceTables, settings: Optional[PolicySettings] = None,
               declarations: Optional[Dict[str, Any]] = None, label: str = "") -> str:
        """Queue a run and return its id. Identical inputs return the existing run.

        Raises ValidationBlocked before anything is stored if inputs have blockers.
        """
        settings = settings or PolicySettings()
        declarations = declarations or {}
        report = validate_inputs(inputs.platform, inputs.mta, inputs.holdout, inputs.benchmarks, settings, declarations)
        if not report.ok:
            raise ValidationBlocked(report)
        key = run_key(inputs, settings, declarations)
        run_id, created = self.store.get_or_create_run(workspace_id, key, settings, declarations, inputs.hashes(),
                                                       report.to_dict(), code_fingerprint(), label)
        if created:
            with self._lock:
                self._futures[run_id] = self._pool.submit(self._execute, workspace_id, run_id, inputs, settings, declarations)
        return run_id

    def _execute(self, workspace_id: str, run_id: str, inputs: SourceTables, settings: PolicySettings,
                 declarations: Dict[str, Any]) -> None:
        try:
            self.store.set_status(workspace_id, run_id, RUNNING)
            result = run_pipeline(inputs, settings, declarations)
            self.store.save_result(workspace_id, run_id, result)
        except Exception as exc:  # recorded, never raised into the pool
            self.store.set_status(workspace_id, run_id, FAILED, f"{type(exc).__name__}: {exc}")

    def status(self, workspace_id: str, run_id: str) -> str:
        return self.store.get_run(workspace_id, run_id)["status"]

    def wait(self, workspace_id: str, run_id: str, timeout: float = 120.0, poll: float = 0.1) -> str:
        """Block until the run reaches a terminal state (or timeout) and return its status."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.status(workspace_id, run_id)
            if status in (SUCCEEDED, FAILED):
                return status
            time.sleep(poll)
        return self.status(workspace_id, run_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
