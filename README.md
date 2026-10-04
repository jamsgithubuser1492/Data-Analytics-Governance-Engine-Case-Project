# Media Measurement & Governance Engine (MMGE)

Reconciles three competing views of marketing performance and decides which one to act on:

1. **Platform self-reported** conversions (ad network claims, built-in attribution bias)
2. **Multi-touch attribution (MTA)** output (linear decay deduplication)
3. **Geo holdout incrementality** (randomized ground truth)

Runs locally on **DuckDB**, with SQL written to also run on **Snowflake**. Includes a causal impact runner, an 8-point governance audit, an event-driven agent orchestrator and a Streamlit executive dashboard.

## Architecture

```
 data/generate_synthetic_data.py  (seed 42, 90 days, 4 channels x 2 campaigns)
            |
            v
 RAW LAYER        sql/01_raw_schema.sql           RAW_PLATFORM_DATA | RAW_MTA_OUTPUT | RAW_HOLDOUT_DATA | BUSINESS_BENCHMARKS
            |
 STAGING          sql/02_staging_transforms.sql   STG_UNIFIED_MEASUREMENT   (date, channel, campaign_id grain, holdout / 0.40)
            |
 ANALYTICS        sql/03_analytics_reconciliation.sql   ANALYTICS_MEASUREMENT_RECONCILIATION (reported_roas, incremental_roas, inflation_ratio)
            |
 GOVERNANCE       sql/04_governance_queries.sql   GOVERNANCE_CAMPAIGN_ALERTS | GOVERNANCE_AUDIT_SUMMARY
                  sql/05_rolling_performance.sql  ROLLING_7D_PERFORMANCE
            |
            +--> python/causal_impact_runner.py --> python/governance_checker.py (8 checks, trust score, JSON + markdown)
            +--> python/agent_orchestrator.py  --> app/app.py (Streamlit, persona filtered agent packets)
            +--> outputs/*.csv
```

## Repository layout

| Path | Purpose |
| --- | --- |
| `data/` | Generator plus the four raw CSVs |
| `sql/` | Five ANSI SQL files (Snowflake and DuckDB compatible) |
| `python/database_manager.py` | Builds the in-memory DuckDB warehouse and exports `outputs/` |
| `python/causal_impact_runner.py` | Synthetic control (OLS) estimate: point estimate, 95% CI, relative lift |
| `python/governance_checker.py`, `report_generator.py` | 8-point audit, JSON and markdown reports |
| `python/agent_orchestrator.py` | Three persona agents and simulated Snowflake action log |
| `app/app.py` | Streamlit executive dashboard |
| `tests/test_pipeline.py` | Pytest suite |

## Run it

```bash
pip install -r requirements.txt
python data/generate_synthetic_data.py      # regenerates data/*.csv (deterministic)
python python/database_manager.py           # SQL pipeline -> outputs/*.csv
python python/governance_checker.py         # causal impact + 8-point audit -> outputs/governance_audit_report.{json,md}
pytest tests/test_pipeline.py
streamlit run app/app.py                    # opens http://localhost:8501
```

## Snowflake setup

Run `sql/01_raw_schema.sql` in a worksheet. The commented block at its bottom creates the database, schema, CSV file format and internal stage, and lists the `COPY INTO` commands (upload `data/*.csv` to `@MMGE_RAW_STAGE` first). Then run `02` to `05` in order. Nothing in the SQL is DuckDB specific.

## Metrics

* `reported_roas = total_platform_revenue / total_spend`
* `incremental_roas (iROAS) = total_holdout_revenue / total_spend`
* `inflation_ratio = total_platform_conversions / total_holdout_conversions`
* Holdout treatment conversions and revenue are divided by 0.40 to correct for the 40% geo sample.

Governance status: `CRITICAL_INFLATION_WARNING` at ratio >= 3.0, `MODERATE_INFLATION` at 1.5 to <3.0, `NO_HOLDOUT_COVERAGE` when holdout data is missing, otherwise `PASS`.

