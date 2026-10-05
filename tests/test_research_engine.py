"""Research engine: triggers, computed design numbers, tentative wording."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

import research_engine as re_  # noqa: E402
from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import LocalRunStore  # noqa: E402
from runview import load_view  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿←-⇿ℹ‍️]")


@pytest.fixture(scope="module")
def views():
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("t")
    runner = JobRunner(store, max_workers=2)
    cfg = store.latest_workspace_config(ws)
    a = runner.submit(ws, SourceTables.from_directory(), cfg[0], cfg[1], "spec")
    runner.wait(ws, a, timeout=300)
    from config import PolicySettings
    b = runner.submit(ws, SourceTables.from_directory(), PolicySettings(**{**cfg[0].to_dict(), "headline_metric": "strict_lift"}), cfg[1], "strict")
    runner.wait(ws, b, timeout=300)
    return load_view(store, ws, a), load_view(store, ws, b)


def kinds(specs, ch=None):
    return {s.kind for s in specs if ch is None or s.channel == ch}


def test_spec_basis_triggers_match_the_demo_story(views) -> None:
    spec, _ = views
    s = re_.build_specs(spec)
    assert "evidence_gap" in kinds(s, "Netflix Ads")          # Directional evidence
    assert "step_up" in kinds(s, "Google Ads") and "step_up" in kinds(s, "Meta Ads")  # strong, Verified returns
    assert "mmm_calibration" in kinds(s, "TikTok Ads") and "seasonality_retest" in kinds(s, "TikTok Ads")  # 1.30x over-claim, drift warnings
    assert "mmm_calibration" not in kinds(s, "Google Ads") and "evidence_gap" not in kinds(s, "Google Ads")
    assert "strict_confirmation" in kinds(s) and "audience_split" in kinds(s)


def test_design_numbers_follow_the_stated_formulas(views) -> None:
    spec, _ = views
    s = {x.id: x for x in re_.build_specs(spec)}
    gap = s["SPEC-NETFLIX_ADS-EVIDENCE_GAP"]
    mde = max(k["value"] for c in spec.report["campaigns"] if c["channel"] == "Netflix Ads" for k in c["checks"] if k["check_id"] == 2)
    import math
    need = int(math.ceil(60 * (mde / 25.0) ** 2))
    assert gap.quantities["days_needed"] == need
    daily = float(spec.ch.set_index("channel").loc["Netflix Ads", "total_spend"]) / 90
    assert gap.quantities["spend_estimate"] == pytest.approx(daily * 0.40 * need)
    step = s["SPEC-GOOGLE_ADS-STEP_UP"]
    g_daily = float(spec.ch.set_index("channel").loc["Google Ads", "total_spend"]) / 90
    assert step.quantities["extra_spend"] == pytest.approx(g_daily * 0.40 * 60 * (0.25 + 0.50)) or step.quantities["extra_spend"] == pytest.approx(g_daily * 0.40 * 28 * 0.75)
    assert "0%, +25%, +50%" in dict(step.design)["Cells"]


def test_ranking_is_descending_scaled_to_100_and_explained(views) -> None:
    spec, _ = views
    s = re_.build_specs(spec)
    pri = [x.priority for x in s]
    assert pri == sorted(pri, reverse=True) and pri[0] == 100.0 and all(0 <= p <= 100 for p in pri)
    assert all("Spend at stake" in x.priority_note for x in s)


def test_every_recommendation_sentence_is_tentative_and_no_emoji(views) -> None:
    for v in views:
        for sp in re_.build_specs(v):
            for line in sp.consider:
                assert line.startswith(re_.OPENERS), line
            for _, outcome in sp.decision_tree:
                assert outcome.startswith(("consider", "Consider")), outcome
            text = sp.markdown("run", v.basis)
            assert not EMOJI.search(text) and "—" not in text and "–" not in text


def test_resources_are_blank_fields_not_invented_numbers(views) -> None:
    spec, _ = views
    for sp in re_.build_specs(spec):
        assert all(not re.search(r"\d", r) for r in sp.resources)
        assert "______" in sp.markdown()


def test_strict_basis_builds_priors_for_calibration_and_spec_basis_explains_why_not(views) -> None:
    spec, strict = views
    mm_strict = [x for x in re_.build_specs(strict) if x.kind == "mmm_calibration"]
    assert mm_strict and any("log normal mu" in dict(x.design)["Prior from the test"] for x in mm_strict)
    mm_spec = [x for x in re_.build_specs(spec) if x.kind == "mmm_calibration"]
    assert all("needs the strict lift basis" in dict(x.design)["Prior from the test"] for x in mm_spec)
    assert not any(x.kind == "strict_confirmation" for x in re_.build_specs(strict))


def test_a_clean_strong_run_produces_no_evidence_gap(views) -> None:
    spec, _ = views
    clean = type(spec)(**{**spec.__dict__})
    clean.ch = spec.ch.assign(tier="VERIFIED")
    assert not any(s.kind == "evidence_gap" for s in re_.build_specs(clean))


def test_spec_packet_is_signable_and_carries_the_tier(views) -> None:
    spec, _ = views
    s = re_.build_specs(spec)[0]
    p = re_.spec_packet(s, spec)
    assert p["agent_id"] == "RESEARCH_SPEC" and p["tier"] in ("VERIFIED", "DIRECTIONAL", "NOT_DECISION_GRADE") and p["title"].startswith("Authorize research")
    assert p["recommended_action"] == "AUTHORIZE_RESEARCH"
