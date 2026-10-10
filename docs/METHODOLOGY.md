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

## 4. Two ways to count: only revenue the ads caused, or all test market revenue

**Only revenue the ads caused (strict lift)** counts just the gap the ads created, scaled to the full market. It is the more conservative and defensible view. **All revenue in the test markets (reported by spec)** counts every dollar sold in the test markets as caused by ads. It is simpler but overstates the return whenever the markets would have sold anyway. Both are always calculated. The counting basis in the sidebar decides which one drives headlines, and every chart says which basis it uses. When the all revenue count is more than 15% above the caused revenue count, the dashboard explains that the two ways of counting disagree and by how much.

## 5. Breakeven and margin

A return of 1.00x only breaks even if every dollar of revenue were profit. Breakeven is **1 divided by your contribution margin**: at a 50% margin you need $2 of revenue per $1 spent, so breakeven is 2.00x. A margin is never assumed silently. If you do not declare one, returns are shown as revenue returns and breakeven is 1.00x. You can declare a margin in Settings or choose an industry proxy, which is an upper bound.

## 6. How sure we are: confidence, significance and the three confidence levels

Every campaign gets a 0 to 100 trust score from eight quality checks. The Dashboard turns it into plain words, but the score and checks stay available under Sources: (1) treatment and control moved together before launch, (2) the test was big enough to detect a realistic lift, (3) the confidence interval is narrow enough to be useful, (4) results sit inside a verified benchmark range (not applicable unless a verified benchmark exists), (5) the control markets did not drift because of seasonality, (6) the independent sources agree, (7) platform over-claiming is plausible, and (8) the result is useful for a decision under its uncertainty.

- **Confident** (called Verified in the audit, score 75 or more, and check 1 passes): the evidence is strong enough to act on and to hand to the team that makes the change.
- **Leaning** (called Directional, 50 to 74): the evidence points one way but is not yet strong. You may approve, but handing off is switched off until further testing.
- **Not yet reliable** (called Not decision grade, below 50): money decisions are locked until the data improves.

Results show a **95% confidence range**: we are 95% sure the true value sits inside it. A campaign is **statistically significant** when that range sits entirely above zero, meaning the lift is clearly real and not noise. The Dashboard summarizes this as the confidence level, the number of significant campaigns, the number ready for a confident decision and the test coverage. Channel ranges add campaign bounds together, which is conservative.

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

## 9. Audience tiers: who the money actually reaches

Ad platforms are rewarded for conversions, so they naturally reach people who were already likely to buy, such as past visitors. That produces a high reported return, but much of that revenue would have arrived anyway. The audience view separates the two.

People are grouped into tiers by how likely they were to buy without seeing an ad (for example Tier 1 is the most likely buyers, Tier 3 is a broad audience). For each tier we compare the conversion rate in the test markets with the rate in the matched control markets. The share of conversions the ads caused is the gap between the two, divided by the test rate. Reported revenue times that share is the revenue the ads caused; the rest would have happened anyway. Spend is split the same way, which gives the headline figure: how many dollars of a tier's spend are paying for sales that would have happened anyway.

Each tier carries a 95% range. A tier is only judged when both the test and control markets reached enough people and produced enough conversions (you set the minimums in Settings). Tiers below that bar show "not enough data" and never raise a recommendation. Evidence is Confident when the range is narrow and the control markets match well, and Leaning when either falls short. When the share of credited sales that ads did not cause passes your line (75% by default) and the evidence is at least Leaning, a recommendation to consider reducing spend on that tier appears on the Sign-off desk. A person decides.

This layer always counts only the extra conversions the ads caused (strict lift). It uses aggregate counts only: no person level rows and no personal data. The example files are synthetic.

## 10. Control markets: how well the comparison is matched

A comparison is only as fair as the markets it is made against. Each group of test markets is matched to a blend of control markets that did not see the ads. The match uses two things: the sales history of the markets before launch, and the mix of people in them (the share of residents in each of ten likelihood to buy groups). Matching on both avoids choosing markets that sold similar amounts but are home to different kinds of people.

Three measures describe the match: how much of the pre launch movement in sales the blend explains, how much the audience mixes overlap, and how large the pre launch error is as a share of average sales. Each is compared with a standard you can change in Settings, and the card says Match passed or Review required. The match quality is computed from the data, and the page also shows what a history only match would have scored, so the benefit of matching on audience is visible rather than assumed.

## 11. The advisory council

The council is four seasoned advisors who read the same results through their own priorities: **The Steward** (CFO, conservative), **The Builder** (CMO, aggressive), **The Translator** (agency director, moderate) and **The Mechanic** (platform lead, moderate). Each has their own bar for proof, their own idea of what counts as clearly profitable, and their own tolerance for platforms claiming more than the tests confirm. Their stances read Put more behind it, Keep as is, Test again before deciding, Reduce spend and Prove it before deciding. They disagree on purpose: the disagreement shows where judgement, not data alone, decides.

