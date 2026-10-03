-- =============================================================================
-- 03_analytics_reconciliation.sql : ANALYTICS LAYER
-- 90-day campaign totals plus the three core reconciliation ratios.
--   reported_roas    = total_platform_revenue / total_spend
--   incremental_roas = total_holdout_revenue  / total_spend   (iROAS)
--   inflation_ratio  = total_platform_conversions / total_holdout_conversions
-- NULLIF guards every division against zero denominators.
-- =============================================================================
CREATE OR REPLACE VIEW ANALYTICS_MEASUREMENT_RECONCILIATION AS
WITH aggregated_campaigns AS (
    SELECT
        channel,
        campaign_id,
        SUM(platform_spend)       AS total_spend,
        SUM(platform_conversions) AS total_platform_conversions,
        SUM(platform_revenue)     AS total_platform_revenue,
        SUM(mta_conversions)      AS total_mta_conversions,
        SUM(mta_revenue)          AS total_mta_revenue,
        SUM(holdout_conversions)  AS total_holdout_conversions,
        SUM(holdout_revenue)      AS total_holdout_revenue,
        MAX(has_holdout_coverage) AS has_holdout_coverage
    FROM STG_UNIFIED_MEASUREMENT
    GROUP BY channel, campaign_id
)

SELECT
    channel,
    campaign_id,
    ROUND(total_spend, 2)                                              AS total_spend,
    total_platform_conversions,
    total_platform_revenue,
    total_mta_conversions,
    total_mta_revenue,
    total_holdout_conversions,
    total_holdout_revenue,
    has_holdout_coverage,
    ROUND(total_platform_revenue / NULLIF(total_spend, 0), 2)          AS reported_roas,
    ROUND(total_mta_revenue / NULLIF(total_spend, 0), 2)               AS mta_roas,
    ROUND(total_holdout_revenue / NULLIF(total_spend, 0), 2)           AS incremental_roas,
    ROUND(total_platform_conversions / NULLIF(total_holdout_conversions, 0), 2) AS inflation_ratio
FROM aggregated_campaigns;