Agents: `CAPITAL_PRESERVATION_AGENT` (reported ROAS >= 1.5 and iROAS < 1.0), `ATTRIBUTION_SHIELD_AGENT` (1.25 < inflation <= 3.0), `SCALE_OPPORTUNITY_AGENT` (iROAS >= 3.0 and inflation <= 1.25). Triggers are independent, so one campaign can fire more than one agent.

## Key findings (seed 42 data)

| Channel | Spend | Platform ROAS | MTA ROAS | iROAS | Action |
| --- | --- | --- | --- | --- | --- |
| Google Ads | $264.7k | 6.31x | 5.37x | 5.71x | Scale |
| Meta Ads | $207.97k | 4.02x | 3.42x | 3.25x | Scale |
| TikTok Ads | $113.85k | 2.79x | 2.38x | 2.15x | Monitor |
| Netflix Ads | $161.6k | 0.40x | 0.34x | 0.35x | Reduce |

* Portfolio: $748.1k spend, $2.89M platform revenue claimed, $2.49M holdout revenue, blended iROAS 3.33x.
* The causal runner recovers the planted 1.20x lift (about +20%) for Google, Meta and TikTok. Netflix volume is too small for a significant lift (interval includes zero), so the audit marks that result as not decision grade.
* Shifting all Netflix spend 50/50 into Google and Meta projects about **+$667.5k** net revenue (dashboard simulator default), assuming average iROAS holds at higher spend.
* Currently no campaign triggers the Capital Preservation agent: Netflix is unprofitable, but its platform ROAS (0.4x) is below the 1.5x "looks profitable" gate. It is flagged by the channel level `UNPROFITABLE` action and the audit instead.

## Trust foundations (Phase 0 of the product roadmap)

* `python/config.py`: validated `PolicySettings` (geo sample, thresholds, trust tiers, headline metric). Settings flow into SQL through the one row `POLICY_PARAMS` table, so the same SQL still runs on Snowflake.
* `python/schemas.py` and `python/validation.py`: data contract plus two tier validation (blockers stop a run, warnings are acknowledged). Covers missing columns, bad dates, negatives, duplicate keys, mixed currency, personal data columns, spend unit suspicion, date gaps, coverage gaps, short pre-period and low volume.
* Missing sources are now NULL (unknown), never 0, with per source coverage flags. Channel iROAS divides by the spend of campaigns that actually have holdout coverage.
* `DatabaseManager.build()` runs integrity assertions (row counts, grain uniqueness, spend preserved, no negatives) and raises `PipelineIntegrityError` on failure.
* `python/strict_lift.py`: strict lift iROAS (causal gap only, over test period spend) next to the spec view. The headline metric is a user policy choice and is stamped on every number.
* Trust tiers (Verified, Directional, Not decision grade) gate the money agents: cut and scale packets never fire on results that are not decision grade.

### Spec view vs strict lift (seed 42 data)

| Channel | Reported by spec iROAS | Strict lift iROAS |
| --- | --- | --- |
| Google Ads | 5.71x | about 1.00x (95% CI roughly 0.78 to 1.21) |
| Meta Ads | 3.25x | about 0.57x |
| TikTok Ads | 2.15x | about 0.38x |
| Netflix Ads | 0.35x | about 0.02x (not statistically distinguishable from zero) |

The planted lift is 1.20x, so only about one sixth of treatment geo revenue is truly incremental. Under strict lift no channel clears breakeven on revenue, which changes the budget story: the +$667.5k reallocation figure holds only under the spec view (about +$124k under strict lift).

## Runs, onboarding and the multipage app (Phases 1 and 2)

The dashboard is now a product loop: **Upload, Map, Check, Run, Decide, Act.**

| Page | What it does |
| --- | --- |
| Dashboard (`app/app.py`) | Plain English briefing, KPIs, trust gated agent packets with approve then execute, charts, scenario simulator, all read from a stored run |
| Upload (`app/pages/1_Upload.py`) | Templates, CSV or Excel upload, column mapping with confidence scores, totals row detection, validation report, preview, acknowledge warnings, run |
| Runs (`app/pages/2_Runs.py`) | Run history, compare two runs, agent inbox, audit log, safe CSV and JSON export |
| Settings (`app/pages/3_Settings.py`) | Data declarations (currency, timezone, spend unit, decimal and date format, channel aliases) and measurement policy, saved as versions |

