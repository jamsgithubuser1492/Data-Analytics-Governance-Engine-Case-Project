"""Render the governance audit report as JSON and human readable text/markdown."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

ICON = {"PASS": "✅", "WARN": "🟡", "FAIL": "🔴"}


def render_text_summary(report: Dict[str, Any]) -> str:
    """Return a plain text summary of the audit report."""
    lines = [
        "=== MMGE GOVERNANCE AUDIT SUMMARY ===",
        f"Campaigns audited: {report['campaigns_audited']}   "
        f"Average trust score: {report['average_trust_score']}",
        f"Verdicts: {report['verdict_counts']}",
        "",
    ]
    for c in report["campaigns"]:
        lines.append(f"{c['campaign_id']:<20} trust {c['trust_score']:>5}  {c['verdict']:<9} {c['recommendation']}")
        for chk in c["checks"]:
            lines.append(f"    {ICON[chk['status']]} {chk['check_id']}. {chk['name']}: {chk['detail']}")
    return "\n".join(lines)


def render_markdown(report: Dict[str, Any]) -> str:
    """Return a markdown version of the audit report."""
    out = ["# MMGE Governance Audit Report", "",
           f"- Campaigns audited: **{report['campaigns_audited']}**",
           f"- Average trust score: **{report['average_trust_score']}**",
           f"- Verdicts: {report['verdict_counts']}", "",
           "| Campaign | Channel | Trust | Verdict | Recommendation |", "| --- | --- | --- | --- | --- |"]
    for c in report["campaigns"]:
        out.append(f"| {c['campaign_id']} | {c['channel']} | {c['trust_score']} | {c['verdict']} | {c['recommendation']} |")
    out.append("")
    for c in report["campaigns"]:
        out += [f"## {c['campaign_id']}", "", "| # | Check | Status | Detail |", "| --- | --- | --- | --- |"]
        out += [f"| {k['check_id']} | {k['name']} | {ICON[k['status']]} {k['status']} | {k['detail']} |" for k in c["checks"]]
        out.append("")
    return "\n".join(out)


def write_reports(report: Dict[str, Any], output_dir: Path) -> Tuple[Path, Path]:
    """Write ``governance_audit_report.json`` and ``.md`` into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "governance_audit_report.json"
    md_path = output_dir / "governance_audit_report.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
