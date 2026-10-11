# Feeding a media mix model and other systems: architecture and design framework

**Status:** the evidence pack (section 5) is built and tested. Everything marked Designed or Future is a design, not running software. All figures in worked examples come from the synthetic demo data.

## 1. In one page, for non specialists

A media mix model (MMM) is a statistical model that looks at years of spending and sales and estimates what each channel contributes. It is powerful, because it covers every channel and every week, but it works from correlation. When two things move together (an ad campaign and a sales peak that was coming anyway), it can credit the ads with sales they did not cause.

Controlled tests (geo holdouts) are the opposite. They are narrow, covering one channel, one place and a few weeks, but they show what the ads actually caused.

This system produces the tests. The idea is to let the tests keep the model honest:

1. **The tests become starting beliefs.** A result such as "this channel returned 0.57 for every $1, and we are 95% sure it is between 0.45 and 0.70" is turned into a starting belief (a prior) for that channel's contribution in the model. The model then starts from proof rather than from a blank page.
2. **Weak evidence counts for less.** A result that is only "leaning", that is old, or whose comparison markets were a poor match, is given a wider, humbler belief. A result that is not reliable is never used, and the reason is written down.
3. **The model's answers come back.** The model's saturation curves (how returns fall as spend rises) improve the Strategy page, point to where the next test would teach the most, and raise a flag when the model and the tests disagree.
4. **Other teams use the same facts.** Finance planning, business intelligence, the experiment backlog, audience teams and ad operations can all read the same evidence instead of keeping their own versions of the truth.
5. **A person signs every release.** Nothing flows into a production model or changes spend without a named person reviewing and signing it, and everything is traceable to the run, the settings and the data that produced it.

## 2. Design principles

| Principle | What it means here |
| --- | --- |
| Experiments anchor, models extend | Tests supply causal anchors; the model fills in the channels, weeks and combinations tests cannot cover |
| Evidence before inference | Every record carries its range, evidence level, test window and quality flags. A number without them does not leave the system |
| Humble by default | Weak, old or poorly matched evidence widens the belief; unreliable evidence is excluded and the exclusion is visible |
| One source of truth | Other systems read the evidence ledger; they do not recompute it |
| Aggregate only | No person level data in, none out. Audience results are counts and rates per tier |
| People release, machines propose | A signed person releases evidence to a production model; models and tools never approve or spend |
| Reproducible | Same run, settings and code give the same pack, with a hash that exposes any edit |
| Honest about assumptions | Any default that is a design assumption, not a research finding, is labelled and adjustable |

## 3. The evidence this system produces

| Evidence | Level | What it measures | Source in MMGE | Quality gate | Status |
| --- | --- | --- | --- | --- | --- |
| Campaign test | Campaign | Incremental return per $1 (strict lift), 95% range | Geo holdout, synthetic control | Trust checks, evidence level (Confident, Leaning, Not yet reliable) | Built |
| Channel test result | Channel | The campaign results combined, weighted by their precision | Derived from campaign tests | Lowest evidence level among the campaigns used | Built |
| Audience tier result | Audience tier | Share of credited sales the ads caused, return caused by ads, 95% range | Tier conversion rates, test versus control | Sample guard, range width, control market match | Built |
| Control market match | Per test group | How fair the comparison was (history explained, audience overlap, error) | Propensity weighted control matching | Policy thresholds, pass or review | Built |
| Platform and attribution claims | Campaign | What platforms and the attribution model say | Source files | Never used as a prior; used only to show the gap | Built |
| Signed decisions | Decision | What a person approved, changed or rejected, and why | Sign-off desk and its log | Hash chained record | Built |
| Test designs and backlog | Idea | What to test next, with computed sizes and durations | Research next | Priority computed from spend and uncertainty | Built |

Only the strict lift basis has an interval, so only strict lift evidence can produce a prior. The counting method that credits all test market revenue is listed for comparison and never used.

## 4. From evidence to informed priors

### 4.1 The transformation
For each included record with an estimate and a 95% range:

