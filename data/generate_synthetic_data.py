"""Synthetic data generator for the Media Measurement & Governance Engine (MMGE).

Produces four raw source tables over a 90-day window starting 2026-01-01:

* RAW_PLATFORM_DATA   platform self-reported metrics (carries over-reporting bias)
* RAW_MTA_OUTPUT      multi-touch attribution (fractional deduplication)
* RAW_HOLDOUT_DATA    geo holdout experiment (days 0-29 pre-period, 30-89 treatment)
* BUSINESS_BENCHMARKS governance reference ranges per channel

Run:  python data/generate_synthetic_data.py [--out-dir data] [--seed 42]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

START_DATE = datetime(2026, 1, 1)
NUM_DAYS = 90
PRE_PERIOD_DAYS = 30
TRUE_LIFT = 1.20
GEO_SAMPLE_FRACTION = 0.40
AVG_ORDER_VALUE = 75.0
CAMPAIGNS_PER_CHANNEL = 2

CHANNELS_CONFIG: Dict[str, Dict] = {
    "Meta Ads": {"spend_range": (800, 1500), "cpm": 12.0, "ctr": 0.015, "cvr": 0.03, "bias_range": (1.35, 1.45)},
    "Google Ads": {"spend_range": (1000, 2000), "cpm": 15.0, "ctr": 0.025, "cvr": 0.04, "bias_range": (1.20, 1.30)},
    "TikTok Ads": {"spend_range": (400, 900), "cpm": 8.0, "ctr": 0.010, "cvr": 0.02, "bias_range": (1.40, 1.55)},
    "Netflix Ads": {"spend_range": (600, 1200), "cpm": 25.0, "ctr": 0.008, "cvr": 0.015, "bias_range": (1.15, 1.25)},
}

BENCHMARKS = [
    {"channel": "Meta Ads", "expected_roas_min": 1.5, "expected_roas_max": 3.5, "expected_cvr_min": 0.015, "expected_cvr_max": 0.045, "typical_incrementality_min": 0.40, "typical_incrementality_max": 0.65},
    {"channel": "Google Ads", "expected_roas_min": 2.0, "expected_roas_max": 4.5, "expected_cvr_min": 0.020, "expected_cvr_max": 0.060, "typical_incrementality_min": 0.50, "typical_incrementality_max": 0.75},
    {"channel": "TikTok Ads", "expected_roas_min": 1.0, "expected_roas_max": 2.5, "expected_cvr_min": 0.008, "expected_cvr_max": 0.030, "typical_incrementality_min": 0.30, "typical_incrementality_max": 0.55},
    {"channel": "Netflix Ads", "expected_roas_min": 0.8, "expected_roas_max": 2.0, "expected_cvr_min": 0.005, "expected_cvr_max": 0.020, "typical_incrementality_min": 0.20, "typical_incrementality_max": 0.45},
]


def generate_all_data(seed: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate the four raw tables deterministically.

    Args:
        seed: NumPy random seed for exact reproducibility.

    Returns:
        Tuple of (platform, mta, holdout, benchmarks) DataFrames.
    """
    np.random.seed(seed)
    platform_rows, mta_rows, holdout_rows = [], [], []

    for day_idx in range(NUM_DAYS):
        current_date = (START_DATE + timedelta(days=day_idx)).strftime("%Y-%m-%d")
        for channel, cfg in CHANNELS_CONFIG.items():
            for campaign_num in range(1, CAMPAIGNS_PER_CHANNEL + 1):
                campaign_id = f"{channel.replace(' ', '_').upper()}_CMP_{campaign_num:02d}"

                # 1. Platform self-reported (inflated) view
                spend = np.random.uniform(*cfg["spend_range"])
                impressions = int(round((spend / cfg["cpm"]) * 1000))
                clicks = int(round(impressions * np.clip(np.random.normal(cfg["ctr"], 0.002), 0.001, 0.10)))
                daily_cvr = np.clip(np.random.normal(cfg["cvr"], 0.005), 0.001, 0.20)
                true_conversions = int(round(clicks * daily_cvr))
                bias = np.random.uniform(*cfg["bias_range"])
                reported_conversions = int(round(true_conversions * bias))
                platform_rows.append({
                    "date": current_date, "channel": channel, "campaign_id": campaign_id,
                    "spend": round(spend, 2), "impressions": impressions, "clicks": clicks,
                    "reported_conversions": reported_conversions,
                    "reported_revenue": round(reported_conversions * AVG_ORDER_VALUE, 2),
                })

                # 2. MTA model output (fractional deduplication of platform claims)
                dedup = np.random.uniform(0.80, 0.90)
                mta_conversions = int(round(reported_conversions * dedup))
                mta_rows.append({
                    "date": current_date, "channel": channel, "campaign_id": campaign_id,
                    "mta_attributed_conversions": mta_conversions,
                    "mta_attributed_revenue": round(mta_conversions * AVG_ORDER_VALUE, 2),
                    "mta_attribution_weight": round(dedup, 3), "model_version": "linear_decay_v1.2",
                })

                # 3. Geo holdout experiment (40% sample, 1.20x true lift in treatment from day 30)
                for group in ("control", "treatment"):
                    active = day_idx >= PRE_PERIOD_DAYS and group == "treatment"
                    lift = TRUE_LIFT if active else 1.00
                    base = int(round(true_conversions * GEO_SAMPLE_FRACTION))
                    conv = int(round(base * lift))
                    holdout_rows.append({
                        "date": current_date, "experiment_id": f"EXP_{campaign_id}", "campaign_id": campaign_id,
                        "geo_or_cohort_id": f"GEO_{group.upper()}_US", "group_type": group,
                        "treatment_flag": 1 if active else 0, "population_size": 500000,
                        "conversions": conv, "revenue": round(conv * AVG_ORDER_VALUE, 2),
                    })

    return (pd.DataFrame(platform_rows), pd.DataFrame(mta_rows),
            pd.DataFrame(holdout_rows), pd.DataFrame(BENCHMARKS))


def main() -> None:
    """CLI entry point: write the four CSVs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = ["RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS"]
    for name, df in zip(names, generate_all_data(args.seed)):
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"Wrote {name}.csv ({len(df):,} rows)")


if __name__ == "__main__":
    main()
