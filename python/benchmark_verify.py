"""Independent verification of the benchmark registry.

offline: re-derive every Tier A value from the stored primary snapshots and compare (detects hand edits and
         corrupted snapshots); re-check all reconciliations; re-check every Tier B record against its claim
         spec (numbers in the quote, value, definition class); check schema, staleness and the exclusion log.
live:    re-fetch the primary sources, compare content hashes and re-check that every quote is still on its page.
         Changed content is reported as DRIFT (a new vintage), not as a failure.

CLI:  python python/benchmark_verify.py [--live]
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from benchmark_registry import EXCLUDE_AFTER_DAYS, STALE_AFTER_DAYS, Registry, RegistryError
from benchmark_sync import (BENCH_DIR, CLAIMS, URLS, extract_quote, fetch, numbers_in, page_text, parse_damodaran, parse_fred,
                            parse_pep_counties, parse_pep_states, seasonal_index, sha)


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | WARN | DRIFT
    detail: str


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def expected_tier_a(root: Path) -> Dict[str, Dict[str, float]]:
    """Recompute every Tier A numeric value from the snapshots alone."""
    snap = root / "snapshots"
    out: Dict[str, Dict[str, float]] = {}
    dam, _ = parse_damodaran((snap / "damodaran_margin.xls").read_bytes())
    for i, r in dam.iterrows():
        out[f"DAM_gross_margin_aggregate_{i:03d}"] = {"value": round(float(r["gross_margin"]), 6), "n": float(r["n_firms"])}
        out[f"DAM_net_margin_aggregate_{i:03d}"] = {"value": round(float(r["net_margin"]), 6), "n": float(r["n_firms"])}
    states = parse_pep_states((snap / "census_pep2025_states.csv").read_bytes())
    out["PEP_US_POP_2025"] = {"value": float(states[states["sumlev"] == 10]["pop_2025"].iloc[0])}
    fred = {s: parse_fred((snap / f"fred_{s}.csv").read_bytes()) for s in ("RSXFS", "RSXFSN", "ECOMPCTSA", "ECOMSA")}
    out["CENSUS_ECOM_PCT_LATEST"] = {"value": float(fred["ECOMPCTSA"].iloc[-1]["value"])}
    out["CENSUS_ECOM_SALES_LATEST"] = {"value": float(fred["ECOMSA"].iloc[-1]["value"]) * 1e6}
    idx = seasonal_index(fred["RSXFS"], fred["RSXFSN"])
    for _, r in idx.iterrows():
        out[f"FRED_RETAIL_SEAS_M{int(r['month']):02d}"] = {"value": round(float(r["mean"]), 5), "low": round(float(r["low"]), 5), "high": round(float(r["high"]), 5)}
    return out


def verify_offline(root: Path = BENCH_DIR) -> List[Check]:
    root = Path(root)
    checks: List[Check] = []

    def add(name: str, ok: bool, detail: str, warn: bool = False) -> None:
        checks.append(Check(name, "PASS" if ok else ("WARN" if warn else "FAIL"), detail))

    try:
        reg = Registry.load(root)
        add("registry_loads_and_validates", True, f"{len(reg.values)} values, {len(reg.sources)} sources, version {reg.version}")
    except RegistryError as exc:
        add("registry_loads_and_validates", False, str(exc))
        return checks
    ev = json.loads((root / "evidence.json").read_text(encoding="utf-8"))["sources"]
    # 1. snapshot integrity
    for key, fname in (("damodaran", "damodaran_margin.xls"), ("pep_states", "census_pep2025_states.csv"), ("fred_RSXFS", "fred_RSXFS.csv"),
                       ("fred_RSXFSN", "fred_RSXFSN.csv"), ("fred_ECOMPCTSA", "fred_ECOMPCTSA.csv"), ("fred_ECOMSA", "fred_ECOMSA.csv")):
        p = root / "snapshots" / fname
        add(f"snapshot_hash_{key}", p.exists() and _sha_file(p) == ev[key]["sha256"], f"{fname} matches the hash recorded at retrieval ({ev[key]['sha256'][:12]})")
    cdf = pd.read_csv(root / "snapshots" / "census_pep2025_counties.csv", dtype={"fips": str})
    add("snapshot_counties_rows", len(cdf) == ev["pep_counties"]["derived_rows"], f"{len(cdf)} county rows")
    # 2. re-derive Tier A and compare
    exp = expected_tier_a(root)
    vals = reg.values.set_index("value_id")
    bad = []
    for vid, e in exp.items():
        if vid not in vals.index:
            bad.append(f"{vid} missing")
            continue
        for k, want in e.items():
            got = vals.loc[vid, k]
            if pd.isna(got) or abs(float(got) - want) > 1e-6 * max(1.0, abs(want)):
                bad.append(f"{vid}.{k}: file {got} vs derived {want}")
    tier_a_ids = set(vals[vals["tier"] == "A"].index)
    extra = tier_a_ids - set(exp)
    for vid in sorted(extra):
        if vid not in ("CENSUS_ECOM_PCT_LATEST", "CENSUS_ECOM_SALES_LATEST"):
            bad.append(f"{vid} is Tier A but cannot be derived from snapshots")
    add("tier_a_rederived_from_snapshots", not bad, f"{len(exp)} Tier A values recomputed from primary snapshots" + (f"; mismatches: {bad[:3]}" if bad else ""))
    # 3. reconciliations
    snap = root / "snapshots"
    dam, updated = parse_damodaran((snap / "damodaran_margin.xls").read_bytes())
    add("damodaran_gm_equals_1_minus_cogs", bool(((dam["gross_margin"] - (1 - dam["cogs_over_sales"])).abs() < 1e-9).all()), "gross margin = 1 - COGS/sales in every industry")
    add("damodaran_gm_not_below_net", bool((dam["gross_margin"] >= dam["net_margin"]).all()), "gross margin >= net margin in every industry")
    add("damodaran_firm_count", int(dam[dam["industry"] == "Total Market"]["n_firms"].iloc[0]) == ev["damodaran"]["total_firms"], "Total Market firm count matches evidence")
    states = parse_pep_states((snap / "census_pep2025_states.csv").read_bytes())
    us = int(states[states["sumlev"] == 10]["pop_2025"].iloc[0])
    st = int(states[(states["sumlev"] == 40) & (states["state_fips"] != "72")]["pop_2025"].sum())
    add("pep_states_sum_to_us", st == us, f"states + DC = {st:,} vs US {us:,}")
    add("pep_counties_sum_to_us", int(cdf["pop_2025"].sum()) == us, f"counties = {int(cdf['pop_2025'].sum()):,} vs US {us:,}")
    add("pep_unique_fips", cdf["fips"].is_unique and cdf["fips"].str.len().eq(5).all(), "county FIPS are unique 5 digit codes")
    f1, f2 = parse_fred((snap / "fred_ECOMPCTSA.csv").read_bytes()), parse_fred((snap / "fred_ECOMSA.csv").read_bytes())
    add("fred_ecommerce_series_end_together", f1["date"].iloc[-1] == f2["date"].iloc[-1], f"both end {f1['date'].iloc[-1]}")
    census_quote = vals.loc["CENSUS_ECOM_PCT_LATEST", "quote"]
    add("census_text_matches_fred_pct", f"{f1['value'].iloc[-1]:.1f} percent" in census_quote, f"Census text '{f1['value'].iloc[-1]:.1f} percent' present; FRED agrees")
    add("census_text_matches_fred_level", "340.2" in vals.loc["CENSUS_ECOM_SALES_LATEST", "quote"] and abs(f2["value"].iloc[-1] / 1000 - 340.2) < 0.06, "Census $340.2 billion matches FRED ECOMSA to rounding")
    # 4. Tier B claims against their specs
    spec = {c.claim_id: c for c in CLAIMS}
    bad_b = []
    for _, r in reg.values[reg.values["tier"] == "B"].iterrows():
        c = spec.get(r["value_id"])
        if c is None:
            bad_b.append(f"{r['value_id']} has no claim spec (hand-added record)")
            continue
        q, nums = r["quote"], numbers_in(r["quote"])
        for want in c.check_numbers:
            if not any(abs(want - g) < 1e-9 for g in nums):
                bad_b.append(f"{r['value_id']}: {want} not in quote")
        for tx in c.check_text:
            if tx not in q:
                bad_b.append(f"{r['value_id']}: '{tx}' not in quote")
        if c.value is not None and abs(float(r["value"]) - c.value) > 1e-9:
            bad_b.append(f"{r['value_id']}: value {r['value']} differs from spec {c.value}")
        if r["definition_class"] != c.definition_class or r["metric_id"] != c.metric_id:
            bad_b.append(f"{r['value_id']}: metric or definition class changed")
    add("tier_b_claims_match_specs", not bad_b, f"{int((reg.values['tier'] == 'B').sum())} Tier B records re-checked" + (f"; problems: {bad_b[:3]}" if bad_b else ""))
    add("tier_b_all_specs_present", {c.claim_id for c in CLAIMS} == set(reg.values[reg.values["tier"] == "B"]["value_id"]),
        "every curated claim is either admitted or listed as rejected" if not json.loads((root / "evidence.json").read_text())["rejected"] else "some claims were rejected at sync", warn=True)
    # 5. staleness and exclusions
    ages = [reg.record(r)["age_days"] for _, r in reg.values.iterrows()]
    old = sum(1 for a in ages if a is not None and a > STALE_AFTER_DAYS)
    expired = sum(1 for a in ages if a is not None and a > EXCLUDE_AFTER_DAYS)
    add("staleness", old == 0, f"{old} records older than {STALE_AFTER_DAYS} days, {expired} older than {EXCLUDE_AFTER_DAYS} days (not offered)", warn=True)
    add("exclusion_log_present", len(reg.excluded) >= 5, f"{len(reg.excluded)} refused claims are logged with reasons")
    add("tier_b_quotes_short", bool(reg.values[reg.values["tier"] == "B"]["quote"].str.len().le(460).all()), "all quotes are brief")
    return checks


def verify_live(root: Path = BENCH_DIR) -> List[Check]:
    """Re-fetch primary sources: hash drift is reported; vanished quotes fail."""
    root = Path(root)
    checks: List[Check] = []
    reg = Registry.load(root)
    ev = json.loads((root / "evidence.json").read_text(encoding="utf-8"))["sources"]
    for key, url in (("damodaran", URLS["damodaran"]), ("pep_states", URLS["pep_states"])):
        try:
            _, meta = fetch(url)
            checks.append(Check(f"live_{key}", "PASS" if meta["sha256"] == ev[key]["sha256"] else "DRIFT",
                                "identical to snapshot" if meta["sha256"] == ev[key]["sha256"] else "publisher file changed since the snapshot (a new vintage); run sync and review"))
        except Exception as exc:
            checks.append(Check(f"live_{key}", "WARN", f"could not fetch: {exc}"))
    texts: Dict[str, str] = {}
    for key in ("haus", "gordon", "lewis", "littledata"):
        try:
            raw, _ = fetch(URLS[key])
            texts[key] = page_text(raw)
        except Exception as exc:
            checks.append(Check(f"live_{key}", "WARN", f"could not fetch: {exc}"))
    for c in CLAIMS:
        if c.source in texts:
            q = extract_quote(texts[c.source], c.anchor, c.max_len, c.start_at_anchor)
            stored = reg.values[reg.values["value_id"] == c.claim_id]["quote"].iloc[0]
            checks.append(Check(f"live_quote_{c.claim_id}", "PASS" if q == stored else ("FAIL" if q is None else "DRIFT"),
                                "quote unchanged on the live page" if q == stored else ("quote no longer on the page" if q is None else "page text around the claim changed")))
    return checks


def report(checks: List[Check]) -> str:
    return "\n".join(f"{c.status:<5} {c.name}: {c.detail}" for c in checks)


if __name__ == "__main__":
    live = "--live" in sys.argv
    res = verify_offline() + (verify_live() if live else [])
    print(report(res))
    n_fail = sum(c.status == "FAIL" for c in res)
    print(f"\n{len(res)} checks: {sum(c.status == 'PASS' for c in res)} pass, {sum(c.status == 'WARN' for c in res)} warn, {sum(c.status == 'DRIFT' for c in res)} drift, {n_fail} fail")
    sys.exit(1 if n_fail else 0)