The council is the **interpretation layer**. Everything else in the app states facts. The advisors speak in revenue, budget and client terms, and offer possibilities in tentative language ("Consider...", "Given that..., perhaps we should think about...", "In order to address..., we might want to think about...") and always show the numbers behind a view and what would change their mind. The decision stays with the executive.

## 12. Business strategy: from results to company decisions

The Strategy page works from the same run. It shows what moving budget would change and how sure that is (a best and worst case on the strict basis), a modeled value of waiting per week, and a sensitivity that answers the usual objection: **how much lower could the return on the new money be before the move stops adding revenue?**

It then lists, for Finance, Marketing and creative, Agencies, Data and engineering, and Legal, what changes and what would need to be found out. The system computes what the data supports and leaves the rest (costs, hours, contract terms) blank for you, so it never states an unsourced figure as fact. A change plan suggests who may care about what and a phased path. An optional budget lens compares today's spend with a tiered target mix you set. A monitor shows whether returns are holding and which campaigns would meet a capital protection rule; it is information only.

## 13. The AI brief and the answer check

The AI brief turns a run into a prompt you can paste into your company's approved AI service. Every number is a numbered fact [F#] computed from the run, an interval appears only when the run computed one, and the rules ask the assistant to cite facts, label assumptions, argue both sides and never tell you to move money. Raw rows and personal data are never included, anything you type is scanned and redacted, and you can replace channel and campaign names with aliases. Exports are recorded by fingerprint only.

Paste the assistant's answer into **Check an AI answer** and every figure is compared with the facts. A figure that is not in the facts may be an assumption or an invention. The check looks at numbers and overconfident phrasing; it cannot judge whether the reasoning is sound.

## 14. Research next: what to test after a result

A result is one measurement of one period. The Research page looks at what the run leaves uncertain and ranks tests to consider: a longer test with a synthetic control when evidence is below Verified, a multi-cell step-up test when a strong channel's behavior at higher spend is unknown, a media mix model calibrated with the test result when platforms claim much more than the test confirms, a re-test around seasonality, and an audience split for strong channels. Test length, spend in the test markets and the minimum detectable effect are computed from your run; people, hours and contract terms are left blank for your teams. Two tools help design a test: a synthetic control matcher (a weighted blend of untreated markets that mimics the test markets before launch, with a fit check) and a calculator that turns a test result and its margin of error into a starting belief for a media mix model.

## 15. The sign-off desk: every decision is signed

Nothing changes without a signature. For every decision, whether you approve it, change it to a decision of your own or reject it, you write a note of at least 10 characters, give your email and role and tick four acknowledgements. The decision is written to a log in which each entry is chained to the one before, so a later edit or deletion is visible, and the store refuses to move any item to approved, executed or dismissed without that signature. A result that is not decision grade cannot be approved. A strong result does not skip the signature. Guardrail flags, strategy scenarios and research ideas all arrive in the same queue. Until single sign-on is set up, the email is typed by the signer and the log records it as typed in rather than verified. The hand off step only records the approved change for the team that makes it; nothing is sent to an ad platform.

## 16. Automation: connecting AI models safely

The Automation blueprint describes how AI models could connect to the engine through the Model Context Protocol so that data pipelines and proposals run continuously. It is a design, not a running server. A connected model would have six narrow tools: five that read and one that stages a proposal. There is no approve tool and no execute tool, the model can never supply its own trust score, and a staged proposal does nothing until a person signs it on the Sign-off desk.

## 17. What the system will never do

- It never moves money. Every action needs a human signature, and changes of decision need a written reason that is saved in a tamper evident log.
- It never invents numbers. Every figure comes from the run. Written memos are checked so that any number not tied to a verified fact is rejected.
- It never tells you what to do. Headlines state findings. The advisors and strategy notes suggest ideas to consider.
- It never hides uncertainty. Results carry confidence ranges, confidence levels and the way they were counted.

## 18. Limits and honest caveats

- The demo data is synthetic and built so that the case study is repeatable. Real data will be noisier. Platform names such as Google, Meta, TikTok and Netflix are illustrative labels with no affiliation to those companies.
- Signing and hand off are simulated. Nothing is sent to an ad platform and no real money moves. This is a portfolio demonstration, not production software or financial advice.
- Scaling a test sample to the full market assumes the test markets are representative. The engine checks this against population data when you declare the geos.
- Average returns do not hold forever. Moving large budgets usually lowers the return, so confirm with a scaled test.
- Outside benchmarks are context, not truth. No verified channel return range exists in the registry, so none is drawn.
