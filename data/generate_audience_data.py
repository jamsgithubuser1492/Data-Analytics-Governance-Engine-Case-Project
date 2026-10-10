"""Generate the SYNTHETIC audience layer for the case study (aggregate only, seeded, repeatable).

Writes three CSVs to data/audience/ by default. They sit beside, and never replace, the verified case study files:
  AUDIENCE_TIER_PERFORMANCE.csv   per day, campaign and audience tier: spend, reported revenue, people reached and conversions
                                  in the test and control markets (daily campaign spend and revenue come from RAW_PLATFORM_DATA)
  AUDIENCE_DMA_SERIES.csv         daily sales for test market groups and control (donor) markets
  AUDIENCE_DMA_PROPENSITY.csv     the share of each market's population in each of ten propensity deciles

Nothing here is real. Market names are generic labels and platform names are illustrative.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEED = 7
TIERS = [("Tier 1 (High intent)", 1, 2), ("Tier 2 (Mid intent)", 3, 5), ("Tier 3 (Broad)", 6, 10)]
# share of campaign spend, share of reported revenue, people reached per day in each arm, baseline conversion rate, share of conversions caused by ads
PROFILE = {
    "Google Ads": [(0.35, 0.70, 14000, 0.060, 0.06), (0.40, 0.22, 42000, 0.020, 0.45), (0.25, 0.08, 110000, 0.005, 0.70)],
    "Meta Ads": [(0.30, 0.55, 15000, 0.055, 0.20), (0.40, 0.30, 45000, 0.019, 0.65), (0.30, 0.15, 115000, 0.005, 0.80)],
    "TikTok Ads": [(0.15, 0.30, 12000, 0.050, 0.35), (0.35, 0.35, 40000, 0.018, 0.75), (0.50, 0.35, 120000, 0.004, 0.85)],
    "Netflix Ads": [(0.10, 0.25, 12000, 0.045, 0.50), (0.30, 0.35, 38000, 0.016, 0.60), (0.60, 0.40, 105000, 0.004, 0.70)],
}
SMALL_TIER = ("NETFLIX_ADS_CMP_02", "Tier 1 (High intent)", 90)  # a tiny audience: too few people to judge, on purpose
CHANNEL_CODE = {"Google Ads": "TX_GOOGLE", "Meta Ads": "TX_META", "TikTok Ads": "TX_TIKTOK", "Netflix Ads": "TX_NETFLIX"}
N_DONORS = 12


def tier_performance(platform: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    dates = sorted(platform["date"].unique())[30:]  # the 60 day test period
    p = platform[platform["date"].isin(dates)]
    rows = []
    for (date, channel, camp), g in p.groupby(["date", "channel", "campaign_id"]):
        spend, rev = float(g["spend"].sum()), float(g["reported_revenue"].sum())
        for (name, lo, hi), (s_sh, r_sh, users, cvr, delta) in zip(TIERS, PROFILE[channel]):
            n = users * (0.9 + 0.2 * rng.random())
            if (camp, name) == SMALL_TIER[:2]:
                n = SMALL_TIER[2] * (0.9 + 0.2 * rng.random())
            n_t, n_c = int(round(n)), int(round(n))
            p_t = cvr * (1 + 0.05 * rng.standard_normal())
            p_c = p_t * (1 - delta * (1 + 0.04 * rng.standard_normal()))
            rows.append({"date": date, "channel": channel, "campaign_id": camp, "tier_name": name, "tier_decile_start": lo, "tier_decile_end": hi,
                         "spend": round(spend * s_sh, 2), "reported_revenue": round(rev * r_sh, 2),
                         "treatment_conversions": int(rng.binomial(n_t, min(max(p_t, 1e-6), 0.9))), "treatment_users": n_t,
                         "control_conversions": int(rng.binomial(n_c, min(max(p_c, 1e-6), 0.9))), "control_users": n_c})
    return pd.DataFrame(rows)


def markets(platform: pd.DataFrame, rng: np.random.Generator):
    dates = sorted(platform["date"].unique())
    t = np.arange(len(dates))
    base_profile = np.array([0.02, 0.03, 0.05, 0.07, 0.10, 0.12, 0.14, 0.16, 0.15, 0.16])
    donors = [f"CONTROL_{i + 1:02d}" for i in range(N_DONORS)]
    level = rng.uniform(25000, 120000, N_DONORS)
    phase = rng.uniform(0, 2 * np.pi, N_DONORS)
    common = 1 + 0.04 * np.sin(t / 9.0) + 0.0012 * t
    D = np.zeros((len(t), N_DONORS))
    for j in range(N_DONORS):
        D[:, j] = level[j] * common * (1 + 0.10 * np.sin(2 * np.pi * t / 7 + phase[j])) * (1 + 0.008 * rng.standard_normal(len(t)))
    P_donor = np.array([rng.dirichlet(base_profile * rng.uniform(30, 60)) for _ in range(N_DONORS)])
    series, props = [], []
    for j, code in enumerate(donors):
        series += [{"date": d, "dma_code": code, "role": "control", "channel": "", "revenue": round(float(D[i, j]), 2)} for i, d in enumerate(dates)]
        props.append({"dma_code": code, "dma_name": f"Control market {j + 1:02d}", **{f"decile_{k + 1}_pct": round(float(P_donor[j, k]), 4) for k in range(10)}})
    for channel, code in CHANNEL_CODE.items():
        w = rng.dirichlet(np.full(N_DONORS, 0.9))
        scale = rng.uniform(0.9, 1.3)
        y = (D @ w) * scale * (1 + 0.006 * rng.standard_normal(len(t)))
        y = y * np.where(t >= 30, 1.03, 1.0)  # a small lift after launch
        p = w @ P_donor
        if channel == "TikTok Ads":  # a younger skewing test audience that no mix of control markets can reproduce: a deliberate review case
            skew = np.array([0.0, 0.0, 0.02, 0.05, 0.10, 0.18, 0.22, 0.23, 0.12, 0.08])
            p = 0.12 * p + 0.88 * skew
        p = p / p.sum()
        series += [{"date": d, "dma_code": code, "role": "treatment", "channel": channel, "revenue": round(float(y[i]), 2)} for i, d in enumerate(dates)]
        props.append({"dma_code": code, "dma_name": f"Test market group, {channel}", **{f"decile_{k + 1}_pct": round(float(p[k]), 4) for k in range(10)}})
    prop = pd.DataFrame(props)
    cols = [f"decile_{k}_pct" for k in range(1, 11)]
    prop[cols] = prop[cols].div(prop[cols].sum(axis=1), axis=0).round(4)
    return pd.DataFrame(series), prop


def generate(out_dir: Path, platform_path: Path = ROOT / "data" / "RAW_PLATFORM_DATA.csv") -> dict:
    platform = pd.read_csv(platform_path)
    rng = np.random.default_rng(SEED)
    tiers = tier_performance(platform, rng)
    series, prop = markets(platform, rng)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {"AUDIENCE_TIER_PERFORMANCE": tiers, "AUDIENCE_DMA_SERIES": series, "AUDIENCE_DMA_PROPENSITY": prop}
    for name, df in frames.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    (out_dir / "SYNTHETIC_DATA_NOTE.txt").write_text(
        "These files are SYNTHETIC. They were generated by data/generate_audience_data.py (seed 7) for a repeatable case study.\n"
        "Market names are generic labels, platform names are illustrative, and no real company or person data is used.\n", encoding="utf-8")
    return frames


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "data" / "audience"))
    args = ap.parse_args()
    for n, df in generate(Path(args.out)).items():
        print(f"{n}: {len(df):,} rows")
