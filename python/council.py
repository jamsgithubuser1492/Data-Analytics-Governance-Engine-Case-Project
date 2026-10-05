"""The advisory council: four personas that interpret the same verified facts through different motivations.

Design rules (these are tested):
  * Facts come from the run and are never invented. Every number in a persona's text is computed here from the inputs.
  * Personas are the interpretation layer. They never instruct. Every recommendation sentence opens with one of the
    allowed forms: "Consider ...", "Given that ..., perhaps we should think about ...", or
    "In order to address ..., we might want to think about ...".
  * Each persona has a lean (conservative, moderate or aggressive) that changes how much evidence they want, how
    close to breakeven counts as clearly profitable, and how much over-claiming they tolerate. The council is
    deterministic: the same facts always produce the same readings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from voice import STANCE_VERB

TIER_RANK = {"NOT_DECISION_GRADE": 0, "DIRECTIONAL": 1, "VERIFIED": 2}
TIER_WORDS = {"VERIFIED": "Verified", "DIRECTIONAL": "Directional", "NOT_DECISION_GRADE": "Not decision grade"}
CONFIDENCE_WORDS = {"VERIFIED": "confident evidence", "DIRECTIONAL": "directional evidence", "NOT_DECISION_GRADE": "evidence not yet reliable"}
BAR_WORDS = {"VERIFIED": "confident evidence", "DIRECTIONAL": "at least directional evidence", "NOT_DECISION_GRADE": "any evidence"}
ALLOWED_OPENERS = ("Consider ", "Given that ", "In order to address ")
STANCES = ["Lean in", "Hold", "Re-test", "Pull back", "Get more evidence"]


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    lean: str  # conservative | moderate | aggressive
    background: str
    personality: str
    motivations: List[str]
    first_question: str
    evidence_floor: str  # lowest trust tier they will lean on before backing a money move
    clearance: float  # multiple of breakeven that counts as clearly profitable
    cut_below: float  # multiple of breakeven under which they would pull back (above it, they would re-test)
    overclaim_tolerance: float  # platform claim relative to proof they will tolerate
    uses_lower_bound: bool  # judge a channel by the pessimistic end of its 95% interval when one exists
    related_rule: str  # the decision rule (agent) that feeds this persona's evidence panel


PERSONAS: List[Persona] = [
    Persona("STEWARD", "The Steward", "Brand CFO / VP Finance", "conservative",
            "Twenty years in corporate finance. Has sat through budget cuts where marketing could not defend its numbers.",
            "Careful, numerate and allergic to surprises. Asks for the downside before the upside.",
            ["Protect capital", "Be able to defend every number to the board", "Avoid paying twice for sales that would have happened anyway"],
            "Is every dollar earned back, and how sure are we?", "VERIFIED", 1.5, 0.95, 1.15, True, "CAPITAL_PRESERVATION_AGENT"),
    Persona("BUILDER", "The Builder", "CMO / Growth VP", "aggressive",
            "Grew two consumer brands by finding channels early and scaling them before competitors noticed.",
            "Optimistic, fast and impatient with analysis that never ends in a decision. Wary of cutting something that might be working.",
            ["Grow revenue and share", "Find the next channel to scale", "Keep the portfolio balanced for the long run"],
            "Where is there room to grow, and what are we missing by waiting?", "DIRECTIONAL", 1.1, 0.6, 1.5, False, "SCALE_OPPORTUNITY_AGENT"),
    Persona("TRANSLATOR", "The Translator", "Agency Director", "moderate",
            "Runs client relationships. Has lost accounts when reported results and the client's own books disagreed.",
            "Diplomatic, precise with words and focused on trust. Wants a story the client can verify.",
            ["Prove campaign value transparently", "Keep client reporting defensible", "Avoid being caught out by an over-claiming platform"],
            "Can I explain this to a client in one page, and will it hold up?", "VERIFIED", 1.3, 0.9, 1.25, False, "ATTRIBUTION_SHIELD_AGENT"),
    Persona("MECHANIC", "The Mechanic", "Platform / Media Lead", "moderate",
            "Lives in the ad platforms every day. Knows how tracking breaks and where numbers get inflated.",
            "Practical, detail oriented and sceptical of dashboards. Prefers a small test to a big opinion.",
            ["Keep campaigns healthy", "Spot tracking and measurement problems early", "Run clean tests that settle arguments"],
            "Which campaigns are measured well enough to trust, and which need work?", "DIRECTIONAL", 1.2, 0.9, 1.25, False, "ATTRIBUTION_SHIELD_AGENT"),
]
PERSONA_BY_ID = {p.id: p for p in PERSONAS}


@dataclass
class ChannelView:
    channel: str
    stance: str
    text: str
    facts: str
    change_my_mind: str


@dataclass
class Reading:
    persona: Persona
    headline: str
    kpis: List[Dict[str, str]]
    channels: List[ChannelView]
    portfolio: List[str] = field(default_factory=list)


@dataclass
class Council:
    readings: List[Reading]
    agree: List[str]
    split: List[str]
    basis: str


def _x(v: Any) -> str:
    return "not measured" if v is None or pd.isna(v) else f"{float(v):.2f}x"


def _usd(v: Any) -> str:
    return "n/a" if v is None or pd.isna(v) else f"${abs(float(v)):,.0f}"


def _fact_line(r: pd.Series, be: float) -> str:
    base = f"{r['channel']} returns {_x(r['proven'])} for every $1 spent, against a {be:.2f}x breakeven ({CONFIDENCE_WORDS.get(r['tier'], r['tier'])}"
    if pd.notna(r.get("lower")) and pd.notna(r.get("upper")):
        base += f"; we are 95% sure the true return is between {_x(r['lower'])} and {_x(r['upper'])}"
    return base + ")"


def stance_for(p: Persona, r: pd.Series, be: float) -> str:
    """Where this persona stands on one channel, from the facts and their own bar for evidence."""
    if pd.isna(r["proven"]):
        return "Get more evidence"
    if TIER_RANK.get(r["tier"], 0) < TIER_RANK[p.evidence_floor]:
        return "Get more evidence"
    value = r["lower"] if p.uses_lower_bound and pd.notna(r.get("lower")) else r["proven"]
    if value >= be * p.clearance:
        return "Lean in"
    if value >= be * 0.95:
        return "Hold"
    if value >= be * p.cut_below:
        return "Re-test"
    return "Pull back"


def _mind(stance: str, p: Persona, be: float) -> str:
    bar = BAR_WORDS[p.evidence_floor]
    return {
        "Lean in": f"the return falling toward the {be:.2f}x breakeven, or the evidence weakening below {bar}",
        "Hold": f"a fresh test showing a return of at least {be * p.clearance:.2f}x with {bar}",
        "Re-test": f"a longer or cleaner test that either clears {be:.2f}x or confirms the shortfall",
        "Pull back": f"a fresh test showing a return above {be:.2f}x with {bar}",
        "Get more evidence": f"a longer or larger test that lifts the evidence to {bar}",
    }[stance]


def _text(p: Persona, stance: str, r: pd.Series, be: float) -> str:
    ch, x = r["channel"], _x(r["proven"])
    spent = _usd(r.get("unearned"))
    t = {
        ("STEWARD", "Lean in"): f"Given that {ch} returns {x} for every $1 against a {be:.2f}x breakeven, even on a cautious reading, perhaps we should think about adding budget in stages, confirming the return at each step before committing more.",
        ("STEWARD", "Hold"): f"Consider keeping {ch} at its current budget. It covers its cost, but the cushion is thin for a board that will ask us to defend every dollar.",
        ("STEWARD", "Re-test"): f"In order to address the shortfall on {ch}, we might want to think about a fresh test before deciding, since {spent} of spend has not been earned back.",
        ("STEWARD", "Pull back"): f"Given that {spent} of {ch} spend has not been earned back, perhaps we should think about reducing what we put at risk until a new test shows otherwise.",
        ("STEWARD", "Get more evidence"): f"In order to address how uncertain the {ch} result is, we might want to think about running a longer or larger test before the number goes into a budget decision.",
        ("BUILDER", "Lean in"): f"Given that {ch} returns {x} for every $1 against a {be:.2f}x breakeven, perhaps we should think about putting more budget behind it in a controlled way and watching whether the return holds.",
        ("BUILDER", "Hold"): f"Consider keeping {ch} in the mix while we look for creative or audience changes that could lift its return above {be * p.clearance:.2f}x.",
        ("BUILDER", "Re-test"): f"Before cutting {ch}, consider whether it plays a role the test cannot see, such as reach or brand awareness. We might want to think about a targeted re-test rather than a cut.",
        ("BUILDER", "Pull back"): f"Given that {ch} returns {x}, well under breakeven, perhaps we should think about moving part of its budget to channels with stronger proven returns.",
        ("BUILDER", "Get more evidence"): f"In order to avoid missing an opportunity on {ch}, we might want to think about a faster, larger test so this decision is not left waiting.",
        ("TRANSLATOR", "Lean in"): f"Given that {ch} is clearly above breakeven and the result is solid, perhaps we should think about featuring it as the proof point in client reporting.",
        ("TRANSLATOR", "Hold"): f"Consider presenting {ch} to the client as covering its cost, with the likely range shown, so they see the result without reading too much into it.",
        ("TRANSLATOR", "Re-test"): f"In order to address the gap between what the platform reports and what we can prove on {ch}, we might want to think about walking the client through how it was tested and agreeing a re-test.",
        ("TRANSLATOR", "Pull back"): f"Given that {ch} has not earned back its spend on the proven numbers, perhaps we should think about an open client conversation, anchored on the test results, before the next report.",
        ("TRANSLATOR", "Get more evidence"): f"Consider telling the client that {ch} is not yet measured well enough to base a decision on, and agreeing what would make it so.",
        ("MECHANIC", "Lean in"): f"Consider checking that conversion counting on {ch} stays stable as spend rises, since the proven return of {x} depends on clean measurement.",
        ("MECHANIC", "Hold"): f"Consider reviewing creative and audience settings on {ch}. A return of {x} leaves little room for measurement slipping.",
        ("MECHANIC", "Re-test"): f"In order to address the shortfall on {ch}, we might want to think about checking how its conversions are being counted before running the test again.",
        ("MECHANIC", "Pull back"): f"Given that {ch} returns {x}, perhaps we should think about checking campaign setup and conversion counting before assuming the channel itself is the problem.",
        ("MECHANIC", "Get more evidence"): f"In order to address the weak evidence on {ch}, we might want to think about a longer test, more test markets or a cleaner comparison group.",
    }
    return t[(p.id, stance)]


def _overclaim_items(p: Persona, cd: pd.DataFrame) -> List[str]:
    d = cd.dropna(subset=["overclaim_ratio"])
    over = d[d["overclaim_ratio"] > p.overclaim_tolerance]
    if over.empty:
        return []
    worst = over.sort_values("overclaim_ratio", ascending=False).iloc[0]
    n, m = len(over), len(d)
    base = f"{n} of {m} campaigns report more than {p.overclaim_tolerance:g} times the results the test can confirm (the widest gap is {worst['campaign_id']}, at {worst['overclaim_ratio']:.1f} times)"
    return [{
        "STEWARD": f"Given that {base}, perhaps we should think about reconciling the revenue finance sees with the proven figure before the next budget cycle.",
        "BUILDER": f"Given that {base}, perhaps we should think about whether the strongest platform claims are real before planning growth around them.",
        "TRANSLATOR": f"In order to address the fact that {base}, we might want to think about anchoring client reporting on the proven number.",
        "MECHANIC": f"In order to address the fact that {base}, we might want to think about checking how those campaigns count conversions.",
    }[p.id]]


def _kpis(p: Persona, ch: pd.DataFrame, cd: pd.DataFrame, tot: Dict[str, Any], be: float, holdout_cov: float) -> List[Dict[str, str]]:
    verified_share = float((cd["tier"] == "VERIFIED").mean()) if len(cd) else 0.0
    above = ch[ch["proven"] >= be * 1.05]
    if p.id == "STEWARD":
        return [dict(label="Spend not earned back", value=_usd(tot["unearned"])), dict(label="Claimed but unproven revenue", value=_usd(tot["overclaim_revenue"])),
                dict(label="Proven return per $1", value=_x(tot["proven"]))]
    if p.id == "BUILDER":
        share = float(above["spend"].sum() / ch["spend"].sum()) if ch["spend"].sum() else 0.0
        return [dict(label="Proven return per $1", value=_x(tot["proven"])), dict(label="Budget in channels above breakeven", value=f"{share:.0%}"),
                dict(label="Channels above breakeven", value=f"{len(above)} of {int(ch['proven'].notna().sum())}")]
    if p.id == "TRANSLATOR":
        n_over = int((cd["overclaim_ratio"] > p.overclaim_tolerance).sum())
        return [dict(label="Platforms report versus proven", value=f"{_x(ch['claimed'].mean())} vs {_x(tot['proven'])}"), dict(label="Campaigns overstated", value=f"{n_over} of {len(cd)}"),
                dict(label="Campaigns we can act on with confidence", value=f"{verified_share:.0%}")]
    n_weak = int((cd["tier"] != "VERIFIED").sum())
    worst = cd["overclaim_ratio"].max()
    return [dict(label="Campaigns needing more testing", value=f"{n_weak} of {len(cd)}"), dict(label="Biggest gap between claimed and proven", value=_x(worst)), dict(label="Campaigns with a control test", value=f"{holdout_cov:.0%}")]


def _headline(p: Persona, ch: pd.DataFrame, tot: Dict[str, Any], be: float) -> str:
    below = ch[ch["proven"] < be * 0.95]
    unmeasured = int(ch["proven"].isna().sum())
    if p.id == "STEWARD":
        return (f"{_usd(tot['unearned'])} of ad spend has not been earned back, and platforms claim {_usd(tot['overclaim_revenue'])} more revenue than our tests support. "
                f"{len(below)} of {len(ch)} channels do not repay their cost.")
    if p.id == "BUILDER":
        above = ch[ch["proven"] >= be * 1.05]
        return (f"{len(above)} of {len(ch)} channels earn more than they cost, and the portfolio returns {_x(tot['proven'])} for every $1 spent. "
                f"{len(below)} fall short of breakeven and {unmeasured} have not been measured yet.")
    if p.id == "TRANSLATOR":
        return (f"Platforms report an average return of {_x(ch['claimed'].mean())}, while the tests prove {_x(tot['proven'])}. That gap is the conversation to have with clients.")
    weak = ch[ch["tier"] != "VERIFIED"]
    return (f"{len(weak)} of {len(ch)} channels are not yet measured well enough to bet on"
            + (f" ({', '.join(weak['channel'])})." if len(weak) else ".") + " How cleanly each campaign is tracked and tested decides how far its numbers can be trusted.")


def _names(v: List[str]) -> str:
    v = [n.replace("The ", "the ", 1) for n in v]
    return v[0] if len(v) == 1 else ", ".join(v[:-1]) + " and " + v[-1]


def convene(ch: pd.DataFrame, cd: pd.DataFrame, tot: Dict[str, Any], breakeven: float, is_strict: bool, holdout_coverage: float = 1.0) -> Council:
    """Every persona reads the same channel facts. Returns readings plus where the council agrees and splits."""
    readings: List[Reading] = []
    for p in PERSONAS:
        views = []
        for _, r in ch.sort_values("proven", ascending=False, na_position="last").iterrows():
            s = stance_for(p, r, breakeven)
            views.append(ChannelView(r["channel"], s, _text(p, s, r, breakeven), _fact_line(r, breakeven), _mind(s, p, breakeven)))
        readings.append(Reading(p, _headline(p, ch, tot, breakeven), _kpis(p, ch, cd, tot, breakeven, holdout_coverage), views, _overclaim_items(p, cd)))
    agree, split = [], []
    for ch_name in ch["channel"]:
        picks = {rd.persona.name: next(v.stance for v in rd.channels if v.channel == ch_name) for rd in readings}
        kinds = set(picks.values())
        if len(kinds) == 1:
            agree.append(f"All four advisors would {STANCE_VERB[next(iter(kinds))]} {ch_name}.")
        else:
            groups: Dict[str, List[str]] = {}
            for name, s in picks.items():
                groups.setdefault(s, []).append(name)
            split.append(f"{ch_name}: " + "; ".join(f"{_names(v)} would {STANCE_VERB[k]} it" for k, v in groups.items()) + ".")
    return Council(readings, agree, split, "Strict lift" if is_strict else "Reported by spec")
