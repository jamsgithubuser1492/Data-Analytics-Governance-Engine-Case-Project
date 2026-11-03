"""The code tokens must match the written design system, and the new components must stay emoji free."""
from __future__ import annotations

import re

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "python")]

import ui  # noqa: E402

DOC = (ROOT / "docs" / "DESIGN_SYSTEM.md").read_text(encoding="utf-8")


def test_light_tokens_match_the_documented_palette() -> None:
    for token in (ui.LIGHT["ink"], ui.LIGHT["accent"], ui.LIGHT["accent2"], ui.LIGHT["bg"], ui.LIGHT["card"], ui.LIGHT["border"], ui.LIGHT["ok"], ui.LIGHT["ok_mid"],
                  ui.LIGHT["claimed"], ui.LIGHT["model"], ui.LIGHT["surface"], ui.LIGHT["surface2"]):
        assert token.upper() in DOC.upper(), token


def test_three_methods_have_fixed_distinct_colours() -> None:
    assert len({ui.LIGHT["claimed"], ui.LIGHT["model"], ui.LIGHT["proven"]}) == 3
    assert len({ui.DARK["claimed"], ui.DARK["model"], ui.DARK["proven"]}) == 3


def test_streamlit_theme_uses_the_navy_primary() -> None:
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "#18345B" in cfg and "#F6F8FB" in cfg


def test_components_render_without_emoji_or_dollar_escapes_breaking(monkeypatch) -> None:
    rendered = []
    monkeypatch.setattr(ui.st, "markdown", lambda body, **k: rendered.append(body))
    ui.briefing("Executive briefing", "Headline", "Summary", "Impact", "+$1", "note", [("$1", "a")], "conf")
    ui.decision_flow(3)
    ui.governance_status([("Check", True), ("Other", False)])
    ui.measurement_trio("1.00x", "2.00x", "3.00x")
    ui.validity_ring(87, [("Coverage", "92%")])
    text = " ".join(rendered)
    assert not ui.EMOJI.search(text)
    assert "MMGE" in ui.brand() and "<svg" in ui.brand()


def test_logo_file_exists_and_is_valid_svg() -> None:
    svg = (ROOT / "docs" / "img" / "logo.svg").read_text()
    assert svg.startswith("<svg") and re.search(r"#159A83", svg)


def _lum(hex_: str) -> float:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("theme", ["LIGHT", "DARK"])
def test_text_colours_meet_the_contrast_standard_on_their_surfaces(theme: str) -> None:
    t = getattr(ui, theme)
    pairs = [("ink", "bg"), ("ink", "card"), ("ink", "surface"), ("ink", "surface2"), ("muted", "bg"), ("muted", "card"), ("muted", "surface"), ("muted", "surface2"),
             ("ok_text", "ok_bg"), ("ok", "card"), ("ok", "bg"), ("warn", "warn_bg"), ("warn", "card"), ("bad", "bad_bg"), ("bad", "card"), ("accent", "accent_soft"), ("accent", "card")]
    for fg, bg in pairs:
        assert _ratio(t[fg], t[bg]) >= 4.5, (theme, fg, bg, round(_ratio(t[fg], t[bg]), 2))


def test_the_chart_series_colours_are_distinguishable_from_the_page() -> None:
    for key in ("claimed", "model", "proven"):
        assert _ratio(ui.LIGHT[key], ui.LIGHT["card"]) >= 3.0, key  # graphical objects need 3:1
