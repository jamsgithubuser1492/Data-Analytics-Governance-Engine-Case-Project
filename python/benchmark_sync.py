"""Fetch primary benchmark sources, parse them, and build the registry tables with evidence.

Tier A (official data) is parsed straight from the publisher's file. Tier B (published studies)
is only admitted claim by claim: each claim has an anchor phrase, the verbatim quote is extracted
from the fetched page, and every number in the claim must appear in that quote. Anything that
cannot be verified is not admitted (see benchmarks/excluded_claims.csv).

CLI:  python python/benchmark_sync.py sync        # fetch live, rewrite benchmarks/
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmarks"
SNAP_DIR = BENCH_DIR / "snapshots"
UA = "Mozilla/5.0 (compatible; MMGE-benchmark-verifier/1.0)"

URLS = {
    "damodaran": "https://www.stern.nyu.edu/~adamodar/pc/datasets/margin.xls",
    "pep_states": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv",
    "pep_counties": "https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/counties/totals/co-est2025-alldata.csv",
    "census_ecom": "https://www.census.gov/retail/ecommerce.html",
    "haus": "https://www.haus.io/blog/the-meta-report-lessons-from-640-haus-incrementality-experiments",
    "gordon": "https://ideas.repec.org/a/inm/ormksc/v38y2019i2p193-225.html",
    "lewis": "https://ideas.repec.org/a/oup/qjecon/v130y2015i4p1941-1973.html",
    "littledata": "https://www.littledata.io/benchmarks",
}
FRED = {s: f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}" for s in ("RSXFS", "RSXFSN", "ECOMPCTSA", "ECOMSA")}
FRED_PAGES = {s: f"https://fred.stlouisfed.org/series/{s}" for s in FRED}


# ------------------------------------------------------------------------- fetching
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch(url: str, retries: int = 1, timeout: int = 60) -> Tuple[bytes, Dict[str, Any]]:
    """GET a URL with a polite user agent. Returns (bytes, meta). Raises on HTTP errors."""
    last: Optional[Exception] = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=min(timeout, 20)) as r:
                data = r.read()
                return data, {"url": url, "status": r.status, "bytes": len(data), "sha256": sha(data), "retrieved_at": now_iso(),
                              "last_modified": r.headers.get("Last-Modified")}
        except Exception as exc:  # network, 4xx, 5xx
            last = exc
            time.sleep(1.5 * (i + 1))
    # Some hosts (for example FRED) reset connections from custom clients; fall back to the system curl, as a person would.
    if shutil.which("curl"):
        try:
            res = subprocess.run(["curl", "-sS", "-L", "-f", "-m", str(timeout), url], capture_output=True, check=True)
            data = res.stdout
            return data, {"url": url, "status": 200, "bytes": len(data), "sha256": sha(data), "retrieved_at": now_iso(), "last_modified": None, "via": "curl"}
        except Exception as exc:
            last = f"{last}; curl: {exc}"
    raise RuntimeError(f"Could not fetch {url}: {last}")


def page_text(raw: bytes) -> str:
    """Visible text of an HTML page: scripts and tags removed, entities decoded, whitespace and quotes normalized."""
    t = raw.decode("utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return norm(t)


def norm(t: str) -> str:
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip()


_SENT_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z$\"(])")


def extract_quote(text: str, anchor: str, max_len: int = 320, start_at_anchor: bool = False) -> Optional[str]:
    """A verbatim, bounded quote around the first occurrence of ``anchor``; None if the anchor is absent.

    The quote starts at the beginning of the containing sentence, or at the anchor itself when
    ``start_at_anchor`` is set (used for titles and table rows that are not sentences). It ends at the
    sentence end or ``max_len`` characters, always on word boundaries (an ellipsis marks trimming).
    """
    i = text.find(anchor)
    if i < 0:
        return None
    if start_at_anchor:
        s = i
    else:
        starts = [m.end() for m in _SENT_BREAK.finditer(text[:i])]
        s = starts[-1] if starts else max(0, i - 120)
    m = _SENT_BREAK.search(text, i + len(anchor))
    e = m.start() if m else min(len(text), i + len(anchor) + 160)
    e = max(e, i + len(anchor))
    q = text[s:e].strip()
    if len(q) > max_len:
        lo = 0
        a = q.find(anchor)
        if a > max_len // 2:
            lo = a - (max_len - len(anchor)) // 2
        hi = lo + max_len
        if lo > 0:
            lo = q.find(" ", lo) + 1 or lo
        if hi < len(q):
            hi = q.rfind(" ", lo, hi) if q.rfind(" ", lo, hi) > lo else hi
        q = ("... " if lo > 0 else "") + q[lo:hi].strip() + (" ..." if hi < len(q) else "")
    return q


NUM = re.compile(r"\d[\d,]*\.?\d*")


def numbers_in(s: str) -> List[float]:
    out = []
    for m in NUM.finditer(s):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


# ------------------------------------------------------------------------- Tier A parsers
def parse_damodaran(raw: bytes) -> Tuple[pd.DataFrame, str]:
    """Industry margin table and the file's 'Date updated'."""
    x = pd.ExcelFile(io.BytesIO(raw))
    top = x.parse("Industry Averages", header=None, nrows=3)
    updated = str(pd.to_datetime(top.iloc[0, 1]).date())
    d = x.parse("Industry Averages", header=8)
    d = d[d["Industry Name"].notna() & d["Number of firms"].notna()].copy()
    keep = d[["Industry Name", "Number of firms", "Gross Margin", "Net Margin", "COGS/Sales"]].copy()
    keep.columns = ["industry", "n_firms", "gross_margin", "net_margin", "cogs_over_sales"]
    keep["industry"] = keep["industry"].astype(str).str.strip()
    return keep.reset_index(drop=True), updated


