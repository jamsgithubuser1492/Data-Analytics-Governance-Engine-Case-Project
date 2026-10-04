"""Design system for the MMGE app: tokens (light and dark), CSS, and small components.

Rules this module enforces (from the product requirements): one primary accent, colorblind safe data colors, no
emojis, status always shown as a distinct shape AND a text label, definitions available on hover, every chart card
has a Chart or Table toggle, and the active counting basis is stamped on every chart.
"""
from __future__ import annotations

import html
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import streamlit as st

# ------------------------------------------------------------------------------------------- tokens
LIGHT: Dict[str, str] = dict(bg="#ffffff", surface="#f5f8fc", surface2="#ecf1f8", border="#dfe6f0", ink="#121a27", muted="#526075",
                             accent="#1d4ed8", accent_soft="#e8eefc", ok="#15734d", ok_bg="#e3f4eb", warn="#855400", warn_bg="#fcf0d6",
                             bad="#a62a1e", bad_bg="#fbe6e3", grid="#e6ebf2", claimed="#9aa7bd", model="#7d98d6", proven="#1d4ed8",
                             hero_a="#f1f5ff", hero_b="#ffffff")
DARK: Dict[str, str] = dict(bg="#0f141c", surface="#171e29", surface2="#1e2735", border="#2a3547", ink="#e8edf5", muted="#9aa8bd",
                            accent="#8fb0ff", accent_soft="#1a2848", ok="#5fd1a0", ok_bg="#123226", warn="#f0c25e", warn_bg="#3a2f12",
                            bad="#ff8f84", bad_bg="#3d1a18", grid="#263143", claimed="#6f7d93", model="#5d7fcc", proven="#8fb0ff",
                            hero_a="#16213a", hero_b="#0f141c")
# Okabe-Ito based channel colors: distinguishable under the common forms of color blindness
CHANNEL_COLORS = {"Google Ads": "#E69F00", "Meta Ads": "#0072B2", "TikTok Ads": "#009E73", "Netflix Ads": "#CC79A7"}
FALLBACK = ["#56B4E9", "#D55E00", "#F0E442", "#999999"]

EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2139\u200d\uFE0F]")


def scrub(text: object) -> str:
    """Remove emoji and pictographs from any text, including text stored by older runs."""
    return EMOJI.sub("", str(text)).replace("  ", " ").strip() if text is not None else ""


def mode() -> str:
    """'light' or 'dark' following the viewer's Streamlit theme (system setting by default)."""
    try:
        t = st.context.theme.type
        return t if t in ("light", "dark") else "light"
    except Exception:
        return "light"


def tokens() -> Dict[str, str]:
    return DARK if mode() == "dark" else LIGHT


def channel_color(name: str, i: int = 0) -> str:
    return CHANNEL_COLORS.get(name, FALLBACK[i % len(FALLBACK)])


