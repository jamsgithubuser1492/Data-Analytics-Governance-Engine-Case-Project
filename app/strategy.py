"""Business strategy calculations: trade-offs, cost of delay, implications, change plan, budget lens, monitoring.

Everything numeric is computed from the run. Organizational estimates the data cannot support (people, hours, contract
terms) are left as blank worksheet fields for the executive to fill in; nothing here states an unsourced figure as fact.
Prose offers ideas only in the tentative forms the product uses: "Consider...", "Given that..., perhaps we should think
about...", "In order to address..., we might want to think about...".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

TIER_WORDS = {"VERIFIED": "Verified", "DIRECTIONAL": "Directional", "NOT_DECISION_GRADE": "Not decision grade"}


def _usd(v: float) -> str:
    return f"${abs(v):,.0f}"


# ------------------------------------------------------------------------------------------------ trade-offs
def plan_reallocation(ch: pd.DataFrame, moves: Sequence[Dict[str, Any]], haircut: float = 0.0) -> Dict[str, Any]:
    """Move money between channels at their proven average returns (no saturation unless ``haircut`` is set).

    ``moves``: dicts with ``source``, ``target``, ``amount``. ``haircut`` lowers the return earned on new money (0.2 means 20% lower).
    Best and worst case use the 95% interval and exist only when every channel involved has one (the strict basis).
    """
    c = ch.set_index("channel")
    rows: Dict[str, Dict[str, float]] = {n: {"before": float(c.loc[n, "spend"]), "delta": 0.0} for n in c.index}
    gross = lost = low_net = high_net = 0.0
    have_ci = True
    for m in moves:
        s, t, amt = m["source"], m["target"], float(m["amount"])
        if s not in c.index or t not in c.index:
            raise KeyError(f"Unknown channel in move: {s} or {t}")
        amt = min(amt, rows[s]["before"] + rows[s]["delta"]) if amt > 0 else 0.0
        if amt <= 0:
            continue
        rows[s]["delta"] -= amt
        rows[t]["delta"] += amt
        src_spend = float(c.loc[s, "spend"])
        lost_here = float(c.loc[s, "proven_revenue"]) * (amt / src_spend) if src_spend else 0.0
        gross_here = amt * float(c.loc[t, "proven"]) * (1 - haircut)
        gross += gross_here
        lost += lost_here
        if pd.notna(c.loc[t, "lower"]) and pd.notna(c.loc[t, "upper"]) and pd.notna(c.loc[s, "lower"]) and pd.notna(c.loc[s, "upper"]):
            low_net += amt * float(c.loc[t, "lower"]) * (1 - haircut) - amt * float(c.loc[s, "upper"])
            high_net += amt * float(c.loc[t, "upper"]) * (1 - haircut) - amt * float(c.loc[s, "lower"])
        else:
            have_ci = False
    table = pd.DataFrame([{"channel": n, "spend_before": r["before"], "change": r["delta"], "spend_after": r["before"] + r["delta"],
                           "change_pct": (r["delta"] / r["before"]) if r["before"] else np.nan} for n, r in rows.items()])
    moved = float(sum(max(0.0, -r["delta"]) for r in rows.values()))
    return {"table": table, "moved": moved, "gross": gross, "lost": lost, "net": gross - lost,
            "net_low": low_net if have_ci and moved else float("nan"), "net_high": high_net if have_ci and moved else float("nan"), "haircut": haircut}


def cost_of_delay(net: float, test_days: int) -> Dict[str, float]:
    """Modeled value of the move per week and per 30 days, from the net change over the observed test period."""
    weeks = max(test_days, 1) / 7.0
    return {"per_week": net / weeks, "per_30_days": net / weeks * (30 / 7.0), "weeks": weeks}


def saturation_sensitivity(ch: pd.DataFrame, moves: Sequence[Dict[str, Any]], haircuts: Sequence[float] = (0.0, 0.1, 0.2, 0.3, 0.4)) -> Dict[str, Any]:
    """Net change if the return on the new money is lower than the average return: the objective answer to diminishing returns."""
    base = plan_reallocation(ch, moves, 0.0)
    rows = [{"haircut": h, "net": plan_reallocation(ch, moves, h)["net"]} for h in haircuts]
    be = float("nan") if base["gross"] <= 0 else max(0.0, 1.0 - base["lost"] / base["gross"])
    return {"table": pd.DataFrame(rows), "break_even_haircut": be, "gross": base["gross"], "lost": base["lost"]}


# ------------------------------------------------------------------------------------------ implications
FUNCTIONS = ["Finance and treasury", "Marketing and creative", "Agencies and media buying", "Data and engineering", "Legal and privacy"]


def implications(ch: pd.DataFrame, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per function: what changes (computed), questions to answer, and blank fields for the executive's own estimates."""
    t = plan["table"]
    srcs = t[t["change"] < 0]
    dsts = t[t["change"] > 0]
    src_txt = ", ".join(f"{r.channel} ({_usd(r.change)} less, {abs(r.change_pct):.0%} of its spend)" for r in srcs.itertuples()) or "no channel"
    dst_txt = ", ".join(f"{r.channel} ({_usd(r.change)} more, {r.change_pct:.0%} above its current spend)" for r in dsts.itertuples()) or "no channel"
    tiers = ch.set_index("channel")["tier"]
    dst_tiers = ", ".join(f"{r.channel}: {TIER_WORDS.get(tiers.get(r.channel), 'unrated')}" for r in dsts.itertuples()) or "none"
    return [
        dict(function=FUNCTIONS[0], what_changes=f"Spend would fall on {src_txt} and rise on {dst_txt}. The channel level cash plan and the quarterly forecast change with it.",
             questions=["Are there upfront commitments, insertion orders or minimum spends on the channels losing budget, and what do the cancellation terms say?",
                        "How do payment terms differ between the platforms gaining budget?", "Which budget approvals are needed, and how long do they take?"],
             fields=["Commitment or penalty exposure ($)", "Approval lead time (days)", "Forecast notes"]),
        dict(function=FUNCTIONS[1], what_changes=f"Creative must cover {dst_txt}. Evidence on the receiving channels: {dst_tiers}.",
             questions=["How many new creative variations would the extra spend need each week to avoid fatigue?", "Which formats does each receiving channel need?",
                        "Is there a creative pipeline gap in the first weeks?"],
             fields=["New creative variations per week", "Creative lead time (days)", "Formats needed"]),
        dict(function=FUNCTIONS[2], what_changes="Managed spend moves between platforms, which can change agency workload and fee bases.",
             questions=["Are agency incentives tied to gross spend or platform reported return, and does that conflict with a proven return basis?",
                        "Which restructuring work falls to the agency, and who approves it?"],
             fields=["Fee impact ($)", "Restructuring hours", "Contract changes needed"]),
        dict(function=FUNCTIONS[3], what_changes="Higher spend on a channel puts more weight on its tracking, and a larger test needs clean test and control markets.",
             questions=["Is conversion tracking healthy enough to hold up at higher spend?", "Can a scaled holdout verify the return at the new spend level, and how long would it need?",
                        "Do the test markets stay free of other campaigns?"],
             fields=["Engineering hours", "Scaled test duration (days)", "Tracking issues found"]),
        dict(function=FUNCTIONS[4], what_changes="Moving budget does not change what data is used, but contracts and data processing terms with each platform may apply.",
             questions=["Do the platform contracts allow the change without a review?", "Is any customer or personal data used in tests, and is it covered by current agreements?",
                        "Is the AI service used for briefs approved by the company?"],
             fields=["Review needed (yes or no)", "Owner", "Notes"]),
    ]


