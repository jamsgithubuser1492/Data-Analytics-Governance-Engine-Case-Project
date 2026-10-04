"""Executive chart builders: one message per chart, plain language labels, axes sized to the data.

Pure functions (no Streamlit) so they can be unit tested. Every chart carries an action title that
states the finding, a short subtitle that says how to read it, and reference lines that come from
the run itself (breakeven from the margin economics, thresholds from the policy).
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go

INK, MUTED, GRID = "#16202f", "#4b586b", "#e6eaf0"
BLUE, ORANGE, GREEN = "#1d4ed8", "#d9631e", "#1a7f5a"
AMBER, RED = "#c98a00", "#c0392b"
CHANNEL_COLORS = {"Meta Ads": "#2a78d6", "Google Ads": "#eb6834", "TikTok Ads": "#1baf7a", "Netflix Ads": "#c98a00"}
FALLBACK_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#c98a00", "#8a5cc2", "#4b586b"]
SERIES = {"claimed": ("Claimed by the platform", "#9aa7bd"), "model": ("Attribution model estimate", "#5b7fd6"),
          "proven": ("Proven by the holdout test", GREEN)}


def padded_range(values: Iterable[float], include: Sequence[float] = (), floor_zero: bool = True,
                 pad: float = 0.18, robust: bool = False) -> Tuple[float, float]:
    """Axis range that fits the data and the reference lines, with headroom for labels.

    ``robust`` clips to the 2nd to 98th percentile so one early spike does not flatten the rest.
    """
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if robust and len(arr) >= 20:
        arr = np.clip(arr, *np.percentile(arr, [2, 98]))
    pts = np.concatenate([arr, np.asarray([x for x in include if x is not None and np.isfinite(x)], dtype=float)])
    if pts.size == 0:
        return (0.0, 1.0)
    lo, hi = float(pts.min()), float(pts.max())
    if floor_zero:
        lo = min(lo, 0.0)
    span = (hi - lo) or max(abs(hi), 1.0)
    return (lo - (0.0 if floor_zero and lo == 0 else pad * span), hi + pad * span)


def bar_height(n_items: int, base: int = 300, per_item: int = 36, cap: int = 900) -> int:
    """Pixel height that grows with the number of bars so labels never collide."""
    return int(min(cap, max(base, 110 + per_item * max(n_items, 1))))


def _layout(fig: go.Figure, title: str, subtitle: str, height: Optional[int] = None, legend: bool = True, bottom: int = 70) -> go.Figure:
    """Shared look. The finding and how to read it travel in ``fig.layout.meta`` and are rendered as HTML above the chart
    (crisp, wrapping text); the figure itself carries no title."""
    fig.update_layout(
        meta=dict(headline=title, subtitle=subtitle),
        template="plotly_white", font=dict(family="Inter, system-ui, sans-serif", size=13, color=INK),
        margin=dict(t=44, b=bottom, l=8, r=24), height=height, hovermode="closest",
        showlegend=legend, legend=dict(orientation="h", yref="container", y=0, yanchor="bottom", x=0, title_text=""),
        paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def _x(v: float) -> str:
    return "not measured" if pd.isna(v) else f"{v:.2f}x"


# ------------------------------------------------------------------ headlines (the message of each chart)
AT_BREAKEVEN_BAND = 0.05  # within 5% of breakeven counts as "about breakeven", not a loss


def classify(proven: float, breakeven: float) -> str:
    """'above', 'at' (within 5% of breakeven) or 'below'; 'unmeasured' when there is no holdout evidence."""
    if proven is None or pd.isna(proven):
        return "unmeasured"
    if proven >= breakeven * (1 + AT_BREAKEVEN_BAND):
        return "above"
    return "at" if proven >= breakeven * (1 - AT_BREAKEVEN_BAND) else "below"


def returns_headline(ch: pd.DataFrame, breakeven: float) -> str:
    """ch has columns channel, claimed, proven. Returns a sentence that states the finding."""
    d = ch.dropna(subset=["proven"]).copy()
    if d.empty:
        return "No channel has holdout evidence yet, so no return can be proven"
    d["status"] = d["proven"].map(lambda v: classify(v, breakeven))
    above, at, below = (d[d["status"] == k]["channel"].tolist() for k in ("above", "at", "below"))
    if not below and not at:
        return f"All {len(above)} measured channels earn back more than they cost"
    if not above and not at:
        return f"None of the {len(below)} measured channels proves it earns back its spend"
    parts = []
    if above:
        parts.append(f"{', '.join(above)} earn{'s' if len(above) == 1 else ''} a profit")
    if at:
        parts.append(f"{', '.join(at)} just break{'s' if len(at) == 1 else ''} even")
    if below:
        parts.append(f"{', '.join(below)} lose{'s' if len(below) == 1 else ''} money")
    text = "; ".join(parts)
    return text[0].upper() + text[1:]


def overclaim_headline(inf: pd.DataFrame, moderate: float, critical: float) -> str:
    d = inf.dropna(subset=["inflation_ratio"])
    if d.empty:
        return "No campaign has holdout data, so platform claims cannot be tested"
    over = d[d["inflation_ratio"] > moderate]
    worst = d.loc[d["inflation_ratio"].idxmax()]
    if over.empty:
        return f"Platform claims hold up: no campaign over-claims beyond {moderate:g}x"
    crit = int((d["inflation_ratio"] > critical).sum())
    tail = f", {crit} at a critical level" if crit else ""
    return f"{len(over)} of {len(d)} campaigns over-claim by more than {moderate:g}x{tail}; the largest is {worst['campaign_id']} at {worst['inflation_ratio']:.1f}x"


def trend_headline(ch_roll: pd.DataFrame, breakeven: float) -> str:
    last = ch_roll.sort_values("date").groupby("channel").tail(1).dropna(subset=["iroas"])
    if last.empty:
        return "Not enough holdout days to show a trend yet"
    under = last[last["iroas"] < breakeven * (1 - AT_BREAKEVEN_BAND)]["channel"].tolist()
    if not under:
        return "Every channel is currently above breakeven"
    return f"Currently below breakeven: {', '.join(under)}"


# --------------------------------------------------------------------------------------- charts
def returns_chart(ch: pd.DataFrame, breakeven: float, breakeven_label: str, proven_name: str, headline: str) -> go.Figure:
    """Grouped bars: what platforms claim, what the attribution model says, what the test proves."""
    ch = ch.sort_values("proven", ascending=False, na_position="last")
    fig = go.Figure()
    for key, (name, color) in SERIES.items():
        col = key if key != "proven" else "proven"
        label = name if key != "proven" else proven_name
        fig.add_bar(x=ch["channel"], y=ch[col], name=label, marker_color=color,
                    text=ch[col].map(_x), textposition="outside", cliponaxis=False,
                    hovertemplate="%{x}<br>" + label + ": %{y:.2f}x<extra></extra>")
    lo, hi = padded_range(ch[["claimed", "model", "proven"]].to_numpy().ravel(), include=[breakeven], pad=0.2)
    fig.update_yaxes(range=[lo, hi], title_text="Revenue per $1 of ad spend", ticksuffix="x")
    fig.add_hline(y=breakeven, line_dash="dash", line_color=RED, line_width=2)
    fig.add_scatter(x=[None], y=[None], mode="lines", name=breakeven_label, line=dict(color=RED, dash="dash", width=2))  # legend entry
    fig.update_layout(barmode="group", bargap=0.28)
    return _layout(fig, headline, "Bars above the red line earn back their cost. Compare the grey bar (claimed) with the green bar (proven).", 440)


def overclaim_chart(inf: pd.DataFrame, moderate: float, critical: float, headline: str, basis: str = "conversions") -> go.Figure:
    """Horizontal bars, worst at the top, colored by status. Height grows with the number of campaigns and the axis
    is capped when one outlier would flatten the rest (the outlier bar is labelled with its true value)."""
    d = inf.dropna(subset=["inflation_ratio"]).sort_values("inflation_ratio").copy()
    cap = critical * 4
    d["shown"] = d["inflation_ratio"].clip(upper=cap)
    d["label"] = d.apply(lambda r: f"{r['inflation_ratio']:.2f}x" + (" (off scale)" if r["inflation_ratio"] > cap else ""), axis=1)
    status = np.where(d["inflation_ratio"] > critical, "Critical over-claim",
                      np.where(d["inflation_ratio"] > moderate, "Over-claim, review", "Within normal range"))
    colors = {"Critical over-claim": RED, "Over-claim, review": AMBER, "Within normal range": GREEN}
    fig = go.Figure()
    for name, color in colors.items():
        m = status == name
        if m.any():
            sub = d[m]
            fig.add_bar(y=sub["campaign_id"], x=sub["shown"], orientation="h", name=name, marker_color=color,
                        text=sub["label"], textposition="outside", cliponaxis=False,
                        customdata=sub["inflation_ratio"], hovertemplate="%{y}<br>Platform claims %{customdata:.2f}x what the test confirms<extra></extra>")
    hi = padded_range(d["shown"], include=[moderate, critical], floor_zero=True, pad=0.3)[1]
    axis = ("Conversions the platform claims, per conversion the test confirms" if basis == "conversions"
            else "Return the platform claims, per $1 the test proves")
    fig.update_xaxes(range=[0, hi], title_text=axis, ticksuffix="x", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False, autorange=True)
    for x, label, color, shift in ((moderate, f"Review above {moderate:g}x", AMBER, 0), (critical, f"Critical above {critical:g}x", RED, 16)):
        fig.add_vline(x=x, line_dash="dot", line_color=color, line_width=1.5)
        fig.add_annotation(x=x, yref="paper", y=1.0, yshift=shift, text=label, showarrow=False, yanchor="bottom", xanchor="left",
                           font=dict(color=color, size=11))
    fig.update_layout(barmode="overlay")
    return _layout(fig, headline, "A value of 1.0x means the platform claims exactly what the test confirms. Higher means more over-claiming.",
                   bar_height(len(d)) + 40, bottom=96)


def trend_chart(ch_roll: pd.DataFrame, breakeven: float, breakeven_label: str, headline: str) -> go.Figure:
    """Rolling return by channel with the breakeven line, a shaded loss zone and direct end labels."""
    fig = go.Figure()
    channels = [c for c in ch_roll["channel"].unique()]
    lo, hi = padded_range(ch_roll["iroas"], include=[breakeven], robust=True, pad=0.15)
    fig.add_hrect(y0=lo, y1=breakeven, fillcolor="rgba(192,57,43,0.06)", line_width=0, layer="below")
    for i, ch in enumerate(channels):
        d = ch_roll[ch_roll["channel"] == ch].sort_values("date").dropna(subset=["iroas"])
        if d.empty:
            continue
        color = CHANNEL_COLORS.get(ch, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        fig.add_scatter(x=d["date"], y=d["iroas"], name=ch, mode="lines", line=dict(color=color, width=2.5),
                        hovertemplate="%{x}<br>" + ch + ": %{y:.2f}x<extra></extra>")
        fig.add_scatter(x=d["date"].iloc[-1:], y=d["iroas"].iloc[-1:], mode="markers+text", showlegend=False,
                        marker=dict(color=color, size=8), text=[f" {ch.replace(' Ads', '')} {d['iroas'].iloc[-1]:.2f}x"],
                        textposition="middle right", textfont=dict(color=color, size=12), hoverinfo="skip", cliponaxis=False)
    fig.add_hline(y=breakeven, line_dash="dash", line_color=RED, line_width=2)
    fig.add_scatter(x=[None], y=[None], mode="lines", name=breakeven_label, line=dict(color=RED, dash="dash", width=2))  # legend entry
    fig.update_yaxes(range=[lo, hi], title_text="Revenue per $1 (7 day rolling)", ticksuffix="x")
    fig.update_layout(margin=dict(t=24, b=70, l=8, r=170))
    fig = _layout(fig, headline, "Shaded area is below breakeven. Each line is a channel's last 7 days of test results; the axis is zoomed to the typical range.", 420)
    return fig.update_layout(margin=dict(t=44, b=70, l=8, r=170))