def parse_pep_states(raw: bytes) -> pd.DataFrame:
    s = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
    out = s[["SUMLEV", "STATE", "NAME", "POPESTIMATE2025"]].copy()
    out.columns = ["sumlev", "state_fips", "name", "pop_2025"]
    out["state_fips"] = out["state_fips"].astype(int).astype(str).str.zfill(2)
    return out


def parse_pep_counties(raw: bytes) -> pd.DataFrame:
    c = pd.read_csv(io.BytesIO(raw), encoding="latin-1")
    c = c[c["SUMLEV"] == 50]
    out = pd.DataFrame({"fips": c["STATE"].astype(int).astype(str).str.zfill(2) + c["COUNTY"].astype(int).astype(str).str.zfill(3),
                        "county": c["CTYNAME"], "state": c["STNAME"], "pop_2025": c["POPESTIMATE2025"].astype(int)})
    return out.reset_index(drop=True)


def parse_fred(raw: bytes) -> pd.DataFrame:
    f = pd.read_csv(io.BytesIO(raw))
    f.columns = ["date", "value"]
    f["value"] = pd.to_numeric(f["value"], errors="coerce")
    return f.dropna().reset_index(drop=True)


def seasonal_index(sa: pd.DataFrame, nsa: pd.DataFrame, first_year: int = 2021, last_year: int = 2025) -> pd.DataFrame:
    """Monthly NSA/SA ratio per calendar month over complete years; mean, min, max, years used."""
    m = sa.merge(nsa, on="date", suffixes=("_sa", "_nsa"))
    m["date"] = pd.to_datetime(m["date"])
    m = m[(m["date"].dt.year >= first_year) & (m["date"].dt.year <= last_year)]
    m["ratio"] = m["value_nsa"] / m["value_sa"]
    m["month"] = m["date"].dt.month
    g = m.groupby("month")["ratio"].agg(["mean", "min", "max", "count"]).reset_index()
    g.columns = ["month", "mean", "low", "high", "n_years"]
    return g


# ------------------------------------------------------------------------- curated Tier B claims
@dataclass
class Claim:
    claim_id: str
    source: str  # key in URLS
    metric_id: str
    anchor: str  # phrase that must appear in the page
    value: Optional[float]
    unit: str
    entity: str = ""  # what the number describes
    vertical: str = "general"
    channel: str = ""
    definition_class: str = ""
    definition: str = ""
    statistic: str = "reported"
    n: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    attribution_window: str = ""
    confidence: str = "medium"
    notes: str = ""
    check_numbers: Tuple[float, ...] = ()  # every one of these must appear in the quote
    check_text: Tuple[str, ...] = ()  # every one of these substrings must appear in the quote
    max_len: int = 320
    start_at_anchor: bool = False