# ------------------------------------------------------------------------------------------- css
def _css(t: Dict[str, str]) -> str:
    return f"""
<style>
:root {{ --mm-accent: {t['accent']}; --mm-ink: {t['ink']}; --mm-muted: {t['muted']}; --mm-border: {t['border']}; --mm-surface: {t['surface']}; }}
[data-testid="stSidebarNav"] {{display: none;}}
[data-testid="stHeader"] {{background: transparent;}}
.block-container {{padding-top: 1.6rem; padding-bottom: 5rem; max-width: 1240px;}}
h1, h2, h3, h4, h5 {{letter-spacing: -0.015em;}}
h5 {{font-weight: 650; font-size: 1.12rem; margin-bottom: .1rem;}}
[data-testid="stSidebar"] {{border-right: 1px solid {t['border']};}}
[data-testid="stMetric"] {{background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 14px; padding: 14px 16px;}}
[data-testid="stMetricValue"] {{font-weight: 700; font-variant-numeric: tabular-nums;}}
[data-testid="stVerticalBlockBorderWrapper"] {{border-radius: 16px; border-color: {t['border']};}}
[data-testid="stExpander"] {{border-radius: 12px; border-color: {t['border']};}}
.stButton > button {{border-radius: 10px; font-weight: 600;}}
.hero {{position: relative; overflow: hidden; border: 1px solid {t['border']}; border-radius: 22px; padding: 44px 48px 36px;
  background: radial-gradient(1200px 400px at 85% -10%, {t['accent_soft']} 0%, transparent 60%), linear-gradient(180deg, {t['hero_a']}, {t['hero_b']});}}
.kicker {{font-size: .78rem; letter-spacing: .12em; text-transform: uppercase; color: {t['muted']}; font-weight: 650;}}
.hero h1 {{font-size: clamp(1.9rem, 3.6vw, 3.1rem); line-height: 1.08; margin: .5rem 0 .9rem; font-weight: 750; color: {t['ink']}; max-width: 900px;}}
.hero .lede {{font-size: 1.12rem; line-height: 1.6; color: {t['muted']}; max-width: 780px;}}
.hero .lede b {{color: {t['ink']};}}
.chips {{display: flex; flex-wrap: wrap; gap: 8px; margin-top: 22px;}}
.chip {{display: inline-block; padding: 7px 14px; border-radius: 999px; border: 1px solid {t['border']}; background: {t['bg']};
  color: {t['ink']} !important; text-decoration: none !important; font-size: .86rem; font-weight: 600;}}
.chip:hover {{border-color: {t['accent']}; color: {t['accent']} !important;}}
.sec {{margin: 4.2rem 0 1.1rem; scroll-margin-top: 70px;}}
.sec .num {{font-variant-numeric: tabular-nums; color: {t['accent']}; font-weight: 700; font-size: .9rem; letter-spacing: .08em;}}
.sec h2 {{font-size: 1.85rem; margin: .15rem 0 .35rem; font-weight: 720; color: {t['ink']};}}
.sec p {{color: {t['muted']}; font-size: 1.04rem; max-width: 820px; line-height: 1.55; margin: 0;}}
.pill {{display: inline-flex; align-items: center; gap: 6px; padding: 3px 11px 3px 9px; border-radius: 999px; font-size: .78rem; font-weight: 650;
  line-height: 1.5; border: 1px solid transparent; white-space: nowrap;}}
.pill svg {{flex: none;}}
.pill-ok {{background: {t['ok_bg']}; color: {t['ok']};}} .pill-warn {{background: {t['warn_bg']}; color: {t['warn']};}}
.pill-bad {{background: {t['bad_bg']}; color: {t['bad']};}} .pill-info {{background: {t['accent_soft']}; color: {t['accent']};}}
.pill-muted {{background: {t['surface2']}; color: {t['muted']};}}
.stats {{display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 18px 0 8px;}}
.stat {{background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 16px; padding: 18px 20px;}}
.stat .l {{font-size: .82rem; color: {t['muted']}; font-weight: 600;}}
.stat .v {{font-size: 2rem; font-weight: 740; letter-spacing: -.02em; color: {t['ink']}; font-variant-numeric: tabular-nums; line-height: 1.15; margin-top: 4px;}}
.stat .s {{font-size: .82rem; color: {t['muted']}; margin-top: 4px; line-height: 1.4;}}
.stat.ok .v {{color: {t['ok']};}} .stat.bad .v {{color: {t['bad']};}} .stat.warn .v {{color: {t['warn']};}}
.callout {{border: 1px solid {t['border']}; border-left: 4px solid {t['accent']}; background: {t['surface']}; padding: 16px 20px; border-radius: 12px; line-height: 1.55;}}
.callout.bad {{border-left-color: {t['bad']}; background: {t['bad_bg']};}} .callout.ok {{border-left-color: {t['ok']}; background: {t['ok_bg']};}}
.callout.warn {{border-left-color: {t['warn']}; background: {t['warn_bg']};}}
.note {{color: {t['muted']}; font-size: .86rem; line-height: 1.5;}}
.src {{color: {t['muted']}; font-size: .78rem; border-top: 1px dashed {t['border']}; padding-top: 8px; margin-top: 6px; line-height: 1.5;}}
.tip {{border-bottom: 1px dotted {t['muted']}; cursor: help; position: relative;}}
.tip:hover::after, .tip:focus::after {{content: attr(data-tip); position: absolute; left: 0; top: 130%; z-index: 99; width: 280px; white-space: normal;
  background: {t['ink']}; color: {t['bg']}; padding: 10px 12px; border-radius: 10px; font-size: .8rem; font-weight: 450; line-height: 1.45; box-shadow: 0 8px 24px rgba(0,0,0,.25);}}
.lens {{border: 1px solid {t['border']}; border-radius: 16px; padding: 18px 20px; background: {t['surface']}; min-height: 360px;}}
.lens h4 {{margin: 6px 0 4px; font-size: 1.1rem;}}
.lens .rule {{font-size: .86rem; color: {t['muted']}; background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 8px 10px; margin: 8px 0;}}
.step {{display: flex; gap: 10px; flex-wrap: wrap; margin: 6px 0 22px;}}
.step .s {{flex: 1 1 140px; border: 1px solid {t['border']}; border-radius: 12px; padding: 10px 14px; background: {t['surface']}; font-size: .86rem;}}
.step .s b {{display: block; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; color: {t['muted']};}}
.step .s.on {{border-color: {t['accent']}; background: {t['accent_soft']};}} .step .s.done b::after {{content: " complete"; color: {t['ok']};}}
.page-head {{margin: .2rem 0 1.4rem;}} .page-head h1 {{font-size: 2.3rem; margin: .2rem 0 .3rem; font-weight: 740;}}
.page-head p {{color: {t['muted']}; font-size: 1.05rem; max-width: 760px; line-height: 1.55; margin: 0;}}
table.mm {{border-collapse: collapse; width: 100%; font-size: .9rem;}} table.mm th {{text-align: left; color: {t['muted']}; font-weight: 650; font-size: .76rem;
  letter-spacing: .05em; text-transform: uppercase; border-bottom: 1px solid {t['border']}; padding: 8px 10px;}}
table.mm td {{padding: 9px 10px; border-bottom: 1px solid {t['border']}; font-variant-numeric: tabular-nums;}}
@media (max-width: 760px) {{ .hero {{padding: 28px 22px;}} .sec h2 {{font-size: 1.5rem;}} }}
</style>
"""


