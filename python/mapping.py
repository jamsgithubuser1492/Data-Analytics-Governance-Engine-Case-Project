"""Upload reading, column mapping suggestions and value standardization.

A mapping is only ever a proposal: each suggestion carries a confidence score and
anything below ``CONFIRM_BELOW`` must be confirmed by a person. Ambiguous values are
never silently coerced; they become empty and the validation layer blocks the run.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from schemas import SCHEMAS

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ROWS = 1_000_000
CONFIRM_BELOW = 0.90
FUZZY_MIN = 0.62

SYNONYMS: Dict[str, Dict[str, List[str]]] = {
    "RAW_PLATFORM_DATA": {
        "date": ["day", "reporting starts", "report date", "date start", "dt"],
        "channel": ["platform", "network", "source", "publisher", "media channel"],
        "campaign_id": ["campaign", "campaign name", "campaign id", "cmp", "campaign_name"],
        "spend": ["cost", "amount spent", "spend usd", "ad spend", "total cost", "cost usd"],
        "impressions": ["impr", "imps", "views"],
        "clicks": ["link clicks", "all clicks", "click"],
        "reported_conversions": ["conversions", "purchases", "results", "conv", "all conv", "platform conversions"],
        "reported_revenue": ["revenue", "purchase value", "conversion value", "conv value", "sales", "platform revenue"],
    },
    "RAW_MTA_OUTPUT": {
        "date": ["day", "report date"], "channel": ["platform", "network", "source"],
        "campaign_id": ["campaign", "campaign name", "campaign id"],
        "mta_attributed_conversions": ["mta conversions", "attributed conversions", "conversions", "mta conv"],
        "mta_attributed_revenue": ["mta revenue", "attributed revenue", "revenue"],
        "mta_attribution_weight": ["weight", "attribution weight"], "model_version": ["model", "version"],
    },
    "RAW_HOLDOUT_DATA": {
        "date": ["day", "report date"], "experiment_id": ["experiment", "test id", "test"],
        "campaign_id": ["campaign", "campaign name", "campaign id"],
        "geo_or_cohort_id": ["geo", "region", "market", "dma", "cohort"],
        "group_type": ["group", "arm", "cell", "test group"],
        "treatment_flag": ["treatment", "is treatment", "test flag", "exposed"],
        "population_size": ["population", "pop"], "conversions": ["orders", "purchases", "conv"],
        "revenue": ["sales", "value", "order value"],
    },
    "BUSINESS_BENCHMARKS": {"channel": ["platform", "network"]},
}

TOTAL_PAT = re.compile(r"^\s*(grand\s+)?totals?\b|^\s*sum\s*$|^\s*all campaigns\s*$", re.I)


class UploadError(ValueError):
    """Raised for unreadable or oversized uploads, with a plain language message."""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


# ----------------------------------------------------------------------- reading
def read_table_file(data: bytes, filename: str, sheet: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Parse a CSV or XLSX upload into a string DataFrame with detected header, encoding and delimiter."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    info: Dict[str, Any] = {"filename": filename}
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            book = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
        except Exception as exc:
            raise UploadError(f"Could not open the Excel file: {exc}") from exc
        info["sheets"] = book.sheet_names
        info["sheet"] = sheet or book.sheet_names[0]
        raw = book.parse(info["sheet"], header=None, dtype=str)
    elif name.endswith((".csv", ".tsv", ".txt")):
        text, info["encoding"] = None, None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text, info["encoding"] = data.decode(enc), enc
                break
            except UnicodeDecodeError:
                continue
        sample = "\n".join(text.splitlines()[:20])
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
        info["delimiter"] = delim
        try:
            raw = pd.read_csv(io.StringIO(text), sep=delim, header=None, dtype=str, skip_blank_lines=True,
                              on_bad_lines="skip", engine="python")
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
            raise UploadError("The file is empty or could not be read as a table.") from exc
    else:
        raise UploadError("Unsupported file type. Upload a .csv or .xlsx file.")
    if len(raw) > MAX_ROWS:
        raise UploadError(f"File has more than {MAX_ROWS:,} rows.")
    raw = raw.dropna(how="all").reset_index(drop=True)
    if raw.empty:
        raise UploadError("The file is empty.")
    counts = raw.notna().sum(axis=1)
    header_idx = int(next(i for i, c in counts.items() if c >= max(2, 0.6 * counts.max())))
    header = [str(h).strip() if pd.notna(h) else f"unnamed_{i}" for i, h in enumerate(raw.iloc[header_idx])]
    seen: Dict[str, int] = {}
    dups = []
    for i, h in enumerate(header):
        if h in seen:
            seen[h] += 1
            dups.append(h)
            header[i] = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
    info["header_row"], info["duplicate_headers"] = header_idx, dups
    df = raw.iloc[header_idx + 1:].reset_index(drop=True)
    df.columns = header
    return df, info


# --------------------------------------------------------------------- suggestions
@dataclass
class Suggestion:
    source: str
    target: Optional[str]
    confidence: float
    reason: str

    @property
    def needs_confirmation(self) -> bool:
        return self.target is not None and self.confidence < CONFIRM_BELOW


def suggest_mapping(table: str, columns: List[str]) -> List[Suggestion]:
    """Propose source column -> canonical field; each target is used at most once."""
    fields = [f.name for f in SCHEMAS[table]]
    syn = SYNONYMS.get(table, {})
    cands: List[Tuple[float, str, str, str]] = []
    for col in columns:
        n = _norm(col)
        for f in fields:
            if n == _norm(f):
                cands.append((1.0, col, f, "exact match"))
            elif n in {_norm(s) for s in syn.get(f, [])}:
                cands.append((0.95, col, f, "known synonym"))
            else:
                best = max([SequenceMatcher(None, n, _norm(x)).ratio() for x in [f, *syn.get(f, [])]])
                if best >= FUZZY_MIN:
                    cands.append((round(best * 0.9, 3), col, f, f"similar name ({best:.0%})"))
    taken_t, taken_s, out = set(), set(), []
    for conf, col, f, why in sorted(cands, key=lambda x: -x[0]):
        if col in taken_s or f in taken_t:
            continue
        taken_s.add(col), taken_t.add(f)
        out.append(Suggestion(col, f, conf, why))
    out += [Suggestion(c, None, 0.0, "no match; kept as an extra column") for c in columns if c not in taken_s]
    return sorted(out, key=lambda s: columns.index(s.source))


def missing_required(table: str, mapping: Dict[str, Optional[str]]) -> List[str]:
    """Required canonical fields that no source column maps to."""
    used = {t for t in mapping.values() if t}
    return [f.name for f in SCHEMAS[table] if f.required and f.name not in used]


# ------------------------------------------------------------------- standardizing
def detect_total_rows(df: pd.DataFrame) -> List[int]:
    """Row indexes that look like totals or notes (first text cell says Total, or an id column is empty)."""
    idx = []
    for i, row in df.iterrows():
        cells = [str(v) for v in row.values if pd.notna(v)]
        if any(TOTAL_PAT.match(c) for c in cells[:3]):
            idx.append(i)
    return idx


_CUR = re.compile(r"[^\d,.\-()%\s]")


def parse_number(value: Any, decimal: str = ".") -> float:
    """Parse a localized number string. Returns NaN when empty or ambiguous (never guesses)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return float("nan")
    if isinstance(value, (int, float, np.number)):
        return float(value)
    s = str(value).strip()
    if not s:
        return float("nan")
    neg = s.startswith("(") and s.endswith(")")
    pct = s.endswith("%")
    s = _CUR.sub("", s).replace("(", "").replace(")", "").replace("%", "").replace(" ", "")
    if s.startswith("-"):
        neg, s = True, s[1:]
    if decimal == ".":
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?", s):
            s = s.replace(",", "")
        else:
            return float("nan")  # e.g. '1,5' under a '.' decimal declaration is ambiguous
    else:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?|\d+(,\d+)?", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            return float("nan")
    val = float(s)
    val = val / 100 if pct else val
    return -val if neg else val