Backend modules: `python/pipeline.py` (`run_pipeline`), `python/run_store.py` (SQLite WAL metadata plus Parquet artifacts, atomic commits, idempotent run keys, workspace scoping, inbox lifecycle, audit log), `python/job_runner.py` (background runs with a concurrency limit), `python/mapping.py` (file reading, mapping suggestions, number and date standardization) and `python/run_compare.py`.

Run data is stored under `var/` (set `MMGE_DATA_DIR` to change it). `PostgresRunStore` is the same code on Postgres but has **not** been exercised against a live database; real object storage, a login provider (Streamlit `st.login`) and Slack or email delivery are deployment steps still to do.

## Agent builder and fact checked memos (Phase 4)

**Agents are data, not code** (`app/pages/4_Agents.py`). A definition has a trigger (conditions on whitelisted metrics), persona, severity, an allowed action, a minimum trust tier, a spend floor, an optional deadband, value-add formulas and a message template. Formulas run in `python/safe_expr.py`, an AST allowlist evaluator (numbers, known field names, arithmetic, `min max abs round div`; no attribute access, imports or other calls). The three original agents ship as presets (`python/agent_presets.py`) and are proven identical to the old hardcoded orchestrator at every boundary, in both headline views. Money actions (cut or scale budget) can never fire below the Directional tier. Opposing money actions on the same campaign are resolved by priority. Each save is a new version, stored per workspace and stamped on every packet and run. The builder previews a rule on a real run and shows a plus or minus 10 percent sensitivity table that flags cliff edge campaigns.

**Memos can only contain numbers the code produced** (`app/pages/5_Memos.py`). Every number a memo may use is a numbered fact (`python/memo_facts.py`). The verifier (`python/memo_verify.py`) rejects any number that does not match, within its displayed precision and unit, a fact cited in the same sentence, plus uncited numbers, missing citations, links, code, markup and instruction-like text. Writers: a deterministic template writer, and a Claude writer (`python/memo_writer.py`) that is only enabled when `ANTHROPIC_API_KEY` is set (model from `MMGE_MEMO_MODEL`, default `claude-opus-5-5`; no tools, no sampling parameters). An AI draft gets one retry with the verifier's feedback, then falls back to the template; refusals, API errors and the daily cap (50 per workspace) also fall back. A memo moves draft, approved, exported; export needs a human approval, edits are re-verified, and every step is in the audit log. Set `MMGE_MEMO_WRITER=template` to disable AI drafting.

Not yet exercised: the live Claude call (tests use a fake client with the same interface).

## Benchmark registry (verified, with provenance)

`benchmarks/` holds `values.csv` (234 records), `sources.csv`, `evidence.json`, `excluded_claims.csv` and `snapshots/` of the primary files. Run `python python/benchmark_sync.py sync` to rebuild from the live sources, `python python/benchmark_verify.py` to re-verify offline (23 checks) and `python python/benchmark_verify.py --live` to re-download and compare (52 checks). `MMGE_LIVE=1 pytest` includes the live check.

**How reliability is enforced (not just documented):**
1. *Official data is parsed from the publisher's file and reconciled.* Damodaran margins (Jan 2026): gross margin equals 1 minus COGS/sales in all 96 industries. Census Vintage 2025: 50 states plus DC equal the US total (341,784,857), and 3,144 county rows equal it again. Census e-commerce share (17.1%, Q2 2026) equals the FRED series. Retail seasonality is the ratio of two Census series (RSXFSN over RSXFS), 12 months by 5 years.
2. *Study claims are admitted one by one.* Each has a verbatim quote extracted from the fetched primary page, and its numbers must appear in that quote; otherwise it is rejected. Every record carries its definition, attribution window, sample size and a confidence grade.
3. *Offline verification re-derives every official value from the stored snapshots* and re-checks every study claim against its spec, so hand edited values, tampered snapshots and hand added records fail (tested). Live verification re-fetches sources; changed files are reported as DRIFT (a new vintage), vanished quotes as FAIL.
4. *Comparability rules decide what a benchmark may be compared with.* For example, Littledata's median conversion rate is a site-wide session rate, so it is offered for order value (as a proxy) but explicitly refused for paid-ad click conversion. Channel ROAS, CPM and absolute incrementality factors have no verified primary source and are answered with "not comparable".
5. *Refused claims are logged with reasons* (`excluded_claims.csv`), including claims that checking the primary pages showed to be wrong or unsupported.

