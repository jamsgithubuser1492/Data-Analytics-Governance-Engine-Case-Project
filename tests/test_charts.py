"""Executive chart helpers: dynamic ranges, sizing, headlines and a no-emoji guard for the UI."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import charts  # noqa: E402

EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿←-⇿ℹ️]")


def test_padded_range_includes_reference_lines_and_headroom() -> None:
    lo, hi = charts.padded_range([0.4, 1.1], include=[3.0])
    assert lo == 0 and hi > 3.0
    lo2, hi2 = charts.padded_range([10, 12], include=[2.0])
    assert hi2 > 12 and lo2 == 0  # zero baseline kept for bars


def test_padded_range_handles_negative_nan_and_empty() -> None:
    lo, hi = charts.padded_range([-1.0, 0.5, np.nan])
    assert lo < -1.0 and hi > 0.5
    assert charts.padded_range([]) == (0.0, 1.0)


def test_robust_range_ignores_a_single_spike() -> None:
    vals = list(np.linspace(0.8, 1.2, 60)) + [40.0]
    assert charts.padded_range(vals, robust=True)[1] < 3
    assert charts.padded_range(vals, robust=False)[1] > 40


def test_bar_height_grows_and_caps() -> None:
    assert charts.bar_height(3) < charts.bar_height(12) < charts.bar_height(40) == 900 or charts.bar_height(40) <= 900
    assert charts.bar_height(1000) == 900


def test_headlines_state_the_finding() -> None:
    ch = pd.DataFrame({"channel": ["A", "B", "C"], "claimed": [4, 3, 2], "proven": [1.2, 0.4, np.nan]})
    assert charts.returns_headline(ch, 1.0) == "A earns a profit; B loses money"
    assert "just breaks even" in charts.returns_headline(ch.assign(proven=[1.2, 0.99, np.nan]), 1.0)
    assert charts.classify(1.04, 1.0) == "at" and charts.classify(1.06, 1.0) == "above" and charts.classify(0.9, 1.0) == "below"
    assert charts.classify(float("nan"), 1.0) == "unmeasured"
    assert "None of" in charts.returns_headline(ch.assign(proven=[0.1, 0.2, 0.3]), 1.0)
    inf = pd.DataFrame({"campaign_id": ["X", "Y", "Z"], "inflation_ratio": [1.1, 2.0, 3.5]})
    h = charts.overclaim_headline(inf, 1.5, 3.0)
    assert "2 of 3" in h and "1 at a critical level" in h and "Z" in h
    assert "hold up" in charts.overclaim_headline(inf.assign(inflation_ratio=[1.0, 1.1, 1.2]), 1.5, 3.0)


def test_figures_carry_their_message_for_rendering() -> None:
    inf = pd.DataFrame({"campaign_id": ["X", "Y"], "inflation_ratio": [1.2, 8.0]})
    fig = charts.overclaim_chart(inf, 1.5, 3.0, "My finding", basis="return")
    assert fig.layout.meta["headline"] == "My finding" and "Higher means" in fig.layout.meta["subtitle"]
    assert fig.layout.xaxis.range[1] > 8.0 and "per $1 the test proves" in fig.layout.xaxis.title.text


def test_figures_build_with_missing_data() -> None:
    ch = pd.DataFrame({"channel": ["A", "B"], "claimed": [4.0, np.nan], "model": [3.0, 2.0], "proven": [1.2, np.nan]})
    fig = charts.returns_chart(ch, 2.0, "Breakeven 2.00x", "Proven", "Title")
    assert fig.layout.yaxis.range[1] > 4.0
    inf = pd.DataFrame({"campaign_id": [f"C{i}" for i in range(20)], "inflation_ratio": np.linspace(1, 4, 20)})
    assert charts.overclaim_chart(inf, 1.5, 3.0, "T").layout.height > charts.bar_height(4)
    roll = pd.DataFrame({"date": pd.date_range("2026-02-01", periods=10).tolist() * 2, "channel": ["A"] * 10 + ["B"] * 10,
                         "iroas": list(np.linspace(0.5, 1.5, 10)) + [np.nan] * 10})
    assert charts.trend_chart(roll, 1.0, "Breakeven", "T").layout.yaxis.range[0] <= 0.5


def test_no_emoji_anywhere_in_the_ui_or_agent_text() -> None:
    offenders = []
    for f in list((ROOT / "app").rglob("*.py")) + list((ROOT / "python").glob("*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if EMOJI.search(line):
                offenders.append(f"{f.name}:{i}")
    assert not offenders, offenders