# ------------------------------------------------------------------------------------------------ change plan
def change_plan(totals: Dict[str, Any], ch: pd.DataFrame, divergence_count: int, campaigns: int, is_strict: bool, run_tier: str, breakeven: float) -> Dict[str, Any]:
    """Stakeholder rows and phased checklist, with the facts that matter to each group computed from the run."""
    below = ch[ch["proven"] < breakeven * 0.95]["channel"].tolist()
    stakeholders = [
        dict(group="Finance leadership", worries="Marketing numbers that cannot be defended, and budget spent on claimed rather than proven results.",
             evidence=f"{_usd(totals['unearned'])} of ad spend has not been earned back; platforms claim {_usd(totals['overclaim_revenue'])} more revenue than the test supports.",
             consider="Consider agreeing which counting basis governs budget decisions and financial reporting."),
        dict(group="Growth and brand leadership", worries="Losing reach or top line by cutting channels, and being slowed by analysis.",
             evidence=f"The portfolio returns {totals['proven']:.2f}x per $1 against a breakeven of {breakeven:.2f}x" + (f"; {', '.join(below)} sit below breakeven." if below else "; no channel sits below breakeven."),
             consider="Given that a result is a measurement of one period, perhaps we should think about pairing any budget move with a follow-up test that can show the effect."),
        dict(group="Agencies and media buyers", worries="Being measured on spend or platform reported return, which a proven basis can undercut.",
             evidence=f"Reported and proven returns differ for {divergence_count} of {campaigns} campaigns." if divergence_count else "Reported and proven returns are close for every campaign.",
             consider="In order to address any gap in incentives, we might want to think about reviewing how agency success is defined in the next contract cycle."),
        dict(group="Creative and platform teams", worries="Performance dropping after budgets rise, and unclear priorities.",
             evidence=f"Evidence quality is {TIER_WORDS.get(run_tier, run_tier)} across the run.",
             consider="Consider sharing which campaigns are measured to a Verified standard so the team knows where numbers can be leaned on."),
    ]
    phases = [
        ("Align", ["Consider agreeing one counting basis for decisions and reporting.", "Consider listing the questions each function needs answered (see Implications)."]
         + ([f"Given that the spec view exceeds strict lift for {divergence_count} of {campaigns} campaigns, perhaps we should think about explaining both views in the first stakeholder briefing."] if divergence_count else [])),
        ("Prove", [f"In order to address stakeholder doubt about {below[0]}, we might want to think about a parallel proof test before any cut." if below else "Consider scheduling a confirmation test on the strongest channel before scaling.",
                   "Consider agreeing in advance what result would change the plan."]),
        ("Phase in", ["Consider moving budget in stages, with a checkpoint after each stage.", "Consider naming one owner for each function's checklist."]),
        ("Embed", ["Consider adding the proven return to agency and internal scorecards.", "Consider a regular review of the advisory council views and guardrail settings."]),
    ]
    return {"stakeholders": stakeholders, "phases": phases}


