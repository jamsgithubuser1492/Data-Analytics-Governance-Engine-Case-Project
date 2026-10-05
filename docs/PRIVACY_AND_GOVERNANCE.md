# Privacy and governance

This document describes how the Media Measurement and Governance Engine protects the data it works with, protects company resources, and keeps its recommendations objective. It describes design intent and the safeguards built into the code. It is not legal advice, and it does not replace your own legal, privacy and security review.

## 1. What data the system uses

The system works on **aggregate marketing measurements**: daily spend, impressions, clicks and conversions by campaign, attribution model output by campaign, and geo level experiment counts. It does not need, and must not receive, information about individual people.

| Rule | How it is enforced |
| --- | --- |
| No personal data in uploads | Column names that look like personal data (email, phone, name, address, ID, IP address) are blocked at upload (`python/schemas.py`, `python/validation.py`). |
| Aggregate only in prompts | The AI brief is built only from channel and campaign totals. A guard (`privacy.assert_aggregate_only`) stops raw rows from ever entering a prompt. |
| No personal data in free text | Text typed into the AI brief is scanned for emails, phone numbers, government ID numbers, payment card numbers (with a valid check digit) and IP addresses, and anything found is replaced with a marker (`python/privacy.py`). |
| Names can be hidden | Channel and campaign names can be replaced with reversible local aliases before a prompt leaves the app. The alias key stays in the app. |
| Minimal logging | Exports of an AI brief are recorded in the audit trail by SHA-256 fingerprint only. The text itself is never stored. |

## 2. Principles the design follows

These map to common privacy principles, for example those in GDPR and CCPA. They are design alignments, not a statement of compliance.

* **Data minimization.** Collect and send only what the purpose needs. Aggregate totals are enough; individual records are not.
* **Purpose limitation.** Data is used to measure advertising effect and support budget decisions.
* **Storage limitation.** Runs are stored per workspace. Decide a retention period and delete runs that are no longer needed.
* **Security.** Keep the data directory and any database private, use access control and encryption at rest, and keep API keys in environment variables, never in code.
* **Accountability.** Every decision step is logged. Overrides are written to a hash chained log that reveals later edits or deletions.
* **Transparency.** Every figure states its counting basis, its evidence level and its source.

## 3. Using an AI service safely

The AI brief is designed so that an executive can use their own company approved assistant without exposing data.

1. Use only an AI service your company has approved for confidential information, ideally one with no training on your inputs and appropriate data retention terms.
2. Read the privacy review panel before copying. It lists what is in the brief and what is not.
3. Prefer the alias option when the service is outside your control.
4. Do not paste customer data, contract terms you are not allowed to share, or anything else the brief did not contain.
5. Use the answer check. It compares each number in an answer with the facts and flags overconfident phrasing.

## 4. Objective recommendations and protecting company resources

* **Facts and interpretation are separate.** Headlines, charts and stats state findings from the data. Interpretation lives in the advisory council and strategy notes, and is worded only as "Consider...", "Given that..., perhaps we should think about..." or "In order to address..., we might want to think about...".
* **Uncertainty is always shown.** Results that count only revenue the ads caused carry a 95% likely range. Confidence levels (Confident, Leaning, Not yet reliable) limit what can be approved or handed off.
* **Plain language is a governance control.** Decision text is written for non-technical leaders so that people sign what they understand (`docs/VOICE_GUIDE.md`).
* **Assumptions are labelled.** Anything the data cannot support (people, hours, contract terms, saturation) is a blank worksheet field or a labelled sensitivity, not a stated fact.
* **Even handed prompts.** The brief asks the assistant to present both sides, name the strongest case against the leading option and say what would change the conclusion.
* **Money does not move automatically.** The system never executes spending changes on its own. Every decision (approve, override or reject) is a signed entry with a note, an email, a role and four acknowledgements, written to a hash chained log, and the store refuses to approve, execute or dismiss an item without it. Until single sign-on is configured, the signer's email is typed and recorded as self asserted. See `docs/ARCHITECTURE_MCP.md` for how AI models could connect without any ability to decide.
* **Resources.** Aggregate processing is light. Calls to an AI service are optional, capped and verified before display.

## 5. Open items for your organization

* Name an owner for data protection decisions and an approved AI service list.
* Decide retention and deletion rules for runs and audit logs.
* Decide who may access the workspace and how sign in is provided.
* Review contracts with ad platforms and any AI vendor, including where data is processed.
