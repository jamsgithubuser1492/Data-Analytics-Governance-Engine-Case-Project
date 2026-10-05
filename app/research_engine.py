"""Research and experimentation engine: turn what a run leaves uncertain into the next test worth considering.

Every number is computed from the run (spend rate, test length, minimum detectable effect, interval, trust). Quantities only the
organization knows (people, hours, contract terms) are blank worksheet fields. Wording is tentative: the engine proposes, a person decides.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import mmm_priors
from runview import RunView

TARGET_MDE_PCT = 25.0  # the quality bar used by the sample size check
OVERCLAIM_FLAG = 1.25  # same default as the Attribution shield guardrail
STEP_UP_CELLS = (0.0, 0.25, 0.50)  # design defaults, editable on the page
KIND_WEIGHT = {"evidence_gap": 1.0, "step_up": 0.8, "mmm_calibration": 0.7, "seasonality_retest": 0.6, "strict_confirmation": 0.5, "audience_split": 0.3}
KIND_LABEL = {"evidence_gap": "Strengthen the evidence", "step_up": "Find where returns start to fall", "mmm_calibration": "Calibrate a media mix model",
              "seasonality_retest": "Re-test around seasonality", "strict_confirmation": "Confirm on the strict basis", "audience_split": "See which audiences drive the lift"}
TIER_WORDS = {"VERIFIED": "Verified", "DIRECTIONAL": "Directional", "NOT_DECISION_GRADE": "Not decision grade"}
OPENERS = ("Consider ", "Given that ", "In order to address ")
FORMULA = "Priority = spend at stake x uncertainty x method weight, scaled so the top item is 100. Uncertainty is the interval width divided by the return (strict basis) or 1 minus the trust score share plus 0.1 (spec basis)."


@dataclass
class ExperimentSpec:
    id: str
    kind: str
    channel: str
    title: str
    priority: float
    priority_note: str
    saw: List[str]
    consider: List[str]
    objective: str
    method: str
    design: List[Tuple[str, str]]
    resources: List[str]
    decision_tree: List[Tuple[str, str]]
    assumptions: List[str]
    quantities: Dict[str, float] = field(default_factory=dict)

    def markdown(self, run_label: str = "", basis: str = "") -> str:
        out = [f"# Research specification: {self.title}", "", f"**Specification id:** {self.id}  ", f"**Channel:** {self.channel}  ", f"**Method:** {self.method}  ",
               f"**Counting basis:** {basis}  " if basis else "", f"**Run:** {run_label}  " if run_label else "", "", "## What the run showed", ""]
        out += [f"- {s}" for s in self.saw]
        out += ["", "## Research objective", "", self.objective, "", "## Ideas to consider", ""] + [f"- {s}" for s in self.consider]
        out += ["", "## Design (computed from the run)", ""] + [f"- **{k}:** {v}" for k, v in self.design]
        out += ["", "## Resources and budget (to be completed by your teams)", ""] + [f"- {r}: ______" for r in self.resources]
        out += ["", "## Decision tree", ""] + [f"- **{k}** {v}" for k, v in self.decision_tree]
        out += ["", "## Assumptions", ""] + [f"- {a}" for a in self.assumptions]
        out += ["", f"_{FORMULA}_", ""]
        return "\n".join(x for x in out if x is not None)


def _x(v: float) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.2f}x"


def _usd(v: float) -> str:
    return f"${v:,.0f}"


def _channel_checks(v: RunView, channel: str) -> Dict[str, Any]:
    camp = [c for c in v.report["campaigns"] if c["channel"] == channel]
    mde = max((k["value"] for c in camp for k in c["checks"] if k["check_id"] == 2 and k["value"] is not None), default=float("nan"))
    width = max((k["value"] for c in camp for k in c["checks"] if k["check_id"] == 3 and k["value"] is not None), default=float("nan"))
    drift = [(c["campaign_id"], k["value"]) for c in camp for k in c["checks"] if k["check_id"] == 5 and k["status"] in ("WARN", "FAIL") and k["value"] is not None]
    return {"mde": mde, "ci_width": width, "drift": drift, "campaigns": [c["campaign_id"] for c in camp]}


def _days(v: RunView) -> Tuple[int, int]:
    total = int(v.rolling["date"].nunique()) if len(v.rolling) else 90
    return total, max(total - int(v.settings.pre_period_days), 1)


def _uncertainty(r: pd.Series, v: RunView) -> float:
    if v.is_strict and pd.notna(r.get("lower")) and pd.notna(r.get("upper")) and r["proven"]:
        return float(min((r["upper"] - r["lower"]) / max(abs(r["proven"]), 1e-9), 3.0))
    return float(1.0 - r["trust_score"] / 100.0 + 0.1)


def build_specs(v: RunView, cells: Tuple[float, ...] = STEP_UP_CELLS) -> List[ExperimentSpec]:
    """Ranked research specifications for this run (highest priority first)."""
    total_days, test_days = _days(v)
    frac = float(v.settings.geo_sample_fraction)
    be = v.breakeven
    div = v.cd.dropna(subset=["overclaim_ratio"]).groupby("channel")["overclaim_ratio"].max()
    specs: List[ExperimentSpec] = []
    priors = mmm_priors.priors_table(v.ch) if v.is_strict else None
    for r in v.ch.itertuples():
        row = v.ch.set_index("channel").loc[r.channel]
        chk = _channel_checks(v, r.channel)
        daily = float(row["total_spend"]) / max(total_days, 1)
        tier = TIER_WORDS.get(row["tier"], row["tier"])
        interval = f", 95% interval {_x(row['lower'])} to {_x(row['upper'])}" if pd.notna(row.get("lower")) else ""
        facts = [f"{r.channel} returns {_x(row['proven'])} per $1 against a {be:.2f}x breakeven ({tier} evidence{interval}).",
                 f"Average trust score {row['trust_score']:.0f} of 100; the test could detect a lift of about {chk['mde']:.0f}% over {test_days} test days." if pd.notna(chk["mde"]) else f"Average trust score {row['trust_score']:.0f} of 100."]
        stakes = float(row["spend"])
        unc = _uncertainty(row, v)

        def add(kind: str, title: str, saw: List[str], consider: List[str], objective: str, method: str, design: List[Tuple[str, str]], resources: List[str],
                tree: List[Tuple[str, str]], assumptions: List[str], q: Dict[str, float]) -> None:
            score = stakes * unc * KIND_WEIGHT[kind]
            specs.append(ExperimentSpec(f"SPEC-{re.sub(r'[^A-Z0-9]+', '_', r.channel.upper()).strip('_')}-{kind.upper()}", kind, r.channel, title, score,
                                        f"Spend at stake {_usd(stakes)} x uncertainty {unc:.2f} x method weight {KIND_WEIGHT[kind]:.1f}", saw, consider, objective, method, design,
                                        resources, tree, assumptions, q))

        # 1. evidence gap: not Verified, a very wide interval, or an interval that straddles breakeven
        wide = v.is_strict and pd.notna(row.get("lower")) and (row["upper"] - row["lower"]) / max(abs(row["proven"]), 1e-9) > 1.0
        straddles = v.is_strict and pd.notna(row.get("lower")) and row["lower"] < be < row["upper"]
        if row["tier"] != "VERIFIED" or wide or straddles:
            need = test_days if not pd.notna(chk["mde"]) or chk["mde"] <= TARGET_MDE_PCT else int(min(math.ceil(test_days * (chk["mde"] / TARGET_MDE_PCT) ** 2), 365))
            spend_est = daily * frac * need
            why = "the evidence is below Verified" if row["tier"] != "VERIFIED" else ("the interval is wider than the result itself" if wide else "the interval includes breakeven")
            add("evidence_gap", f"{r.channel}: strengthen the evidence", facts,
                [f"Given that {why}, perhaps we should think about a longer or larger test before treating the number as final.",
                 "Consider a synthetic control: a weighted blend of untreated markets that matches the test markets before launch, with a fit check on the pre-period."],
                f"Learn whether {r.channel} truly returns more or less than {be:.2f}x per $1, to a Verified standard.", "Synthetic control geo test with a longer pre-period",
                [("Test length", f"about {need} days, from {test_days} days today (minimum detectable effect scales roughly with 1 over the square root of days; the bar is {TARGET_MDE_PCT:.0f}%)"),
                 ("Minimum detectable effect today", f"{chk['mde']:.0f}%" if pd.notna(chk["mde"]) else "not available"),
                 ("Estimated spend in test markets", f"{_usd(spend_est)} (current daily spend {_usd(daily)} x declared sample {frac:.0%} x {need} days)"),
                 ("Fit check", "pre-period error under 5% of the average level")],
                ["Markets to include and exclude", "Engineering hours to verify tracking", "Agency hours to hold delivery to test markets", "Approval owner"],
                [(f"If the new proven return is at least {be * 1.05:.2f}x with Verified evidence:", f"consider treating {r.channel} as measured and revisiting its budget through the sign-off desk."),
                 (f"If it is below {be * 0.95:.2f}x with Verified evidence:", "consider reviewing the budget with the sign-off desk."),
                 ("If evidence is still below Verified:", "consider adding markets or time, or accepting that the channel stays advisory.")],
                [f"Spend rate stays at today's level.", "The declared geo sample fraction holds.", "Test markets stay free of other campaigns."],
                {"days_needed": float(need), "spend_estimate": float(spend_est)})
        # 2. step-up: strong, Verified return with unknown saturation
        if row["tier"] == "VERIFIED" and pd.notna(row["proven"]) and row["proven"] >= 1.5 * be:
            days = max(int(v.settings.min_test_days), 28)
            extra = daily * frac * days * sum(c for c in cells if c > 0)
            lab = ", ".join(f"{c:+.0%}" if c else "0%" for c in cells)
            add("step_up", f"{r.channel}: find where returns start to fall", facts,
                [f"Given that {r.channel} returns {_x(row['proven'])} at today's spend, perhaps we should think about measuring what happens to the return at higher spend before committing a large increase.",
                 "Consider a multi-cell test with matched market groups at different spend levels."],
                "Estimate how the return changes as spend rises, to find the level where it approaches breakeven.", f"Multi-cell step-up geo experiment ({len(cells)} cells)",
                [("Cells", f"{len(cells)} matched market groups at spend changes of {lab} (design defaults, editable)"), ("Test length", f"at least {days} days (the policy minimum)"),
                 ("Extra spend in test markets", f"about {_usd(extra)} above today's level (daily spend {_usd(daily)} x sample {frac:.0%} x {days} days x total increase)")],
                ["Matched market pairs", "Creative capacity for higher spend", "Engineering hours to verify tracking", "Approval owner"],
                [(f"If the return at the highest cell stays above {be * 1.5:.2f}x:", "consider a staged budget increase with checkpoints."),
                 (f"If it falls toward {be:.2f}x:", "consider capping spend near the previous cell."),
                 ("If cells cannot be told apart:", "consider a longer test or a larger step.")],
                ["Returns are measured at spend levels the cells actually reach.", "Cells are matched on pre-period behavior."], {"days": float(days), "extra_spend": float(extra)})
        # 3. MMM calibration: platform claims differ materially from the proof
        ratio = div.get(r.channel, np.nan)
        if pd.notna(ratio) and ratio > OVERCLAIM_FLAG:
            if priors is not None and priors[priors["channel"] == r.channel]["usable"].any():
                p = priors[priors["channel"] == r.channel].iloc[0]
                prior_line = f"Calibrated prior from this run: mean {p['proven']:.2f}x, standard error {p['se']:.3f}, log normal mu {p['mu']:.3f} and sigma {p['sigma']:.3f}."
            elif v.is_strict:
                prior_line = "A prior cannot be built because the proven return or its interval is not usable."
            else:
                prior_line = "A calibrated prior needs the strict lift basis, which carries a confidence interval. Switch the counting basis first."
            add("mmm_calibration", f"{r.channel}: calibrate a media mix model", facts + [f"Platforms claim up to {ratio:.2f}x what the test confirms for this channel."],
                [f"Given that platforms claim {ratio:.2f}x what the test confirms, perhaps we should think about a media mix model that uses the test result as its starting point, so it does not just follow platform credit.",
                 "In order to address effects a short test cannot see, such as delayed response and spillover to other channels, we might want to think about comparing the model with the test."],
                "Triangulate the short term test result with longer term and cross channel effects.", "Bayesian media mix model with test-calibrated priors",
                [("Prior from the test", prior_line), ("Model history", "ideally two or more years of weekly data (to be confirmed with your analysts)"),
                 ("Reference transforms", "geometric adstock for carry over and a Hill curve for saturation (see the Research page tools)")],
                ["Weekly spend and outcome history available", "Analyst or vendor to build the model", "Review cadence"],
                [("If the model and the test agree within the test's interval:", "consider using the model for longer range planning."),
                 ("If they disagree:", "consider investigating tracking, seasonality and overlap before trusting either.")],
                ["Past spend varied enough to learn from.", "The test result describes one period."], {"overclaim": float(ratio)})
        # 4. seasonality
        if chk["drift"]:
            worst = max(chk["drift"], key=lambda t: abs(t[1]))
            add("seasonality_retest", f"{r.channel}: re-test around seasonality", facts + [f"The control markets drifted {worst[1]:+.1f}% between the pre and test periods ({worst[0]}), which is more than the check allows."],
                ["In order to address drift in the control markets, we might want to think about re-running the test over a calmer period or adding a seasonality adjustment.",
                 "Consider rotating which markets are test and control so the result does not depend on one grouping."],
                "Separate the effect of advertising from seasonal movement in the control markets.", "Repeat the holdout over a stable period, with rotated market groups",
                [("Test length", f"at least {max(int(v.settings.min_test_days), 28)} days"), ("Control drift to beat", "within the check's allowance")],
                ["Calendar window to avoid", "Market rotation plan", "Approval owner"],
                [("If drift is within the allowance:", "consider relying on the new result."), ("If drift persists:", "consider a seasonality adjustment or a different control group.")],
                ["The seasonal pattern repeats from year to year."], {"drift": float(worst[1])})
        # 5. strict confirmation
        if not v.is_strict and pd.notna(ratio):
            sub = v.cd[v.cd["channel"] == r.channel]
            gap = sub.dropna(subset=["spec_iroas", "strict_iroas"])
            ratios = (gap["spec_iroas"] / gap["strict_iroas"].where(gap["strict_iroas"] > 0)).replace([np.inf], np.nan).dropna()
            if len(ratios) and ratios.max() > v.settings.spec_vs_strict_warning_ratio:
                add("strict_confirmation", f"{r.channel}: confirm on the strict basis", facts + [f"The spec view is up to {ratios.max():.1f} times the strict lift view for this channel."],
                    ["Given that the two counting bases differ this much, perhaps we should think about reviewing the strict lift view before any budget decision.",
                     "In order to address the difference, we might want to think about a confirmation test whose design matches the strict basis."],
                    "Know which counting basis is closer to the truth for this channel.", "Confirmation test measured on the strict lift basis",
                    [("First step", "switch the counting basis on the dashboard to strict lift and compare"), ("Follow up", "a test sized for the strict basis (see the evidence gap card if one exists)")],
                    ["Owner of the counting basis decision"],
                    [("If the strict view agrees with the spec view:", "consider keeping the spec view for communication."), ("If not:", "consider anchoring decisions on strict lift.")],
                    ["Both bases are computed from the same test."], {"spec_to_strict": float(ratios.max())})
        # 6. audience split
        if row["tier"] == "VERIFIED" and pd.notna(row["proven"]) and row["proven"] >= be * 1.05:
            add("audience_split", f"{r.channel}: see which audiences drive the lift", facts,
                [f"Given that {r.channel} is above breakeven, perhaps we should think about whether one audience type is carrying the result.",
                 "Consider splitting the audience into three groups, such as existing customers, high intent prospects and a broad audience, each with its own holdout."],
                "Learn whether the return comes from reaching new people or from people who were likely to buy anyway.", "Segmented audience holdout (three cells)",
                [("Cells", "three audience groups, each with a holdout (design default)"), ("Test length", f"at least {max(int(v.settings.min_test_days), 28)} days")],
                ["Audience definitions that can be held out", "Platform support for audience level holdouts", "Approval owner"],
                [("If one group carries most of the lift:", "consider shaping targeting and budget around it."), ("If lift is spread evenly:", "consider broader targeting.")],
                ["Audience groups can be separated cleanly in the platform."], {})
    if not specs:
        return []
    # the counting basis question is portfolio wide: keep one card, naming the other affected channels
    conf = sorted([s for s in specs if s.kind == "strict_confirmation"], key=lambda s: -s.priority)
    if len(conf) > 1:
        others = ", ".join(c.channel for c in conf[1:])
        conf[0].saw.append(f"The same gap between the two counting bases appears for {others}.")
        conf[0].title = "Portfolio: confirm on the strict basis"
        drop = {id(c) for c in conf[1:]}
        specs = [s for s in specs if id(s) not in drop]
    top = max(s.priority for s in specs) or 1.0
    for s in specs:
        s.priority = round(s.priority / top * 100.0, 1)
    return sorted(specs, key=lambda s: (-s.priority, s.id))


def spec_packet(spec: ExperimentSpec, v: RunView) -> Dict[str, Any]:
    """An inbox packet so a research specification can be signed off like any other decision."""
    row = v.ch.set_index("channel").loc[spec.channel]
    return {"packet_id": f"RESEARCH:{spec.id}", "agent_id": "RESEARCH_SPEC", "agent_version": 1, "agent_name": "Research next", "target_persona": "Research and measurement",
            "campaign_id": spec.id, "channel": spec.channel, "severity": "INFO", "tier": row["tier"], "priority": 60, "title": f"Authorize research: {spec.title}",
            "value_add_metrics": {"Method": spec.method, **{k: v_ for k, v_ in spec.design[:2]}}, "raw_metrics": spec.quantities,
            "strategic_callout": spec.objective + " " + (spec.consider[0] if spec.consider else ""), "recommended_action": "AUTHORIZE_RESEARCH", "notes": [],
            "proposed_changes": [{"entity": spec.channel, "change": spec.method}]}