def parse_date(value: Any, order: str = "ymd", tz: Optional[str] = None) -> Any:
    """Parse a date using the declared order; Excel serials and offset timestamps are handled."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value).strip() == "":
        return pd.NaT
    s = str(value).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", s):  # Excel serial date
        return (pd.Timestamp("1899-12-30") + pd.to_timedelta(float(s), unit="D")).normalize()
    try:
        if re.search(r"(Z|[+-]\d{2}:?\d{2})$", s):  # timestamp with offset: convert to the declared zone
            ts = pd.Timestamp(s)
            return (ts.tz_convert(tz) if tz else ts.tz_convert("UTC")).tz_localize(None).normalize()
        if re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}.*", s):
            return pd.Timestamp(pd.to_datetime(s, errors="raise")).normalize()
        if order in ("mdy", "dmy") and re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", s):
            return pd.Timestamp(pd.to_datetime(s, dayfirst=(order == "dmy"), errors="raise")).normalize()
        return pd.NaT  # unrecognized or order undeclared: do not guess
    except (ValueError, TypeError):
        return pd.NaT


@dataclass
class MappedTable:
    data: pd.DataFrame
    extras: pd.DataFrame
    excluded_rows: int = 0
    notes: List[str] = field(default_factory=list)


def apply_mapping(df: pd.DataFrame, table: str, mapping: Dict[str, Optional[str]],
                  declarations: Optional[Dict[str, Any]] = None, exclude_rows: Optional[List[int]] = None) -> MappedTable:
    """Rename, clean and type the columns of ``df`` into the canonical schema."""
    decl = declarations or {}
    decimal, order, tz = decl.get("decimal_separator", "."), decl.get("date_order", "ymd"), decl.get("timezone")
    notes: List[str] = []
    work = df.drop(index=exclude_rows or [], errors="ignore").reset_index(drop=True)
    mapped = {s: t for s, t in mapping.items() if t}
    out = pd.DataFrame({t: work[s] for s, t in mapped.items() if s in work.columns})
    extras = work[[c for c in work.columns if c not in mapped]].copy()
    for f in SCHEMAS[table]:
        if f.name not in out.columns:
            continue
        if f.kind == "date":
            out[f.name] = out[f.name].map(lambda v: parse_date(v, order, tz)).dt.strftime("%Y-%m-%d")
        elif f.kind in ("int", "float"):
            out[f.name] = out[f.name].map(lambda v: parse_number(v, decimal))
            if f.kind == "int":
                out[f.name] = out[f.name].round().astype("Int64") if out[f.name].notna().all() else out[f.name]
        else:
            out[f.name] = out[f.name].astype("string").str.strip()
    if decl.get("spend_unit") == "cents" and "spend" in out.columns:
        out["spend"] = out["spend"] / 100.0
        notes.append("Spend divided by 100 (declared in cents).")
    if "channel" in out.columns and decl.get("channel_aliases"):
        alias = {_norm(k): v for k, v in decl["channel_aliases"].items()}
        out["channel"] = out["channel"].map(lambda v: alias.get(_norm(v), v) if pd.notna(v) else v)
        notes.append("Channel names normalized using your alias table.")
    return MappedTable(out, extras, len(df) - len(work), notes)


def template_csv(table: str, demo: Optional[pd.DataFrame] = None) -> str:
    """CSV text with the canonical header and (when given) three example rows."""
    cols = [f.name for f in SCHEMAS[table]]
    frame = demo[cols].head(3) if demo is not None else pd.DataFrame(columns=cols)
    return frame.to_csv(index=False)
