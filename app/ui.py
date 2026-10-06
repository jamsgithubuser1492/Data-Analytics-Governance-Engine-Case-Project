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
LIGHT: Dict[str, str] = dict(bg="#F8FAFC", card="#FFFFFF", surface="#F4F7FA", surface2="#F1F6FB", border="#DDE5ED", ink="#10284A", muted="#5B6B80",
                             accent="#18345B", accent2="#24466F", accent_soft="#EAF2FC", ok="#087F6A", ok_bg="#E5F5F0", ok_mid="#159A83", warn="#8A5A00", warn_bg="#FFF5DE",
                             bad="#B23B43", bad_bg="#FDEBEC", grid="#E6ECF2", claimed="#4E8FE7", model="#8D82D8", proven="#159A83",
                             hero_a="#F1F6FB", hero_b="#FFFFFF", shadow="rgba(16,40,74,.06)")
DARK: Dict[str, str] = dict(bg="#0E1A2E", card="#14233B", surface="#122038", surface2="#1A2C47", border="#27395A", ink="#E6EDF7", muted="#9FB0C6",
                            accent="#8FB0FF", accent2="#B4CAFF", accent_soft="#1B2E52", ok="#5FD1B3", ok_bg="#10332D", ok_mid="#43B69F", warn="#F0C25E", warn_bg="#3A2F12",
                            bad="#FF9AA0", bad_bg="#3D1A1E", grid="#233450", claimed="#6FA5F0", model="#A89FE6", proven="#43B69F",
                            hero_a="#16263F", hero_b="#0E1A2E", shadow="rgba(0,0,0,.25)")
# Okabe-Ito based channel colors: distinguishable under the common forms of color blindness
CHANNEL_COLORS = {"Google Ads": "#E69F00", "Meta Ads": "#0072B2", "TikTok Ads": "#009E73", "Netflix Ads": "#CC79A7"}
FALLBACK = ["#56B4E9", "#D55E00", "#F0E442", "#999999"]

EMOJI = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2139\u200d\uFE0F]")


def scrub(text: object) -> str:
    """Remove emoji and pictographs from any text, including text stored by older runs."""
    return EMOJI.sub("", str(text)).replace("  ", " ").strip() if text is not None else ""


def esc(text: object) -> str:
    """Escape dollar signs so Streamlit markdown never reads two of them as a LaTeX formula."""
    return str(text).replace("$", "\\$")


def safe(text: object) -> str:
    """scrub() plus dollar escaping, for text shown through st.markdown or st.caption."""
    return esc(scrub(text))


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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {{ --mm-accent: {t['accent']}; --mm-ink: {t['ink']}; --mm-muted: {t['muted']}; --mm-border: {t['border']}; --mm-surface: {t['surface']}; }}
html, body, .stApp, [data-testid="stMarkdownContainer"], .stButton button, input, textarea, select {{font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;}}
[data-testid="stSidebarNav"] {{display: none;}}
[data-testid="stHeader"] {{background: transparent;}}
.block-container {{padding-top: 1.6rem; padding-bottom: 5rem; max-width: 1240px;}}
h1, h2, h3, h4, h5 {{letter-spacing: -0.02em; color: {t['ink']};}}
h5 {{font-weight: 600; font-size: 1.08rem; margin-bottom: .1rem;}}
[data-testid="stSidebar"] {{border-right: 1px solid {t['border']};}}
[data-testid="stMetric"] {{background: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 14px 16px; box-shadow: 0 1px 3px {t['shadow']};}}
[data-testid="stMetricValue"] {{font-weight: 600; font-variant-numeric: tabular-nums; font-size: 1.7rem;}}
[data-testid="stMetricValue"] *, [data-testid="stMetricLabel"] * {{white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere;}}
[data-testid="stVerticalBlockBorderWrapper"] {{border-radius: 12px; border-color: {t['border']}; background: {t['card']}; box-shadow: 0 1px 3px {t['shadow']};}}
[data-testid="stExpander"] {{border-radius: 10px; border-color: {t['border']};}}
.stButton > button, .stDownloadButton > button {{border-radius: 8px; font-weight: 600; transition: background-color .18s ease-out, border-color .18s ease-out, transform .18s ease-out;}}
.stButton > button:hover {{transform: translateY(-1px);}}
.brand {{display: flex; align-items: center; gap: 10px; padding: 4px 0 6px;}}
.brand svg {{flex: none;}}
.brand .wm {{font-size: 1.35rem; font-weight: 700; letter-spacing: .02em; color: {t['ink']}; line-height: 1;}}
.brand .sub {{font-size: .68rem; line-height: 1.25; color: {t['muted']}; margin-top: 3px;}}
.hero {{position: relative; overflow: hidden; border: 1px solid {t['border']}; border-radius: 14px; padding: 40px 44px 32px;
  background: linear-gradient(180deg, {t['hero_a']}, {t['hero_b']}); box-shadow: 0 1px 3px {t['shadow']};}}