1. Standard error: `se = (upper - lower) / (2 x 1.96)`.
2. Widen for weaker evidence: `se' = se x widening x sqrt(1 + age / half life)`.
   * `widening` is 1.0 for Confident evidence, a larger factor for Leaning evidence, and a further factor if the control markets did not meet the match standard.
   * `age` is the days between the end of the test and the date the model is built.
3. Floor: `se'` is never below a set share of the estimate, so no prior is more certain than the evidence allows.
4. Log normal prior (always positive, right skewed, the usual shape for an efficiency parameter): `sigma^2 = ln(1 + (se' / estimate)^2)` and `mu = ln(estimate) - sigma^2 / 2`, so the prior has the measured mean and standard deviation `se'`.

### 4.2 Inclusion and exclusion rules
| Situation | Treatment | Why |
| --- | --- | --- |
| Evidence is Not yet reliable | Excluded, listed with the reason | Unreliable evidence would mislead a model |
| No interval (counting all test market revenue) | Excluded | A prior needs a standard error |
| Estimate is not positive | Excluded | A log normal prior does not apply; see open decision 1 |
| Leaning (Directional) evidence | Included, widened | Informative but not firm |
| Control markets failed the match standard | Included, widened further | The comparison may be biased |
| Not enough data in an audience tier | Excluded | Too few people or conversions to judge |

### 4.3 The defaults are assumptions
The widening factors, the half life and the floor are in `PriorPolicy` (`python/calibration_pack.py`). They are **design assumptions to be tuned by backtesting (section 11), not research findings.** Today the defaults are: widening 2.0 for Leaning evidence, a further 1.5 for a failed match, a 365 day half life, and a floor of 5% of the estimate.

### 4.4 Worked example (synthetic demo run)
Channel level priors from the strict lift basis. Pooling combines each channel's campaigns with inverse variance weights and treats the campaigns as independent.

| Channel | Proven return per $1 | 95% range | Evidence | Prior mean | Prior spread | Widening |
| --- | --- | --- | --- | --- | --- | --- |
| Google Ads | 0.998 | 0.851 to 1.145 | Confident | 0.998 | 0.075 | 1.0 |
| Meta Ads | 0.572 | 0.448 to 0.695 | Confident | 0.572 | 0.063 | 1.0 |
| TikTok Ads | 0.378 | 0.254 to 0.501 | Confident | 0.378 | 0.063 | 1.0 |
| Netflix Ads | 0.018 | -0.030 to 0.065 | Leaning | 0.018 | 0.048 | 2.0 |

Netflix shows why the rules matter: its range includes zero, the evidence is only Leaning, and so its prior is very wide (log normal sigma about 1.5). A model told this will let its own data speak, which is the intended behavior.

## 5. The calibration pack (built)

`python/calibration_pack.py` assembles the pack from a run. It can be downloaded as JSON or CSV from the Research next page.

```
mmge.calibration_pack/1.0
  lineage        run id, settings fingerprint, counting basis, breakeven, margin, benchmark version, as of date, test window
  usage_notes    plain warnings for the modeling team (scale, double counting, widening, exclusions, release)
  policy         the widening policy used
  experiments    one record per campaign
  channels       one record per channel (campaigns pooled)
  audience_tiers one record per campaign and tier
  summary        records, included, excluded
  pack_hash      sha256 of the contents, so any edit is visible
```

Each record carries: `evidence_id`, `level`, `channel`, `campaign_id`, `tier_name`, `measure`, `basis`, `estimate`, `lower95`, `upper95`, `evidence_level`, `window`, `spend`, `reference_daily_spend`, `geo_sample_fraction`, `quality_flags`, `included`, `exclusion_reason`, `widening` and `prior` (family, mu, sigma, mean, sd). Audience tier records add the share caused by ads and the decile range.

`validate_pack` refuses a pack that has an unknown schema, includes a record that is not strict lift or not reliable, includes a record without a prior, contains a field name that looks like person level data, or whose hash does not match.

