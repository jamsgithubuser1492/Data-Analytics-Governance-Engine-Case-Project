# Changelog

## Portfolio ready (latest)
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
