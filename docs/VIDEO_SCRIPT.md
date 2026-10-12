# Walkthrough video: full script, shot list and practice guide

Two versions live in this file so you can master the long one and cut the short one.

* **Part A. The full walkthrough (about 9 minutes).** Every key section, the design thinking, how it was built, where it goes next, and who you are. Use this to practice and to record the main video.
* **Part B. The 90 second cut.** The same story compressed for a first look, a LinkedIn post or a recruiter email.

Record with any screen recorder (Loom, QuickTime, OBS) at 1440 wide on the live demo. Speak the lines in your own words once you know the beats. About 140 words a minute is a calm pace. Lines in [square brackets] are for you to fill in with your own facts; do not say anything you cannot back up.

---

## Before you record

* Open the live demo and let it finish loading so the Dashboard is on screen when you start.
* Open these in separate tabs so you can switch without scrolling far: Dashboard, Sign-off desk, Strategy, Research next, the README.
* Practice once end to end. Keep the mouse slow and pause one second after each click.
* Say only numbers you can see on screen. The numbers you may quote are in the cheat sheet at the end.
* Keep the tone of a calm colleague briefing a leader, not a salesperson.

---

# Part A. The full walkthrough

## 1. Hook and who you are (0:00 to 0:40)

| On screen | Say |
| --- | --- |
| Dashboard top, headline visible | "Companies spend heavily on online advertising, and the ad platforms grade their own homework. A finance leader asks one question: did this spend earn its money back? The platforms say yes. The evidence often says otherwise." |
| Stay on the headline | "I built this to answer that question in plain language, with the proof behind it, and with a person signing every decision. I'm [your name], [one line on your current role or focus]. I directed this build as a product owner, and I want to show you how I thought about it, not just what it does." |

Key point to land: the problem is a trust problem between marketing and finance, not a charting problem.

## 2. The idea in one breath (0:40 to 1:10)

| On screen | Say |
| --- | --- |
| Scroll slowly through the headline, summary and cards | "The tool compares three views of the same spending: what the platforms say, what an attribution model says, and what a controlled test proves, where some cities keep seeing ads and similar cities do not. The difference shows what the ads actually caused." |
| Point to the sentence under the headline | "In this synthetic example the platforms claim about four hundred thousand dollars more than the tests support." |

Key point to land: three views, one proof.

## 3. The dashboard answers first (1:10 to 2:10)

| On screen | Say |
| --- | --- |
| Headline | "The first thing you see is the finding, in a sentence a board member could repeat: a hundred and five thousand dollars of ad spend has not been earned back." |
| The four confidence cards | "Right under it, how sure we are: a ninety five percent confidence level, six of eight campaigns with strong enough evidence to act on, and the two that need more testing are named." |
| The amber note about two ways of counting | "When two ways of counting disagree, it says so in plain words. Counting every dollar sold in the test markets makes ads look up to thirty two times better than counting only what the ads caused. I show both and say which is safer, because hiding the unflattering number would defeat the point." |
| Click CFO / Finance, then CMO / Growth | "Each leader gets their own view. The finance chief sees where capital is at risk. The growth lead sees where there is room to scale. Same facts, different questions." |

Key point to land: answer first, evidence second, honest about disagreement.

## 4. Audience tiers: who the money really reaches (2:10 to 3:10)

| On screen | Say |
| --- | --- |
| Scroll to Audience tiers, point at the lead sentence | "Averages hide things. Platforms are rewarded for conversions, so they naturally reach people who were already going to buy, like past visitors. That looks great on a report, but much of it would have happened anyway." |
| Point at the red and green bar and the stat cards | "So I split the audience into tiers by how likely people were to buy without an ad, and compare the test markets with matched control markets. In this example about ninety one thousand dollars of spend, across four tiers, is paying for sales that would have happened anyway." |
| Point at the meter | "Each tier shows a range, not a single number, and a plain sentence: this much of the credited sales did not need the ad." |
| Click Table on a chart | "Every chart states its finding and switches to a table you can copy into a spreadsheet." |

Key point to land: the aggregate is not the whole story; the tiers show where waste concentrates.

## 5. A fair comparison, or no result (3:10 to 3:40)

| On screen | Say |
| --- | --- |
| The control match cards, the TikTok card showing Review required | "A comparison is only as good as the markets you compare against. Each test group is matched to control markets on sales history and on the mix of people in them. Most pass. This one narrowly misses the audience standard, so the card says Review required. I left that in on purpose: the tool shows when it is not sure, and tiers with too little data say not enough data and never recommend anything." |

Key point to land: honest uncertainty is a feature.

## 6. Four advisors, not one answer (3:40 to 4:15)

