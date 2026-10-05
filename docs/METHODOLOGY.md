# How the Media Measurement and Governance Engine works

This guide is written for someone who has never seen the model. It explains what is measured, how much to trust it, how the guardrails and the advisory council work, and what the system will never do.

## 1. The question this answers

Ad platforms report how much revenue their ads produced. Those reports are generous: a platform takes credit for every sale it touched, including sales that would have happened anyway. The question for a budget owner is different: **for each $1 spent, how much revenue did advertising actually cause?** This engine reconciles three sources of evidence to answer it, and tells you how sure it is.

## 2. The three sources of evidence

1. **Platform reports.** What each ad platform says it delivered. Useful for spend and activity, but platforms grade their own homework, so the revenue they claim tends to run high.
2. **Attribution model.** A multi touch attribution (MTA) model that splits credit across touchpoints and removes double counting between platforms. Better than platform reports, but still an estimate of credit, not proof of cause.
3. **Geo holdout test.** The proof. Some markets keep seeing ads (test markets) and similar markets do not (control markets). The difference between them shows what the ads caused.

## 3. How the holdout test produces a number

The test has two phases. In the **pre period** (30 days in the demo) both groups run as normal, which shows how similar they are. In the **test period** (60 days) only the test markets are exposed. A statistical control, built from the control markets, estimates what the test markets would have done without ads. The gap between actual and expected is the **revenue the ads caused**. Because the test markets are a sample of the country (40% in the demo), the gap is scaled up to the full market.

## 4. Two ways to count: Strict lift and Reported by spec

**Strict lift** counts only the gap the ads caused, scaled to the full market. It is the more conservative and defensible view. **Reported by spec** counts all revenue in the test markets as caused by ads. It is simpler but overstates the return whenever the markets would have sold anyway. Both are always calculated. The counting basis in the sidebar decides which one drives headlines, and every chart says which basis it uses. When Reported by spec is more than 15% above Strict lift, the dashboard shows a divergence alert.

## 5. Breakeven and margin

A return of 1.00x only breaks even if every dollar of revenue were profit. Breakeven is **1 divided by your contribution margin**: at a 50% margin you need $2 of revenue per $1 spent, so breakeven is 2.00x. A margin is never assumed silently. If you do not declare one, returns are shown as revenue returns and breakeven is 1.00x. You can declare a margin in Settings or choose an industry proxy, which is an upper bound.

## 6. The trust score and the three trust levels

Every campaign gets a 0 to 100 trust score from eight checks: (1) treatment and control moved together before launch, (2) the test was big enough to detect a realistic lift, (3) the confidence interval is narrow enough to be useful, (4) results sit inside a verified benchmark range (not applicable unless a verified benchmark exists), (5) the control markets did not drift because of seasonality, (6) the independent sources agree, (7) platform over-claiming is plausible, and (8) the result is useful for a decision under its uncertainty.

- **Verified** (75 or more, and check 1 passes): the evidence supports action. One click execution is enabled.
- **Directional** (50 to 74): informative but advisory. Execution is switched off and manual review is expected.
- **Not decision grade** (below 50): financial actions are locked until the data improves.

Results show a **95% confidence interval**: the range the true value falls in 95 times out of 100. Channel intervals add campaign bounds together, which is conservative.

## 7. Guardrails: the rules that watch your results

Three guardrails run on every result. You set them in plain business terms on the Advisory council page, under Your guardrails.

| Guardrail | Raises its hand when | If you loosen it | If you tighten it |
| --- | --- | --- | --- |
| Money not earned back | A platform claims a high return but the test proves less than breakeven | Fewer alerts, later warnings | More alerts, earlier warnings |
| Platforms claiming more than proven | A platform claims more than the allowed multiple of what the test confirms | Tolerates more over-claiming | Flags smaller gaps |
| Room to grow | Proven return is high and over-claiming is low | More campaigns qualify | Only the strongest qualify |

Every guardrail also has a minimum evidence level and an optional minimum spend, so small or weakly measured campaigns do not create noise. Money related guardrails never fire on results that are not decision grade.

## 8. Risk appetite: Conservative, Balanced or Aggressive

A risk appetite sets all three guardrails at once. **Conservative** wants stronger proof before money moves and reacts to smaller problems. **Balanced** is the standard case study setting. **Aggressive** acts on earlier signals and tolerates more noise. The page shows how many campaigns each appetite would flag on your current run before you apply it. Every change is saved as a new version.

## 9. The advisory council

The council is four personas who read the same verified facts through different motivations: **The Steward** (CFO, conservative), **The Builder** (CMO, aggressive), **The Translator** (agency director, moderate) and **The Mechanic** (platform lead, moderate). Each has their own bar for evidence, their own idea of what counts as clearly profitable, and their own tolerance for over-claiming. They disagree on purpose: the disagreement shows where judgement, not data, decides.

The council is the **interpretation layer**. Everything else in the app states facts. The personas offer possibilities in tentative language ("Consider...", "Given that..., perhaps we should think about...", "In order to address..., we might want to think about...") and always show the facts and what would change their mind. The decision stays with the executive.

## 10. What the system will never do

- It never moves money. Every action needs a human approval, and overrides need a written reason that is saved in a tamper evident log.
- It never invents numbers. Every figure comes from the run. Written memos are checked so that any number not tied to a verified fact is rejected.
- It never tells you what to do. Headlines state findings. Personas suggest ideas to consider.
- It never hides uncertainty. Results carry intervals, trust levels and the counting basis.

## 11. Limits and honest caveats

- The demo data is synthetic and built so that the case study is repeatable. Real data will be noisier.
- Scaling a test sample to the full market assumes the test markets are representative. The engine checks this against population data when you declare the geos.
- Average returns do not hold forever. Moving large budgets usually lowers the return, so confirm with a scaled test.
- Outside benchmarks are context, not truth. No verified channel return range exists in the registry, so none is drawn.

