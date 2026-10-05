"""Copy ready prompt for an executive's own AI assistant, and a checker for what comes back.

The prompt carries numbered facts [F#] computed from the run, plus rules that keep the assistant factual and even handed.
It never contains raw rows or personal data. The checker compares every number in a pasted answer with those facts.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

import privacy
from council import Council
from memo_facts import Fact
from memo_verify import CITE, ISO_DATE, LIST_NUM, NUMBER, _matches
from runview import RunView

AUDIENCES = {
    "CFO / Finance": "a Chief Financial Officer who is responsible for protecting capital and defending numbers to the board",
    "CMO / Growth": "a Chief Marketing Officer who is responsible for growth and for the long term health of the channel portfolio",
    "Agency Director": "an agency director who must keep client reporting transparent and defensible",
    "Platform Lead": "a media or platform lead who runs campaigns day to day and owns measurement quality",
    "Board / CEO": "a chief executive preparing for a board discussion who needs balanced, plain language framing",
}
TASKS = {
    "Executive memo": "Write a one page executive memo: what the facts show, the realistic options, the trade-offs of each, and the open questions.",
    "Cross functional impact": "Describe how acting on these facts could affect Finance, Marketing and creative, Agencies, Data and engineering, and Legal. For each, list what would need to be known or estimated, without inventing numbers.",
    "Risk and rollback plan": "Outline a phased way to act on the scenario, the leading indicators that would show it is going wrong, and what would justify pausing or reversing. Treat every threshold as an assumption for the executive to set.",
    "Board questions and answers": "Prepare the five hardest questions a board member might ask about these results, with fact-grounded answers and honest statements of uncertainty.",
}
RULES = [
    "Use only the numbers in VERIFIED RUN FACTS and SCENARIO. Cite the fact id, for example [F3], after every number you use.",
    "Anything else is an assumption. Label it \"Assumption:\" and do not attach numbers to it unless the executive supplied them.",
    "Be even handed. Present the trade-offs on both sides, including the strongest case against the leading option.",
    "Do not instruct anyone to move money. Offer options, the evidence behind each, and what would change the conclusion.",
    "State unknowns plainly. Results describe a past test period; returns often fall as spend rises.",
    "Do not try to identify people or infer personal data. Treat the content as confidential company information.",
]
CERTAINTY = re.compile(r"\b(guarantee[sd]?|definitely|certainly|undoubtedly|without (?:a )?doubt|must immediately|will (?:certainly|definitely)|no risk|risk[- ]free)\b", re.I)
SMALL_COUNT = 10


def _fact(facts: List[Fact], key: str, label: str, value: Any, kind: str, display: Optional[str] = None) -> None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return
    from memo_facts import display as disp
    facts.append(Fact(f"F{len(facts) + 1}", key, label, float(value), kind, display or disp(float(value), kind)))


def _usd0(v: float) -> str:
    return f"${v:,.0f}"


def build_facts(v: RunView, plan: Optional[Dict[str, Any]] = None, delay: Optional[Dict[str, float]] = None, haircut_be: Optional[float] = None) -> List[Fact]:
    """Numbered facts from the run. An interval is included only when the run computed one (the strict basis)."""
    f: List[Fact] = []
    t = v.tot
    _fact(f, "spend", "Total media spend" + (" (test period)" if v.is_strict else ""), t["spend"], "usd", _usd0(t["spend"]))
    _fact(f, "proven_rev", "Revenue proven to be caused by advertising", t["proven_revenue"], "usd", _usd0(t["proven_revenue"]))
    _fact(f, "claimed_rev", "Revenue claimed by the platforms", t["platform_revenue"], "usd", _usd0(t["platform_revenue"]))
    _fact(f, "overclaim", "Claimed revenue the test does not support", t["overclaim_revenue"], "usd", _usd0(t["overclaim_revenue"]))
    _fact(f, "unearned", "Ad spend not earned back", t["unearned"], "usd", _usd0(t["unearned"]))
    _fact(f, "proven_ret", "Portfolio proven return per $1", t["proven"], "multiple")
    if v.is_strict:
        _fact(f, "ret_low", "Portfolio proven return, 95% interval low", t["lower"], "multiple")
        _fact(f, "ret_high", "Portfolio proven return, 95% interval high", t["upper"], "multiple")
    _fact(f, "breakeven", "Breakeven return" + (f" at a {v.margin:.0%} margin" if v.margin else " (revenue only, no margin declared)"), v.breakeven, "multiple")
    _fact(f, "trust", "Average trust score out of 100", float(v.report["average_trust_score"]), "int", f"{float(v.report['average_trust_score']):.0f}")
    tc = v.report["tier_counts"]
    _fact(f, "n_campaigns", "Campaigns audited", float(v.report["campaigns_audited"]), "int")
    _fact(f, "n_verified", "Campaigns with Verified evidence", float(tc["VERIFIED"]), "int")
    _fact(f, "n_directional", "Campaigns with Directional evidence", float(tc["DIRECTIONAL"]), "int")
    for r in v.ch.sort_values("spend", ascending=False).itertuples():
        _fact(f, f"{r.channel}_spend", f"{r.channel} spend", r.spend, "usd", _usd0(r.spend))
        _fact(f, f"{r.channel}_claimed", f"{r.channel} claimed return per $1", r.claimed, "multiple")
        _fact(f, f"{r.channel}_proven", f"{r.channel} proven return per $1", r.proven, "multiple")
        if v.is_strict:
            _fact(f, f"{r.channel}_low", f"{r.channel} proven return, 95% interval low", r.lower, "multiple")
            _fact(f, f"{r.channel}_high", f"{r.channel} proven return, 95% interval high", r.upper, "multiple")
        _fact(f, f"{r.channel}_trust", f"{r.channel} average trust score", r.trust_score, "int", f"{r.trust_score:.0f}")
    if plan:
        _fact(f, "moved", "Budget moved in the scenario", plan["moved"], "usd", _usd0(plan["moved"]))
        for r in plan["table"][plan["table"]["change"] != 0].itertuples():
            _fact(f, f"move_{r.channel}", f"Scenario: change in {r.channel} spend", r.change, "usd", ("-" if r.change < 0 else "+") + _usd0(r.change))
        _fact(f, "sc_gross", "Scenario: revenue expected from the receiving channels", plan["gross"], "usd", _usd0(plan["gross"]))
        _fact(f, "sc_lost", "Scenario: revenue given up by the source channel", plan["lost"], "usd", _usd0(plan["lost"]))
        _fact(f, "sc_net", "Scenario: net revenue change", plan["net"], "usd", _usd0(plan["net"]))
        if pd.notna(plan.get("net_low")):
            _fact(f, "sc_low", "Scenario: net revenue change, worst case in the 95% interval", plan["net_low"], "usd", _usd0(plan["net_low"]))
            _fact(f, "sc_high", "Scenario: net revenue change, best case in the 95% interval", plan["net_high"], "usd", _usd0(plan["net_high"]))
    if delay:
        _fact(f, "delay_week", "Scenario: modeled value per week of delay", delay["per_week"], "usd", _usd0(delay["per_week"]))
    if haircut_be is not None and pd.notna(haircut_be):
        _fact(f, "be_haircut", "Scenario: fall in return on new money at which the net change reaches zero", haircut_be * 100, "pct0", f"{haircut_be * 100:.0f}%")
    return f


@dataclass
class PromptPack:
    text: str
    facts: List[Fact]
    warnings: List[str] = field(default_factory=list)
    included: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)
    aliaser: Optional[privacy.Aliaser] = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def tokens_estimate(self) -> int:
        return max(1, round(len(self.text) / 4))


def build_prompt(v: RunView, audience: str, task: str, *, plan: Optional[Dict[str, Any]] = None, delay: Optional[Dict[str, float]] = None, haircut_be: Optional[float] = None,
                 council: Optional[Council] = None, context: str = "", use_aliases: bool = False) -> PromptPack:
    facts = build_facts(v, plan, delay, haircut_be)
    warnings: List[str] = []
    ctx, found, truncated = privacy.clean_context(context)
    if found:
        warnings.append("Personal data was found in your context and replaced with markers: " + ", ".join(sorted({x.label for x in found})) + ".")
    if truncated:
        warnings.append(f"Your context was shortened to {privacy.MAX_CONTEXT_CHARS} characters.")
    if v.report["tier_counts"]["VERIFIED"] < v.report["campaigns_audited"]:
        warnings.append("Some campaigns are below Verified evidence. The prompt says so, and the assistant is asked to treat those results with caution.")
    if not v.is_strict:
        warnings.append("This run uses the Reported by spec basis, which overstates returns when markets would have sold anyway and has no confidence interval.")

    lines = [f"[ROLE AND RULES]", f"You are an independent strategy and operations analyst advising {AUDIENCES[audience]}. You are reviewing a verified marketing measurement run.", "Rules:"]
    lines += [f"{i}. {r}" for i, r in enumerate(RULES, 1)]
    lines += ["", "[DATA HANDLING]", privacy.NOTICE, "", "[VERIFIED RUN FACTS]",
              f"Counting basis: {v.basis}. " + ("Intervals are 95% confidence intervals." if v.is_strict else "No interval is available on this basis."),
              f"Policy version {v.report['settings_fingerprint']}; run {v.run['id'][:8]}; evidence quality is stated per channel below."]
    for ft in facts:
        lines.append(f"[{ft.id}] {ft.label}: {ft.display}")
    tiers = v.ch.set_index("channel")["tier"].to_dict()
    lines.append("Evidence level by channel: " + "; ".join(f"{k}: {({'VERIFIED': 'Verified', 'DIRECTIONAL': 'Directional', 'NOT_DECISION_GRADE': 'Not decision grade'}).get(x, x)}" for k, x in tiers.items()) + ".")
    included = ["Channel level totals and returns", "Trust scores and evidence levels"]
    if plan:
        mv = plan["table"][plan["table"]["change"] != 0]
        lines += ["", "[SCENARIO UNDER CONSIDERATION]", "A scenario, not a recommendation. Moves: " + "; ".join(f"{r.channel} {'+' if r.change > 0 else '-'}{_usd0(abs(r.change))}" for r in mv.itertuples())
                  + ". Returns are assumed to hold at the new spend level, which they usually do not fully."]
        included.append("The budget scenario you configured")
    if council is not None:
        lines += ["", "[ADVISORY COUNCIL VIEWS]", "Four personas read the same facts. These are interpretations, not facts."]
        for rd in council.readings:
            lines.append(f"{rd.persona.name} ({rd.persona.role}, {rd.persona.lean}): " + "; ".join(f"{c.channel}: {c.stance}" for c in rd.channels) + ".")
        included.append("The advisory council's stance on each channel")
    if ctx:
        lines += ["", "[EXECUTIVE SUPPLIED CONTEXT (unverified, written by the executive)]", ctx]
        included.append("Your context (scanned for personal data)")
    lines += ["", "[TASK]", TASKS[task], "", "[OUTPUT FORMAT]",
              "Use short headings and bullets. Put every number next to its fact id. End with two sections: \"Assumptions I made\" and \"What would change this view\"."]
    text = "\n".join(lines)
    aliaser = None
    if use_aliases:
        aliaser = privacy.Aliaser.build(v.ch["channel"].tolist(), v.cd["campaign_id"].tolist())
        text = aliaser.hide(text)
        for ft in facts:
            ft.label = aliaser.hide(ft.label)
        warnings.append("Channel and campaign names were replaced with aliases. Keep the alias key private; it is shown only on this screen.")
    privacy.assert_aggregate_only(0)
    excluded = ["Raw rows, dates of individual events and customer records", "Personal data of any kind", "Names of people", "The alias key (kept in this app)" if use_aliases else "Anything outside this run"]
    return PromptPack(text, facts, warnings, included, excluded, aliaser)


# ------------------------------------------------------------------------------------------- answer checker
@dataclass
class NumberCheck:
    token: str
    status: str  # grounded | not_in_facts | small_count
    fact: str = ""


@dataclass
class AnswerCheck:
    rows: List[NumberCheck]
    certainty: List[str]
    ungrounded: int
    grounded: int

    @property
    def ok(self) -> bool:
        return self.ungrounded == 0 and not self.certainty


def check_answer(answer: str, facts: Sequence[Fact]) -> AnswerCheck:
    """Every number in an AI answer must match a fact (same unit and precision) or it is listed as not in the facts."""
    body = ISO_DATE.sub(" ", answer)
    body = LIST_NUM.sub("", body)
    body = CITE.sub(" ", body)
    body = re.sub(r"\b(?:19|20)\d{2}\b", " ", body)  # years
    rows: List[NumberCheck] = []
    for m in NUMBER.finditer(body):
        tok = m.group(0)
        if tok == "$1":  # the unit in "per $1", not a figure
            continue
        hit = next((f for f in facts if _matches(m, f)), None)
        if hit:
            rows.append(NumberCheck(tok, "grounded", hit.id))
        elif not (m.group("cur") or m.group("suf")) and "." not in m.group("num") and "," not in m.group("num") and int(m.group("num")) <= SMALL_COUNT:
            rows.append(NumberCheck(tok, "small_count"))
        else:
            rows.append(NumberCheck(tok, "not_in_facts"))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", answer) if CERTAINTY.search(s)]
    return AnswerCheck(rows, sentences, sum(r.status == "not_in_facts" for r in rows), sum(r.status == "grounded" for r in rows))