## 6. How a larger MMM uses the pack

Publicly documented MMM toolkits (for example Google's Meridian, Meta's Robyn and PyMC Marketing) describe ways to bring experiment results into a model. The adapters that map a pack to a specific toolkit are **Future** and must be written against that toolkit's current documentation. The patterns are:

| Pattern | How | When to use |
| --- | --- | --- |
| A. Efficiency priors | Set the prior on each channel's return from the pack | Default; simplest; works with any framework that accepts priors on return or contribution |
| B. Calibration observations | Treat each test as an extra observation the model must be able to reproduce (tested spend change and observed lift, with its standard error) | When the framework supports lift test calibration; preferred when tests are short or the tested spend is far from typical spend |
| C. Reconciliation and backtest | Fit freely, then compare each channel's modeled return with the test and flag disagreement | Always, as an independent check on A or B |

**Scale mapping.** A test measures the average incremental return at the tested spend level, not the marginal return. If a model writes a channel's contribution as `beta x S(adstock(spend))`, where `S` is the saturation curve, then a prior on the return at the reference spend `x_ref` implies `beta = return x x_ref / S(adstock(x_ref))`. The pack therefore carries `reference_daily_spend`, and `usage_notes` warns not to use the prior as a marginal return.

**Time.** A test window is short. Carry over effects that land after the window are not seen, so the measured return can understate total return for channels with long delays. Models should use the pack's window and consider immediate versus total effects.

**Levels.** Campaign, channel and audience tier records describe overlapping money. A given model parameter takes evidence from one level only (usually channel, or tier when the model has tier sub-channels), never several, or the same evidence is counted twice.

## 7. Audience tiers in the model

Audience tier results add two things a standard model lacks:
1. **Tier sub-channels.** A channel can be split into tiers (for example high intent retargeting and broad prospecting) with its own saturation behavior and a prior from the tier record. Tiers share information through partial pooling toward their channel, so a thin tier borrows strength without being forced to equal it.
2. **A baseline correction.** The share of credited sales that would have happened anyway tells the model how much of what looks like channel driven sales belongs in the baseline. This reduces the tendency to over credit channels that reach people who were already buying.

This requires aggregate tier level spend and exposure from platforms. It never requires person level data. Tier records with failed control matches carry a flag and a wider prior.

## 8. The loop back: what the model gives the system (Designed)

| Model output | Where it goes | Benefit |
| --- | --- | --- |
| Response curves and marginal return per channel (and tier) | Strategy page | Replaces the constant return assumption and the caution that returns usually fall with a curve and a range |
| Posterior spread per channel | Research next priority | Test where the model is least certain and the spend is largest |
| Disagreement between model and test beyond their ranges | A guardrail raising "Review required" | Catches a model that has drifted, or a test that did not generalize |
| Budget optimization proposals | Decision packets on the Sign-off desk | A person signs any reallocation; the existing action "Move budget between channels" already exists |
| Baseline and seasonality components | Context for the trend view | Separates real movement from calendar effects |

## 9. System architecture

```
 SOURCES                     MMGE EVIDENCE ENGINE (built)                       INTERCHANGE (partly built)
 platform reports      -->   reconcile three views, trust checks,         -->   Evidence ledger (table)
 attribution output          strict lift, synthetic control,                    Calibration pack (JSON, CSV)   [built]
 geo holdout tests           audience tier incrementality,                      Warehouse tables               [designed]
 audience aggregates         control market match                               API and tools (MCP)            [designed]
        |                          |                                                  |
        |                    SIGN-OFF DESK (built)                                    v
        |                    person signs, tamper evident log             CONSUMERS (designed unless stated)
        |                                                                  MMM runner (priors, calibration, backtest)
        +-------- results back (designed) <-------------------------------  BI and metrics layer
                  response curves, posterior spread,                         Finance and FP&A planning
                  divergence flags, optimizer proposals                      Experiment registry and backlog
                                                                             Audience and CDP teams (guidance, never user lists)
                                                                             Ad operations (signed hand off only)
                                                                             CRM and revenue operations (future)
                                                                             Notifications (decision digests)
```

