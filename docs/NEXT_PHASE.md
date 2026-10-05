# Next phase: research engine, sign-off desk and automation blueprint

This phase builds on the Strategy hub and AI brief. Decisions already confirmed:

* **MCP**: blueprint and documentation only, with no server code.
* **Estimates**: organizational estimates are editable worksheet inputs, computed where the run supports it, never stated as facts.
* **Sign-off**: every decision (approve, override or reject) needs a note of 10 or more characters, an email, a role and a short checklist, and nothing may reach approved or executed without a signed entry.

## 1. Research and experimentation engine

Turns what a run shows into the next question to ask, with a specification a team can act on.

| Run signal | What it may mean | Method to consider |
| --- | --- | --- |
| Low trust score and a wide interval | The test was too small or too noisy for a decision | A longer test with a synthetic control, or more markets |
| High proven return, unknown behavior at higher spend | Saturation point is unmeasured | A step-up test with cells at different spend levels |
| High platform over-claim | Platform credit and test results differ | Calibrating a media mix model with the test results |
| Strong return, unknown audience mix | Retargeting may be flattering prospecting | A holdout split by audience tier |

Each recommendation becomes a specification card. Quantities that the run can support (current minimum detectable effect, test duration from conversions per day, test spend from the current spend rate) are computed. Everything else is a labelled input.

Two tested helper tools accompany it:

* **Synthetic control matcher.** Finds non-negative donor weights that sum to one and fit the pre-period, with a fit check on the pre-period error.
* **MMM prior calculator.** Converts a test result and its standard error into the log normal prior parameters an MMM needs, using the standard error implied by the 95% interval.

## 2. Sign-off desk

The final human gate. A decision packet shows the proposed change, the evidence, the trust level and the counting basis. The executive completes a checklist, writes a note, and enters email and role. The outcome is one of approved, overridden or rejected, and each is appended to the hash chained audit log with the policy version, trust score and a signature hash. A store level rule makes it impossible to reach approved or executed without a signed entry, however strong the statistical case.

## 3. Automation blueprint (MCP)

A design for connecting models to the engine through the Model Context Protocol so that data pipelines and decision structures can run continuously while humans stay in control.

* **Read tools**: get verified run facts, evaluate guardrails, simulate a reallocation, recommend experiments.
* **Stage tool**: creates a staged packet only. There is no tool that approves or executes.
* **State machine**: ingested, computed, trust gated, staged, signed, then executed through an outside connector. Below the Directional level nothing can be staged.
* **Security**: read only by default, workspace scoped access, authenticated sessions, an allowlist of tools, every call logged, aggregate data only, no credentials for ad platforms inside the model layer.
* **Always on pipeline**: scheduled ingestion, run creation, guardrail evaluation and notification, with the human gate unchanged.

## 4. Corrections carried forward from the early draft

* A 95% interval exists only on the strict basis; it is never shown for the spec basis.
* Percentages are computed from the run, not asserted.
* Amounts are channel level unless a campaign is named.
* The system does not issue directives such as "lean in" or "pull back". Those are tentative views in the advisory council.
* Trust gating decides what may be staged for a human, not what may happen automatically.
* People, hours, contract terms, 70/20/10 mixes, a 1.25x marginal threshold and a $10,000 capital rule are editable policy lenses or worksheet fields, not facts.