HAUS_DEF_LIFT = "Lift in the brand's primary business KPI caused by Meta (percent), from Haus geo experiments. Not an iROAS and not an incrementality factor."
CLAIMS: List[Claim] = [
    Claim("HAUS_N_EXPERIMENTS", "haus", "study_n_experiments", "Insights from 640 Meta incrementality tests", 640, "count", "Haus Meta experiments", definition_class="study_size",
          definition="Number of Meta incrementality experiments analysed.", statistic="count", n=640, check_numbers=(640,), confidence="medium", max_len=110, start_at_anchor=True),
    Claim("HAUS_TEST_DAYS", "haus", "test_duration_days", "18.6 days", 18.6, "days", "Average Meta test, excluding post-treatment window", definition_class="design_parameter",
          definition="Average test length in days, excluding the post-treatment observation window.", statistic="mean", n=640, check_numbers=(18.6, 8.8, 27.4),
          notes="Total including the 8.8 day post-treatment window is about 27.4 days.", confidence="medium"),
    Claim("HAUS_PTW_DAYS", "haus", "post_treatment_window_days", "8.8-day post-treatment observation window", 8.8, "days", "Average post-treatment observation window", definition_class="design_parameter",
          definition="Average post-treatment observation window in days.", statistic="mean", n=640, check_numbers=(8.8, 27.4), confidence="medium"),
    Claim("HAUS_AVG_SPEND", "haus", "advertiser_annual_spend_usd", "$14 million annually", 14e6, "usd_per_year", "Average advertiser annual Meta spend", definition_class="study_population",
          definition="Average annual Meta spend of advertisers in the study.", statistic="mean", check_numbers=(14,), confidence="medium"),
    Claim("HAUS_META_LIFT", "haus", "meta_lift_primary_kpi_pct", "drove on average", 19.0, "pct", "Meta", channel="Meta Ads", definition_class="lift_pct_on_primary_kpi",
          definition=HAUS_DEF_LIFT, statistic="mean", n=640, check_numbers=(19,), confidence="medium",
          notes="Reported as about 19% (the page uses an approximation sign). Do not compare with iROAS or incrementality factors."),
    Claim("HAUS_IF_MID", "haus", "if_multiplier_vs_lower_funnel", "Below are the average ratios between the incrementality factors", 1.3, "ratio", "Mid-funnel optimization", channel="Meta Ads",
          definition_class="incrementality_factor_ratio", definition="Average ratio of the incrementality factor of this tactic to lower-funnel campaigns, calibrated on a 7-day click, 1-day view window.",
          statistic="mean", attribution_window="7-day click, 1-day view", check_numbers=(1.3,), confidence="medium", max_len=420, start_at_anchor=True),
    Claim("HAUS_IF_TRAFFIC", "haus", "if_multiplier_vs_lower_funnel", "Below are the average ratios between the incrementality factors", 2.4, "ratio", "Traffic optimization", channel="Meta Ads",
          definition_class="incrementality_factor_ratio", definition="Average ratio of the incrementality factor of this tactic to lower-funnel campaigns, calibrated on a 7-day click, 1-day view window.",
          statistic="mean", attribution_window="7-day click, 1-day view", check_numbers=(2.4,), confidence="medium", max_len=420, start_at_anchor=True),
    Claim("HAUS_IF_REACH", "haus", "if_multiplier_vs_lower_funnel", "Below are the average ratios between the incrementality factors", 6.0, "ratio", "Reach and awareness optimization", channel="Meta Ads",
          definition_class="incrementality_factor_ratio", definition="Average ratio of the incrementality factor of this tactic to lower-funnel campaigns, calibrated on a 7-day click, 1-day view window.",
          statistic="mean", attribution_window="7-day click, 1-day view", check_numbers=(6.0,), confidence="medium", max_len=420, start_at_anchor=True),
    Claim("HAUS_ADVPLUS_IROAS", "haus", "advantage_plus_vs_manual_diroas_pct", "Advantage+ drove 12% lower DTC iROAS", -12.0, "pct", "Advantage+ vs Manual", channel="Meta Ads",
          definition_class="relative_iroas_difference", definition="Average difference in DTC-only incremental ROAS of Advantage+ campaigns versus Manual campaigns.", statistic="mean",
          check_numbers=(12, 18), confidence="medium"),
    Claim("HAUS_IF_DEFINITION", "haus", "definition_incrementality_factor", "An incrementality factor (IF) is the ratio", None, "text", "Definition", definition_class="definition",
          definition="Incrementality factor: incremental sales a channel drives divided by sales reported in-platform (here on a 7-day click, 1-day view window).", statistic="definition",
          check_text=("ratio between the amount of incremental sales",), confidence="medium"),
    Claim("GORDON_N_EXPERIMENTS", "gordon", "study_n_experiments", "15 U.S. advertising experiments", 15, "count", "Facebook field experiments", definition_class="study_size",
          definition="Number of U.S. advertising randomized experiments at Facebook in the study.", statistic="count", n=15, check_numbers=(15, 500, 1.6), confidence="high",
          notes="Peer reviewed (Marketing Science, 2019). Abstract quoted."),
    Claim("GORDON_FINDING", "gordon", "finding_observational_vs_rct", "The observational methods often fail to produce the same effects", None, "text", "Observational vs randomized",
          definition_class="qualitative", definition="Observational methods often fail to reproduce the effects measured by randomized experiments, even with extensive controls. The abstract does not state a direction of bias.",
          statistic="qualitative", n=15, confidence="high", notes="Do not describe this as 'overestimation': the abstract does not say that."),
    Claim("LEWIS_N_EXPERIMENTS", "lewis", "study_n_experiments", "Twenty-five large field experiments", 25, "count", "Retail and brokerage field experiments", definition_class="study_size",
          definition="Number of large field experiments with major U.S. retailers and brokerages.", statistic="count", n=25, check_text=("Twenty-five",), confidence="high", notes="Peer reviewed (QJE, 2015). Abstract quoted.", start_at_anchor=True),
    Claim("LEWIS_ROI_CI", "lewis", "roi_ci_width_pp_median", "The median confidence interval on return on investment is over 100 percentage points wide", None, "pp", "ROI estimates from experiments",
          low=100.0, definition_class="uncertainty", definition="Median width of the confidence interval on ROI across the experiments: over 100 percentage points (a lower bound).", statistic="lower_bound", n=25,
          check_numbers=(100,), confidence="high"),
    Claim("LEWIS_CV", "lewis", "individual_sales_cv", "a coefficient of variation of 10 is common", 10.0, "ratio", "Individual-level sales", definition_class="uncertainty",
          definition="Coefficient of variation of individual-level sales relative to per-capita ad cost; 10 is described as common.", statistic="typical", n=25, check_numbers=(10,), confidence="high"),
    Claim("LEWIS_PERSON_WEEKS", "lewis", "required_person_weeks", "can easily require more than 10 million person-weeks", None, "person_weeks", "Informative advertising experiments",
          low=10e6, definition_class="uncertainty", definition="Informative advertising experiments can easily require more than 10 million person-weeks (a lower bound).", statistic="lower_bound", n=25,
          check_numbers=(10,), confidence="high"),
    Claim("LITTLEDATA_N_STORES", "littledata", "study_n_stores", "from 421 Shopify stores", 421, "count", "Shopify stores in the benchmark", definition_class="study_size",
          definition="Stores meeting inclusion rules: Littledata users with GA4, at least 1,000 sessions and 90 purchases in 90 days.", statistic="count", n=421, check_numbers=(421,), confidence="medium"),
    Claim("LITTLEDATA_CVR_ALL", "littledata", "site_cvr_median_pct", "1.4% Median conversion rate", 1.4, "pct", "All Shopify stores", vertical="ecommerce_all", definition_class="site_session_conversion",
          definition="Median share of website sessions that included at least one purchase (session-based, site-wide, all traffic). Not a paid-ad click conversion rate.", statistic="median", n=421,
          check_numbers=(1.4,), confidence="medium", max_len=120, start_at_anchor=True),
    Claim("LITTLEDATA_AOV_ALL", "littledata", "site_aov_median_usd", "$110 Median average order value", 110.0, "usd", "All Shopify stores", vertical="ecommerce_all", definition_class="site_aov",
          definition="Median average order value across stores, USD.", statistic="median", n=421, check_numbers=(110,), confidence="medium", max_len=110, start_at_anchor=True),
    Claim("LITTLEDATA_CVR_FASHION", "littledata", "site_cvr_median_pct", "Fashion & Apparel 69 1.3% $98", 1.3, "pct", "Fashion & Apparel", vertical="fashion_apparel", definition_class="site_session_conversion",
          definition="Median site session conversion rate for Fashion & Apparel stores.", statistic="median", n=69, check_numbers=(69, 1.3, 98), confidence="medium", max_len=100, start_at_anchor=True),
    Claim("LITTLEDATA_AOV_FASHION", "littledata", "site_aov_median_usd", "Fashion & Apparel 69 1.3% $98", 98.0, "usd", "Fashion & Apparel", vertical="fashion_apparel", definition_class="site_aov",
          definition="Median average order value for Fashion & Apparel stores, USD.", statistic="median", n=69, check_numbers=(69, 1.3, 98), confidence="medium", max_len=100, start_at_anchor=True),
    Claim("LITTLEDATA_CVR_HOME", "littledata", "site_cvr_median_pct", "Home & Furniture 54 0.8% $239", 0.8, "pct", "Home & Furniture", vertical="home_furniture", definition_class="site_session_conversion",
          definition="Median site session conversion rate for Home & Furniture stores.", statistic="median", n=54, check_numbers=(54, 0.8, 239), confidence="medium", max_len=100, start_at_anchor=True),
    Claim("LITTLEDATA_AOV_HOME", "littledata", "site_aov_median_usd", "Home & Furniture 54 0.8% $239", 239.0, "usd", "Home & Furniture", vertical="home_furniture", definition_class="site_aov",
          definition="Median average order value for Home & Furniture stores, USD.", statistic="median", n=54, check_numbers=(54, 0.8, 239), confidence="medium", max_len=100, start_at_anchor=True),
    Claim("LITTLEDATA_CVR_BEAUTY", "littledata", "site_cvr_median_pct", "Beauty & Skincare 33 2.6% $66", 2.6, "pct", "Beauty & Skincare", vertical="beauty_skincare", definition_class="site_session_conversion",
          definition="Median site session conversion rate for Beauty & Skincare stores.", statistic="median", n=33, check_numbers=(33, 2.6, 66), confidence="low", max_len=100, notes="Only 33 stores (the minimum to publish).", start_at_anchor=True),
    Claim("LITTLEDATA_AOV_BEAUTY", "littledata", "site_aov_median_usd", "Beauty & Skincare 33 2.6% $66", 66.0, "usd", "Beauty & Skincare", vertical="beauty_skincare", definition_class="site_aov",
          definition="Median average order value for Beauty & Skincare stores, USD.", statistic="median", n=33, check_numbers=(33, 2.6, 66), confidence="low", max_len=100, notes="Only 33 stores.", start_at_anchor=True),
    Claim("LITTLEDATA_CVR_HEALTH", "littledata", "site_cvr_median_pct", "Health & Supplements 33 2.5% $76", 2.5, "pct", "Health & Supplements", vertical="health_supplements", definition_class="site_session_conversion",
          definition="Median site session conversion rate for Health & Supplements stores.", statistic="median", n=33, check_numbers=(33, 2.5, 76), confidence="low", max_len=100, notes="Only 33 stores.", start_at_anchor=True),
    Claim("LITTLEDATA_AOV_HEALTH", "littledata", "site_aov_median_usd", "Health & Supplements 33 2.5% $76", 76.0, "usd", "Health & Supplements", vertical="health_supplements", definition_class="site_aov",
          definition="Median average order value for Health & Supplements stores, USD.", statistic="median", n=33, check_numbers=(33, 2.5, 76), confidence="low", max_len=100, notes="Only 33 stores.", start_at_anchor=True),
]

