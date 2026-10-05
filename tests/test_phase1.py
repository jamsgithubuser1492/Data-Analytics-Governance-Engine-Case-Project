"""Phase 1 tests: pipeline, run store, job runner, inbox lifecycle, comparison, concurrency."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

sys.path.insert(0, str(ROOT / "tests"))
from helpers import sign_for_test  # noqa: E402
from config import HEADLINE_STRICT, PolicySettings  # noqa: E402
from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables, ValidationBlocked, run_key, run_pipeline  # noqa: E402
from run_compare import compare_runs  # noqa: E402
from run_store import (FAILED, LocalArtifactStorage, LocalRunStore, PostgresRunStore, SUCCEEDED,  # noqa: E402
                       StoreError)


@pytest.fixture()
def store(tmp_path: Path) -> LocalRunStore:
    return LocalRunStore(tmp_path / "store")


@pytest.fixture(scope="module")
def tables() -> SourceTables:
    return SourceTables.from_directory()


# ---------------------------------------------------------------- pipeline
def test_pipeline_golden_numbers(tables) -> None:
    r = run_pipeline(tables)
    a = r.tables["GOVERNANCE_AUDIT_SUMMARY"]
    assert a["total_spend"].sum() == pytest.approx(748140.42, abs=0.05)
    assert a["total_holdout_revenue"].sum() == pytest.approx(2490562.50, abs=0.05)
    assert len(r.packets) == 6 and r.audit["campaigns_audited"] == 8
    assert "CAUSAL_IMPACT" in r.tables and r.audit["validation"]["ok"]


def test_pipeline_blocks_on_bad_input(tables) -> None:
    bad = SourceTables(tables.platform.drop(columns=["spend"]), tables.mta, tables.holdout, tables.benchmarks)
    with pytest.raises(ValidationBlocked) as e:
        run_pipeline(bad)
    assert e.value.report.blockers


def test_run_key_stable_and_sensitive(tables) -> None:
    shuffled = SourceTables(tables.platform.sample(frac=1, random_state=1), tables.mta, tables.holdout, tables.benchmarks)
    s = PolicySettings()
    assert run_key(tables, s) == run_key(shuffled, s)  # row order does not matter
    assert run_key(tables, s) != run_key(tables, PolicySettings(headline_metric=HEADLINE_STRICT))
    assert run_key(tables, s) != run_key(tables, s, {"currency": "EUR"})
    changed = tables.platform.copy()
    changed.loc[0, "spend"] += 1
    assert run_key(tables, s) != run_key(SourceTables(changed, tables.mta, tables.holdout, tables.benchmarks), s)


# ------------------------------------------------------------------- store
def test_job_runs_and_is_idempotent(store, tables) -> None:
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    r1 = j.submit(ws, tables, label="march")
    assert j.wait(ws, r1) == SUCCEEDED
    assert j.submit(ws, tables) == r1  # identical inputs return the same run
    assert len(store.list_runs(ws)) == 1
    run = store.get_run(ws, r1)
    assert run["settings_fingerprint"] == PolicySettings().fingerprint() and run["label"] == "march"
    assert set(run["manifest"]) >= {"ANALYTICS_MEASUREMENT_RECONCILIATION", "CAUSAL_IMPACT"}
    assert len(store.load_table(ws, r1, "ANALYTICS_MEASUREMENT_RECONCILIATION")) == 8
    assert store.load_audit(ws, r1)["campaigns_audited"] == 8
    j.shutdown()


def test_validation_blockers_never_create_a_run(store, tables) -> None:
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    bad = tables.platform.copy()
    bad.loc[0, "spend"] = -1
    with pytest.raises(ValidationBlocked):
        j.submit(ws, SourceTables(bad, tables.mta, tables.holdout, tables.benchmarks))
    assert store.list_runs(ws) == []
    j.shutdown()


def test_failed_run_recorded_without_partial_outputs_and_retry(store, tables, monkeypatch) -> None:
    import job_runner
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    monkeypatch.setattr(job_runner, "run_pipeline", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rid = j.submit(ws, tables)
    assert j.wait(ws, rid) == FAILED and "boom" in store.get_run(ws, rid)["error"]
    run_dir = store.artifacts._run_dir(ws, rid)
    assert not run_dir.exists()
    assert not any(p.name.startswith(".tmp") for p in run_dir.parent.glob("*")) if run_dir.parent.exists() else True
    monkeypatch.undo()
    assert j.submit(ws, tables) == rid  # failed runs are retried under the same id
    assert j.wait(ws, rid) == SUCCEEDED
    j.shutdown()


def test_atomic_commit_cleans_up_on_error(tmp_path) -> None:
    st = LocalArtifactStorage(tmp_path)
    with pytest.raises(Exception):
        st.commit_run("w", "r", {"ok": pd.DataFrame({"a": [1]}), "bad": "not a dataframe"}, {})
    base = tmp_path / "workspaces" / "w" / "runs"
    assert not (base / "r").exists() and not list(base.glob(".tmp*"))


def test_workspace_isolation(store, tables) -> None:
    a, b = store.get_or_create_workspace("a"), store.get_or_create_workspace("b")
    j = JobRunner(store)
    rid = j.submit(a, tables)
    j.wait(a, rid)
    with pytest.raises(StoreError):
        store.get_run(b, rid)
    with pytest.raises(StoreError):
        store.load_table(b, rid, "ANALYTICS_MEASUREMENT_RECONCILIATION")
    assert store.list_runs(b) == [] and store.list_inbox(b) == []
    item = store.list_inbox(a)[0]
    with pytest.raises(StoreError):
        store.transition_inbox(b, item["id"], "approved", "mallory")
    assert store.get_or_create_workspace("a") == a  # stable ids
    j.shutdown()


def test_config_and_mapping_versions(store) -> None:
    ws = store.get_or_create_workspace("acme")
    assert store.latest_workspace_config(ws)[2] == 0
    store.save_workspace_config(ws, PolicySettings(), {"currency": "USD"})
    v2 = store.save_workspace_config(ws, PolicySettings(headline_metric=HEADLINE_STRICT), {"currency": "EUR"})
    s, d, v = store.latest_workspace_config(ws)
    assert v == v2 == 2 and s.headline_metric == HEADLINE_STRICT and d == {"currency": "EUR"}
    assert store.get_mapping_profile(ws, "meta") is None
    store.save_mapping_profile(ws, "meta", {"Cost": "spend"})
    assert store.save_mapping_profile(ws, "meta", {"Cost": "spend", "Day": "date"}) == 2
    assert store.get_mapping_profile(ws, "meta")["mapping"] == {"Cost": "spend", "Day": "date"}


# ------------------------------------------------------------------ inbox
def test_inbox_lifecycle_and_audit_log(store, tables) -> None:
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    rid = j.submit(ws, tables)
    j.wait(ws, rid)
    items = store.list_inbox(ws, rid)
    assert len(items) == 6 and all(i["status"] == "new" for i in items)
    it = items[0]["id"]
    with pytest.raises(StoreError):
        store.transition_inbox(ws, it, "executed", "jim")  # cannot execute without approval
    store.transition_inbox(ws, it, "reviewed", "jim")
    with pytest.raises(StoreError):
        store.transition_inbox(ws, it, "approved", "jim", "ok")  # an unsigned approval is refused
    sign_for_test(store, ws, it)
    assert store.get_inbox_item(ws, it)["status"] == "approved"
    store.transition_inbox(ws, it, "executed", "jim")
    with pytest.raises(StoreError):
        store.transition_inbox(ws, it, "dismissed", "jim")  # terminal
    events = [e["event"] for e in store.list_audit_events(ws, rid)]
    assert events.count("inbox_approved") == 1 and "inbox_executed" in events and "run_created" in events
    j.shutdown()


def test_newer_run_supersedes_open_items(store, tables) -> None:
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    r1 = j.submit(ws, tables)
    j.wait(ws, r1)
    first = store.list_inbox(ws, r1)
    sign_for_test(store, ws, first[0]["id"])
    r2 = j.submit(ws, tables, PolicySettings(headline_metric=HEADLINE_STRICT))
    assert j.wait(ws, r2) == SUCCEEDED and r2 != r1
    after = {i["id"]: i["status"] for i in store.list_inbox(ws, r1)}
    assert after[first[0]["id"]] == "approved"  # approved items are kept
    superseded = [i for i in store.list_inbox(ws, r1) if i["status"] == "superseded"]
    assert superseded  # open ones for the same agent and campaign are superseded
    j.shutdown()


# ---------------------------------------------------------------- compare
def test_compare_runs(store, tables) -> None:
    ws, j = store.get_or_create_workspace("acme"), JobRunner(store)
    r1 = j.submit(ws, tables)
    r2 = j.submit(ws, tables, PolicySettings(headline_metric=HEADLINE_STRICT))
    j.wait(ws, r1), j.wait(ws, r2)
    cmp = compare_runs(store, ws, r1, r2)
    assert len(cmp["campaigns"]) == 8 and (cmp["campaigns"]["total_spend_delta"].abs() < 1e-6).all()
    assert any("SCALE_OPPORTUNITY_AGENT" in x for x in cmp["agents_cleared"])  # strict view clears scale agents
    assert any("CAPITAL_PRESERVATION_AGENT" in x for x in cmp["agents_added"])
    j.shutdown()


# ------------------------------------------------------------ concurrency
def test_concurrent_submissions_no_collisions(store, tables) -> None:
    ws = store.get_or_create_workspace("acme")
    j = JobRunner(store, max_workers=3)
    variants = [PolicySettings(inflation_moderate=1.5 + i * 0.01) for i in range(5)]
    ids, errors = [], []

    def go(s):
        try:
            ids.append(j.submit(ws, tables, s))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=go, args=(s,)) for s in variants for _ in range(2)]  # duplicates too
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(set(ids)) == 5  # duplicate submissions collapse to one run each
    assert all(j.wait(ws, r, 120) == SUCCEEDED for r in set(ids))
    assert len(store.list_runs(ws)) == 5
    assert all(len(store.load_table(ws, r, "STG_UNIFIED_MEASUREMENT")) == 720 for r in set(ids))
    j.shutdown()


def test_postgres_store_translates_placeholders() -> None:
    class Fake(PostgresRunStore):
        def __init__(self):  # skip DB setup
            pass
    assert Fake()._sql("SELECT ? , ?") == "SELECT %s , %s"
