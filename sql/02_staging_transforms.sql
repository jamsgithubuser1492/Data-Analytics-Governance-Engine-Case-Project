-- =============================================================================
-- 02_staging_transforms.sql : STAGING LAYER
-- STG_UNIFIED_MEASUREMENT aligns Platform, MTA and Holdout data at the
-- (date, channel, campaign_id) grain.
-- The geo holdout only observes a 40% population sample, so treatment
-- conversions and revenue are scaled by / 0.40 to project to full population.
-- =============================================================================
CREATE OR REPLACE VIEW STG_UNIFIED_MEASUREMENT AS
WITH stg_platform AS (
    SELECT
        date,
        channel,
        campaign_id,
        spend                AS platform_spend,
        reported_conversions AS platform_conversions,
        reported_revenue     AS platform_revenue
    FROM RAW_PLATFORM_DATA
),

stg_mta AS (
    SELECT
        date,
        channel,
        campaign_id,
        SUM(mta_attributed_conversions) AS mta_conversions,
        SUM(mta_attributed_revenue)     AS mta_revenue
    FROM RAW_MTA_OUTPUT
    GROUP BY date, channel, campaign_id
),

stg_holdout AS (
    SELECT
        date,
        campaign_id,
        SUM(conversions) / 0.40 AS holdout_conversions,
        SUM(revenue) / 0.40     AS holdout_revenue
    FROM RAW_HOLDOUT_DATA
    WHERE group_type = 'treatment'
    GROUP BY date, campaign_id
)

SELECT
    p.date,
    p.channel,
    p.campaign_id,
    p.platform_spend,
    p.platform_conversions,
    p.platform_revenue,
    COALESCE(m.mta_conversions, 0)     AS mta_conversions,
    COALESCE(m.mta_revenue, 0)         AS mta_revenue,
    COALESCE(h.holdout_conversions, 0) AS holdout_conversions,
    COALESCE(h.holdout_revenue, 0)     AS holdout_revenue,
    CASE WHEN h.holdout_conversions IS NOT NULL THEN 1 ELSE 0 END AS has_holdout_coverage
FROM stg_platform AS p
LEFT JOIN stg_mta AS m
    ON  p.date = m.date
    AND p.channel = m.channel
    AND p.campaign_id = m.campaign_id
LEFT JOIN stg_holdout AS h
    ON  p.date = h.date
    AND p.campaign_id = h.campaign_id;
