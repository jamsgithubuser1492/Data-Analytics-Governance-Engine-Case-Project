# Status and roadmap

## Built
* Measurement engine, trust levels, guardrails and advisory council.
* Strategy hub, AI brief with privacy guard and answer checker.
* Research engine with a synthetic control matcher and a media mix model prior calculator.
* Sign-off desk: every decision signed, a hash chained log, a store level rule that refuses unsigned decisions.
* Automation blueprint (design and documentation only): `docs/ARCHITECTURE_MCP.md`.
* Plain language pass on the Dashboard, Advisory council and Sign-off desk (see `docs/VOICE_GUIDE.md`).

## In progress
* Module by module language review of Strategy, AI brief, Research next, Automation, Memos, Benchmarks and Settings.

## Not built, and why
* **MCP server.** Specified in the blueprint; building it needs choices about hosting, sign-in and scopes.
* **Execution connectors.** They need real credentials, change windows and a finance approved process, and are best added one platform at a time with their own tests.
* **Single sign-on.** Signatures currently record a typed email as self asserted. Verified identity is a deployment step.
* **Scheduled data pulls.** They depend on where your data lives.

## Corrections carried forward from the early draft
* A 95% interval exists only on the strict basis; it is never shown for the spec basis.
* Percentages and spend figures are computed from the run, not asserted.
* The system does not issue directives. Interpretation lives in the advisory council and strategy notes, in tentative language.
* Trust gating decides what may be proposed to a human, not what may happen automatically. A model has no approve or execute tool and cannot supply its own trust score.
* An L1 penalty on weights that sum to one does nothing, so the synthetic control offers an explicit top k donor step instead.
* People, hours, contract terms and mixes such as 70/20/10 are editable lenses or blank worksheet fields, not facts.