| On screen | Say |
| --- | --- |
| Scroll to the advisory council | "Four advisors read the same results from different angles: a finance chief who protects capital, a growth leader who wants room to scale, an agency director who has to explain it to a client, and a platform lead who worries about measurement quality." |
| Point at where they agree and split | "You see where they agree and where it comes down to judgement. They suggest, using words like consider, and they never instruct. The decision stays with you." |

Key point to land: the system informs judgement, it does not replace it.

## 7. Nothing changes without a person (4:15 to 5:05)

| On screen | Say |
| --- | --- |
| Open the Sign-off desk, pick a decision | "Every suggestion becomes a decision packet in plain language: what is proposed, why, what is at stake, how sure we are, and which governance checks passed." |
| Show the flow strip, tick the boxes, sign | "A person reviews it, writes a note, gives an email and a role, confirms four statements and signs. A weak result cannot be approved at all, and a strong result never skips the signature." |
| Scroll to the log, point at Log intact | "Each signature goes into a permanent record where every entry is linked to the one before, so any later edit or deletion would show. Nothing here connects to an ad platform; handing off only records the approved change for the team that makes it." |

Key point to land: governance is built into the workflow, not added as a report.

## 8. From results to strategy and next tests (5:05 to 5:50)

| On screen | Say |
| --- | --- |
| Strategy page, trade offs | "Strategy turns results into company decisions: what moving budget would change, a best and worst case, the cost of waiting, and how far a new channel's return could fall before the move stops paying. Anything only your teams know, like costs or hours, is left blank. The system never makes those numbers up." |
| AI brief | "The AI brief writes a safe prompt from numbered facts. Personal data is scanned and removed, only summary totals are shared, and an answer checker flags any number in the AI's reply that does not match." |
| Research next | "Research next ranks the tests worth running next, with sizes and durations computed from the data." |

Key point to land: it closes the loop from evidence to action to the next question.

## 9. How I designed it: design thinking (5:50 to 6:50)

| On screen | Say |
| --- | --- |
| The README case study, or the design system doc | "I started from the decision, not the data. Empathize: who sits in this meeting, a finance chief, a growth leader, an agency director and a measurement lead, and what keeps each of them up at night. Define: one question, did this earn its money back, and how sure are we. Ideate: four advisors, audience tiers, honest ranges. Prototype and test: I reviewed every screen in the language of a non technical reader and removed anything that sounded like a machine or like instructions to the builders." |
| Open the design system doc | "Five principles guided it: answer first, plain language, honest uncertainty, privacy by design, and a person always in control. I wrote them down as a design system and a voice guide, and an automated check fails the build if jargon or builder notes leak onto the screen." |

Key point to land: process and principles, written down and enforced.

## 10. How I built it (6:50 to 7:30)

| On screen | Say |
| --- | --- |
| The README "How this was built" and the test count | "I acted as the product owner and orchestrator. I set the goals, made the trade offs, reviewed every result and set the quality bar. Claude wrote the code under that direction. I treat that as a skill in itself: framing the problem, specifying clearly, checking the output and holding it to a standard." |
| Open the repo, tests, CI badge | "The standard is real: the original data is checksummed, there are about five hundred automated tests, continuous integration runs them on every change, and the numbers in the README are checked against the computed results. Under the hood it is Python, a small in memory database and a web app, but I'll spend my time on the decisions rather than the code." |

Key point to land: orchestrating AI with discipline is a repeatable method.

## 11. Where this goes next: scaling the value (7:30 to 8:30)

| On screen | Say |
| --- | --- |
| Research page, evidence pack section | "The tests in this system are the strongest evidence a company has about what advertising really causes, so the next step is to make them useful everywhere. I designed an evidence pack that turns each result, with its range and quality, into a starting belief for a larger media mix model. Weak or old evidence counts for less, unreliable evidence is never used, and a person signs the release." |
| Open the architecture doc diagram | "From there the same evidence can feed finance planning, a business intelligence layer, the experiment backlog, audience teams and ad operations, through a signed hand off. Model results flow back in as response curves, better research priorities and a flag when the model and the tests disagree. A safe automation design lets AI tools read and propose but never approve or spend." |
| Stay on the diagram | "What would make it real is real data, a validation study that plants a known effect and measures how often the system finds it, proper sign in and roles, and conversations with the people who would use it, to test whether the pain is as sharp as I believe." |

Key point to land: evidence as a shared asset across growth and data systems, with governance throughout.

## 12. Who I am and how I'll use this (8:30 to 9:15)

