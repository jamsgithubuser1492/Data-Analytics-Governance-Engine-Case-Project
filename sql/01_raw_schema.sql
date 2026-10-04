-- =============================================================================
-- 01_raw_schema.sql : RAW LAYER DDL (Snowflake + DuckDB compatible)
-- Four source tables. Data is loaded from data/*.csv by python/database_manager.py
-- locally, or with the Snowflake COPY INTO commands at the bottom of this file.
-- =============================================================================

-- 1. Platform self-reported ad network data
CREATE OR REPLACE TABLE RAW_PLATFORM_DATA (
    date                 DATE,
    channel              VARCHAR,
    campaign_id          VARCHAR,
    spend                DECIMAL(38, 2),
    impressions          INTEGER,
    clicks               INTEGER,
    reported_conversions INTEGER,
    reported_revenue     DECIMAL(38, 2)
);

-- 2. Multi-touch attribution (linear decay) model output
CREATE OR REPLACE TABLE RAW_MTA_OUTPUT (
    date                       DATE,
    channel                    VARCHAR,
    campaign_id                VARCHAR,
    mta_attributed_conversions INTEGER,
    mta_attributed_revenue     DECIMAL(38, 2),
    mta_attribution_weight     FLOAT,
    model_version              VARCHAR
);

-- 3. Geo holdout experiment data
CREATE OR REPLACE TABLE RAW_HOLDOUT_DATA (
    date             DATE,
    experiment_id    VARCHAR,
    campaign_id      VARCHAR,
    geo_or_cohort_id VARCHAR,
    group_type       VARCHAR,
    treatment_flag   INTEGER,
    population_size  INTEGER,
    conversions      INTEGER,
    revenue          DECIMAL(38, 2)
);

-- 4. Business benchmark reference ranges
CREATE OR REPLACE TABLE BUSINESS_BENCHMARKS (
    channel                    VARCHAR,
    expected_roas_min          FLOAT,
    expected_roas_max          FLOAT,
    expected_cvr_min           FLOAT,
    expected_cvr_max           FLOAT,
    typical_incrementality_min FLOAT,
    typical_incrementality_max FLOAT
);

-- 5. Policy parameters (single row). Editable governance settings used by the
--    staging and governance layers. The Python runner overwrites this row with
--    the workspace's settings; defaults below match the original spec.
CREATE OR REPLACE TABLE POLICY_PARAMS (
    geo_sample_fraction FLOAT,
    inflation_moderate  FLOAT,
    inflation_critical  FLOAT
);

INSERT INTO POLICY_PARAMS VALUES (0.40, 1.5, 3.0);

-- -----------------------------------------------------------------------------
-- SNOWFLAKE ONLY (run in a Snowflake worksheet, skipped by the DuckDB runner):
--   CREATE DATABASE IF NOT EXISTS MMGE_DB;  USE DATABASE MMGE_DB;
--   CREATE SCHEMA IF NOT EXISTS RAW_LAYER;  USE SCHEMA RAW_LAYER;
--   CREATE OR REPLACE FILE FORMAT CSV_FF TYPE = 'CSV' FIELD_DELIMITER = ','
--       SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"' NULL_IF = ('NULL', 'null', '');
--   CREATE OR REPLACE STAGE MMGE_RAW_STAGE FILE_FORMAT = CSV_FF;
--   -- upload data/*.csv to @MMGE_RAW_STAGE (PUT or the Snowsight UI), then:
--   COPY INTO RAW_PLATFORM_DATA  FROM @MMGE_RAW_STAGE/RAW_PLATFORM_DATA.csv;
--   COPY INTO RAW_MTA_OUTPUT     FROM @MMGE_RAW_STAGE/RAW_MTA_OUTPUT.csv;
--   COPY INTO RAW_HOLDOUT_DATA   FROM @MMGE_RAW_STAGE/RAW_HOLDOUT_DATA.csv;
--   COPY INTO BUSINESS_BENCHMARKS FROM @MMGE_RAW_STAGE/BUSINESS_BENCHMARKS.csv;
-- -----------------------------------------------------------------------------
