"""Policy settings and run declarations (versioned per workspace)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import get_store, identity, page_setup  # noqa: E402

page_setup("Settings", "⚙️")

import streamlit as st  # noqa: E402

from config import HEADLINE_SPEC, HEADLINE_STRICT, PolicySettings, SettingsError  # noqa: E402

store = get_store()
actor, ws = identity()
settings, decl, version = store.latest_workspace_config(ws)
decl = {"currency": "USD", "timezone": "UTC", "spend_unit": "dollars", "decimal_separator": ".", "date_order": "ymd",
        "channel_aliases": {}, **decl}

st.title("⚙️ Policy and declarations")
st.caption(f"Workspace: **{ws[:6]}…** · Settings version {version or 'defaults (never saved)'}. Every change is saved as a new "
           "version, and each run records the policy it used.")

with st.form("settings"):
    st.subheader("Data declarations")
    st.caption("Tell the engine how your files are written. Mapping uses these, and anything ambiguous is rejected, never guessed.")
    a, b, c = st.columns(3)
    currency = a.text_input("Currency (ISO code, one per run)", decl["currency"], max_chars=3).upper()
    tz = b.text_input("Timezone (IANA name)", decl["timezone"])
    spend_unit = c.selectbox("Spend unit", ["dollars", "cents"], index=["dollars", "cents"].index(decl["spend_unit"]))
    d, e = st.columns(2)
    decimal = d.selectbox("Decimal separator in numbers", [".", ","], index=[".", ","].index(decl["decimal_separator"]),
                          help="Use ',' for European style numbers like 1.234,50")
    order = e.selectbox("Date order for dates like 03/04/2026", ["ymd", "mdy", "dmy"], index=["ymd", "mdy", "dmy"].index(decl["date_order"]),
                        help="ymd means ISO dates (2026-04-03). Slash dates are only read when you choose mdy or dmy.")
    aliases_text = st.text_area("Channel aliases (one per line, alias = Canonical name)",
                                "\n".join(f"{k} = {v}" for k, v in decl["channel_aliases"].items()),
                                placeholder="facebook = Meta Ads\nyoutube = Google Ads")

    st.subheader("Measurement policy")
    headline = st.radio("Headline incrementality metric", [HEADLINE_SPEC, HEADLINE_STRICT],
                        index=[HEADLINE_SPEC, HEADLINE_STRICT].index(settings.headline_metric), horizontal=True,
                        format_func=lambda v: "Reported by spec (all treatment geo revenue)" if v == HEADLINE_SPEC else "Strict lift (causal gap only)")
    f1, f2, f3 = st.columns(3)
    geo = f1.number_input("Geo sample fraction", 0.01, 1.0, float(settings.geo_sample_fraction), 0.01)
    pre = f2.number_input("Pre-period days", 7, 365, int(settings.pre_period_days))
    aov = f3.number_input("Typical order value ($)", 0.01, 1_000_000.0, float(settings.avg_order_value))
    g1, g2, g3 = st.columns(3)
    min_pre = g1.number_input("Minimum pre-period days", 7, 365, int(settings.min_pre_period_days))
    min_test = g2.number_input("Minimum test days", 7, 365, int(settings.min_test_days))
    min_conv = g3.number_input("Min daily conversions per geo", 0.0, 10_000.0, float(settings.min_daily_conversions))
    h1, h2 = st.columns(2)
    infl_m = h1.number_input("Inflation: moderate at", 1.0, 10.0, float(settings.inflation_moderate), 0.05)
    infl_c = h2.number_input("Inflation: critical at", 1.0, 20.0, float(settings.inflation_critical), 0.05)
    i1, i2 = st.columns(2)
    t_ver = i1.number_input("Trust score for Verified (and up)", 1.0, 100.0, float(settings.trust_verified_min))
    t_dir = i2.number_input("Trust score for Directional (and up)", 0.0, 100.0, float(settings.trust_directional_min))
    submitted = st.form_submit_button("Save new version", type="primary")

if submitted:
    try:
        aliases = {}
        for line in aliases_text.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip() and v.strip():
                    aliases[k.strip()] = v.strip()
        if len(currency) != 3 or not currency.isalpha():
            raise SettingsError("Currency must be a 3 letter ISO code such as USD.")
        new = PolicySettings(geo_sample_fraction=geo, pre_period_days=int(pre), min_pre_period_days=int(min_pre),
                             min_test_days=int(min_test), min_daily_conversions=min_conv, avg_order_value=aov,
                             inflation_moderate=infl_m, inflation_critical=infl_c, trust_verified_min=t_ver,
                             trust_directional_min=t_dir, headline_metric=headline)
        v = store.save_workspace_config(ws, new, {"currency": currency, "timezone": tz.strip() or "UTC", "spend_unit": spend_unit,
                                                  "decimal_separator": decimal, "date_order": order, "channel_aliases": aliases})
        st.success(f"Saved as version {v}. New uploads will use it; existing runs keep the policy they ran with.")
    except SettingsError as exc:
        st.error(str(exc))
