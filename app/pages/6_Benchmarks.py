"""Benchmark registry browser: verified records, comparability, sources, verification and refused claims."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import page_setup  # noqa: E402

page_setup("Benchmarks",":material/menu_book:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from benchmark_registry import COMPARABILITY, NOT_COMPARABLE_NOTES, Registry, RegistryError  # noqa: E402
from benchmark_verify import verify_live, verify_offline  # noqa: E402

st.title("Benchmarks")
st.caption("Every number here was checked against its primary source. Context, not a verdict: no agent takes a money action because of a benchmark.")
try:
    reg = Registry.load()
except RegistryError as exc:
    st.error(str(exc))
    st.stop()

a, b, c, d = st.columns(4)
a.metric("Registry version", reg.version)
b.metric("Verified records", len(reg.values))
c.metric("Tier A official data", int((reg.values["tier"] == "A").sum()))
d.metric("Refused claims (logged)", len(reg.excluded))
st.info("Tier A is parsed from the publisher's own file and reconciled (for example Census e-commerce share equals the FRED series, and state and county populations sum to the US total). "
        "Tier B is a published study: each number is tied to a verbatim quote that was found on the primary page, and carries its definition and sample size. "
        "A benchmark is only shown against a metric it truly matches; otherwise the answer is 'not comparable'.")

tab_find, tab_browse, tab_sources, tab_verify, tab_refused = st.tabs(["Is it comparable?", "Browse records", "Sources", "Verification", "Refused claims"])

with tab_find:
    st.markdown("Pick what you want to check. The registry answers with comparable records and their caveats, or explains why none exist.")
    labels = {"order_value": "Average order value", "contribution_margin_upper_bound": "Margin (upper bound for contribution margin)", "seasonal_index": "Retail seasonality",
              "test_duration_days": "Holdout test length", "kpi_lift_pct": "Lift on the primary KPI", "roi_interval_width": "Width of ROI confidence intervals",
              "ecommerce_share": "E-commerce share of retail", "ad_click_cvr": "Paid ad click to purchase conversion rate", "channel_roas": "ROAS by channel",
              "incrementality_factor": "Incrementality factor by channel", "cpm": "CPM"}
    metric = st.selectbox("Our metric", list(labels), format_func=labels.get)
    verticals = ["(any)"] + sorted({v for v in reg.values["vertical"].dropna().unique() if not str(v).startswith("industry:")})
    vertical = st.selectbox("Vertical", verticals)
    channel = st.selectbox("Channel", ["(any)", "Meta Ads", "Google Ads", "TikTok Ads", "Netflix Ads"])
    res = reg.find(metric, None if vertical == "(any)" else vertical, None if channel == "(any)" else channel)
    if res.found:
        st.success(f"{len(res.records)} comparable record(s). Fit: **{res.fit}**." + (" Some records are stale." if res.stale else ""))
        st.dataframe(pd.DataFrame([{"Value": r["value"] if r["value"] is not None else f">{r['low']:g}", "Unit": r["unit"], "Entity": r["entity"], "n": r["n"], "Confidence": r["confidence"],
                                    "Fit": r["fit"], "Caveat": r["caveat"], "Source": r["source_title"], "As of": r["as_of"] or "page retrieved " + str(r["age_days"]) + " days ago"}
                                   for r in res.records[:40]]), hide_index=True, width="stretch")
    else:
        st.warning("**Not comparable.** " + " ".join(res.reasons))
    with st.expander("What the registry refuses to compare, and why"):
        for k, why in NOT_COMPARABLE_NOTES.items():
            st.markdown(f"* **{labels.get(k, k)}**: {why}")

with tab_browse:
    f1, f2, f3 = st.columns(3)
    tiers = f1.multiselect("Tier", ["A", "B"], default=["A", "B"])
    metrics = f2.multiselect("Metric", sorted(reg.values["metric_id"].unique()))
    conf = f3.multiselect("Confidence", ["high", "medium", "low"], default=["high", "medium", "low"])
    view = reg.values[reg.values["tier"].isin(tiers) & reg.values["confidence"].isin(conf)]
    if metrics:
        view = view[view["metric_id"].isin(metrics)]
    st.caption(f"{len(view)} records")
    st.dataframe(view[["value_id", "tier", "metric_id", "entity", "value", "low", "high", "unit", "n", "statistic", "confidence", "as_of"]], hide_index=True, width="stretch")
    pick = st.selectbox("Inspect a record", view["value_id"].tolist()) if len(view) else None
    if pick:
        rec = reg.record(reg.values[reg.values["value_id"] == pick].iloc[0])
        st.markdown(f"**{rec['metric_id']}** for **{rec['entity']}**: {rec['value'] if rec['value'] is not None else '>' + str(rec['low'])} {rec['unit']} (confidence {rec['confidence']})")
        st.write("Definition:", rec["definition"])
        st.write("How it was verified:", rec["verification"])
        if rec.get("notes"):
            st.write("Notes:", rec["notes"])
        if rec.get("quote"):
            st.code(rec["quote"], language=None)
        st.markdown(f"Source: [{rec['source_title']}]({rec['source_url']}) · {rec['source_publisher']} · reliability {rec['source_reliability']} · {rec['license_note']}")

with tab_sources:
    st.dataframe(reg.sources.drop(columns=["content_sha256"]), hide_index=True, width="stretch")
    st.caption("Reliability A: official or peer reviewed. B: vendor study with a published method and sample, used only claim by claim and with short attributed quotes.")

with tab_verify:
    st.markdown("Offline verification re-derives every official value from the stored primary files and re-checks every study claim. "
                "Live verification re-downloads the sources and compares.")
    if st.button("Run offline verification", type="primary"):
        res_off = verify_offline()
        st.session_state["verify"] = res_off
    if st.button("Run live verification (downloads sources)"):
        with st.spinner("Fetching primary sources..."):
            try:
                st.session_state["verify"] = verify_offline() + verify_live()
            except Exception as exc:
                st.error(f"Live verification could not run: {exc}")
    checks = st.session_state.get("verify")
    if checks:
        st.dataframe(pd.DataFrame([{"Status": c.status, "Check": c.name, "Detail": c.detail} for c in checks]), hide_index=True, width="stretch")
        st.caption("DRIFT means the publisher changed a file or page since the snapshot: a new vintage to review, not an error.")

with tab_refused:
    st.markdown("Claims that were seen but not admitted, each with the reason and what would make it admissible. Most channel ROAS and CPM figures online fall here.")
    st.dataframe(reg.excluded, hide_index=True, width="stretch")
