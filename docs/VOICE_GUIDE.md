# Voice guide: writing for the business reader

Everything on screen is written for a leader who thinks in revenue, budget, resources and where to focus next. They do not have a marketing science or data science background. This guide keeps new text consistent. Shared wording lives in `python/voice.py`.

See also `docs/DESIGN_SYSTEM.md` for colour, layout and components.

## Principles
1. **Lead with the business consequence.** Say what it means for money, a client or a team, then give the number.
2. **Sound like a person briefing a senior colleague.** One clear sentence beats three statistics. Example: "While platforms have self-reported revenue figures, our holdout tests reveal a $399,188 gap between what they claim and what our measurements support."
3. **Facts are objective; ideas are tentative.** Headlines and figures state findings. Recommendations open only with "Consider...", "Given that X, perhaps we should think about...", or "In order to address X, we might want to think about...".
4. **Never state an unsourced estimate as fact.** Costs, hours and contract terms are blank worksheet fields for the user to fill in.
5. **Never show builder notes.** Design intent, requirement numbers and explanations of how the page was built do not appear on screen. Code comments are the place for them.
6. **No emojis, no dashes in sentences.** Status is a distinct shape plus a text label.
7. **Explain a term once in plain words.** Technical names appear only in the Sources section or in hover definitions.

## Translation table
| Internal term | What the reader sees |
| --- | --- |
| Verified, Directional, Not decision grade | Confident, Leaning, Not yet reliable |
| Trust score 89 of 100 | "How sure we are" in a phrase; the score stays under Sources |
| Strict lift | Only revenue the ads caused |
| Reported by spec | All revenue in the test markets |
| iROAS | Proven return per $1 |
| Over-claim multiple | How many times the platform overstates results |
| Holdout test | Control test in matched markets |
| 95% CI | We are 95% sure the true figure is between X and Y |
| Statistically significant | The lift is clearly more than zero |
| Divergence alert | The two ways of counting results disagree |
| Capital preservation rule | Money not earned back |
| Lean in / Hold / Re-test / Pull back / Get more evidence | Put more behind it / Keep as is / Test again before deciding / Reduce spend / Prove it before deciding |
| REDUCE_BUDGET_50% | Reduce the budget by half |
| Override | Change to a decision of your own |
| Dry run execution | Hand off to the team (nothing is sent to an ad platform) |
| self_asserted | Typed in by user |

## Enforcement
`python/voice.py` holds `BANNED_ON_SCREEN`, a list of phrases that must never render. `tests/test_dashboard_ui.py` checks every dashboard perspective against it. Add to the list when a new builder phrase slips through.

## Pages still to review
The Dashboard, Advisory council and Sign-off desk have had this pass. Strategy, AI brief, Research next, Automation, Memos, Benchmarks and Settings are reviewed module by module as feedback arrives.
