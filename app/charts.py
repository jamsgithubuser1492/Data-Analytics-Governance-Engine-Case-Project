"""Executive chart builders: one message per chart, plain language labels, axes sized to the data.

Pure functions (no Streamlit rendering) so they can be unit tested. Every figure carries its finding and a reading guide in
``fig.layout.meta`` (rendered as HTML by the chart card), uses the active theme (light or dark) and never uses a second y axis.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dashdata import AT_BREAKEVEN_BAND, classify  # noqa: F401  (classify re-exported for callers and tests)
import ui
from ui import LIGHT, channel_color

_THEME: Dict[str, str] = dict(LIGHT)
SERIES_NAMES = {"claimed": "Claimed by the platform", "model": "Attribution model estimate", "proven": "Proven by the holdout test"}


def use_theme(tokens: Dict[str, str]) -> None:
    """Colors for every figure built after this call (light or dark)."""
    global _THEME
    _THEME = dict(tokens)


def T() -> Dict[str, str]:
    return _THEME


def _dark() -> bool:
    return _THEME["bg"] != LIGHT["bg"]


def good() -> str:
    return "#5fd1a0" if _dark() else "#15734d"


def caution() -> str:
    return "#f0c25e" if _dark() else "#b87900"


def danger() -> str:
    return "#ff8f84" if _dark() else "#c0392b"


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


def _x(v: float) -> str:
    return "not measured" if pd.isna(v) else f"{v:.2f}x"


def _layout(fig: go.Figure, title: str, subtitle: str, height: Optional[int] = None, legend: bool = True, bottom: int = 70,
            right: int = 24) -> go.Figure:
    t = _THEME
    fig.update_layout(
        meta=dict(headline=title, subtitle=subtitle), template="plotly_dark" if _dark() else "plotly_white",
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=t["ink"]),
        margin=dict(t=30, b=bottom, l=8, r=right), height=height, hovermode="closest", showlegend=legend,
        legend=dict(orientation="h", yref="container", y=0, yanchor="bottom", x=0, title_text=""),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False, linecolor=t["grid"], zeroline=False)
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False)
    return fig


def _breakeven_line(fig: go.Figure, y: float, label: str) -> None:
    fig.add_hline(y=y, line_dash="dash", line_color=danger(), line_width=2)
    fig.add_scatter(x=[None], y=[None], mode="lines", name=label, line=dict(color=danger(), dash="dash", width=2))  # legend entry


# ------------------------------------------------------------------ headlines (the message of each chart)
def returns_headline(ch: pd.DataFrame, breakeven: float) -> str:
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


def waterfall_headline(steps: Sequence[Tuple[str, float, str]]) -> str:
    claimed, delta, proven = steps[0][1], steps[1][1], steps[2][1]
    share = (-delta / claimed * 100) if claimed else 0.0
    return f"{share:.0f}% of the revenue platforms claim is not caused by their ads"


def portfolio_headline(ch: pd.DataFrame) -> str:
    n = ch["action"].value_counts().to_dict()
    words = {"Scale": "with a strong return", "Maintain": "at or above breakeven", "Cut": "below breakeven", "Restructure": "needing stronger evidence"}
    bits = [f"{n[k]} {words[k]}" for k in ("Scale", "Maintain", "Cut", "Restructure") if n.get(k)]
    return "Where returns stand: " + ", ".join(bits)


# ------------------------------------------------------------------------------------------------ charts
def returns_chart(ch: pd.DataFrame, breakeven: float, breakeven_label: str, proven_name: str, headline: str) -> go.Figure:
    """Grouped bars: claimed, attribution model, proven (with its 95% interval when the strict view provides one)."""
    t = _THEME
    ch = ch.sort_values("proven", ascending=False, na_position="last")
    colors = {"claimed": t["claimed"], "model": t["model"], "proven": t["proven"]}
    fig = go.Figure()
    for key in ("claimed", "model", "proven"):
        name = proven_name if key == "proven" else SERIES_NAMES[key]
        kw = {}
        if key == "proven" and {"lower", "upper"} <= set(ch.columns) and ch["lower"].notna().any():
            kw["error_y"] = dict(type="data", symmetric=False, array=(ch["upper"] - ch["proven"]).clip(lower=0).fillna(0),
                                 arrayminus=(ch["proven"] - ch["lower"]).clip(lower=0).fillna(0), color=t["ink"], thickness=1.4, width=5)
        fig.add_bar(x=ch["channel"], y=ch[key], name=name, marker_color=colors[key], text=ch[key].map(_x), textposition="outside", cliponaxis=False,
                    hovertemplate="%{x}<br>" + name + ": %{y:.2f}x<extra></extra>", **kw)
    vals = list(ch[["claimed", "model", "proven"]].to_numpy().ravel())
    if "upper" in ch.columns:
        vals += list(ch["upper"].dropna())
    lo, hi = padded_range(vals, include=[breakeven], pad=0.2)
    fig.update_yaxes(range=[lo, hi], title_text="Revenue per $1 of ad spend", ticksuffix="x")
    _breakeven_line(fig, breakeven, breakeven_label)
    fig.update_layout(barmode="group", bargap=0.28)
    sub = "Bars above the dashed line earn back their cost. Compare the grey bar (claimed) with the blue bar (proven)."
    if "lower" in ch.columns and ch["lower"].notna().any():
        sub += " Whiskers show the 95% confidence interval."
    return _layout(fig, headline, sub, 440)


def overclaim_chart(inf: pd.DataFrame, moderate: float, critical: float, headline: str, basis: str = "conversions") -> go.Figure:
    """Horizontal bars, worst at the top, colored by status. The axis is capped when one outlier would flatten the rest."""
    t = _THEME
    d = inf.dropna(subset=["inflation_ratio"]).sort_values("inflation_ratio").copy()
    cap = critical * 4
    d["shown"] = d["inflation_ratio"].clip(upper=cap)
    d["label"] = d.apply(lambda r: f"{r['inflation_ratio']:.2f}x" + (" (off scale)" if r["inflation_ratio"] > cap else ""), axis=1)
    status = np.where(d["inflation_ratio"] > critical, "Critical over-claim", np.where(d["inflation_ratio"] > moderate, "Over-claim, review", "Within normal range"))
    colors = {"Critical over-claim": danger(), "Over-claim, review": caution(), "Within normal range": good()}
    fig = go.Figure()
    for name, color in colors.items():
        m = status == name
        if m.any():
            sub = d[m]
            fig.add_bar(y=sub["campaign_id"], x=sub["shown"], orientation="h", name=name, marker_color=color, text=sub["label"], textposition="outside",
                        cliponaxis=False, customdata=sub["inflation_ratio"],
                        hovertemplate="%{y}<br>Platform claims %{customdata:.2f}x what the test confirms<extra></extra>")
    hi = padded_range(d["shown"], include=[moderate, critical], floor_zero=True, pad=0.3)[1]
    axis = ("Conversions the platform claims, per conversion the test confirms" if basis == "conversions" else "Return the platform claims, per $1 the test proves")
    fig.update_xaxes(range=[0, hi], title_text=axis, ticksuffix="x", showgrid=True, gridcolor=t["grid"])
    fig.update_yaxes(showgrid=False, autorange=True)
    for x, label, color, shift in ((moderate, f"Review above {moderate:g}x", caution(), 0), (critical, f"Critical above {critical:g}x", danger(), 16)):
        fig.add_vline(x=x, line_dash="dot", line_color=color, line_width=1.5)
        fig.add_annotation(x=x, yref="paper", y=1.0, yshift=shift, text=label, showarrow=False, yanchor="bottom", xanchor="left", font=dict(color=color, size=11))
    fig.update_layout(barmode="overlay")
    return _layout(fig, headline, "A value of 1.0x means the platform claims exactly what the test confirms. Higher means more over-claiming.", bar_height(len(d)) + 40, bottom=96)


def trend_chart(ch_roll: pd.DataFrame, breakeven: float, breakeven_label: str, headline: str) -> go.Figure:
    """7 day rolling return by channel: breakeven line, shaded loss zone, a shaded envelope of recent variation, direct end labels."""
    t = _THEME
    fig = go.Figure()
    has_band = {"band_low", "band_high"} <= set(ch_roll.columns)
    vals = list(ch_roll["iroas"].dropna())
    lo, hi = padded_range(vals, include=[breakeven], robust=True, pad=0.15)
    fig.add_hrect(y0=lo, y1=breakeven, fillcolor="rgba(192,57,43,0.07)", line_width=0, layer="below")
    for i, ch in enumerate(ch_roll["channel"].unique()):
        d = ch_roll[ch_roll["channel"] == ch].sort_values("date").dropna(subset=["iroas"])
        if d.empty:
            continue
        color = channel_color(ch, i)
        if has_band:
            b = d.dropna(subset=["band_low", "band_high"])
            fig.add_scatter(x=pd.concat([b["date"], b["date"][::-1]]), y=pd.concat([b["band_high"], b["band_low"][::-1]]), fill="toself",
                            fillcolor=_alpha(color, 0.14), line=dict(width=0), hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=d["date"], y=d["iroas"], name=ch, mode="lines", showlegend=False, line=dict(color=color, width=2.5), hovertemplate="%{x}<br>" + ch + ": %{y:.2f}x<extra></extra>")
        fig.add_scatter(x=d["date"].iloc[-1:], y=d["iroas"].iloc[-1:], mode="markers+text", showlegend=False, marker=dict(color=color, size=8),
                        text=[f" {ch.replace(' Ads', '')} {d['iroas'].iloc[-1]:.2f}x"], textposition="middle right", textfont=dict(color=color, size=12),
                        hoverinfo="skip", cliponaxis=False)
    _breakeven_line(fig, breakeven, breakeven_label)
    fig.update_yaxes(range=[lo, hi], title_text="Revenue per $1 (7 day rolling)", ticksuffix="x")
    sub = ("Shaded area under the dashed line is below breakeven. Each line is a channel's last 7 days of test results; the axis is zoomed to the typical range."
           + (" The soft band around each line shows how far it has typically wandered over recent weeks (variation, not a statistical interval)." if has_band else ""))
    fig = _layout(fig, headline, sub, 440, right=170)
    return fig


def waterfall_chart(steps: Sequence[Tuple[str, float, str]], headline: str) -> go.Figure:
    """Claimed revenue, minus the over-claim, equals revenue proven by the test (a single axis, never dual)."""
    t = _THEME
    claimed, delta, proven = steps[0][1], steps[1][1], steps[2][1]
    labels = [s[0] for s in steps]
    fig = go.Figure()
    fig.add_bar(x=[labels[0]], y=[claimed], marker_color=t["claimed"], text=[f"${claimed:,.0f}"], textposition="outside", cliponaxis=False, name="Claimed")
    fig.add_bar(x=[labels[1]], y=[-delta], base=[proven], marker_color=danger(), text=[f"-${-delta:,.0f}"], textposition="outside", cliponaxis=False, name="Over-claim")
    fig.add_bar(x=[labels[2]], y=[proven], marker_color=t["proven"], text=[f"${proven:,.0f}"], textposition="outside", cliponaxis=False, name="Proven")
    fig.update_yaxes(range=[0, claimed * 1.18], tickprefix="$", tickformat="~s", title_text="Revenue")
    fig.update_layout(showlegend=False, bargap=0.35)
    return _layout(fig, headline, "Platforms claim the first bar. The red step is revenue they take credit for that the test does not support. The last bar is what the test proves.",
                   360, legend=False, bottom=40)


def portfolio_chart(ch: pd.DataFrame, headline: str) -> go.Figure:
    """Spend share vs proven revenue share. Above the diagonal a channel earns more than its share of spend."""
    t = _THEME
    sym = {"Scale": "circle", "Maintain": "square", "Restructure": "diamond", "Cut": "triangle-down"}
    col = {"Scale": good(), "Maintain": caution(), "Restructure": t["accent"], "Cut": danger()}
    fig = go.Figure()
    top = float(np.nanmax([ch["spend_share"].max(), ch["revenue_share"].max(), 0.05]))
    lim = top * 1.25
    fig.add_scatter(x=[0, lim], y=[0, lim], mode="lines", line=dict(color=t["muted"], dash="dot", width=1.2), name="Revenue share equals spend share", hoverinfo="skip")
    for action in ("Scale", "Maintain", "Restructure", "Cut"):
        d = ch[ch["action"] == action]
        if d.empty:
            continue
        fig.add_scatter(x=d["spend_share"], y=d["revenue_share"], mode="markers+text", name=ui.ACTION_LABEL[action], text=[c.replace(" Ads", "") for c in d["channel"]],
                        textposition="top center", marker=dict(symbol=sym[action], size=np.clip(d["spend"] / ch["spend"].max() * 34, 16, 36), color=col[action],
                                                               line=dict(color=t["bg"], width=1.5)),
                        customdata=np.stack([d["channel"], d["proven"].fillna(0)], axis=-1),
                        hovertemplate="%{customdata[0]}<br>Share of spend %{x:.0%}<br>Share of proven revenue %{y:.0%}<br>Proven return %{customdata[1]:.2f}x<extra></extra>")
    fig.update_xaxes(range=[0, lim], tickformat=".0%", title_text="Share of ad spend", showgrid=True, gridcolor=t["grid"])
    fig.update_yaxes(range=[0, lim], tickformat=".0%", title_text="Share of proven revenue")
    return _layout(fig, headline, "Above the dotted line a channel earns more than its share of the budget; below it, less. Marker shape and the label show where each channel's return stands.", 400, bottom=80)


def _alpha(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def spend_shift_chart(table: pd.DataFrame, headline: str) -> go.Figure:
    """Spend by channel before and after a scenario, on one axis."""
    t = _THEME
    fig = go.Figure()
    fig.add_bar(x=table["channel"], y=table["spend_before"], name="Spend today", marker_color=t["claimed"], text=table["spend_before"].map(lambda v: f"${v:,.0f}"), textposition="outside", cliponaxis=False)
    fig.add_bar(x=table["channel"], y=table["spend_after"], name="Spend in the scenario", marker_color=t["proven"], text=table["spend_after"].map(lambda v: f"${v:,.0f}"), textposition="outside", cliponaxis=False)
    hi = padded_range(list(table["spend_before"]) + list(table["spend_after"]), pad=0.2)[1]
    fig.update_yaxes(range=[0, hi], tickprefix="$", tickformat="~s", title_text="Ad spend")
    fig.update_layout(barmode="group", bargap=0.3)
    return _layout(fig, headline, "Spend by channel today and after the scenario. Total spend does not change.", 400)


def sensitivity_chart(table: pd.DataFrame, break_even: float, headline: str) -> go.Figure:
    """Net revenue change as the return on the new money falls below its average. One axis, a zero line, a marked break-even point."""
    t = _THEME
    pct = table["haircut"] * 100
    fig = go.Figure()
    fig.add_scatter(x=pct, y=table["net"], mode="lines+markers+text", line=dict(color=t["proven"], width=3), marker=dict(size=9), name="Net revenue change",
                    text=table["net"].map(lambda v: f"${v:,.0f}"), textposition="top center", cliponaxis=False)
    fig.add_hline(y=0, line_dash="dash", line_color=danger(), line_width=2)
    fig.add_scatter(x=[None], y=[None], mode="lines", name="No net change", line=dict(color=danger(), dash="dash", width=2))
    lo, hi = padded_range(table["net"], include=[0.0], floor_zero=False, pad=0.2)
    fig.update_yaxes(range=[lo, hi], tickprefix="$", tickformat="~s", title_text="Net revenue change")
    fig.update_xaxes(title_text="How much lower the return on the new money is than its average", ticksuffix="%")
    if pd.notna(break_even) and 0 < break_even < table["haircut"].max() * 2:
        fig.add_vline(x=break_even * 100, line_dash="dot", line_color=caution(), line_width=1.5)
        fig.add_annotation(x=break_even * 100, yref="paper", y=1.0, text=f"Net change reaches zero at {break_even:.0%}", showarrow=False, yanchor="bottom", font=dict(color=caution(), size=11))
    return _layout(fig, headline, "If returns fall as spend rises, the net gain shrinks. The dashed line marks where the move stops adding revenue.", 400, bottom=90)


def allocation_chart(table: pd.DataFrame, headline: str) -> go.Figure:
    """Current share of spend by tier against an editable target mix."""
    t = _THEME
    d = table.copy()
    fig = go.Figure()
    fig.add_bar(x=d["tier"], y=d["share"], name="Current share of spend", marker_color=t["proven"], text=d["share"].map(lambda v: f"{v:.0%}"), textposition="outside", cliponaxis=False)
    tg = d.dropna(subset=["target"])
    fig.add_bar(x=tg["tier"], y=tg["target"], name="Target mix", marker_color=t["claimed"], text=tg["target"].map(lambda v: f"{v:.0%}"), textposition="outside", cliponaxis=False)
    fig.update_yaxes(range=[0, max(1.0, float(d["share"].max())) * 1.15], tickformat=".0%", title_text="Share of spend")
    fig.update_layout(barmode="group", bargap=0.3)
    return _layout(fig, headline, "Where today's spend sits by evidence and return tier, against the target mix you set.", 380)
