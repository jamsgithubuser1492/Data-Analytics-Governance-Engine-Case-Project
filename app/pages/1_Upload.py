"""Guided onboarding: upload, map, validate, preview and run."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DEMO_NOTICE, demo_mode, demo_tables, get_runner, get_store, identity, page_setup, safe_page_link, wait_for_run  # noqa: E402

page_setup("Upload",":material/upload:")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

import ui  # noqa: E402

from mapping import (UploadError, apply_mapping, detect_total_rows, missing_required, read_table_file,  # noqa: E402
                     suggest_mapping, template_csv)
from pipeline import SourceTables, ValidationBlocked  # noqa: E402
from schemas import SCHEMAS  # noqa: E402
from validation import validate_inputs  # noqa: E402

store, runner = get_store(), get_runner()
actor, ws = identity()
settings, decl, cfg_version = store.latest_workspace_config(ws)
decl = {"currency": "USD", "timezone": "UTC", "spend_unit": "dollars", "decimal_separator": ".", "date_order": "ymd",
        "channel_aliases": {}, **decl}

LABELS = {"RAW_PLATFORM_DATA": ("Platform data", "Daily spend, clicks and conversions as reported by each ad platform."),
          "RAW_MTA_OUTPUT": ("Attribution model output", "Daily conversions your multi touch attribution (MTA) model credits to each campaign."),
          "RAW_HOLDOUT_DATA": ("Holdout experiment", "Daily conversions for the control and treatment geos of your holdout test."),
          "BUSINESS_BENCHMARKS": ("Business benchmarks", "Expected return, conversion rate and incrementality ranges per channel (optional context, never used to score without a verified source).")}
demo = demo_tables().as_dict()
uploads = st.session_state.setdefault("uploads", {})

ui.page_head("Onboarding", "Bring your data", "Five guided steps with plain-language checks and row-level examples. Nothing runs until every blocker is fixed and every warning is acknowledged.")
if demo_mode():
    ui.callout("Uploading is switched off on the public demo so nobody shares company files on a public server. " + DEMO_NOTICE + " To use your own data, run the app on your own computer (see the README).")
    safe_page_link("app.py", "Back to the Dashboard", ":material/analytics:")
    st.stop()
STEPS = ["Declare", "Upload", "Map columns", "Validate and preview", "Confirm and run"]
step_slot = st.empty()


def at_step(n: int) -> None:
    with step_slot.container():
        ui.stepper(STEPS, n)


at_step(2)

with st.container(border=True):
    st.markdown("**Step 1. Declare** (how your files are written)")
    st.write(f"Currency **{decl['currency']}** · Timezone **{decl['timezone']}** · Spend in **{decl['spend_unit']}** · "
             f"Decimal **'{decl['decimal_separator']}'** · Dates **{decl['date_order']}** · Settings version {cfg_version or 'defaults'}")
    safe_page_link("pages/3_Settings.py", "Change declarations or policy", ":material/tune:")

st.markdown("**Step 2. Upload your four files**")
from verify_data import all_verified  # noqa: E402

c_demo, c_gen = st.columns(2)
with c_demo:
    if st.button("Use the verified demo data (the original case study files)", width="stretch"):
        st.session_state["uploads"] = {t: (df.astype(str), {"filename": "demo", "demo": True}) for t, df in demo.items()}
        st.rerun()
    st.caption("Verified: the files match the recorded checksums." if all_verified() else "Notice: the case study files in data/ differ from the verified originals. Restore them with git checkout -- data/ for a repeatable result.")
with c_gen, st.popover("Generate new synthetic data", width="stretch"):
    st.caption("Optional. Creates a fresh synthetic dataset in memory for experiments. It never replaces the verified case study files, and the same seed always gives the same data.")
    seed = st.number_input("Random seed", 0, 1_000_000, 7, 1, key="gen_seed")
    if st.button("Generate and load", key="gen_go"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data"))
        from generate_synthetic_data import generate_all_data
        names_ = ["RAW_PLATFORM_DATA", "RAW_MTA_OUTPUT", "RAW_HOLDOUT_DATA", "BUSINESS_BENCHMARKS"]
        st.session_state["uploads"] = {n: (df.astype(str), {"filename": f"synthetic data, seed {int(seed)}", "demo": True}) for n, df in zip(names_, generate_all_data(int(seed)))}
        st.rerun()
for table, (title, blurb) in LABELS.items():
    with st.expander(f"{title}" + (" (uploaded)" if table in uploads else ""), expanded=table not in uploads):
        st.caption(blurb)
        st.download_button("Download template", template_csv(table, demo[table]), f"{table}_template.csv", key=f"tpl_{table}")
        f = st.file_uploader(f"{title} file (CSV or Excel)", type=["csv", "tsv", "txt", "xlsx"], key=f"up_{table}")
        if f is not None:
            try:
                data = f.getvalue()
                sheet = None
                if f.name.lower().endswith((".xlsx", ".xlsm")):
                    names = pd.ExcelFile(f).sheet_names
                    sheet = st.selectbox("Sheet", names, key=f"sh_{table}") if len(names) > 1 else names[0]
                uploads[table] = read_table_file(data, f.name, sheet)
            except UploadError as exc:
                st.error(str(exc))
        if table in uploads:
            df, info = uploads[table]
            st.success(f"{len(df):,} rows, {len(df.columns)} columns read from {info['filename']}"
                       + (f" (header found on row {info['header_row'] + 1})" if info.get("header_row") else ""))
            if info.get("duplicate_headers"):
                st.warning(f"Duplicate column names were renamed: {info['duplicate_headers']}")

# ------------------------------------------------------------------ optional audience layer
audience_ok = True
st.session_state["aud_attach"] = None
with st.expander("Optional: add audience tier data (aggregate files only)"):
    st.caption("Shows which audience tiers are paying for sales that would have happened anyway. Aggregate counts only: one row per day, campaign and tier, one sales series per market, "
               "and one audience mix per market. Files with person level or personal columns are refused.")
    from audience_tiers import load_demo_audience, validate_audience
    from schemas import AUDIENCE_SCHEMAS, AUDIENCE_TABLES
    use_demo_aud = st.checkbox("Use the synthetic example audience data that ships with the project", key="aud_demo")
    aud_frames = {}
    if use_demo_aud:
        aud_frames = load_demo_audience()
    else:
        for name in AUDIENCE_TABLES:
            cols = st.columns([3, 1])
            up = cols[0].file_uploader(name.replace("_", " ").capitalize(), type=["csv"], key=f"up_{name}")
            cols[1].download_button("Template", pd.DataFrame(columns=[f.name for f in AUDIENCE_SCHEMAS[name]]).to_csv(index=False), f"{name}_template.csv", key=f"tp_{name}")
            if up is not None:
                aud_frames[name] = pd.read_csv(up)
    if aud_frames:
        if len(aud_frames) < len(AUDIENCE_TABLES):
            st.warning("Add all three audience files, or none.")
            audience_ok = False
        else:
            arep = validate_audience(aud_frames, settings)
            for i in arep.blockers:
                st.markdown(f"**Blocker.** **{i.rule}** ({i.table}): {i.message}")
            for i in arep.warnings:
                st.markdown(f"**Warning.** **{i.rule}** ({i.table}): {i.message}")
            audience_ok = arep.ok
            if arep.ok:
                st.success("The audience files passed the checks and will be included in the run.")
                st.session_state["aud_attach"] = aud_frames

if len(uploads) < 4:
    st.info(f"Upload all four files to continue ({len(uploads)} of 4 ready). No files handy? Use the demo data above, or download a template for each file.")
    st.stop()

# ------------------------------------------------------------------------ mapping
at_step(3)
st.markdown("**Step 3. Check the column mapping**")
mapped_tables, mapping_ok, all_extras = {}, True, {}
for table, (title, _) in LABELS.items():
    df, info = uploads[table]
    fields = [f.name for f in SCHEMAS[table]]
    saved = store.get_mapping_profile(ws, table)
    sugg = suggest_mapping(table, list(df.columns))
    chosen, confirmed = {}, True
    with st.expander(f"{title}: mapping", expanded=info.get("demo") is None):
        use_saved = bool(saved) and st.checkbox(f"Use my saved mapping profile (v{saved['version']})", key=f"sv_{table}") if saved else False
        for s in sugg:
            default = (saved["mapping"].get(s.source) if use_saved and s.source in saved["mapping"] else s.target)
            options = ["(ignore)"] + fields
            c1, c2, c3 = st.columns([3, 3, 3])
            c1.write(f"**{s.source}**")
            pick = c2.selectbox(f"Maps to {s.source}", options, index=options.index(default) if default in options else 0,
                                key=f"map_{table}_{s.source}", label_visibility="collapsed")
            chosen[s.source] = None if pick == "(ignore)" else pick
            label = f"{s.confidence:.0%} · {s.reason}" if s.target else s.reason
            c3.caption(("Confirm: " if s.needs_confirmation else "") + label)
            if chosen[s.source] and chosen[s.source] != s.target and not use_saved and s.target is None:
                c3.caption("Chosen by you")
        low = [s.source for s in sugg if s.needs_confirmation and chosen.get(s.source) == s.target]
        if low:
            confirmed = st.checkbox(f"I confirm the low confidence matches: {', '.join(low)}", key=f"cf_{table}")
        miss = missing_required(table, chosen)
        if miss:
            st.error(f"Required fields not mapped: {miss}")
        totals = detect_total_rows(df)
        exclude = []
        if totals:
            st.warning(f"{len(totals)} row(s) look like totals or notes (for example row {totals[0] + 1}).")
            if st.checkbox("Exclude them", value=True, key=f"tot_{table}"):
                exclude = totals
        if st.button("Save as my mapping profile", key=f"sp_{table}"):
            store.save_mapping_profile(ws, table, chosen)
            st.toast("Mapping profile saved.")
    if miss or not confirmed:
        mapping_ok = False
        continue
    m = apply_mapping(df, table, chosen, decl, exclude)
    mapped_tables[table], all_extras[table] = m, m.extras
    for n in m.notes:
        st.caption(f"{title}: {n}")
if not mapping_ok:
    st.warning("Finish the mapping above to continue.")
    st.stop()

# --------------------------------------------------------------------- validation
at_step(4)
st.markdown("**Step 4. Validate and preview**")
tables = SourceTables(*(mapped_tables[t].data for t in LABELS))
report = validate_inputs(tables.platform, tables.mta, tables.holdout, tables.benchmarks, settings, decl)
if report.blockers:
    st.error(f"{len(report.blockers)} blocker(s) must be fixed before a run can start.")
for i in report.blockers:
    st.markdown(f"**Blocker.** **{i.rule}** ({i.table}): {i.message}")
    if i.examples:
        st.code(str(i.examples))
for i in report.warnings:
    st.markdown(f"**Warning.** **{i.rule}** ({i.table}): {i.message}")
    if i.examples:
        st.caption(f"Examples: {i.examples}")
if report.ok and not report.warnings:
    st.success("No issues found.")
if report.coverage:
    c1, c2 = st.columns(2)
    c1.metric("Attribution model coverage of platform campaigns", f"{report.coverage.get('mta', 0):.0%}")
    c2.metric("Holdout coverage of platform campaigns", f"{report.coverage.get('holdout', 0):.0%}")
if any(len(e.columns) for e in all_extras.values()):
    st.caption("Extra columns kept aside, not used in the analysis: " + "; ".join(f"{t}: {list(e.columns)}" for t, e in all_extras.items() if len(e.columns)))

# ------------------------------------------------------------------------ preview
with st.expander("Preview: your row next to what the engine understood"):
    src, std = uploads["RAW_PLATFORM_DATA"][0].head(3), tables.platform.head(3)
    st.write("Your platform file (first rows)"), st.dataframe(src, hide_index=True)
    st.write("Standardized"), st.dataframe(std, hide_index=True)

# --------------------------------------------------------------------------- run
at_step(5)
st.markdown("**Step 5. Confirm and run**")
ack = True
if report.warnings:
    ack = st.checkbox("I have read the warnings above and want to continue", key="ack")
label = st.text_input("Name this run", value="Uploaded data")
if st.button("Run measurement", type="primary", disabled=bool(report.blockers) or not ack or not audience_ok):
    try:
        tables.audience = st.session_state.get("aud_attach")
        rid = runner.submit(ws, tables, settings, decl, label)
        status = wait_for_run(ws, rid)
        if status == "succeeded":
            st.success("Run complete. Open the Dashboard page to see the results.")
            safe_page_link("app.py", "Open the dashboard", ":material/analytics:")
        else:
            st.error(f"The run failed: {store.get_run(ws, rid)['error']}")
    except ValidationBlocked as exc:
        st.error(str(exc))