## 10. Interface catalog

| Interface | Direction | Payload | Cadence | Governance | Status |
| --- | --- | --- | --- | --- | --- |
| Calibration pack download | Out | JSON and CSV evidence with priors | On demand | Aggregate only; hash; review before release | Built |
| MMM runner | Out then back | Priors out; response curves and posterior summaries back | Per model build | Signed release; pinned pack hash; model card | Designed |
| Warehouse tables (`MMGE_EVIDENCE` schema) | Out | Evidence ledger, prior policy, pack releases | Per run | Read only for consumers; row level lineage | Designed |
| BI and metrics layer | Out | Governed metrics (proven return, gap, share not caused by ads) | Per run | One metric definition, owned here | Designed |
| Finance and FP&A planning | Out | Scenario and budget tables with ranges | Monthly or quarterly | Ranges shown; no point forecasts without a range | Designed |
| Experiment registry and ticketing | Out and back | Test ideas with computed designs; results back as evidence | Weekly | Test authorization is a signed decision | Designed |
| Audience and CDP teams | Out | Tier guidance (which tiers pay for sales that would have happened anyway) | Per run | Aggregate guidance only; no user lists, ever | Designed |
| Ad operations | Out | Signed hand off entries | On signature | Human signature; nothing sent by this system | Built (simulated), Future (real) |
| MCP tools | Out | Read facts, read the pack, stage a proposal | On request | No approve or execute tool; caller cannot supply trust or evidence level | Designed |
| Notifications | Out | Digest of decisions awaiting signature and divergence flags | Daily or weekly | No figures that are not in the ledger | Future |
| CRM and revenue operations | Out and back | Pipeline quality weighting, long cycle outcomes | Per cycle | Aggregate only | Future |

## 11. Data contracts

### 11.1 Evidence ledger (flat table, built as `calibration_pack.to_frame`)
`evidence_id, level, channel, campaign_id, tier_name, measure, basis, estimate, lower95, upper95, evidence_level, window_start, window_end, spend, reference_daily_spend, quality_flags, included, exclusion_reason, prior_family, prior_mu, prior_sigma, prior_mean, prior_sd, widening, run_id, schema`

### 11.2 Results back from a model (designed)
`model_id, model_version, built_on (pack_hash), channel, tier_name, period_start, period_end, posterior_mean_return, posterior_sd_return, marginal_return_at_current_spend, saturation_half_point, saturation_shape, adstock_decay, share_of_baseline, fit_notes, signed_by, signed_at`

### 11.3 Warehouse design (ANSI sketch, designed)
```sql
CREATE TABLE mmge_evidence.evidence_ledger  (evidence_id VARCHAR, run_id VARCHAR, level VARCHAR, channel VARCHAR, campaign_id VARCHAR, tier_name VARCHAR,
                                             estimate DOUBLE, lower95 DOUBLE, upper95 DOUBLE, evidence_level VARCHAR, included BOOLEAN, exclusion_reason VARCHAR,
                                             prior_mu DOUBLE, prior_sigma DOUBLE, window_start DATE, window_end DATE, PRIMARY KEY (evidence_id, run_id));
CREATE TABLE mmge_evidence.pack_releases    (pack_hash VARCHAR PRIMARY KEY, run_id VARCHAR, released_by VARCHAR, role VARCHAR, released_at TIMESTAMP, note VARCHAR);
CREATE TABLE mmge_evidence.model_results_in (model_id VARCHAR, model_version VARCHAR, built_on_pack_hash VARCHAR, channel VARCHAR, posterior_mean_return DOUBLE,
                                             posterior_sd_return DOUBLE, marginal_return_at_current_spend DOUBLE, period_start DATE, period_end DATE);
CREATE TABLE mmge_evidence.divergence_flags (model_id VARCHAR, evidence_id VARCHAR, model_return DOUBLE, test_return DOUBLE, gap_in_standard_errors DOUBLE, raised_at TIMESTAMP);
```