.kicker {{font-size: .74rem; letter-spacing: .1em; text-transform: uppercase; color: {t['muted']}; font-weight: 600;}}
.hero h1 {{font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.9rem, 3.4vw, 2.7rem); line-height: 1.12; margin: .5rem 0 .9rem; font-weight: 600; color: {t['ink']}; max-width: 900px;}}
.hero .lede {{font-size: 1.08rem; line-height: 1.6; color: {t['muted']}; max-width: 780px;}}
.hero .lede b {{color: {t['ink']};}}
.chips {{display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px;}}
.chip {{display: inline-block; padding: 6px 14px; border-radius: 999px; border: 1px solid {t['border']}; background: {t['card']};
  color: {t['ink']} !important; text-decoration: none !important; font-size: .84rem; font-weight: 500; transition: border-color .18s ease-out, color .18s ease-out;}}
.chip:hover {{border-color: {t['ok_mid']}; color: {t['ok']} !important;}}
.brief {{display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr); gap: 18px; align-items: stretch;}}
.brief .main {{border: 1px solid {t['border']}; border-radius: 14px; padding: 30px 34px; background: linear-gradient(180deg, {t['ok_bg']}, {t['card']} 70%); box-shadow: 0 1px 3px {t['shadow']};}}
.brief h1 {{font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.7rem, 3vw, 2.35rem); line-height: 1.14; font-weight: 600; margin: .7rem 0 .8rem; color: {t['ink']};}}
.brief .lede {{font-size: 1.02rem; line-height: 1.62; color: {t['muted']};}}
.brief .lede b {{color: {t['ink']};}}
.brief .impact {{border: 1px solid {t['border']}; border-radius: 14px; padding: 24px 26px; background: {t['card']}; box-shadow: 0 1px 3px {t['shadow']}; display: flex; flex-direction: column;}}
.brief .impact .big {{font-size: 2.6rem; font-weight: 600; color: {t['ok']}; letter-spacing: -.02em; line-height: 1.1; font-variant-numeric: tabular-nums; margin: 6px 0 2px;}}
.brief .impact .big.neutral {{color: {t['ink']};}}
.brief .facts {{display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; border-top: 1px solid {t['border']}; margin-top: 16px; padding-top: 14px;}}
.brief .facts .v {{font-size: 1.12rem; font-weight: 600; color: {t['ink']}; font-variant-numeric: tabular-nums;}}
.brief .facts .l {{font-size: .74rem; color: {t['muted']}; line-height: 1.35; margin-top: 2px;}}
.brief .conf {{margin-top: auto; padding-top: 14px; border-top: 1px solid {t['border']}; font-size: .84rem; color: {t['muted']}; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;}}
.brief .conf span:nth-child(2) {{flex: 1 1 170px;}}
.brief .conf a {{margin-left: auto; color: {t['accent']}; font-weight: 600; text-decoration: none;}}
.brief .conf a:hover {{text-decoration: underline;}}
@media (max-width: 900px) {{ .brief {{grid-template-columns: 1fr;}} .brief .main {{padding: 22px 22px;}} }}
.sec {{margin: 3.6rem 0 1rem; scroll-margin-top: 70px;}}
.sec .num {{font-variant-numeric: tabular-nums; color: {t['ok']}; font-weight: 600; font-size: .86rem; letter-spacing: .08em;}}
.sec h2 {{font-size: 1.6rem; margin: .15rem 0 .3rem; font-weight: 600; color: {t['ink']};}}
.sec p {{color: {t['muted']}; font-size: 1rem; max-width: 820px; line-height: 1.55; margin: 0;}}
.pill {{display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px 2px 8px; border-radius: 999px; font-size: .76rem; font-weight: 600;
  line-height: 1.5; border: 1px solid transparent; white-space: nowrap;}}
