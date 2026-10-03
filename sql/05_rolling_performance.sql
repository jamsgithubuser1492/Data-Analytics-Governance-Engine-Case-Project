-- =============================================================================
-- 05_rolling_performance.sql : 7-DAY ROLLING PERFORMANCE
-- Window frame covers the current day and the 6 preceding days per campaign.
-- Rolling iROAS = rolling holdout revenue / rolling spend.
-- =============================================================================
CREATE OR REPLACE VIEW ROLLING_7D_PERFORMANCE AS
WITH daily AS (
    SELECT
        date,
        channel,
        campaign_id,
        platform_spend,
        platform_revenue,
        holdout_revenue
    FROM STG_UNIFIED_MEASUREMENT
),

rolling AS (
    SELECT
        date,
        channel,
        campaign_id,
        platform_spend AS daily_spend,
        SUM(platform_spend) OVER (
            PARTITION BY campaign_id ORDER BY date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_spend,
        SUM(platform_revenue) OVER (
            PARTITION BY campaign_id ORDER BY date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_reported_revenue,
        SUM(holdout_revenue) OVER (
            PARTITION BY campaign_id ORDER BY date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_incremental_revenue
    FROM daily
)

SELECT
    date,
    channel,
    campaign_id,
    ROUND(daily_spend, 2)                 AS daily_spend,
    ROUND(rolling_7d_spend, 2)            AS rolling_7d_spend,
    ROUND(rolling_7d_reported_revenue, 2) AS rolling_7d_reported_revenue,
    ROUND(rolling_7d_incremental_revenue, 2) AS rolling_7d_incremental_revenue,
    ROUND(rolling_7d_reported_revenue / NULLIF(rolling_7d_spend, 0), 2)    AS rolling_7d_reported_roas,
    ROUND(rolling_7d_incremental_revenue / NULLIF(rolling_7d_spend, 0), 2) AS rolling_7d_iroas
FROM rolling;
