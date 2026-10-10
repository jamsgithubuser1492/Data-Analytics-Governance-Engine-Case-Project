# Changelog

## Audience tier layer (latest)
* Propensity weighted control matching (sales history plus audience mix) with computed match quality, a pass or review verdict against policy thresholds, and a visible comparison with a history only match.
* Audience tier incrementality: share of credited sales caused by ads, revenue and spend paying for sales that would have happened anyway, 95% ranges, a minimum sample guard and evidence levels.
* Aggregate only data contract (decile mix, tier performance, market sales), a staging view in `sql/audience_tier_views.sql`, and synthetic example data in `data/audience/`.
* New policy settings, a new guardrail ("platform credit for sales that would happen anyway") and a "Reduce audience tier spend" action, limited to Leaning evidence or better and always signed by a person.
* New Dashboard section with a dollar first summary per perspective, cannibalization meters, tier charts with table views, control match cards and a view from each advisor; Sign-off desk governance checks for tier decisions; Settings and Upload controls.

## Design system refresh
* Written style guide: `docs/DESIGN_SYSTEM.md` (north star, colour meaning, type, layout, components, language, motion, imagery).
* New navy and green palette on a light page with white cards, Inter with a Georgia headline, subtle borders and shadows, 150 to 250 ms motion, and a branching leaf brand mark.
* New components: executive briefing with impact panel, measurement validity ring, platform, attribution model and holdout comparison, governance checks, and a decision flow that shows where the human approval sits.
* Charts use fixed colours for the three methods (blue, purple, green). Decision cards and the Sign-off desk follow the recommendation card layout.
* Friendlier empty state; Streamlit theme updated for light and dark.

## Portfolio ready
* Public demo mode (`MMGE_DEMO_MODE`): the verified sample data loads by itself, every visitor gets a private throwaway workspace, uploads and settings are read only, and a plain disclaimer is shown.
* README rebuilt for non technical reviewers: one minute idea, findings table, screenshots and GIF, case study, honest limits box, how it was built.
* New guides: page by page guide, glossary, role fit, deploy steps, video script.
* Continuous integration (tests on Python 3.11 and 3.12 plus an app health check), pinned dependencies, Dockerfile, devcontainer, all rights reserved licence.
* `scripts/make_screenshots.py` rebuilds the images and GIF from the demo.

## Plain language pass
* Dashboard headline summary rewritten for executives, with the ROAS stated briefly and a plain statement of how many campaigns support a confident recommendation.
* Trust banner replaced by a confidence strip: confidence level, statistically significant campaigns, campaigns ready for a decision, test coverage.
* Divergence alert explained in business terms. Counting basis labels renamed.
* Confidence levels renamed Confident, Leaning, Not yet reliable.
* Advisory council rewritten to speak in budget, growth, client and measurement terms; stance names made plain.
* Decision cards, agent guardrail text and the Sign-off desk rewritten; actions shown in words; sign-off checklist reworded; hand off replaces dry run wording.
* Builder notes removed from screen; a test blocks them from returning.
* Sidebar version stamp; update instructions added.
* Documentation: `docs/VOICE_GUIDE.md`, `docs/GETTING_STARTED.md`, this changelog; methodology regenerated.

## Research, sign-off and automation
Research engine (ranked tests, synthetic control, media mix priors), Sign-off desk with a hash chained log and a store level rule refusing unsigned decisions, automation blueprint (design only).

## Strategy and AI brief
Strategy hub, privacy guarded AI brief with an answer checker.

## Executive dashboard and advisory council
Redesigned dashboard with perspectives, light and dark themes, Chart or Table toggle; advisory council; guardrails with risk appetite presets; verified data as the default.

## Foundations
Measurement pipeline, trust checks, run store, agent engine, benchmark registry, memos.