## 12. Governance and privacy

* **Release workflow (Designed):** Draft pack, review by an analyst, signed release by a named person (recorded in the tamper evident log, with the pack hash), consumed by a model that pins that hash. A model built on an unsigned pack is not production.
* **Change control:** each change to the widening policy is versioned and stamped on every pack; the pack carries its policy.
* **Aggregate only:** the pack is refused if any field name looks like person level data. Audience inputs are aggregate counts and rates.
* **No machine approvals:** consumers and tools can read and propose; they cannot approve or spend. This matches the automation blueprint.
* **Reproducibility:** the same run, settings and code produce the same pack and hash.
* **Model card (Designed):** every model that consumes a pack records the pack hash, the framework and version, the priors used, the backtest results and the sign off.

## 13. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| A short test does not generalize to the year | Carry the window and reference spend; use calibration observations; widen with age; retest on a schedule |
| Tested spend differs from usual spend | Reference spend in the pack; scale mapping; caution against reading the prior as a marginal return |
| The same evidence counted at several levels | One level per parameter; flag `overlaps_channel_level_evidence` on tier records |
| Test spillover between markets | Control market match checks; tests designed with separated markets; flagged as an assumption in each result |
| Model and test disagree | Reconciliation (pattern C) and a divergence guardrail; a person reviews |
| Overconfident priors | Floor on spread; widening for weak evidence; exclusion of unreliable evidence |
| Stale evidence | Age widening; a visible as of date; the research backlog prioritizes retests |
| A mistaken pack reaches production | Signed release, pinned hash, validation that refuses malformed or tampered packs |
| Privacy drift when connecting systems | Aggregate only contracts; person level field names refused |

## 14. Validation plan

1. **Simulation with known truth (Future).** Generate data with a planted effect and confusing background movement; measure how often the engine and the model recover the truth, and whether the 95% ranges contain it about 95% of the time.
2. **Prior sensitivity.** Rerun the model with the widening policy varied; record how much the answers move; tune the defaults to the stable region.
3. **Backtest.** Hold out the last period; compare predictive accuracy with and without the priors, and with and without audience tiers.
4. **Calibration check.** For each past test, did the model reproduce the test result within its range?
5. **Acceptance criteria** are set by the modeling and finance owners before launch; none are assumed here.

## 15. Rollout

| Phase | What | Status |
| --- | --- | --- |
| A | Evidence pack with priors, exclusion rules, hash and validation; download on the Research page | Built |
| B | Warehouse tables and a BI metrics layer; pack releases recorded with a signature | Designed |
| C | MMM runner integration: toolkit adapters, priors and calibration, backtest harness | Designed |
| D | Results back: response curves in Strategy, research priorities from posterior spread, divergence guardrail | Designed |
| E | MCP tools for the pack and results; scheduled builds; notifications; ad operations connectors, each with its own safeguards | Future |

## 16. What each audience gets

| Audience | Value |
| --- | --- |
| Finance chief | A planning model that starts from proof, with ranges, and a signed record of what it was told |
| Growth lead | An optimizer that knows where returns saturate, and tiers that show where growth is real |
| Agency director | One set of facts shared with the client, including exactly which evidence a model used |
| Measurement and platform lead | Lineage from a model parameter back to the test, the markets and the data |
| Data and analytics teams | Stable contracts and tables instead of one off exports |

## 17. Open decisions

1. **Results indistinguishable from zero.** A log normal prior cannot represent a return at or below zero. Options: treat as near zero with a truncated prior, use a different family, or exclude. The current rule excludes only non positive estimates and gives near zero estimates a very wide prior.
2. **Which level feeds the model by default** (channel or tier) and when to split a channel into tiers.
3. **How aggressively to age evidence**, and whether the half life differs by channel.
4. **Which MMM toolkit** to integrate first, and who owns the model.
5. **Who may sign a pack release**, and whether finance and marketing must both sign.
6. **How results come back**: file drop, warehouse write, or API.
