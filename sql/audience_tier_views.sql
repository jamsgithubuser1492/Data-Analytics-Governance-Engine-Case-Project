-- Audience tier incrementality: staging tables and a derived view. ANSI SQL for DuckDB and Snowflake.
-- This file is documentation and a parity check for python/audience_tiers.py. It is NOT run by the standard pipeline
-- (the pipeline is pandas based for this layer so it can also compute 95% ranges). Aggregate inputs only: no person
-- level rows and no feature columns are staged.

CREATE TABLE IF NOT EXISTS stg_dma_propensity_distributions (
    dma_code VARCHAR PRIMARY KEY,
    dma_name VARCHAR,
    decile_1_pct DOUBLE, decile_2_pct DOUBLE, decile_3_pct DOUBLE, decile_4_pct DOUBLE, decile_5_pct DOUBLE,
    decile_6_pct DOUBLE, decile_7_pct DOUBLE, decile_8_pct DOUBLE, decile_9_pct DOUBLE, decile_10_pct DOUBLE   -- each row sums to 1.0
);

CREATE TABLE IF NOT EXISTS stg_audience_tier_performance (
    date DATE NOT NULL,
    channel VARCHAR NOT NULL,
    campaign_id VARCHAR NOT NULL,
    tier_name VARCHAR NOT NULL,
    tier_decile_start INTEGER NOT NULL,
    tier_decile_end INTEGER NOT NULL,
    spend DOUBLE NOT NULL,
    reported_revenue DOUBLE NOT NULL,
    treatment_conversions DOUBLE NOT NULL,
    treatment_users DOUBLE NOT NULL,
    control_conversions DOUBLE NOT NULL,
    control_users DOUBLE NOT NULL,
    PRIMARY KEY (date, campaign_id, tier_name)
);

-- Share of credited conversions that the ads caused, and the share that would have happened anyway.
CREATE OR REPLACE VIEW view_audience_tier_disaggregation AS
WITH t AS (
    SELECT channel, campaign_id, tier_name,
           SUM(spend) AS total_spend,
           SUM(reported_revenue) AS total_reported_revenue,
           SUM(treatment_conversions) / NULLIF(SUM(treatment_users), 0) AS cvr_treatment,
           SUM(control_conversions) / NULLIF(SUM(control_users), 0) AS cvr_control
    FROM stg_audience_tier_performance
    GROUP BY channel, campaign_id, tier_name
), l AS (
    SELECT *, GREATEST(0.0, (cvr_treatment - cvr_control) / NULLIF(cvr_treatment, 0)) AS incremental_lift_ratio FROM t
)
SELECT channel, campaign_id, tier_name, total_spend, total_reported_revenue, cvr_treatment, cvr_control, incremental_lift_ratio,
       total_reported_revenue * incremental_lift_ratio AS strict_incremental_revenue,
       total_reported_revenue * (1.0 - incremental_lift_ratio) AS cannibalized_revenue,
       (1.0 - incremental_lift_ratio) * 100.0 AS cannibalization_index_pct,
       total_spend * (1.0 - incremental_lift_ratio) AS spend_for_organic_sales,
       total_reported_revenue / NULLIF(total_spend, 0) AS reported_roas,
       total_reported_revenue * incremental_lift_ratio / NULLIF(total_spend, 0) AS strict_iroas
FROM l;
