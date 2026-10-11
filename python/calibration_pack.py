"""The calibration pack: what this system knows, packaged so a media mix model (and other systems) can use it.

Each causal measurement a run produces (campaign tests, channel level pooled tests and audience tier results) becomes one
evidence record with its estimate, 95% interval, evidence level, quality flags, test window, lineage and, when it is fit to
inform a model, a log normal prior. Records that are not fit to inform a model are still listed, with the reason, so nothing is
silently dropped.

Rules (all adjustable in ``PriorPolicy``; the defaults are design assumptions to be tuned by backtesting, not research findings):
  * Only the strict lift basis has an interval, so only it can yield a prior.
  * Records below the Directional evidence level are excluded.
  * A Directional record has its standard error widened, as does a record whose control markets failed the match standard.
  * Evidence ages: the standard error grows with the time between the test and the date the model is built.
  * A floor stops any prior from being more certain than a set share of its own estimate.
Aggregate only: no person level data is ever carried, and the pack is refused if a forbidden column name appears.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd

import mmm_priors as mp
from config import PolicySettings

SCHEMA = "mmge.calibration_pack/1.0"
LEVELS = ("campaign", "channel", "audience_tier")
FORBIDDEN_TOKENS = ("email", "phone", "address", "ssn", "ip", "user", "customer", "device", "cookie", "feature", "age", "gender", "income", "zip", "postal")


USAGE_NOTES = [
    "Each prior describes the average incremental return at the tested spend level (see reference_daily_spend). A model with saturation curves must map it to its own parameters; do not use it as a marginal return.",
    "Campaign, channel and audience tier records describe overlapping money. Use one level for a given model parameter, never several, or the same evidence is counted twice.",
    "Standard errors are widened for weaker evidence and for age. The widening factors are design defaults to be tuned by backtesting, not research findings.",
    "Records marked excluded are listed so nothing is dropped silently. Do not turn an excluded record into a prior by hand.",
    "The pack describes one test window. Release it to a production model only after a person has reviewed and signed it.",
]


@dataclass(frozen=True)
class PriorPolicy:
    directional_widening: float = 2.0  # multiply the standard error for Leaning (Directional) evidence
    match_failed_widening: float = 1.5  # multiply again when the control markets did not meet the match standard
    age_half_life_days: float = 365.0  # standard error grows by sqrt(1 + age / half life)
    min_relative_se: float = 0.05  # a prior is never tighter than this share of its own estimate

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _prior(estimate: Optional[float], lower: Optional[float], upper: Optional[float], level: str, match_ok: bool, age_days: float,
           pol: PriorPolicy) -> Dict[str, Any]:
    """Prior and inclusion decision for one record."""
    out: Dict[str, Any] = {"included": False, "exclusion_reason": "", "prior": None, "widening": None}
    if level == "NOT_DECISION_GRADE":
        out["exclusion_reason"] = "Evidence is not yet reliable, so it should not inform a model."
    elif estimate is None or lower is None or upper is None:
        out["exclusion_reason"] = "No confidence interval, so no standard error can be derived."
    elif not estimate > 0:
        out["exclusion_reason"] = "The measured return is not positive, so a log normal prior does not apply."
    elif upper < lower:
        out["exclusion_reason"] = "The interval is invalid."
    else:
        se = mp.se_from_interval(lower, upper)
        widen = (pol.directional_widening if level == "DIRECTIONAL" else 1.0) * (1.0 if match_ok else pol.match_failed_widening)
        widen_age = math.sqrt(1.0 + max(age_days, 0.0) / pol.age_half_life_days)
        se_final = max(se * widen * widen_age, pol.min_relative_se * estimate)
        p = mp.lognormal_prior(estimate, se_final)
        out.update(included=True, widening=round(widen * widen_age, 4),
                   prior={"family": "lognormal", "mu": round(p["mu"], 6), "sigma": round(p["sigma"], 6), "mean": round(estimate, 6), "sd": round(se_final, 6)})
    return out


def _age(end: Optional[date], as_of: Optional[date]) -> float:
    return 0.0 if end is None or as_of is None else float(max((as_of - end).days, 0))


def build_pack(tables: Dict[str, pd.DataFrame], audit: Dict[str, Any], settings: PolicySettings, *, run_id: str = "", as_of: Optional[date] = None,
               policy: Optional[PriorPolicy] = None) -> Dict[str, Any]:
    """Assemble the pack from one run's stored tables and audit report."""
    pol = policy or PriorPolicy()
    hold = tables.get("INPUT_RAW_HOLDOUT_DATA")
    start = end = None
    n_days = 0
    if hold is not None and len(hold):
        d = pd.to_datetime(hold["date"])
        days = sorted(d.dt.date.unique())
        n_days = len(days)
        pre = min(settings.pre_period_days, max(n_days - 1, 0))
        start, end = (days[pre] if n_days > pre else days[0]), days[-1]
    test_days = (end - start).days + 1 if start and end else 0
    window = {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None, "test_days": test_days}
    as_of = as_of or end
    age = _age(end, as_of)
    econ = audit.get("economics") or {}
    camps = [c for c in audit.get("campaigns", [])]
    experiments: List[Dict[str, Any]] = []
    for c in camps:
        est, lo, hi = _f(c.get("strict_iroas")), _f(c.get("strict_iroas_lower")), _f(c.get("strict_iroas_upper"))
        spend = _f(c.get("test_period_spend"))
        flags = []
        if c.get("divergence_warning"):
            flags.append("counting_methods_disagree")
        pr = _prior(est, lo, hi, c["tier"], True, age, pol)
        experiments.append({"evidence_id": f"campaign:{c['campaign_id']}", "level": "campaign", "channel": c["channel"], "campaign_id": c["campaign_id"], "tier_name": None,
                            "measure": "incremental_roas", "basis": "strict_lift", "estimate": est, "lower95": lo, "upper95": hi,
                            "evidence_level": c["tier"], "trust_score": _f(c.get("trust_score")), "window": window, "spend": spend,
                            "reference_daily_spend": (spend / test_days if spend and test_days else None), "geo_sample_fraction": settings.geo_sample_fraction,
                            "quality_flags": flags, **pr})
    # channel level: combine campaigns with inverse variance weights (campaigns within a channel are treated as independent)
    channels: List[Dict[str, Any]] = []
    by_ch: Dict[str, List[Dict[str, Any]]] = {}
    for e in experiments:
        by_ch.setdefault(e["channel"], []).append(e)
    for ch, rows in by_ch.items():
        use = [r for r in rows if r["estimate"] is not None and r["lower95"] is not None and r["upper95"] is not None and r["evidence_level"] != "NOT_DECISION_GRADE" and r["estimate"] > 0]
        spend = sum(r["spend"] or 0.0 for r in rows)
        if use:
            ses = [mp.se_from_interval(r["lower95"], r["upper95"]) for r in use]
            w = [1.0 / (s * s) for s in ses]
            est = sum(wi * r["estimate"] for wi, r in zip(w, use)) / sum(w)
            se = math.sqrt(1.0 / sum(w))
            lo, hi = est - 1.959964 * se, est + 1.959964 * se
            level = "VERIFIED" if all(r["evidence_level"] == "VERIFIED" for r in use) else "DIRECTIONAL"
        else:
            est = lo = hi = None
            level = "NOT_DECISION_GRADE"
        pr = _prior(est, lo, hi, level, True, age, pol)
        channels.append({"evidence_id": f"channel:{ch}", "level": "channel", "channel": ch, "campaign_id": None, "tier_name": None, "measure": "incremental_roas", "basis": "strict_lift",
                         "estimate": est, "lower95": lo, "upper95": hi, "evidence_level": level, "trust_score": None, "window": window, "spend": spend,
                         "reference_daily_spend": (spend / test_days if spend and test_days else None), "geo_sample_fraction": settings.geo_sample_fraction,
                         "quality_flags": ["campaigns_pooled_inverse_variance"] if use else [], "n_campaigns": len(rows), "n_used": len(use), **pr})
    tiers: List[Dict[str, Any]] = []
    tt, mq = tables.get("AUDIENCE_TIER_RESULTS"), tables.get("AUDIENCE_MATCH_QUALITY")
    if tt is not None and len(tt):
        passed = {r["channel"]: bool(r["passed"]) for _, r in mq.iterrows()} if mq is not None and len(mq) else {}
        for _, r in tt.iterrows():
            est, lo, hi = _f(r["strict_iroas"]), _f(r["strict_iroas_low"]), _f(r["strict_iroas_high"])
            flags = ["overlaps_channel_level_evidence"]
            if not r["sample_ok"]:
                flags.append("not_enough_data")
            if not passed.get(r["channel"], False):
                flags.append("control_match_review_required")
            if r["range_width"] > settings.tier_max_range_width:
                flags.append("wide_range")
            pr = _prior(est, lo, hi, r["evidence_tier"], bool(passed.get(r["channel"], False)), age, pol)
            tiers.append({"evidence_id": f"audience_tier:{r['campaign_id']}|{r['tier_name']}", "level": "audience_tier", "channel": r["channel"], "campaign_id": r["campaign_id"],
                          "tier_name": r["tier_name"], "measure": "incremental_roas", "basis": "strict_lift", "estimate": est, "lower95": lo, "upper95": hi,
                          "evidence_level": r["evidence_tier"], "trust_score": None, "window": window, "spend": _f(r["spend"]), "reference_daily_spend": (_f(r["spend"]) / test_days if test_days else None),
                          "geo_sample_fraction": settings.geo_sample_fraction, "quality_flags": flags, "share_caused_by_ads": _f(r["lift_ratio"]),
                          "share_not_caused_by_ads": _f(r["cannibalization_pct"]) / 100.0 if _f(r["cannibalization_pct"]) is not None else None,
                          "decile_range": [int(r["decile_start"]), int(r["decile_end"])], **pr})
    body = {"schema": SCHEMA, "lineage": {"run_id": run_id, "settings_fingerprint": settings.fingerprint(), "counting_basis": "strict_lift",
                                          "breakeven_return": _f(econ.get("breakeven_iroas")), "margin": _f(econ.get("margin")), "benchmark_set_version": econ.get("benchmark_set_version"),
                                          "as_of": as_of.isoformat() if as_of else None, "window": window},
            "usage_notes": USAGE_NOTES, "policy": pol.to_dict(), "experiments": experiments, "channels": channels, "audience_tiers": tiers}
    body["summary"] = {"records": len(experiments) + len(channels) + len(tiers), "included": sum(1 for r in experiments + channels + tiers if r["included"]),
                       "excluded": sum(1 for r in experiments + channels + tiers if not r["included"])}
    body["pack_hash"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return body


def to_frame(pack: Dict[str, Any]) -> pd.DataFrame:
    """The ledger as one flat table (for a warehouse, a spreadsheet or a modeling notebook)."""
    rows = []
    for r in pack["experiments"] + pack["channels"] + pack["audience_tiers"]:
        p = r.get("prior") or {}
        rows.append({"evidence_id": r["evidence_id"], "level": r["level"], "channel": r["channel"], "campaign_id": r["campaign_id"], "tier_name": r["tier_name"], "measure": r["measure"],
                     "basis": r["basis"], "estimate": r["estimate"], "lower95": r["lower95"], "upper95": r["upper95"], "evidence_level": r["evidence_level"],
                     "window_start": r["window"]["start"], "window_end": r["window"]["end"], "spend": r["spend"], "reference_daily_spend": r["reference_daily_spend"],
                     "quality_flags": ";".join(r["quality_flags"]), "included": r["included"], "exclusion_reason": r["exclusion_reason"], "prior_family": p.get("family"),
                     "prior_mu": p.get("mu"), "prior_sigma": p.get("sigma"), "prior_mean": p.get("mean"), "prior_sd": p.get("sd"), "widening": r["widening"],
                     "run_id": pack["lineage"]["run_id"], "schema": pack["schema"]})
    return pd.DataFrame(rows)


def validate_pack(pack: Dict[str, Any]) -> List[str]:
    """Structural and privacy checks. An empty list means the pack is fit to share."""
    errs: List[str] = []
    if pack.get("schema") != SCHEMA:
        errs.append("Unknown schema version.")
    allowed = set()
    for r in pack.get("experiments", []) + pack.get("channels", []) + pack.get("audience_tiers", []):
        if r["level"] not in LEVELS:
            errs.append(f"Unknown level in {r.get('evidence_id')}.")
        if r["included"] and r["basis"] != "strict_lift":
            errs.append(f"{r['evidence_id']} is included but not on the strict lift basis.")
        if r["included"] and r["evidence_level"] == "NOT_DECISION_GRADE":
            errs.append(f"{r['evidence_id']} is included although its evidence is not reliable.")
        if r["included"] and not r["prior"]:
            errs.append(f"{r['evidence_id']} is included without a prior.")
        for k in r:
            if any(t in k.lower().split("_") for t in FORBIDDEN_TOKENS):
                errs.append(f"Field '{k}' looks like person level data.")
    h = pack.get("pack_hash")
    body = {k: v for k, v in pack.items() if k != "pack_hash"}
    if h != hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest():
        errs.append("The pack hash does not match its contents.")
    return errs