SOURCES: Dict[str, Dict[str, str]] = {
    "DAMODARAN_MARGINS": dict(publisher="Aswath Damodaran, NYU Stern", title="Operating and Net Margins: Margins by Sector (US)", url=URLS["damodaran"], kind="official_dataset",
                              license_note="Free to download; cite the author. Aggregates of US publicly traded companies.", reliability="A", key="damodaran"),
    "CENSUS_PEP_2025": dict(publisher="U.S. Census Bureau", title="Vintage 2025 Population Estimates (state and county totals)", url=URLS["pep_states"], kind="official_dataset",
                            license_note="U.S. Government public domain.", reliability="A", key="pep_states"),
    "CENSUS_ECOM": dict(publisher="U.S. Census Bureau", title="Quarterly Retail E-Commerce Sales", url=URLS["census_ecom"], kind="official_dataset",
                        license_note="U.S. Government public domain.", reliability="A", key="census_ecom"),
    "FRED_RETAIL": dict(publisher="Federal Reserve Bank of St. Louis (FRED), series from U.S. Census Bureau", title="Retail trade and e-commerce series (RSXFS, RSXFSN, ECOMPCTSA, ECOMSA)",
                        url="https://fred.stlouisfed.org/", kind="official_dataset", license_note="Census sourced series; cite FRED and the Census Bureau.", reliability="A", key="fred"),
    "HAUS_META_REPORT": dict(publisher="Haus", title="The Meta Report: Lessons from 640 Haus Incrementality Experiments", url=URLS["haus"], kind="vendor_study",
                             license_note="Vendor marketing content. Short quotes with attribution only; do not redistribute.", reliability="B", key="haus"),
    "GORDON_2019": dict(publisher="Marketing Science (Gordon, Zettelmeyer, Bhargava, Chapsky)", title="A Comparison of Approaches to Advertising Measurement: Evidence from Big Field Experiments at Facebook",
                        url=URLS["gordon"], kind="peer_reviewed", license_note="Abstract quoted from the RePEc index page.", reliability="A", key="gordon"),
    "LEWIS_RAO_2015": dict(publisher="Quarterly Journal of Economics (Lewis, Rao)", title="The Unfavorable Economics of Measuring the Returns to Advertising", url=URLS["lewis"], kind="peer_reviewed",
                           license_note="Abstract quoted from the RePEc index page.", reliability="A", key="lewis"),
    "LITTLEDATA_BENCHMARKS": dict(publisher="Littledata", title="Shopify benchmarks (421 stores)", url=URLS["littledata"], kind="vendor_study",
                                  license_note="Vendor marketing content. Short quotes with attribution only.", reliability="B", key="littledata"),
}