| On screen | Say |
| --- | --- |
| Back to the dashboard or the README top | "A bit about me: [two sentences on your background and what you care about]. What this project taught me is [your own words, for example: that governance works best when it is part of the product experience, that plain language is a design discipline, and that directing AI well is about clear problems and firm standards]." |
| Stay on screen | "I plan to bring this into [the kinds of work you want to do: for example measurement and analytics governance, data and AI product work, strategy and operations]. I'll keep using the same habits: start from the decision, show the proof and the uncertainty, keep a person accountable, and write it so anyone can follow it. And I'm looking for [your goal: role, team or collaboration]." |

Key point to land: this is how you work, and where you want to apply it.

## 13. Honest close (9:15 to 9:30)

| On screen | Say |
| --- | --- |
| The README limits box | "To be clear about what this is: the data is synthetic, platform names are only labels with no affiliation, nothing connects to a real ad platform, and it is a portfolio project, not production software. Thanks for watching. The demo and the guides are linked below." |

---

# Part B. The 90 second cut

| Time | On screen | Say |
| --- | --- | --- |
| 0:00 to 0:10 | Dashboard headline | "Companies spend heavily on online ads, and the platforms grade their own homework. This tool checks whether the money is really earning its keep, and it keeps a person in charge of every decision." |
| 0:10 to 0:25 | Sentence under the headline, then the four confidence cards | "Here the platforms claim nearly four hundred thousand dollars more than controlled tests support, and six of eight campaigns have strong enough evidence to act on." |
| 0:25 to 0:35 | Click CFO / Finance | "Each leader gets their own view, in their own terms." |
| 0:35 to 0:45 | Audience tiers, the red and green bar | "Platforms often take credit for people who would have bought anyway. About ninety one thousand dollars of spend sits in tiers where most credited sales did not need the ad." |
| 0:45 to 0:55 | Advisory council | "Four advisors read the same results from different angles. They suggest; they never instruct." |
| 0:55 to 1:05 | A chart, then Table | "Every chart states its finding and switches to a table." |
| 1:05 to 1:20 | Sign-off desk, sign, then the log | "Nothing changes without a person. Each decision is signed and kept in a record where any edit would show." |
| 1:20 to 1:30 | Evidence pack or README close | "I designed it from the decision backwards, directed the build as the product owner, and I'm taking it next into media mix models and planning systems. The data is synthetic and the platform names are only labels." |

---

# Practice guide

## Numbers you may quote (all from the synthetic demo; check them on screen)

| Say | Number | Where it appears |
| --- | --- | --- |
| Total ad spend | $748,140 | Dashboard summary card |
| Return per $1, simple count | 3.33x | Dashboard |
| Spend not earned back | $105,158 | Dashboard headline |
| Claimed but unproven revenue | $399,188 | Sentence under the headline |
| Campaigns ready for a confident decision | 6 of 8 | Confidence cards |
| Counting methods disagree by up to | 32.1 times | Amber note |
| Return counting only revenue the ads caused | about 0.57x | README findings table |
| Spend paying for sales that would have happened anyway, in the most affected tiers | $91,288 across 4 tiers | Audience tiers section, README |

## Phrases to memorize

* "The platforms grade their own homework."
* "Answer first, evidence second."
* "Honest uncertainty is a feature."
* "They suggest; they never instruct."
* "Nothing changes without a person."
* "Simple on the surface, rigorous underneath."
* "I directed the build as the product owner."

## Questions you may be asked, and honest answers

| Question | Answer in your own words |
| --- | --- |
| Is this just a ChatGPT wrapper? | No. The core is deterministic measurement and governance logic. AI is optional, sits behind privacy and number checking, and has no power to approve or spend |
| Did you write the code? | I directed it. I set requirements, made the trade offs, reviewed everything and set the quality bar; Claude wrote the code. The tests and checks are how I hold it to a standard |
| Is the data real? | No. It is synthetic and repeatable, and platform names are labels with no affiliation. Real data would be noisier, and I say so |
| What is novel? | Putting evidence, plain language and signed accountability in one workflow, and showing uncertainty and match quality instead of hiding them |
| How does it scale? | Evidence pack into media mix models, then planning, business intelligence and experiment systems, with a signed release and aggregate only data |
| What about privacy? | Aggregate counts only, personal and person level columns are refused, AI prompts use totals, and every release is traceable |
| What would you do differently? | Validate on real or public data, plant a known effect to measure how often it is found, add real sign in, and test with real executives |
| Why should a company trust it? | Ranges, quality checks, a fair comparison requirement, a hash that shows edits, and a person signing every decision |

## Pacing and delivery

* Do not read the screen aloud. Say the sentence, then point.
* One idea per sentence. If you run long, cut the section 8 detail first, then section 10.
* Pause after each key point. A one second pause reads as confidence.
* Record in one take for the full version only after two clean practice runs; for the 90 second cut, record three takes and keep the calmest.
* After uploading, paste the video link into the README line "Watch the 90 second walkthrough".
