-- =============================================================================
-- 04_governance_queries.sql : GOVERNANCE LAYER
-- GOVERNANCE_CAMPAIGN_ALERTS : per campaign status flag from inflation thresholds
-- GOVERNANCE_AUDIT_SUMMARY   : per channel roll up with a recommended action
-- =============================================================================
CREATE OR REPLACE VIEW GOVERNANCE_CAMPAIGN_ALERTS AS
SELECT
    channel,
    campaign_id,
    total_spend,
    total_platform_conversions,
    total_mta_conversions,
    total_holdout_conversions,
    reported_roas,
    mta_roas,
    incremental_roas,
    inflation_ratio,
    CASE
        WHEN total_holdout_conversions IS NULL OR total_holdout_conversions = 0
            THEN 'NO_HOLDOUT_COVERAGE ⚠️'
        WHEN inflation_ratio >= 3.0
            THEN 'CRITICAL_INFLATION_WARNING 🚨'
        WHEN inflation_ratio >= 1.5
            THEN 'MODERATE_INFLATION 🟡'
        ELSE 'PASS ✅'
    END AS governance_status
FROM ANALYTICS_MEASUREMENT_RECONCILIATION;

CREATE OR REPLACE VIEW GOVERNANCE_AUDIT_SUMMARY AS
WITH channel_totals AS (
    SELECT
        channel,
        SUM(total_spend)                AS total_spend,
        SUM(total_platform_conversions) AS total_platform_conversions,
        SUM(total_platform_revenue)     AS total_platform_revenue,
        SUM(total_mta_conversions)      AS total_mta_conversions,
        SUM(total_mta_revenue)          AS total_mta_revenue,
        SUM(total_holdout_conversions)  AS total_holdout_conversions,
        SUM(total_holdout_revenue)      AS total_holdout_revenue
    FROM ANALYTICS_MEASUREMENT_RECONCILIATION
    GROUP BY channel
)

SELECT
    channel,
    ROUND(total_spend, 2)               AS total_spend,
    total_platform_conversions,
    total_mta_conversions,
    total_holdout_conversions,
    total_platform_revenue,
    total_mta_revenue,
    total_holdout_revenue,
    ROUND(total_platform_revenue / NULLIF(total_spend, 0), 2) AS platform_roas,
    ROUND(total_mta_revenue / NULLIF(total_spend, 0), 2)      AS mta_roas,
    ROUND(total_holdout_revenue / NULLIF(total_spend, 0), 2)  AS incremental_roas,
    ROUND(total_platform_conversions / NULLIF(total_holdout_conversions, 0), 2) AS inflation_ratio,
    CASE
        WHEN total_holdout_revenue / NULLIF(total_spend, 0) < 1.0
            THEN 'UNPROFITABLE: Reduce Spend 🔴'
        WHEN total_holdout_revenue / NULLIF(total_spend, 0) >= 3.0
            THEN 'HEALTHY: Scale Channel 🟢'
        ELSE 'MONITOR: Optimize 🟡'
    END AS governance_action
FROM channel_totals;
