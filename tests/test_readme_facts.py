"""The numbers quoted in the README and the case study must match the computed run, and the honest limits must stay."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "app")]

import dashdata as dd  # noqa: E402
from pipeline import SourceTables, run_pipeline  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")
EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿]")


@pytest.fixture(scope="module")
def totals():
    r = run_pipeline(SourceTables.from_directory())
    recon, camp = r.tables["ANALYTICS_MEASUREMENT_RECONCILIATION"], pd.DataFrame(r.audit["campaigns"])
    out = {}
    for strict in (False, True):
        cd = dd.campaign_frame(recon, camp, strict, 1.0, None)
        ch = dd.channel_frame(cd, r.tables["GOVERNANCE_AUDIT_SUMMARY"], strict, 1.0)
        out[strict] = dd.portfolio_totals(cd, ch, strict)
    out["verified"] = sum(c["tier"] == "VERIFIED" for c in r.audit["campaigns"])
    out["n"] = len(r.audit["campaigns"])
    return out


def test_headline_numbers_match_the_run(totals) -> None:
    spec, strict = totals[False], totals[True]
    assert f"${spec['spend']:,.0f}" in README
    assert f"{spec['proven']:.2f}x" in README
    assert f"${spec['unearned']:,.0f}" in README
    assert f"${spec['overclaim_revenue']:,.0f}" in README
    assert f"{totals['verified']} of {totals['n']}" in README
    assert f"about **{strict['proven']:.2f}x**" in README


def test_audience_example_figure_matches_the_computed_summary() -> None:
    import audience_tiers as at
    s = at.summary(at.compute(at.load_demo_audience())["AUDIENCE_TIER_RESULTS"])
    assert f"${s['critical_spend_for_organic']:,.0f}" in README


def test_honest_limits_are_on_the_first_screen() -> None:
    first_screen = README[:3500].lower()
    for phrase in ("synthetic", "illustrative", "no affiliation", "nothing here moves real money", "portfolio project"):
        assert phrase in first_screen, phrase


def test_every_linked_document_and_image_exists() -> None:
    for target in re.findall(r"\]\(((?:docs|LICENSE)[^)#]*)\)", README):
        assert (ROOT / target).exists(), target
    for md in (ROOT / "docs").glob("*.md"):
        for target in re.findall(r"\]\(([^)#:]+\.(?:md|png|gif))\)", md.read_text(encoding="utf-8")):
            assert (md.parent / target).exists() or (ROOT / target).exists(), (md.name, target)


def test_no_emojis_and_no_unfinished_placeholders_in_new_docs() -> None:
    for name in ("README.md", "docs/PAGE_GUIDE.md", "docs/ROLE_FIT.md", "docs/GLOSSARY.md", "docs/DEPLOY.md", "docs/VIDEO_SCRIPT.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not EMOJI.search(text), name
        assert "TODO" not in text and "lorem" not in text.lower(), name


def test_licence_and_supporting_files_exist() -> None:
    for f in ("LICENSE", "Dockerfile", ".dockerignore", ".github/workflows/ci.yml", ".devcontainer/devcontainer.json", "requirements-dev.txt"):
        assert (ROOT / f).exists(), f
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            assert "==" in line, f"not pinned: {line}"