.pill svg {{flex: none;}}
.pill-ok {{background: {t['ok_bg']}; color: {t['ok']};}} .pill-warn {{background: {t['warn_bg']}; color: {t['warn']};}}
.pill-bad {{background: {t['bad_bg']}; color: {t['bad']};}} .pill-info {{background: {t['accent_soft']}; color: {t['accent']};}}
.pill-muted {{background: {t['surface2']}; color: {t['muted']};}}
.stats {{display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 18px 0 8px;}}
.stat {{background: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 3px {t['shadow']}; transition: border-color .18s ease-out;}}
.stat:hover {{border-color: {t['ok_mid']};}}
.stat .l {{font-size: .8rem; color: {t['muted']}; font-weight: 500;}}
.stat .v {{font-size: 1.85rem; font-weight: 600; letter-spacing: -.02em; color: {t['ink']}; font-variant-numeric: tabular-nums; line-height: 1.15; margin-top: 4px;}}
.stat .s {{font-size: .8rem; color: {t['muted']}; margin-top: 4px; line-height: 1.4;}}
.stats.compact {{grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin: 12px 0;}}
.stats.compact .stat {{padding: 12px 14px; border-radius: 10px;}}
.stats.compact .stat .v {{font-size: 1.3rem;}}
.stat.ok .v {{color: {t['ok']};}} .stat.bad .v {{color: {t['bad']};}} .stat.warn .v {{color: {t['warn']};}}
.callout {{border: 1px solid {t['border']}; border-left: 4px solid {t['accent']}; background: {t['surface2']}; padding: 14px 18px; border-radius: 10px; line-height: 1.55;}}
.callout.bad {{border-left-color: {t['bad']}; background: {t['bad_bg']};}} .callout.ok {{border-left-color: {t['ok']}; background: {t['ok_bg']};}}
.callout.warn {{border-left-color: {t['warn']}; background: {t['warn_bg']};}}
.tblwrap {{overflow-x: auto; max-width: 100%;}}
.stat .v, .stat .l, .lens, .callout, .hero h1, .sec h2, .brief h1 {{overflow-wrap: anywhere;}}
.note {{color: {t['muted']}; font-size: .86rem; line-height: 1.5;}}
.src {{color: {t['muted']}; font-size: .78rem; border-top: 1px dashed {t['border']}; padding-top: 8px; margin-top: 6px; line-height: 1.5;}}
.tip {{border-bottom: 1px dotted {t['muted']}; cursor: help; position: relative;}}
.tip:hover::after, .tip:focus::after {{content: attr(data-tip); position: absolute; left: 0; top: 130%; z-index: 99; width: 280px; white-space: normal;
  background: {t['accent']}; color: {t['card']}; padding: 10px 12px; border-radius: 8px; font-size: .8rem; font-weight: 400; line-height: 1.45; box-shadow: 0 8px 24px rgba(0,0,0,.2);}}
