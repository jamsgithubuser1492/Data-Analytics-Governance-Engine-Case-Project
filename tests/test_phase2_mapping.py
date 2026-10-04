"""Phase 2 tests: messy uploads through reading, mapping, standardizing, validation and the pipeline."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from mapping import (UploadError, apply_mapping, detect_total_rows, missing_required, parse_date, parse_number,  # noqa: E402
                     read_table_file, suggest_mapping, template_csv)
from pipeline import SourceTables, run_pipeline  # noqa: E402
from validation import validate_inputs  # noqa: E402

DEMO = SourceTables.from_directory()
PLAT = "RAW_PLATFORM_DATA"
META_NAMES = {"date": "Day", "channel": "Platform", "campaign_id": "Campaign name", "spend": "Amount spent",
              "impressions": "Impressions", "clicks": "Link clicks", "reported_conversions": "Results",
              "reported_revenue": "Purchase value"}


def eu(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def messy_platform_csv() -> bytes:
    p = DEMO.platform.copy()
    p["date"] = pd.to_datetime(p["date"]).dt.strftime("%d/%m/%Y")
    p["spend"], p["reported_revenue"] = p["spend"].map(eu), p["reported_revenue"].map(eu)
    p = p.rename(columns=META_NAMES)
    body = p.to_csv(index=False, sep=";")
    total = "Total;;;999.999,00;1;1;1;1\n"
    return ("Exported from Ads Manager;;;;;;;\nGenerated 2026-04-01;;;;;;;\n" + body + total).encode("latin-1")


def map_all(df, table=PLAT, decl=None, **kw):
    sugg = suggest_mapping(table, list(df.columns))
    mapping = {s.source: s.target for s in sugg}
    return apply_mapping(df, table, mapping, decl, **kw), sugg, mapping


# ---------------------------------------------------------------- reading
def test_messy_csv_is_read_with_header_delimiter_and_encoding() -> None:
    df, info = read_table_file(messy_platform_csv(), "export.csv")
    assert info["delimiter"] == ";" and info["header_row"] == 2 and info["encoding"] in ("utf-8", "latin-1", "utf-8-sig")
    assert list(df.columns)[:3] == ["Day", "Platform", "Campaign name"] and len(df) == 721


def test_xlsx_with_notes_rows_and_sheet_choice() -> None:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"a": ["x"]}).to_excel(w, sheet_name="Notes", index=False)
        top = pd.DataFrame([["Report", None, None], [None, None, None]])
        top.to_excel(w, sheet_name="Data", index=False, header=False)
        DEMO.platform.head(5).rename(columns=META_NAMES).to_excel(w, sheet_name="Data", index=False, startrow=2)
    df, info = read_table_file(buf.getvalue(), "m.xlsx", sheet="Data")
    assert info["sheets"] == ["Notes", "Data"] and len(df) == 5 and "Amount spent" in df.columns


def test_duplicate_headers_and_bad_files() -> None:
    df, info = read_table_file(b"a,a,b\n1,2,3\n", "d.csv")
    assert list(df.columns) == ["a", "a_1", "b"] and info["duplicate_headers"] == ["a"]
    for data, name in ((b"", "e.csv"), (b"x", "e.pdf")):
        with pytest.raises(UploadError):
            read_table_file(data, name)
    with pytest.raises(UploadError):
        read_table_file(b"x" * (51 * 1024 * 1024), "big.csv")


# ------------------------------------------------------------- suggestions
def test_suggestions_have_confidence_and_one_target_each() -> None:
    sugg = suggest_mapping(PLAT, list(META_NAMES.values()) + ["Notes", "Spend (alt)"])
    targets = [s.target for s in sugg if s.target]
    assert len(targets) == len(set(targets)) and {s.source: s.target for s in sugg}["Amount spent"] == "spend"
    notes = next(s for s in sugg if s.source == "Notes")
    assert notes.target is None
    fuzzy = next(s for s in suggest_mapping(PLAT, ["Impresions"]) if s.source == "Impresions")
    assert fuzzy.target == "impressions" and fuzzy.needs_confirmation  # typo match needs a person to confirm


def test_missing_required_reported() -> None:
    assert missing_required(PLAT, {"Day": "date"}) and "spend" in missing_required(PLAT, {"Day": "date"})
    assert missing_required(PLAT, {s: t for s, t in zip(META_NAMES.values(), META_NAMES)}) == []


# ---------------------------------------------------------------- parsing
@pytest.mark.parametrize("raw,dec,expected", [("$1,234.50", ".", 1234.5), ("1.234,50", ",", 1234.5), ("(12.00)", ".", -12.0),
                                              ("12%", ".", 0.12), ("1,5", ".", None), ("abc", ".", None), ("", ".", None),
                                              ("1.5", ",", None), ("€ 3.000,25", ",", 3000.25)])
def test_parse_number(raw, dec, expected) -> None:
    v = parse_number(raw, dec)
    assert (pd.isna(v) if expected is None else v == pytest.approx(expected))


def test_parse_date_rules() -> None:
    assert parse_date("2026-02-03") == pd.Timestamp("2026-02-03")
    assert parse_date("03/04/2026", "dmy") == pd.Timestamp("2026-04-03")
    assert parse_date("03/04/2026", "mdy") == pd.Timestamp("2026-03-04")
    assert pd.isna(parse_date("03/04/2026", "ymd"))  # ambiguous and undeclared: never guessed
    assert parse_date("46000") == pd.Timestamp("2025-12-09")  # Excel serial
    assert parse_date("2026-01-05T23:30:00-08:00", tz="UTC") == pd.Timestamp("2026-01-06")  # converted to declared zone
    assert pd.isna(parse_date("not a date"))


# -------------------------------------------------------- end to end messy
def test_messy_platform_round_trips_to_demo_numbers() -> None:
    raw, _ = read_table_file(messy_platform_csv(), "export.csv")
    totals = detect_total_rows(raw)
    assert len(totals) == 1
    mapped, _, _ = map_all(raw, decl={"decimal_separator": ",", "date_order": "dmy"}, exclude_rows=totals)
    assert mapped.excluded_rows == 1 and len(mapped.data) == 720
    pd.testing.assert_frame_equal(mapped.data.reset_index(drop=True)[["date", "channel", "campaign_id"]],
                                  DEMO.platform[["date", "channel", "campaign_id"]], check_dtype=False)
    assert mapped.data["spend"].sum() == pytest.approx(DEMO.platform["spend"].sum(), abs=0.5)
    rep = validate_inputs(mapped.data, DEMO.mta, DEMO.holdout, DEMO.benchmarks)
    assert rep.ok, [i.message for i in rep.blockers]


def test_totals_row_left_in_is_caught_by_validation() -> None:
    raw, _ = read_table_file(messy_platform_csv(), "export.csv")
    mapped, _, _ = map_all(raw, decl={"decimal_separator": ",", "date_order": "dmy"})  # user forgot to exclude it
    rep = validate_inputs(mapped.data, DEMO.mta, DEMO.holdout, DEMO.benchmarks)
    assert not rep.ok  # the Total row has no valid date or campaign


def test_wrong_declarations_never_pass_silently() -> None:
    raw, _ = read_table_file(messy_platform_csv(), "export.csv")
    totals = detect_total_rows(raw)
    for decl in ({"decimal_separator": ".", "date_order": "dmy"}, {"decimal_separator": ",", "date_order": "ymd"}):
        mapped, _, _ = map_all(raw, decl=decl, exclude_rows=totals)
        assert not validate_inputs(mapped.data, DEMO.mta, DEMO.holdout, DEMO.benchmarks).ok


def test_cents_declaration_and_channel_aliases() -> None:
    p = DEMO.platform.copy()
    p["spend"] = (p["spend"] * 100).round()
    p["channel"] = p["channel"].replace({"Meta Ads": "facebook"})
    mapped, _, _ = map_all(p.astype(str), decl={"spend_unit": "cents", "channel_aliases": {"facebook": "Meta Ads"}})
    assert mapped.data["spend"].sum() == pytest.approx(DEMO.platform["spend"].sum(), abs=1.0)
    assert set(mapped.data["channel"]) == set(DEMO.platform["channel"]) and len(mapped.notes) == 2


def test_extra_columns_are_kept_not_dropped() -> None:
    p = DEMO.platform.head(10).astype(str).assign(Notes="x", Owner="y")
    mapped, _, _ = map_all(p)
    assert list(mapped.extras.columns) == ["Notes", "Owner"] and "Notes" not in mapped.data.columns


def test_messy_upload_runs_full_pipeline() -> None:
    raw, _ = read_table_file(messy_platform_csv(), "export.csv")
    mapped, _, _ = map_all(raw, decl={"decimal_separator": ",", "date_order": "dmy"}, exclude_rows=detect_total_rows(raw))
    res = run_pipeline(SourceTables(mapped.data, DEMO.mta, DEMO.holdout, DEMO.benchmarks))
    assert res.tables["GOVERNANCE_AUDIT_SUMMARY"]["total_spend"].sum() == pytest.approx(748140.42, abs=1.0)


def test_template_round_trips_through_mapping() -> None:
    csv_text = template_csv(PLAT, DEMO.platform)
    df, _ = read_table_file(csv_text.encode(), "t.csv")
    sugg = suggest_mapping(PLAT, list(df.columns))
    assert all(s.confidence == 1.0 for s in sugg) and not missing_required(PLAT, {s.source: s.target for s in sugg})