def apply_theme() -> None:
    st.markdown(_css(tokens()), unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------- glossary
GLOSSARY: Dict[str, Tuple[str, str, str]] = {
    "proven": ("Proven return per $1", "Revenue the holdout test shows the ads actually caused, for each $1 spent.", "caused revenue / ad spend  (iROAS)"),
    "claimed": ("Claimed return", "Revenue the ad platform says it generated, for each $1 spent. Platforms grade their own work, so it runs high.", "platform reported revenue / ad spend  (ROAS)"),
    "model": ("Attribution model estimate", "The same question answered by our attribution model, which removes double counting between platforms.", "MTA attributed revenue / ad spend"),
    "breakeven": ("Breakeven", "The return needed to cover the cost of advertising. At a 50% margin you need $2 of revenue per $1 spent.", "1 / contribution margin"),
    "overclaim": ("Over-claim multiple", "How many times more a platform claims than the test confirms. 1.0x means they agree.", "claimed / proven (return basis) or platform conversions / holdout conversions"),
    "phantom": ("Unearned or claimed organic sales", "Revenue a platform takes credit for that would have happened without the ads.", "platform claimed revenue - proven revenue"),
    "unearned": ("Spend not earned back", "Ad spend that the proven revenue did not repay.", "max(0, spend - proven revenue x margin)"),
    "trust": ("Trust score", "0 to 100 quality score of the evidence. 75 and above is Verified, 50 to 74 Directional, below 50 Not decision grade.", "weighted result of six statistical and data checks"),
    "ci": ("95% confidence interval", "The range the true value falls in 95 times out of 100. A narrow range means a precise result.", "estimate +/- sampling uncertainty"),
    "strict": ("Strict lift", "Counts only the gap between test markets and a synthetic control, scaled to the full market.", "(actual - counterfactual) / sample fraction"),
    "spec": ("Reported by spec", "Counts all revenue in the test markets as caused by ads. Simple, but it overstates when markets already sell.", "treatment market revenue / spend"),
    "holdout": ("Holdout test", "Some markets see ads and similar markets do not. The difference between them is the proof of what ads caused.", ""),
    "headroom": ("Growth headroom", "Extra monthly spend the scale leaders can take at today's proven return, assuming returns hold.", "25% of leader spend per month"),
}


def term(key: str, text: Optional[str] = None) -> str:
    """Inline term with a hover definition and formula (always on glossary)."""
    label, plain, formula = GLOSSARY[key]
    tip = plain + (f" Formula: {formula}." if formula else "")
    return f'<span class="tip" tabindex="0" data-tip="{html.escape(tip, quote=True)}">{html.escape(text or label)}</span>'


def tip_text(key: str) -> str:
    """Plain text version for st.metric help= tooltips."""
    label, plain, formula = GLOSSARY[key]
    return plain + (f" Formula: {formula}." if formula else "")


# ------------------------------------------------------------------------------------------- shapes and badges
SHAPES = {"ok": '<circle cx="6" cy="6" r="5" fill="currentColor"/>', "warn": '<rect x="1.2" y="1.2" width="9.6" height="9.6" rx="1.5" fill="currentColor"/>',
          "bad": '<path d="M6 1 11 11H1z" fill="currentColor"/>', "info": '<path d="M6 .8 11.2 6 6 11.2.8 6z" fill="currentColor"/>',
          "muted": '<circle cx="6" cy="6" r="4.2" fill="none" stroke="currentColor" stroke-width="1.6"/>'}
ACTION_KIND = {"Scale": "ok", "Maintain": "warn", "Restructure": "info", "Cut": "bad"}
TIER_LABEL = {"VERIFIED": ("Verified", "ok"), "DIRECTIONAL": ("Directional", "warn"), "NOT_DECISION_GRADE": ("Not decision grade", "bad")}
SEVERITY_LABEL = {"CRITICAL": ("Critical", "bad"), "WARNING": ("Warning", "warn"), "OPPORTUNITY": ("Opportunity", "ok"), "INFO": ("Info", "info")}


def pill(text: str, kind: str = "muted") -> str:
    """Status label: a distinct shape (circle, square, triangle, diamond) plus text, never color alone."""
    return f'<span class="pill pill-{kind}"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">{SHAPES.get(kind, SHAPES["muted"])}</svg>{html.escape(text)}</span>'


def tier_pill(tier: Optional[str]) -> str:
    label, kind = TIER_LABEL.get(tier or "", ("Unrated", "muted"))
    return pill(label, kind)


def action_pill(action: str) -> str:
    return pill(action, ACTION_KIND.get(action, "muted"))


# ------------------------------------------------------------------------------------------- layout components
def hero(kicker: str, title: str, lede: str, chips: Sequence[Tuple[str, str]] = ()) -> None:
    chip_html = "".join(f'<a class="chip" href="#{h}">{html.escape(l)}</a>' for l, h in chips)
    st.markdown(f'<div class="hero"><div class="kicker">{kicker}</div><h1>{title}</h1><div class="lede">{lede}</div>'
                f'<div class="chips">{chip_html}</div></div>', unsafe_allow_html=True)


def page_head(kicker: str, title: str, lede: str = "") -> None:
    st.markdown(f'<div class="page-head"><div class="kicker">{html.escape(kicker)}</div><h1>{html.escape(title)}</h1>'
                + (f"<p>{lede}</p>" if lede else "") + "</div>", unsafe_allow_html=True)


def section(num: str, title: str, lede: str = "", anchor: str = "") -> None:
    st.markdown(f'<div class="sec" id="{anchor}"><div class="num">{num}</div><h2>{html.escape(title)}</h2>' + (f"<p>{lede}</p>" if lede else "") + "</div>",
                unsafe_allow_html=True)


def stat_row(stats: Iterable[Dict[str, str]]) -> None:
    """Cards: dict(label, value, sub, kind, term). Values are display strings; label may carry a glossary term."""
    cards = []
    for s in stats:
        label = term(s["term"], s["label"]) if s.get("term") else html.escape(s["label"])
        cards.append(f'<div class="stat {s.get("kind", "")}"><div class="l">{label}</div><div class="v">{html.escape(s["value"])}</div>'
                     f'<div class="s">{s.get("sub", "")}</div></div>')
    st.markdown(f'<div class="stats">{"".join(cards)}</div>', unsafe_allow_html=True)


def callout(text: str, kind: str = "") -> None:
    st.markdown(f'<div class="callout {kind}">{text}</div>', unsafe_allow_html=True)


def stepper(steps: Sequence[str], current: int) -> None:
    cells = []
    for i, s in enumerate(steps, 1):
        cls = "on" if i == current else ("done" if i < current else "")
        cells.append(f'<div class="s {cls}"><b>Step {i}</b>{html.escape(s)}</div>')
    st.markdown(f'<div class="step">{"".join(cells)}</div>', unsafe_allow_html=True)


def source_line(text: str) -> None:
    st.markdown(f'<div class="src">{text}</div>', unsafe_allow_html=True)


def chart_card(key: str, headline: str, subtitle: str, fig, table: pd.DataFrame, basis: str, source: str = "") -> None:
    """A chart in a bordered card: finding on the left, basis stamp and Chart or Table toggle on the right (FR-UX02, FR-UX03)."""
    with st.container(border=True):
        left, right = st.columns([5, 2])
        with left:
            st.markdown(f"##### {scrub(headline)}")
            st.caption(subtitle)
        with right:
            view = st.segmented_control("View", ["Chart", "Table"], default="Chart", key=f"view_{key}", label_visibility="collapsed") or "Chart"
            st.markdown(f'<div style="text-align:right">{pill(basis, "info")}</div>', unsafe_allow_html=True)
        if view == "Table":
            st.dataframe(table, hide_index=True, width="stretch")
        else:
            st.plotly_chart(fig, width="stretch", theme=None, key=f"fig_{key}")
        if source:
            source_line(source)
