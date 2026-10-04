"""8-point governance audit for every campaign.

Checks: (1) pre-period parallel trends, (2) sample size adequacy, (3) CI width
precision, (4) business benchmark adherence, (5) seasonality contamination,
(6) cross-source directional alignment, (7) attribution inflation plausibility,
(8) decision usefulness under uncertainty.

Each check returns PASS (1.0), WARN (0.5) or FAIL (0.0); the trust score is the
mean x 100. Output: JSON audit report plus a human readable summary.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from causal_impact_runner import run_all  # noqa: E402
from config import TIER_NOT_DECISION_GRADE, PolicySettings  # noqa: E402
from database_manager import DatabaseManager, OUTPUT_DIR, ROOT  # noqa: E402
from strict_lift import divergence_warning, headline_iroas, strict_lift_row  # noqa: E402

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
SCORE = {PASS: 1.0, WARN: 0.5, FAIL: 0.0}
MIN_WINDOW_DAYS = 28


@dataclass
class CheckResult:
    """Outcome of a single governance check."""
    check_id: int
    name: str
    status: str
    value: Any
    threshold: str
    detail: str


@dataclass
class CampaignAudit:
    """Full audit for one campaign."""
    campaign_id: str
    channel: str
    trust_score: float
    verdict: str
    recommendation: str
    tier: str = TIER_NOT_DECISION_GRADE
    spec_iroas: Optional[float] = None
    strict_iroas: Optional[float] = None
    strict_iroas_lower: Optional[float] = None
    strict_iroas_upper: Optional[float] = None
    strict_incremental_revenue: Optional[float] = None
    test_period_spend: Optional[float] = None
    headline_metric: str = ""
    headline_iroas: Optional[float] = None
    divergence_warning: bool = False
    checks: List[CheckResult] = field(default_factory=list)


# ---------------------------------------------------------------- individual checks
def check_parallel_trends(c: pd.Series) -> CheckResult:
    p = float(c["parallel_trend_p_value"])
    return CheckResult(1, "Pre-period parallel trend validation", PASS if p > 0.05 else FAIL,
                       round(p, 4), "p > 0.05",
                       "Treatment and control moved together before launch." if p > 0.05
                       else "Pre-period trends diverge; holdout design is biased.")


def check_sample_size(c: pd.Series) -> CheckResult:
    mde = float(c["mde_relative_pct"])
    days_ok = c["pre_period_days"] >= MIN_WINDOW_DAYS and c["post_period_days"] >= MIN_WINDOW_DAYS
    status = FAIL if (not days_ok or mde > 50) else (PASS if mde <= 25 else WARN)
    return CheckResult(2, "Sample size adequacy", status, round(mde, 1),
                       "MDE <= 25% (80% power), >= 28 days per period",
                       f"Smallest detectable lift is {mde:.1f}% over {int(c['post_period_days'])} test days.")


def check_ci_width(c: pd.Series) -> CheckResult:
    pt = abs(float(c["point_estimate"]))
    rel = (float(c["ci_upper"]) - float(c["ci_lower"])) / pt if pt > 0 else float("inf")
    status = PASS if rel <= 1.0 else (WARN if rel <= 2.0 else FAIL)
    return CheckResult(3, "CI width precision", status, round(rel, 2),
                       "CI width / |estimate| <= 1.0",
                       f"95% CI [{c['ci_lower']:.0f}, {c['ci_upper']:.0f}] around {c['point_estimate']:.0f} incremental conversions.")


def check_benchmarks(r: pd.Series, b: pd.Series) -> CheckResult:
    iroas = float(r["incremental_roas"])
    lo, hi = float(b["expected_roas_min"]), float(b["expected_roas_max"])
    inside = lo <= iroas <= hi
    where = "inside" if inside else ("below" if iroas < lo else "above")
    return CheckResult(4, "Business benchmark range adherence", PASS if inside else WARN, round(iroas, 2),
                       f"iROAS in [{lo}, {hi}]",
                       f"iROAS {iroas:.2f}x is {where} the {r['channel']} expected ROAS band.")


def check_seasonality(c: pd.Series) -> CheckResult:
    drift = abs(float(c["control_drift_pct"]))
    status = PASS if drift <= 10 else (WARN if drift <= 20 else FAIL)
    return CheckResult(5, "Seasonality contamination check", status, round(float(c["control_drift_pct"]), 1),
                       "|control drift pre -> post| <= 10%",
                       f"Unexposed control geo moved {c['control_drift_pct']:+.1f}% between periods.")


def check_directional_alignment(r: pd.Series) -> CheckResult:
    below = int(r["total_mta_conversions"] <= r["total_platform_conversions"]) + \
        int(r["total_holdout_conversions"] <= r["total_platform_conversions"])
    status = {2: PASS, 1: WARN, 0: FAIL}[below]
    return CheckResult(6, "Cross-source directional alignment", status, below,
                       "MTA and holdout both <= platform claims",
                       f"{below}/2 independent sources agree the platform over-claims "
                       f"(platform {r['total_platform_conversions']:.0f}, MTA {r['total_mta_conversions']:.0f}, "
                       f"holdout {r['total_holdout_conversions']:.0f}).")


def check_inflation(r: pd.Series) -> CheckResult:
    ratio = r["inflation_ratio"]
    if pd.isna(ratio):
        return CheckResult(7, "Attribution inflation plausibility", FAIL, None, "1.0 <= ratio < 1.5", "No holdout coverage.")
    status = FAIL if (ratio >= 3.0 or ratio < 1.0) else (WARN if ratio >= 1.5 else PASS)
    return CheckResult(7, "Attribution inflation plausibility", status, round(float(ratio), 2),
                       "1.0 <= ratio < 1.5 (>= 3.0 critical)",
                       f"Platform claims {ratio:.2f}x the holdout conversions.")


def check_decision_usefulness(c: pd.Series, others: List[CheckResult]) -> CheckResult:
    significant_positive = float(c["ci_lower"]) > 0
    blockers = [o.name for o in others if o.status == FAIL]
    if significant_positive and not blockers:
        status, detail = PASS, "Lift interval excludes zero and no check failed: safe to act."
    elif significant_positive:
        status, detail = WARN, f"Lift is significant but failed checks remain: {', '.join(blockers)}."
    else:
        status, detail = FAIL, "Lift interval includes zero: result cannot support a budget decision."
    return CheckResult(8, "Decision usefulness under uncertainty", status, bool(significant_positive),
                       "CI lower bound > 0 and no failed checks", detail)


def _verdict(score: float) -> str:
    return "TRUSTED" if score >= 75 else ("CAUTION" if score >= 50 else "UNTRUSTED")


def _recommendation(verdict: str, tier: str, iroas: float) -> str:
    if tier == TIER_NOT_DECISION_GRADE or verdict == "UNTRUSTED" or pd.isna(iroas):
        return "HOLD: not decision grade. Do not reallocate budget on this result; rerun or extend the holdout."
    direction = ("SCALE" if iroas >= 3.0 else "REDUCE" if iroas < 1.0 else "MAINTAIN")
    suffix = " after a confirmation test" if tier != "VERIFIED" else ""
    return f"{direction}: iROAS {iroas:.2f}x{suffix}."


def _num(v: float) -> Optional[float]:
    return None if pd.isna(v) else round(float(v), 4)


# ------------------------------------------------------------------------- orchestration
def audit_campaign(recon_row: pd.Series, causal_row: pd.Series, bench_row: pd.Series,
                   settings: Optional[PolicySettings] = None,
                   test_period_spend: Optional[float] = None) -> CampaignAudit:
    """Run the 8-point audit for one campaign and attach tier, strict lift and headline."""
    settings = settings or PolicySettings()
    checks = [
        check_parallel_trends(causal_row), check_sample_size(causal_row), check_ci_width(causal_row),
        check_benchmarks(recon_row, bench_row), check_seasonality(causal_row),
        check_directional_alignment(recon_row), check_inflation(recon_row),
    ]
    checks.append(check_decision_usefulness(causal_row, checks))
    score = round(sum(SCORE[c.status] for c in checks) / len(checks) * 100, 1)
    verdict = _verdict(score)
    tier = settings.trust_tier(score, checks[0].status == PASS)
    strict = strict_lift_row(recon_row, causal_row, settings, test_period_spend)
    spec = float(recon_row["incremental_roas"])
    head = headline_iroas(spec, strict["strict_iroas_point"], settings)
    return CampaignAudit(
        recon_row["campaign_id"], recon_row["channel"], score, verdict, _recommendation(verdict, tier, head),
        tier=tier, spec_iroas=_num(spec), strict_iroas=_num(strict["strict_iroas_point"]),
        strict_incremental_revenue=_num(strict["strict_incremental_revenue_point"]), test_period_spend=_num(test_period_spend if test_period_spend is not None else recon_row["total_spend"]),
        strict_iroas_lower=_num(strict["strict_iroas_lower"]), strict_iroas_upper=_num(strict["strict_iroas_upper"]),
        headline_metric=settings.headline_metric, headline_iroas=_num(head),
        divergence_warning=divergence_warning(spec, strict["strict_iroas_point"], settings), checks=checks)


def run_audit(mgr: Optional[DatabaseManager] = None, settings: Optional[PolicySettings] = None) -> Dict[str, Any]:
    """Audit every campaign and return the structured report."""
    settings = settings or (mgr.settings if mgr else PolicySettings())
    mgr = mgr or DatabaseManager(settings=settings).build()
    recon = mgr.view("ANALYTICS_MEASUREMENT_RECONCILIATION")
    bench = mgr.view("BUSINESS_BENCHMARKS").set_index("channel")
    causal = run_all(mgr.data_dir / "RAW_HOLDOUT_DATA.csv", settings.pre_period_days).set_index("campaign_id")
    test_spend = mgr.view_query("""SELECT campaign_id, SUM(platform_spend) AS s FROM STG_UNIFIED_MEASUREMENT
        WHERE date >= (SELECT MIN(date) FROM RAW_HOLDOUT_DATA WHERE treatment_flag = 1)
        GROUP BY campaign_id""").set_index("campaign_id")["s"].to_dict()
    audits: List[CampaignAudit] = []
    for _, row in recon.sort_values("campaign_id").iterrows():
        if row["campaign_id"] not in causal.index or not row["has_holdout_coverage"]:
            audits.append(CampaignAudit(row["campaign_id"], row["channel"], 0.0, "UNTRUSTED",
                                        "HOLD: no holdout coverage, impact is unknown.", headline_metric=settings.headline_metric))
            continue
        audits.append(audit_campaign(row, causal.loc[row["campaign_id"]], bench.loc[row["channel"]], settings,
                                     test_spend.get(row["campaign_id"])))
    scores = [a.trust_score for a in audits]
    tiers = {t: sum(a.tier == t for a in audits) for t in ("VERIFIED", "DIRECTIONAL", "NOT_DECISION_GRADE")}
    return {
        "report": "MMGE Governance Audit",
        "settings": settings.to_dict(), "settings_fingerprint": settings.fingerprint(),
        "headline_metric": settings.headline_metric, "headline_label": settings.headline_label,
        "campaigns_audited": len(audits),
        "average_trust_score": round(sum(scores) / len(scores), 1) if scores else None,
        "verdict_counts": {v: sum(a.verdict == v for a in audits) for v in ("TRUSTED", "CAUTION", "UNTRUSTED")},
        "tier_counts": tiers,
        "campaigns": [{**{k: v for k, v in a.__dict__.items() if k != "checks"},
                       "checks": [c.__dict__ for c in a.checks]} for a in audits],
    }


def main() -> None:
    """Run the audit, write JSON and markdown reports, print the summary."""
    from report_generator import render_text_summary, write_reports

    report = run_audit()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path, md_path = write_reports(report, OUTPUT_DIR)
    print(render_text_summary(report))
    print(f"\nWrote {json_path.relative_to(ROOT)} and {md_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