.lens {{border: 1px solid {t['border']}; border-radius: 12px; padding: 18px 20px; background: {t['card']}; min-height: 360px;}}
.lens h4 {{margin: 6px 0 4px; font-size: 1.1rem;}}
.lens .rule {{font-size: .86rem; color: {t['muted']}; background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 8px 10px; margin: 8px 0;}}
.step {{display: flex; gap: 10px; flex-wrap: wrap; margin: 6px 0 22px;}}
.step .s {{flex: 1 1 140px; border: 1px solid {t['border']}; border-radius: 10px; padding: 10px 14px; background: {t['card']}; font-size: .86rem;}}
.step .s b {{display: block; font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; color: {t['muted']};}}
.step .s.on {{border-color: {t['accent']}; background: {t['accent_soft']};}} .step .s.done b::after {{content: " complete"; color: {t['ok']};}}
.flow {{display: flex; gap: 0; flex-wrap: wrap; margin: 8px 0 16px; border: 1px solid {t['border']}; border-radius: 10px; overflow: hidden; background: {t['card']};}}
.flow .f {{flex: 1 1 130px; padding: 10px 14px; font-size: .82rem; color: {t['muted']}; border-right: 1px solid {t['border']}; display: flex; gap: 8px; align-items: center;}}
.flow .f:last-child {{border-right: 0;}}
.flow .f.done {{color: {t['ok']};}} .flow .f.now {{background: {t['accent_soft']}; color: {t['accent']}; font-weight: 600;}}
.gov {{display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 8px 18px; margin: 8px 0;}}
.gov div {{display: flex; gap: 8px; align-items: center; font-size: .88rem; color: {t['ink']};}}
.trio {{display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 10px 0;}}
.trio .m {{border: 1px solid {t['border']}; border-top: 3px solid var(--c); border-radius: 10px; padding: 10px 12px; background: {t['card']};}}
.trio .m .l {{font-size: .74rem; color: {t['muted']};}} .trio .m .v {{font-size: 1.3rem; font-weight: 600; font-variant-numeric: tabular-nums; color: {t['ink']};}}
.ring {{display: flex; gap: 22px; align-items: center; flex-wrap: wrap;}}
.ring .rows {{flex: 1 1 220px; display: grid; gap: 8px;}}
.ring .row {{display: flex; justify-content: space-between; font-size: .88rem; border-bottom: 1px solid {t['border']}; padding-bottom: 6px;}}
.ring .row b {{font-variant-numeric: tabular-nums;}}
.page-head {{margin: .2rem 0 1.4rem;}} .page-head h1 {{font-size: 2.1rem; margin: .2rem 0 .3rem; font-weight: 600;}}
.page-head p {{color: {t['muted']}; font-size: 1.02rem; max-width: 760px; line-height: 1.55; margin: 0;}}
table.mm {{border-collapse: collapse; width: 100%; font-size: .9rem;}} table.mm th {{text-align: left; color: {t['muted']}; font-weight: 600; font-size: .74rem;
  letter-spacing: .05em; text-transform: uppercase; border-bottom: 1px solid {t['border']}; padding: 8px 10px;}}
