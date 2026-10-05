"""Privacy guard, copy ready prompt and answer checker."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "app"))

import council as cn  # noqa: E402
import privacy as pv  # noqa: E402
import prompt_pack as pp  # noqa: E402
import strategy as sg  # noqa: E402
from job_runner import JobRunner  # noqa: E402
from pipeline import SourceTables  # noqa: E402
from run_store import LocalRunStore  # noqa: E402
from runview import load_view  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿←-⇿ℹ‍️]")


@pytest.fixture(scope="module")
def env():
    store = LocalRunStore(Path(tempfile.mkdtemp()))
    ws = store.get_or_create_workspace("t")
    runner = JobRunner(store, max_workers=2)
    cfg = store.latest_workspace_config(ws)
    spec = runner.submit(ws, SourceTables.from_directory(), cfg[0], cfg[1], "spec")
    runner.wait(ws, spec, timeout=300)
    from config import PolicySettings
    strict_settings = PolicySettings(**{**cfg[0].to_dict(), "headline_metric": "strict_lift"})
    strict = runner.submit(ws, SourceTables.from_directory(), strict_settings, cfg[1], "strict")
    runner.wait(ws, strict, timeout=300)
    return store, ws, spec, strict


def plan_for(v):
    amt = float(v.ch.set_index("channel").loc["Netflix Ads", "spend"])
    return sg.plan_reallocation(v.ch, [dict(source="Netflix Ads", target="Google Ads", amount=amt / 2), dict(source="Netflix Ads", target="Meta Ads", amount=amt / 2)])


# ---------------------------------------------------------------------------------------------- privacy
@pytest.mark.parametrize("text,kind", [("write to jane.doe@acme.com", "email"), ("call (415) 555-0132 today", "phone"), ("call 415-555-0132", "phone"), ("id 123-45-6789", "ssn"),
                                       ("card 4111 1111 1111 1111", "card"), ("host 192.168.1.20", "ip")])
def test_personal_data_is_detected(text, kind) -> None:
    assert [f.kind for f in pv.scan_text(text)] == [kind]


@pytest.mark.parametrize("text", ["Spend was $748,140 across 8 campaigns", "return 3.33x on 2026-10-05", "order 1234567890123", "version 1.2.3.4.5", "ROAS 5.71 and 3.25", "call it 2026"])
def test_ordinary_business_text_is_not_flagged(text) -> None:
    assert pv.scan_text(text) == []


def test_redaction_and_alias_round_trip() -> None:
    red, found = pv.redact_text("Ask jane@acme.com or 415-555-0132")
    assert "jane" not in red and "[email removed]" in red and len(found) == 2
    a = pv.Aliaser.build(["Meta Ads", "Google Ads"], ["META_ADS_CMP_01", "GOOGLE_ADS_CMP_01"])
    hidden = a.hide("Meta Ads and META_ADS_CMP_01 versus Google Ads")
    assert "Meta" not in hidden and "META" not in hidden and a.reveal(hidden) == "Meta Ads and META_ADS_CMP_01 versus Google Ads"
    with pytest.raises(ValueError):
        pv.assert_aggregate_only(5)
    ctx, found, trunc = pv.clean_context("x" * 3000)
    assert len(ctx) == pv.MAX_CONTEXT_CHARS and trunc


# ------------------------------------------------------------------------------------------------ prompt
def test_every_number_in_the_prompt_traces_to_a_fact_and_no_personal_data_leaks(env) -> None:
    store, ws, spec, strict = env
    v = load_view(store, ws, spec)
    pack = pp.build_prompt(v, "CFO / Finance", "Executive memo", plan=plan_for(v), delay=sg.cost_of_delay(667510.38, 60),
                           haircut_be=0.3, council=cn.convene(v.ch, v.cd, v.tot, v.breakeven, v.is_strict), context="Q4 renewal talks. Contact bob@corp.com or 415-555-0199.")
    scenario = pack.text.split("[SCENARIO UNDER CONSIDERATION]")[1].split("[ADVISORY COUNCIL VIEWS]")[0]
    council_part = pack.text.split("[ADVISORY COUNCIL VIEWS]")[1].split("[EXECUTIVE")[0]
    assert "bob@corp.com" not in pack.text and "415-555-0199" not in pack.text and any("Personal data" in w for w in pack.warnings)
    chk = pp.check_answer(scenario + council_part, pack.facts)  # the free text sections may only contain numbers that are facts
    assert chk.ungrounded == 0 and chk.grounded >= 3, [r for r in chk.rows if r.status == "not_in_facts"]
    facts_block = [ln for ln in pack.text.splitlines() if ln.startswith("[F")]
    assert len(facts_block) == len(pack.facts) and all(re.match(r"\[F\d+\] ", ln) for ln in facts_block)
    assert "$105,158" in pack.text and "3.33x" in pack.text and "Policy version" in pack.text
    assert not EMOJI.search(pack.text) and "—" not in pack.text and "–" not in pack.text


def test_prompt_has_rules_sections_and_audience_and_is_deterministic(env) -> None:
    store, ws, spec, _ = env
    v = load_view(store, ws, spec)
    a = pp.build_prompt(v, "CMO / Growth", "Risk and rollback plan", plan=plan_for(v))
    b = pp.build_prompt(v, "CMO / Growth", "Risk and rollback plan", plan=plan_for(v))
    assert a.sha256 == b.sha256 and a.tokens_estimate > 100
    for sec in ("[ROLE AND RULES]", "[DATA HANDLING]", "[VERIFIED RUN FACTS]", "[SCENARIO UNDER CONSIDERATION]", "[TASK]", "[OUTPUT FORMAT]"):
        assert sec in a.text
    assert "Chief Marketing Officer" in a.text and "Do not instruct anyone to move money" in a.text and "ADVISORY COUNCIL" not in a.text
    assert re.search(r"\[F\d+\] Total media spend: \$748,140", a.text)
    assert "no customer records" in a.text and any("Raw rows" in x for x in a.excluded)


def test_interval_appears_only_on_the_strict_basis(env) -> None:
    store, ws, spec, strict = env
    spec_text = pp.build_prompt(load_view(store, ws, spec), "CFO / Finance", "Executive memo").text
    strict_text = pp.build_prompt(load_view(store, ws, strict), "CFO / Finance", "Executive memo").text
    assert "interval low" not in spec_text and "No interval is available" in spec_text
    assert "95% interval low" in strict_text and "Intervals are 95% confidence intervals" in strict_text


def test_aliases_hide_real_names_everywhere_in_the_prompt(env) -> None:
    store, ws, spec, _ = env
    v = load_view(store, ws, spec)
    pack = pp.build_prompt(v, "Board / CEO", "Board questions and answers", plan=plan_for(v), council=cn.convene(v.ch, v.cd, v.tot, v.breakeven, v.is_strict), use_aliases=True)
    for real in ("Netflix", "Google", "Meta", "TikTok", "NETFLIX_ADS"):
        assert real not in pack.text, real
    assert "Channel A" in pack.text and pack.aliaser.key_table()


# ----------------------------------------------------------------------------------------- answer checker
def test_answer_checker_passes_grounded_answers_and_flags_invented_numbers_and_certainty(env) -> None:
    store, ws, spec, _ = env
    v = load_view(store, ws, spec)
    facts = pp.build_facts(v)
    good = "Spend was $748,140 [F1] and the portfolio returned 3.33x [F6]. Platforms claimed $2,889,750, so $399,188 is unsupported. There are 8 campaigns."
    assert pp.check_answer(good, facts).ok
    bad = "Revenue will rise by $900,000 and the return will reach 7.5x, a guaranteed win. Margins improve 12%."
    r = pp.check_answer(bad, facts)
    assert r.ungrounded == 3 and r.certainty and not r.ok
    assert {x.token for x in r.rows if x.status == "not_in_facts"} >= {"$900,000", "7.5x", "12%"}


def test_exporting_a_prompt_is_audited_by_hash_only(env) -> None:
    store, ws, spec, _ = env
    pack = pp.build_prompt(load_view(store, ws, spec), "CFO / Finance", "Executive memo")
    store.log_event(ws, spec, "prompt_exported", "tester", {"sha256": pack.sha256, "audience": "CFO / Finance"})
    ev = [e for e in store.list_audit_events(ws, spec) if e["event"] == "prompt_exported"]
    assert ev and pack.sha256 in ev[0]["detail_json"] and "[ROLE AND RULES]" not in str(ev[0])
