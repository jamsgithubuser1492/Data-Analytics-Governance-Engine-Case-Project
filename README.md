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

Governance status: `CRITICAL_INFLATION_WARNING 🚨` at ratio >= 3.0, `MODERATE_INFLATION 🟡` at 1.5 to <3.0, `NO_HOLDOUT_COVERAGE ⚠️` when holdout data is missing, otherwise `PASS ✅`.

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

## Caveats

* The synthetic data is deliberately clean: control equals treatment before launch (zero pre-period variance) and the lift is exactly 1.20x. The causal runner applies a Poisson noise floor so intervals stay honest.
* Per the project spec, iROAS uses total treatment geo revenue scaled by 1/0.40. A stricter incrementality view would use only the lift over the counterfactual (treatment minus synthetic control), which is far smaller. `causal_impact_runner.py` produces that estimate.
* The dashboard's "Execute Action" button simulates a Snowflake governance queue write (a JSON line in `outputs/` plus the INSERT it would run).