table.mm td {{padding: 9px 10px; border-bottom: 1px solid {t['border']}; font-variant-numeric: tabular-nums;}}
@media (max-width: 760px) {{ .hero {{padding: 26px 20px;}} .sec h2 {{font-size: 1.4rem;}} .trio {{grid-template-columns: 1fr;}} .brief .facts {{grid-template-columns: 1fr;}} }}
</style>
"""


def apply_theme() -> None:
    st.markdown(_css(tokens()), unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------- glossary
GLOSSARY: Dict[str, Tuple[str, str, str]] = {
    "proven": ("Proven return per $1", "Revenue the holdout test shows the ads actually caused, for each $1 spent.", "caused revenue / ad spend"),
    "claimed": ("Claimed return", "Revenue the ad platform says it generated, for each $1 spent. Platforms grade their own work, so it runs high.", "platform reported revenue / ad spend  (ROAS)"),
    "model": ("Attribution model estimate", "The same question answered by our attribution model, which removes double counting between platforms.", "MTA attributed revenue / ad spend"),
    "breakeven": ("Breakeven", "The return needed to cover the cost of advertising. At a 50% margin you need $2 of revenue per $1 spent.", "1 / contribution margin"),
    "overclaim": ("Over-claim multiple", "How many times more a platform claims than the test confirms. 1.0x means they agree.", "claimed / proven (return basis) or platform conversions / holdout conversions"),
    "phantom": ("Unearned or claimed organic sales", "Revenue a platform takes credit for that would have happened without the ads.", "platform claimed revenue - proven revenue"),
    "unearned": ("Spend not earned back", "Ad spend that the proven revenue did not repay.", "max(0, spend - proven revenue x margin)"),
    "trust": ("Measurement confidence", "0 to 100 quality score of the evidence. 75 and above is Confident, 50 to 74 Leaning, below 50 Not yet reliable.", "weighted result of six statistical and data checks"),
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
TIER_LABEL = {"VERIFIED": ("Confident", "ok"), "DIRECTIONAL": ("Leaning", "warn"), "NOT_DECISION_GRADE": ("Not yet reliable", "bad")}
SEVERITY_LABEL = {"CRITICAL": ("Critical", "bad"), "WARNING": ("Warning", "warn"), "OPPORTUNITY": ("Opportunity", "ok"), "INFO": ("Info", "info")}


def pill(text: str, kind: str = "muted") -> str:
    """Status label: a distinct shape (circle, square, triangle, diamond) plus text, never color alone."""
    return f'<span class="pill pill-{kind}"><svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">{SHAPES.get(kind, SHAPES["muted"])}</svg>{html.escape(text)}</span>'


def tier_pill(tier: Optional[str]) -> str:
    label, kind = TIER_LABEL.get(tier or "", ("Unrated", "muted"))
    return pill(label, kind)


ACTION_LABEL = {"Scale": "Strong return", "Maintain": "At or above breakeven", "Restructure": "Needs stronger evidence", "Cut": "Below breakeven"}
STANCE_KIND = {"Lean in": "ok", "Hold": "info", "Re-test": "warn", "Pull back": "bad", "Get more evidence": "muted"}
LEAN_WORDS = {"conservative": "Leans conservative", "moderate": "Moderate", "aggressive": "Leans aggressive"}


def action_pill(action: str) -> str:
    """Neutral description of where a channel's return stands (a position, never an instruction)."""
    return pill(ACTION_LABEL.get(action, action), ACTION_KIND.get(action, "muted"))


def lean_pill(lean: str) -> str:
    return pill(LEAN_WORDS[lean], {"conservative": "info", "moderate": "muted", "aggressive": "warn"}[lean])


# ------------------------------------------------------------------------------------------- layout components
LOGO_SVG = ('<svg width="34" height="34" viewBox="0 0 64 64" aria-hidden="true"><path d="M32 58V30" stroke="#18345B" stroke-width="4" stroke-linecap="round" fill="none"/>'
            '<path d="M32 34C32 20 24 12 10 12c0 14 8 22 22 22z" fill="#159A83"/><path d="M32 28C32 16 39 8 53 8c0 12-8 20-21 20z" fill="#18345B"/>'
            '<path d="M32 44c0-8 5-13 14-13 0 8-5 13-14 13z" fill="#43B69F"/></svg>')
CHECK_SVG = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6.5" fill="currentColor" opacity=".15"/><path d="M4 7.3 6.1 9.4 10 5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
OPEN_SVG = '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>'


def brand() -> str:
    return (f'<div class="brand">{LOGO_SVG}<div><div class="wm">MMGE</div><div class="sub">Media Measurement and<br>Governance Engine</div></div></div>')