**Things checking the primary pages corrected:** Littledata's own page covers 421 stores (Sept 2026), not the 2,800 quoted by third-party blogs; the Damodaran file has no Retail (Online) row; a paper's abstract says observational methods "often fail to reproduce" experimental effects, not that they overestimate; Haus's publication date was not on the fetched page, so it is recorded as unknown; the Census population API needs a key, while bulk files do not and already hold Vintage 2025.

**What it feeds:** profit aware breakeven (`1 / margin`) from a declared margin or a labeled industry proxy (an upper bound on contribution margin); the geo sample fraction check (treatment geo FIPS codes against Census population, tolerance 15%); an optional seasonality adjustment of the control drift check; and a registry version stamped on any run that used it. The demo's four row `BUSINESS_BENCHMARKS` ranges are unsourced placeholders from the spec, so audit check 4 now reports "not applicable" for them instead of scoring against them.

**Limits:** vendor figures are marketing content (short attributed quotes only, medium confidence at most); Tier B sample sizes are small in places (33 stores); the margin proxies are public company aggregates, not DTC brands; seasonality is macro retail, not your category; Haus lift is a lift on a KPI, not an iROAS.

## Caveats

* The synthetic data is deliberately clean: control equals treatment before launch (zero pre-period variance) and the lift is exactly 1.20x. The causal runner applies a Poisson noise floor so intervals stay honest.
* Per the project spec, iROAS uses total treatment geo revenue scaled by 1/0.40. A stricter incrementality view would use only the lift over the counterfactual (treatment minus synthetic control), which is far smaller. `causal_impact_runner.py` produces that estimate.
* The dashboard's "Execute Action" button simulates a Snowflake governance queue write (a JSON line in `outputs/` plus the INSERT it would run).

## Executive dashboard design

The app is written for non-technical leadership. Design system in `app/ui.py`, chart logic in `app/charts.py`, calculations in `app/dashdata.py` (unit tested), sign-off overrides in `python/overrides.py`.

* **Answer first.** The home page opens with a plain-language hero (for example "Scale Google Ads; maintain Meta Ads and TikTok Ads; cut Netflix Ads") and a note on what moving Netflix spend is worth, before any chart.
* **Five perspectives** (CFO / Finance, CMO / Growth, Agency Director, Platform Lead, Everyone) change the landing view: a capital-at-risk waterfall and leaderboard, a trend and portfolio matrix with growth headroom, side by side spec versus strict lift cards with client note export, or an over-claim alert table with data health.
* **Three lenses.** Capital preservation, attribution shield and scale opportunity each show their rule in words, what they flagged, and the evidence behind each flag (trust score, tier, checks passed, 95% interval, best and worst case).
* **Uncertainty is shown, not hidden.** Strict lift figures carry a 95% confidence interval; channel intervals add campaign bounds (conservative). The trend envelope is labelled as variation, not a statistical interval.
* **Trust gating.** Verified: one click execution. Directional: approval only, execution off. Not decision grade: financial actions locked. A divergence alert appears when the spec view exceeds strict lift by more than 15%.
* **Executive overrides** need a justification of 10 or more characters, an email and a role, and are appended to a hash-chained `run_audit_log.json` that detects any later edit.
* **Every chart** states its finding, stamps the counting basis, and has a Chart or Table toggle. No dual axes. Axes are sized to the data, breakeven and thresholds.
* **Plain labels with an always-on glossary** (hover definitions and formulas). No emojis: status uses a distinct shape plus a text label. Light and dark themes follow the system or the Streamlit menu; data colors are Okabe-Ito based.
* **Honest benchmarks.** No channel return band is drawn because no verified comparable one exists; see the Benchmarks page.