# --------------------------------------------------------------------------------------------- budget lens
def allocation_lens(ch: pd.DataFrame, core_min: float = 2.0, validation_min: float = 1.0, target: Sequence[float] = (70.0, 20.0, 10.0)) -> Dict[str, Any]:
    """Optional policy lens: share of spend by evidence and return tier, against an editable target mix.

    Core: Verified evidence and a proven return of ``core_min`` or more. Validation: at or above ``validation_min`` but not Core.
    Sandbox: no holdout evidence yet. Below threshold: proven return under ``validation_min``.
    """
    d = ch.copy()
    def tier(r: pd.Series) -> str:
        if pd.isna(r["proven"]):
            return "Sandbox"
        if r["tier"] == "VERIFIED" and r["proven"] >= core_min:
            return "Core"
        if r["proven"] >= validation_min:
            return "Validation"
        return "Below threshold"
    d["lens"] = d.apply(tier, axis=1)
    total = float(d["spend"].sum())
    share = {k: float(d.loc[d["lens"] == k, "spend"].sum() / total) if total else 0.0 for k in ("Core", "Validation", "Sandbox", "Below threshold")}
    tgt = {"Core": target[0] / 100, "Validation": target[1] / 100, "Sandbox": target[2] / 100}
    rows = [dict(tier=k, share=share[k], target=tgt.get(k), gap=(share[k] - tgt[k]) if k in tgt else None,
                 channels=", ".join(d.loc[d["lens"] == k, "channel"])) for k in ("Core", "Validation", "Sandbox", "Below threshold")]
    return {"table": pd.DataFrame(rows), "by_channel": d[["channel", "spend", "proven", "tier", "lens"]], "total": total}


# ---------------------------------------------------------------------------------------------- monitoring
def decay_monitor(roll: pd.DataFrame, window: int = 14, floor: float = 1.0) -> pd.DataFrame:
    """Recent direction of the 7 day rolling return per channel. ``roll`` has date, channel, iroas."""
    out = []
    for name, g in roll.dropna(subset=["iroas"]).sort_values("date").groupby("channel"):
        g = g.tail(window + 1)
        if len(g) < 5:
            out.append(dict(channel=name, latest=float(g["iroas"].iloc[-1]) if len(g) else np.nan, earlier=np.nan, change_pct=np.nan, slope_per_day=np.nan, status="Not enough days", note="Fewer than five days of data."))
            continue
        y = g["iroas"].to_numpy(float)
        slope = float(np.polyfit(np.arange(len(y)), y, 1)[0])
        latest, earlier = float(y[-1]), float(y[0])
        change = (latest - earlier) / earlier if earlier else np.nan
        if latest < floor:
            status, note = "Below floor", f"The latest 7 day return is {latest:.2f}x, under the {floor:.2f}x floor."
        elif slope < 0 and pd.notna(change) and change <= -0.10:
            status, note = "Falling", f"The 7 day return fell {abs(change):.0%} over the last {len(g) - 1} days, from {earlier:.2f}x to {latest:.2f}x."
        else:
            status, note = "Stable", f"The 7 day return is {latest:.2f}x, {'up' if (change or 0) >= 0 else 'down'} {abs(change):.0%} over the last {len(g) - 1} days." if pd.notna(change) else "Stable."
        out.append(dict(channel=name, latest=latest, earlier=earlier, change_pct=change, slope_per_day=slope, status=status, note=note))
    return pd.DataFrame(out)


def capital_protection_preview(cd: pd.DataFrame, spend_min: float = 10000.0, floor: float = 1.0) -> pd.DataFrame:
    """Campaigns whose proven return is under the floor with at least ``spend_min`` spent (information only)."""
    d = cd[(cd["proven"] < floor) & (cd["spend"] >= spend_min)][["campaign_id", "channel", "spend", "proven", "tier"]].copy()
    return d.sort_values("spend", ascending=False)


def default_moves(ch: pd.DataFrame, breakeven: float) -> List[Dict[str, Any]]:
    """A starting scenario: move the weakest channel's budget (if it is below breakeven) to the strongest measured channels, split evenly."""
    measured = ch.dropna(subset=["proven"])
    if measured.empty:
        return []
    src = measured.sort_values("proven").iloc[0]
    if src["proven"] >= breakeven * 0.95:
        return []
    dest = measured[(measured["channel"] != src["channel"]) & (measured["proven"] >= breakeven * 1.05) & (measured["tier"] != "NOT_DECISION_GRADE")].sort_values("proven", ascending=False).head(2)
    if dest.empty:
        return []
    share = float(src["spend"]) / len(dest)
    return [dict(source=src["channel"], target=t, amount=share) for t in dest["channel"]]