def briefing(kicker: str, headline: str, summary: str, impact_label: str, impact_value: str, impact_sub: str,
             facts: Sequence[Tuple[str, str]], confidence: str, link: str = "#sources", neutral: bool = False,
             chips: Sequence[Tuple[str, str]] = ()) -> None:
    """The executive briefing: the finding, a plain summary, the modeled impact and how sure we are. Inputs are pre-escaped HTML."""
    facts_html = "".join(f'<div><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in facts)
    chip_html = "".join(f'<a class="chip" href="#{h}">{html.escape(l)}</a>' for l, h in chips)
    st.markdown(
        f'<div class="brief"><div class="main"><div class="kicker">{kicker}</div><h1>{headline}</h1><div class="lede">{summary}</div>'
        f'<div class="chips">{chip_html}</div></div>'
        f'<div class="impact"><div class="kicker">{impact_label}</div><div class="big{" neutral" if neutral else ""}">{impact_value}</div>'
        f'<div class="note">{impact_sub}</div><div class="facts">{facts_html}</div>'
        f'<div class="conf"><span style="color:{tokens()["ok"]}">{CHECK_SVG}</span><span>{confidence}</span><a href="{link}">View methodology</a></div></div></div>',
        unsafe_allow_html=True)


def decision_flow(current: int) -> None:
    """Where this decision stands: the human approval boundary made visible (steps 1 to 5)."""
    steps = ["Evidence analyzed", "Recommendation prepared", "You review", "You sign", "Handed to the team"]
    cells = []
    for i, name in enumerate(steps, 1):
        cls = "done" if i < current else ("now" if i == current else "")
        icon = CHECK_SVG if i < current else OPEN_SVG
        cells.append(f'<div class="f {cls}">{icon}<span>{name}</span></div>')
    st.markdown(f'<div class="flow">{"".join(cells)}</div>', unsafe_allow_html=True)


def governance_status(items: Sequence[Tuple[str, bool]]) -> None:
    """A short list of checks, each with a check mark when passed or an open circle when it needs review."""
    t = tokens()
    cells = "".join(f'<div><span style="color:{t["ok"] if ok else t["warn"]}">{CHECK_SVG if ok else OPEN_SVG}</span>{html.escape(label)}</div>' for label, ok in items)
    st.markdown(f'<div class="gov">{cells}</div>', unsafe_allow_html=True)


def measurement_trio(platform: str, model: str, proven: str, proven_label: str = "Proven by test") -> None:
    """Platform, attribution model and holdout side by side, in their fixed colours."""
    t = tokens()
    cells = "".join(f'<div class="m" style="--c:{c}"><div class="l">{html.escape(l)}</div><div class="v">{html.escape(v)}</div></div>'
                    for l, v, c in (("Platform reports", platform, t["claimed"]), ("Attribution model", model, t["model"]), (proven_label, proven, t["proven"])))
    st.markdown(f'<div class="trio">{cells}</div>', unsafe_allow_html=True)


def validity_ring(score: float, rows: Sequence[Tuple[str, str]]) -> None:
    """Measurement validity: a ring with the average measurement score and a short breakdown."""
    t = tokens()
    pct = max(0.0, min(score, 100.0)) / 100
    circ = 2 * 3.14159 * 52
    svg = (f'<svg width="130" height="130" viewBox="0 0 130 130" role="img" aria-label="Measurement score {score:.0f} out of 100"><circle cx="65" cy="65" r="52" fill="none" stroke="{t["border"]}" stroke-width="12"/>'
           f'<circle cx="65" cy="65" r="52" fill="none" stroke="{t["ok_mid"]}" stroke-width="12" stroke-linecap="round" stroke-dasharray="{circ * pct:.1f} {circ:.1f}" transform="rotate(-90 65 65)"/>'
           f'<text x="65" y="64" text-anchor="middle" font-size="26" font-weight="600" fill="{t["ink"]}">{score:.0f}</text>'
           f'<text x="65" y="84" text-anchor="middle" font-size="11" fill="{t["muted"]}">out of 100</text></svg>')
    body = "".join(f'<div class="row"><span>{html.escape(l)}</span><b>{html.escape(v)}</b></div>' for l, v in rows)
    st.markdown(f'<div class="ring">{svg}<div class="rows">{body}</div></div>', unsafe_allow_html=True)


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


def stat_row(stats: Iterable[Dict[str, str]], compact: bool = False) -> None:
    """Cards: dict(label, value, sub, kind, term). Values are display strings; label may carry a glossary term."""
    cards = []
    for s in stats:
        label = term(s["term"], s["label"]) if s.get("term") else html.escape(s["label"])
        cards.append(f'<div class="stat {s.get("kind", "")}"><div class="l">{label}</div><div class="v">{html.escape(s["value"])}</div>'
                     f'<div class="s">{s.get("sub", "")}</div></div>')
    st.markdown(f'<div class="stats{" compact" if compact else ""}">{"".join(cards)}</div>', unsafe_allow_html=True)


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
