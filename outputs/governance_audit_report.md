# MMGE Governance Audit Report

- Campaigns audited: **8**
- Average trust score: **89.3**
- Verdicts: {'TRUSTED': 6, 'CAUTION': 2, 'UNTRUSTED': 0}
- Trust tiers: {'VERIFIED': 6, 'DIRECTIONAL': 2, 'NOT_DECISION_GRADE': 0}
- Headline metric: **Reported-by-spec iROAS**

| Campaign | Channel | Trust | Tier | Spec iROAS | Strict iROAS (95% CI) | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| GOOGLE_ADS_CMP_01 | Google Ads | 100.0 | VERIFIED | 5.67x (spec overstates) | 1.00x (0.78 to 1.21) | SCALE: iROAS 5.67x. |
| GOOGLE_ADS_CMP_02 | Google Ads | 100.0 | VERIFIED | 5.76x (spec overstates) | 1.00x (0.80 to 1.20) | SCALE: iROAS 5.76x. |
| META_ADS_CMP_01 | Meta Ads | 100.0 | VERIFIED | 3.19x (spec overstates) | 0.56x (0.39 to 0.73) | SCALE: iROAS 3.19x. |
| META_ADS_CMP_02 | Meta Ads | 100.0 | VERIFIED | 3.31x (spec overstates) | 0.59x (0.41 to 0.76) | SCALE: iROAS 3.31x. |
| NETFLIX_ADS_CMP_01 | Netflix Ads | 64.3 | DIRECTIONAL | 0.34x (spec overstates) | 0.01x (-0.06 to 0.08) | REDUCE: iROAS 0.34x after a confirmation test. |
| NETFLIX_ADS_CMP_02 | Netflix Ads | 64.3 | DIRECTIONAL | 0.36x (spec overstates) | 0.02x (-0.04 to 0.09) | REDUCE: iROAS 0.36x after a confirmation test. |
| TIKTOK_ADS_CMP_01 | TikTok Ads | 92.9 | VERIFIED | 2.08x (spec overstates) | 0.36x (0.19 to 0.53) | MAINTAIN: iROAS 2.08x. |
| TIKTOK_ADS_CMP_02 | TikTok Ads | 92.9 | VERIFIED | 2.22x (spec overstates) | 0.39x (0.21 to 0.57) | MAINTAIN: iROAS 2.22x. |

## GOOGLE_ADS_CMP_01

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 6.1% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [363, 561] around 462 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved -9.5% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 11200, MTA 9488, holdout 10140). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.10x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |

## GOOGLE_ADS_CMP_02

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 5.7% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [375, 565] around 470 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved +1.7% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 11068, MTA 9468, holdout 10025). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.10x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |

## META_ADS_CMP_01

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 8.7% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [143, 269] around 206 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved -0.9% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 5463, MTA 4648, holdout 4415). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.24x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |

## META_ADS_CMP_02

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 8.7% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [150, 280] around 215 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved -3.3% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 5694, MTA 4833, holdout 4608). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.24x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |

## NETFLIX_ADS_CMP_01

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | WARN | Smallest detectable lift is 28.9% over 60 test days. |
| 3 | CI width precision | FAIL | 95% CI [-16, 22] around 3 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved -1.0% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 425, MTA 357, holdout 365). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.16x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | FAIL | Lift interval includes zero: result cannot support a budget decision. |

## NETFLIX_ADS_CMP_02

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | WARN | Smallest detectable lift is 26.9% over 60 test days. |
| 3 | CI width precision | FAIL | 95% CI [-12, 26] around 7 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | PASS | Unexposed control geo moved +7.4% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 443, MTA 373, holdout 388). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.14x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | FAIL | Lift interval includes zero: result cannot support a budget decision. |

## TIKTOK_ADS_CMP_01

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 13.7% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [41, 113] around 77 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | WARN | Unexposed control geo moved +10.2% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 2034, MTA 1732, holdout 1570). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.30x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |

## TIKTOK_ADS_CMP_02

| # | Check | Status | Detail |
| --- | --- | --- | --- |
| 1 | Pre-period parallel trend validation | PASS | Treatment and control moved together before launch. |
| 2 | Sample size adequacy | PASS | Smallest detectable lift is 12.8% over 60 test days. |
| 3 | CI width precision | PASS | 95% CI [45, 119] around 82 incremental conversions. |
| 4 | Business benchmark range adherence | NA | The benchmark ranges in this table are illustrative placeholders from the project spec, not verified sources, so no comparison was made. Upload your own benchmark ranges to enable this check. The Benchmarks page lists what has been verified and why most channel ROAS ranges are excluded. |
| 5 | Seasonality contamination check | WARN | Unexposed control geo moved +14.9% between periods. |
| 6 | Cross-source directional alignment | PASS | 2/2 independent sources agree the platform over-claims (platform 2203, MTA 1875, holdout 1698). |
| 7 | Attribution inflation plausibility | PASS | Platform claims 1.30x the holdout conversions. |
| 8 | Decision usefulness under uncertainty | PASS | Lift interval excludes zero and no check failed: safe to act. |