# ------------------------------------------------------------------------- the build
VALUE_COLUMNS = ["value_id", "tier", "source_id", "metric_id", "entity", "vertical", "channel", "geography", "as_of", "value", "low", "high", "unit",
                 "n", "statistic", "definition_class", "definition", "attribution_window", "quote", "evidence_ref", "verification", "confidence", "notes"]


class SyncError(RuntimeError):
    pass


def _fred_title(raw: bytes) -> str:
    m = re.search(r"<title>(.*?)</title>", raw.decode("utf-8", errors="ignore"), re.S | re.I)
    return norm(html.unescape(m.group(1))) if m else ""


def build(live: bool = True, dest: Path = BENCH_DIR) -> Dict[str, Any]:
    """Fetch every source, verify, and rewrite sources.csv, values.csv, evidence.json and snapshots.

    Raises SyncError if a Tier A reconciliation fails. Tier B claims that fail verification are
    not admitted and are listed under ``rejected`` in evidence.json.
    """
    if not live:
        raise SyncError("Offline rebuild is done by benchmark_verify.rebuild_from_snapshots")
    snap = dest / "snapshots"
    snap.mkdir(parents=True, exist_ok=True)
    evidence: Dict[str, Any] = {"generated_at": now_iso(), "sources": {}, "checks": [], "rejected": []}
    rows: List[Dict[str, Any]] = []

    def ev(key: str, meta: Dict[str, Any], **extra: Any) -> str:
        evidence["sources"][key] = {**meta, **extra}
        return key

    def check(name: str, ok: bool, detail: str) -> None:
        evidence["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            raise SyncError(f"Verification failed: {name}: {detail}")

    # ---- Damodaran
    raw, meta = fetch(URLS["damodaran"])
    (snap / "damodaran_margin.xls").write_bytes(raw)
    dam, updated = parse_damodaran(raw)
    check("damodaran_gm_equals_1_minus_cogs", ((dam["gross_margin"] - (1 - dam["cogs_over_sales"])).abs() < 1e-9).all(), "gross margin = 1 - COGS/sales for every industry")
    check("damodaran_total_market_present", (dam["industry"] == "Total Market").any(), "Total Market row present")
    check("damodaran_ranges", dam["gross_margin"].between(-1, 1).all() and dam["net_margin"].between(-5, 1).all(), "margins within plausible ranges")
    tm = dam[dam["industry"] == "Total Market"].iloc[0]
    ref = ev("damodaran", meta, snapshot="snapshots/damodaran_margin.xls", date_updated=updated, industries=int(len(dam)), total_firms=int(tm["n_firms"]))
    for i, r in dam.iterrows():
        for metric, col, label in (("gross_margin_aggregate", "gross_margin", "Gross margin"), ("net_margin_aggregate", "net_margin", "Net margin")):
            rows.append(dict(value_id=f"DAM_{metric}_{i:03d}", tier="A", source_id="DAMODARAN_MARGINS", metric_id=metric, entity=r["industry"], vertical="industry:" + r["industry"],
                             geography="US", as_of=updated, value=round(float(r[col]), 6), unit="ratio", n=int(r["n_firms"]), statistic="aggregate", definition_class="aggregate_public_company_margin",
                             definition=f"{label} of the industry: aggregated across US publicly traded companies in the group (not a single brand, not DTC specific).",
                             evidence_ref=ref, verification="parsed from publisher file; gross margin = 1 - COGS/sales; ranges checked", confidence="high",
                             notes="Public company aggregate. Treat gross margin as an upper bound on a brand's contribution margin."))

    # ---- Census population
    raw_s, meta_s = fetch(URLS["pep_states"])
    raw_c, meta_c = fetch(URLS["pep_counties"])
    (snap / "census_pep2025_states.csv").write_bytes(raw_s)
    states, counties = parse_pep_states(raw_s), parse_pep_counties(raw_c)
    counties.to_csv(snap / "census_pep2025_counties.csv", index=False)
    us_total = int(states[states["sumlev"] == 10]["pop_2025"].iloc[0])
    st = states[states["sumlev"] == 40]
    st_ex_pr = st[st["state_fips"] != "72"]["pop_2025"].sum()
    check("pep_states_sum_to_us", int(st_ex_pr) == us_total, f"50 states + DC sum {int(st_ex_pr)} vs US total {us_total} (Puerto Rico is reported separately and excluded from the US total)")
    check("pep_counties_sum_to_states", int(counties["pop_2025"].sum()) == int(st_ex_pr), f"counties {int(counties['pop_2025'].sum())} vs states {int(st_ex_pr)}")
    check("pep_county_count", len(counties) >= 3100, f"{len(counties)} county rows")
    ev("pep_states", meta_s, snapshot="snapshots/census_pep2025_states.csv")
    ev("pep_counties", meta_c, snapshot="snapshots/census_pep2025_counties.csv", derived_rows=int(len(counties)))
    rows.append(dict(value_id="PEP_US_POP_2025", tier="A", source_id="CENSUS_PEP_2025", metric_id="us_population", entity="United States", vertical="general", geography="US", as_of="2025-07-01",
                     value=us_total, unit="people", statistic="estimate", definition_class="population_estimate",
                     definition="Census Bureau Vintage 2025 resident population estimate (July 1, 2025): 50 states and DC (Puerto Rico is reported separately).", evidence_ref="pep_states",
                     verification="50 states + DC sum to the US total; county rows sum to the same total", confidence="high"))

    # ---- FRED + Census e-commerce
    fred: Dict[str, pd.DataFrame] = {}
    for sid, url in FRED.items():
        raw_f, meta_f = fetch(url)
        (snap / f"fred_{sid}.csv").write_bytes(raw_f)
        fred[sid] = parse_fred(raw_f)
        page, _pmeta = fetch(FRED_PAGES[sid])
        ev(f"fred_{sid}", meta_f, snapshot=f"snapshots/fred_{sid}.csv", series_page_title=_fred_title(page))
    raw_e, meta_e = fetch(URLS["census_ecom"])
    ecom_text = page_text(raw_e)
    q_pct = extract_quote(ecom_text, "accounted for 17.1 percent of total sales") or extract_quote(ecom_text, "percent of total sales")
    q_lvl = extract_quote(ecom_text, "was $340.2 billion")
    check("census_text_found", bool(q_pct and q_lvl), "Census page contains the quarterly e-commerce sentences")
    last = fred["ECOMPCTSA"].iloc[-1]
    last_sa = fred["ECOMSA"].iloc[-1]
    check("census_vs_fred_pct", f"{last['value']:.1f} percent" in q_pct, f"FRED ECOMPCTSA latest {last['value']} appears in Census text")
    check("census_vs_fred_level", abs(last_sa["value"] / 1000 - 340.2) < 0.06 and "340.2" in q_lvl, f"FRED ECOMSA latest {last_sa['value']} million vs Census text $340.2 billion")
    check("fred_dates_agree", fred["ECOMPCTSA"]["date"].iloc[-1] == fred["ECOMSA"]["date"].iloc[-1], "ECOMPCTSA and ECOMSA end on the same quarter")
    ev("census_ecom", meta_e, text_sha256=sha(ecom_text.encode()))
    rows.append(dict(value_id="CENSUS_ECOM_PCT_LATEST", tier="A", source_id="CENSUS_ECOM", metric_id="ecommerce_share_of_retail_pct", entity="U.S. retail", vertical="general", geography="US",
                     as_of=str(last["date"]), value=float(last["value"]), unit="pct", statistic="seasonally_adjusted", definition_class="ecommerce_share",
                     definition="E-commerce sales as a percent of total retail sales, seasonally adjusted (Census Quarterly Retail E-Commerce Report).", quote=q_pct, evidence_ref="census_ecom",
                     verification="Census page text matches FRED ECOMPCTSA latest observation", confidence="high", notes="Context only: the national share, not an advertiser benchmark."))
    rows.append(dict(value_id="CENSUS_ECOM_SALES_LATEST", tier="A", source_id="CENSUS_ECOM", metric_id="ecommerce_sales_usd", entity="U.S. retail", vertical="general", geography="US",
                     as_of=str(last_sa["date"]), value=float(last_sa["value"]) * 1e6, unit="usd", statistic="seasonally_adjusted", definition_class="ecommerce_sales",
                     definition="Quarterly e-commerce sales, adjusted for seasonal variation but not price changes.", quote=q_lvl, evidence_ref="census_ecom",
                     verification="Census page text ($340.2 billion) matches FRED ECOMSA to rounding", confidence="high"))
    idx = seasonal_index(fred["RSXFS"], fred["RSXFSN"])
    check("seasonal_index_complete", len(idx) == 12 and (idx["n_years"] == 5).all(), "12 months x 5 years")
    check("seasonal_index_mean_near_one", abs(idx["mean"].mean() - 1.0) < 0.02, f"mean of monthly ratios {idx['mean'].mean():.4f}")
    check("seasonal_index_range", idx["mean"].between(0.8, 1.25).all(), "monthly ratios within 0.8 to 1.25")
    for _, r in idx.iterrows():
        rows.append(dict(value_id=f"FRED_RETAIL_SEAS_M{int(r['month']):02d}", tier="A", source_id="FRED_RETAIL", metric_id="retail_seasonal_index", entity=f"month {int(r['month']):02d}",
                         vertical="general", geography="US", as_of="2021-01 to 2025-12", value=round(float(r["mean"]), 5), low=round(float(r["low"]), 5), high=round(float(r["high"]), 5),
                         unit="ratio", n=int(r["n_years"]), statistic="mean_of_years", definition_class="nsa_over_sa_ratio",
                         definition="Not seasonally adjusted divided by seasonally adjusted U.S. retail trade sales (FRED RSXFSN / RSXFS) for this calendar month, 2021 to 2025 (low and high are the min and max year).",
                         evidence_ref="fred_RSXFS", verification="ratio of two Census series; 12 months x 5 years; mean of ratios near 1", confidence="high",
                         notes="Macro retail seasonality, not specific to any advertiser or channel."))

    # ---- Tier B
    texts: Dict[str, str] = {}
    for key in ("haus", "gordon", "lewis", "littledata"):
        raw_p, meta_p = fetch(URLS[key])
        texts[key] = page_text(raw_p)
        ev(key, meta_p, text_sha256=sha(texts[key].encode()), text_chars=len(texts[key]))
    for c in CLAIMS:
        q = extract_quote(texts[c.source], c.anchor, c.max_len, c.start_at_anchor)
        problems: List[str] = []
        if not q:
            problems.append("anchor phrase not found on the page")
        else:
            nums = numbers_in(q)
            for want in c.check_numbers:
                if not any(abs(want - got) < 1e-9 for got in nums):
                    problems.append(f"number {want} not in the quote")
            for want_t in c.check_text:
                if want_t not in q:
                    problems.append(f"text '{want_t}' not in the quote")
            if c.value is not None and not c.check_text and c.unit != "usd_per_year" and c.metric_id != "advantage_plus_vs_manual_diroas_pct":
                if not any(abs(abs(c.value) - got) < 1e-9 for got in nums):
                    problems.append(f"value {c.value} not in the quote")
        if problems:
            evidence["rejected"].append({"claim_id": c.claim_id, "source": c.source, "problems": problems, "quote": q})
            continue
        sid = next(k for k, v in SOURCES.items() if v["key"] == c.source)
        rows.append(dict(value_id=c.claim_id, tier="B", source_id=sid, metric_id=c.metric_id, entity=c.entity, vertical=c.vertical, channel=c.channel, geography="US",
                         as_of="", value=c.value, low=c.low, high=c.high, unit=c.unit, n=c.n, statistic=c.statistic, definition_class=c.definition_class, definition=c.definition,
                         attribution_window=c.attribution_window, quote=q, evidence_ref=c.source, verification="verbatim quote extracted from the fetched primary page; numbers matched",
                         confidence=c.confidence, notes=c.notes))
    sources = []
    for sid, s in SOURCES.items():
        e = evidence["sources"].get(s["key"]) or evidence["sources"].get("fred_RSXFS", {})
        sources.append(dict(source_id=sid, publisher=s["publisher"], title=s["title"], url=s["url"], kind=s["kind"], license_note=s["license_note"], reliability=s["reliability"],
                            retrieved_at=e.get("retrieved_at", ""), content_sha256=e.get("sha256", e.get("text_sha256", ""))))
    df = pd.DataFrame(rows).reindex(columns=VALUE_COLUMNS)
    df.to_csv(dest / "values.csv", index=False)
    pd.DataFrame(sources).to_csv(dest / "sources.csv", index=False)
    (dest / "evidence.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    manifest = {"version": registry_version(dest), "values": int(len(df)), "built_at": evidence["generated_at"], "rejected_claims": len(evidence["rejected"])}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"values": len(df), "rejected": evidence["rejected"], "checks": evidence["checks"], "version": manifest["version"]}


def registry_version(dest: Path = BENCH_DIR) -> str:
    """Short hash over the registry files; stamped on every run that uses it."""
    h = hashlib.sha256()
    p = dest / "values.csv"  # content only: retrieval timestamps must not change the version
    if p.exists():
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd != "sync":
        sys.exit("usage: python python/benchmark_sync.py sync")
    out = build(live=True)
    print(f"Registry v{out['version']}: {out['values']} verified values")
    for c in out["checks"]:
        print(("PASS " if c["ok"] else "FAIL ") + c["name"] + ": " + c["detail"])
    for r in out["rejected"]:
        print("REJECTED", r["claim_id"], r["problems"])
