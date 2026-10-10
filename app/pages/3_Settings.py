"""Policy settings and run declarations (versioned per workspace)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DEMO_NOTICE, demo_mode, get_store, identity, page_setup, safe_page_link  # noqa: E402

page_setup("Settings",":material/tune:")

import streamlit as st  # noqa: E402

from config import HEADLINE_SPEC, HEADLINE_STRICT, PolicySettings, SettingsError  # noqa: E402

store = get_store()
actor, ws = identity()
settings, decl, version = store.latest_workspace_config(ws)
decl = {"currency": "USD", "timezone": "UTC", "spend_unit": "dollars", "decimal_separator": ".", "date_order": "ymd",
        "channel_aliases": {}, **decl}

import ui  # noqa: E402

ui.page_head("Policy", "Policy and declarations", "These settings decide how results are counted, when evidence is trusted and what a decision rule may do. Every change creates a new version and is stamped on each run.")
if demo_mode():
    ui.callout("Settings are read only on the public demo. " + DEMO_NOTICE)
    safe_page_link("app.py", "Back to the Dashboard", ":material/analytics:")
    st.stop()
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
    st.subheader("Audience tiers and control markets")
    st.caption("These settings decide how the audience tier view judges results. Tiers that fall short of the sample rules are reported as 'not enough data' and never raise a recommendation.")
    k1, k2 = st.columns(2)
    phi = k1.slider("Weight on matching the audience mix (not just sales history)", 0.0, 2.0, float(settings.propensity_weight_phi), 0.05,
                    help="Higher values force the control markets to resemble the test markets in who lives there, not only in how much they sold before launch.")
    c_warn = k2.number_input("Review a tier when this share of credited sales was not caused by ads (%)", 0.0, 100.0, float(settings.cannibalization_warning_threshold), 1.0)
    k3, k4 = st.columns(2)
    c_crit = k3.number_input("Recommend reducing tier spend at this share not caused by ads (%)", 0.0, 100.0, float(settings.cannibalization_critical_threshold), 1.0,
                             help="Raises a recommendation on the Sign-off desk. It never acts on its own, and needs at least a Leaning (Directional) evidence level.")
    t_spend = k4.number_input("Smallest tier spend that can raise a recommendation ($)", 0.0, 1_000_000_000.0, float(settings.tier_min_spend), 1000.0)
    k5, k6, k7 = st.columns(3)
    t_users = k5.number_input("Minimum people reached per arm", 0.0, 100_000_000.0, float(settings.tier_min_users), 1000.0)
    t_convs = k6.number_input("Minimum conversions per arm", 0.0, 10_000_000.0, float(settings.tier_min_conversions), 10.0)
    t_width = k7.number_input("Widest 95% range on the share caused by ads (0 to 1)", 0.01, 1.0, float(settings.tier_max_range_width), 0.01)
    m1, m2, m3 = st.columns(3)
    mm_r2 = m1.number_input("Control match: minimum sales history explained", 0.0, 1.0, float(settings.match_min_r2), 0.01)
    mm_ov = m2.number_input("Control match: minimum audience mix overlap", 0.0, 1.0, float(settings.match_min_overlap), 0.01)
    mm_err = m3.number_input("Control match: maximum pre-period error (% of sales)", 0.1, 100.0, float(settings.match_max_rmspe_pct), 0.5)
    st.subheader("Economics and benchmarks")
    st.caption("A revenue return of 1.0x is only breakeven at a 100% margin. Declare your contribution margin (revenue minus product, shipping, fees and returns) "
               "to see profit aware returns. Nothing is assumed unless you choose it.")
    known = st.checkbox("I know my contribution margin", value=settings.gross_margin is not None)
    margin_pct = st.number_input("Contribution margin (%), used only if the box above is ticked", 1.0, 100.0, float(settings.gross_margin * 100) if settings.gross_margin else 40.0, 1.0)
    try:
        from benchmark_registry import Registry
        _reg = Registry.load()
        industries = ["(none)"] + _reg.industries()
    except Exception:
        _reg, industries = None, ["(none)"]
    cur_ind = settings.margin_industry if settings.margin_industry in industries else "(none)"
    industry = st.selectbox("Or use an industry proxy (ignored if you declared a margin above)", industries, index=industries.index(cur_ind),
                            help="Damodaran aggregate gross margin of US public companies in the industry: an upper bound on your contribution margin, so your true breakeven is higher.")
    fips_text = st.text_area("Treatment geo codes for the sample fraction check (state 2 digit or county 5 digit FIPS, comma or line separated)",
                             ", ".join(decl.get("test_geo_fips", [])), placeholder="06, 48, 12", help="Used to compare your geo sample fraction with those geos' share of the US population (Census).")
    seasonal = st.checkbox("Adjust the control geo drift check for U.S. retail seasonality (Census via FRED)", value=settings.seasonality_benchmark)
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
                             trust_directional_min=t_dir, headline_metric=headline,
                             gross_margin=(margin_pct / 100.0) if known else None, margin_industry="" if known or industry == "(none)" else industry,
                             seasonality_benchmark=bool(seasonal), propensity_weight_phi=float(phi), cannibalization_warning_threshold=float(c_warn),
                             cannibalization_critical_threshold=float(c_crit), tier_min_users=float(t_users), tier_min_conversions=float(t_convs), tier_min_spend=float(t_spend),
                             tier_max_range_width=float(t_width), match_min_r2=float(mm_r2), match_min_overlap=float(mm_ov), match_max_rmspe_pct=float(mm_err))
        fips = [f.strip() for f in fips_text.replace("\n", ",").split(",") if f.strip()]
        if fips and _reg is not None:
            share = _reg.population_share(fips)
            if share["errors"]:
                raise SettingsError("Treatment geo codes: " + " ".join(share["errors"]))
        v = store.save_workspace_config(ws, new, {"currency": currency, "timezone": tz.strip() or "UTC", "spend_unit": spend_unit,
                                                  "decimal_separator": decimal, "date_order": order, "channel_aliases": aliases,
                                                  "test_geo_fips": fips})
        st.success(f"Saved as version {v}. New uploads will use it; existing runs keep the policy they ran with.")
        if new.gross_margin or new.margin_industry:
            from economics import resolve_economics
            econ = resolve_economics(new, _reg)
            st.info(f"Breakeven return is **{econ['breakeven_iroas']:.2f}x** at a {econ['margin']:.0%} margin. {econ['note']}")
        if fips and _reg is not None:
            s = _reg.population_share(fips)
            gap = abs(s["share"] - geo) / geo
            (st.warning if gap > 0.15 else st.success)(f"Those geos hold {s['share']:.1%} of the US population ({s['vintage']}); your geo sample fraction is {geo:.1%} ({gap:.0%} apart, tolerance 15%).")
    except SettingsError as exc:
        st.error(str(exc))
