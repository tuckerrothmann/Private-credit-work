"""
BDC Portfolio & Borrower Collector
====================================
Downloads BDC 10-K / 10-Q filings from EDGAR, parses the Schedule of
Investments (SOI), and builds a cross-fund borrower / issuer database.

Key outputs
-----------
data/portfolio_cache/{TICKER}_{period}.json   -- per-fund per-period SOI
data/borrower_db.json                         -- cross-fund issuer index

Cross-fund analysis reveals
---------------------------
- Issuers present in 3+ BDC portfolios (systemic risk if they deteriorate)
- Issuers on non-accrual at multiple lenders simultaneously
- PIK borrowers that appear across multiple funds
- Fair value vs cost trends by issuer (unrealized loss escalation)
- Sector concentration stress

Usage
-----
    python portfolio_collector.py --ticker PNNT          # collect one fund
    python portfolio_collector.py --all --max-filings 2  # whole universe, 2 most-recent
    python portfolio_collector.py --analyze              # run cross-fund analysis
    python portfolio_collector.py --borrower "Company X" # search by issuer name
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import csv
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import os

try:
    from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
    import warnings
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
    _BS4_OK = True
except ImportError:
    _BS4_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDGAR_BASE   = "https://data.sec.gov"
EDGAR_FILING = "https://www.sec.gov"
HEADERS      = {"User-Agent": "private-research/1.0 jroth@example.com"}
RATE_DELAY   = 0.15   # sec between EDGAR API calls

PORTFOLIO_CACHE = Path("data/portfolio_cache")
BORROWER_DB     = Path("data/borrower_db.json")
UNIVERSE_PATH   = Path("data/bdc_universe.json")
PROCESSED_DIR   = Path("data/processed")
BORROWER_WATCHLIST = PROCESSED_DIR / "borrower_watchlist.csv"
BORROWER_FAMILY_WATCHLIST = PROCESSED_DIR / "borrower_family_watchlist.csv"
BORROWER_FAMILY_ALIASES = Path("data/borrower_family_aliases.json")
BORROWER_FAMILY_MERGE_CANDIDATES = PROCESSED_DIR / "borrower_family_merge_candidates.csv"
BORROWER_FAMILY_SPLIT_CANDIDATES = PROCESSED_DIR / "borrower_family_split_candidates.csv"

# SOI section headers we search for in filing HTML
SOI_HEADINGS = [
    "schedule of investments",
    "consolidated schedule of investments",
    "condensed consolidated schedule of investments",
    "schedule of portfolio investments",
    # NOTE: "portfolio of investments" intentionally omitted — too broad,
    # matches descriptive prose like "changes in the value of our portfolio of investments"
]

# Column header patterns → standardised field name
COL_PATTERNS = {
    # "investment" removed — a column labeled "Investment" maps to invest_type, not issuer.
    # "company" added (bare word, start-anchored) for filings like OBDC that use "Company".
    r"portfolio\s*company|issuer|borrower|company\s*name|\bcompany\b": "issuer",
    r"industry|sector|type\s*of\s*business":                           "industry",
    # "^investment$" added so a bare "Investment" or "Investments" column → invest_type
    r"investment\s*type|security\s*type|asset\s*type|^investments?$|^type$": "invest_type",
    r"interest\s*rate|rate|coupon|spread":                            "rate_str",
    r"maturity|due\s*date|expiry":                                    "maturity",
    r"principal|par|face\s*amount|notional":                          "par_str",
    r"amortized\s*cost|cost\s*basis|cost":                            "cost_str",
    r"fair\s*value|value|fmv":                                        "fv_str",
    r"% of net assets|%\s*of\s*nav|%\s*net\s*assets|%\s*of\s*total": "pct_nav_str",
    # Dedicated footnote column (e.g. FSK which uses "Footnotes" as a column header)
    r"^footnotes?$":                                                   "footnote_col",
}


# ---------------------------------------------------------------------------
# Investment record
# ---------------------------------------------------------------------------

@dataclass
class Investment:
    fund_ticker:    str
    period:         str       # "2025-09-30"
    filing_type:    str       # "10-K" / "10-Q"

    issuer:         str  = ""
    industry:       str  = ""
    invest_type:    str  = ""     # "Senior Secured", "Subordinated", "Equity", …
    rate_str:       str  = ""     # raw rate string e.g. "SOFR+5.50% (PIK)"
    maturity:       str  = ""
    par_str:        str  = ""
    cost_str:       str  = ""
    fv_str:         str  = ""
    pct_nav_str:    str  = ""
    footnote_col:   str  = ""     # raw text of dedicated footnote column (e.g. FSK "(ac)(v)(z)")

    # Derived
    cost_mm:        Optional[float] = None   # cost in $M
    fv_mm:          Optional[float] = None   # fair value in $M
    pct_nav:        Optional[float] = None   # % of net assets
    is_pik:         bool = False
    is_non_accrual: bool = False
    is_equity:      bool = False
    rate_base:      str  = ""    # "SOFR" / "LIBOR" / "Fixed"
    spread_bps:     Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

_LAST_REQUEST: float = 0.0


def _fetch(url: str, binary: bool = False, timeout: int = 30) -> Any:
    global _LAST_REQUEST
    wait = RATE_DELAY - (time.time() - _LAST_REQUEST)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    _LAST_REQUEST = time.time()
    if binary:
        return data
    return data.decode("utf-8", errors="replace")


def _fetch_json(url: str, cache_path: Optional[Path] = None, ttl_hours: int = 24) -> dict:
    if cache_path and cache_path.exists():
        age = (datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime))
        if age < timedelta(hours=ttl_hours):
            return json.loads(cache_path.read_text(encoding="utf-8"))
    raw = _fetch(url)
    data = json.loads(raw)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# EDGAR submission / filing index helpers
# ---------------------------------------------------------------------------

def _get_submissions(cik: str) -> dict:
    padded = cik.zfill(10)
    url = f"{EDGAR_BASE}/submissions/CIK{padded}.json"
    cache = PORTFOLIO_CACHE / f"_sub_{padded}.json"
    return _fetch_json(url, cache, ttl_hours=12)


def _get_recent_10kq(cik: str, n: int = 3) -> list[dict]:
    """Return the n most-recent 10-K and 10-Q filings with accession info."""
    subs = _get_submissions(cik)
    filings = subs.get("filings", {}).get("recent", {})
    forms   = filings.get("form", [])
    dates   = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    report_dates = filings.get("reportDate", [])

    results = []
    for i, form in enumerate(forms):
        if form in ("10-K", "10-Q"):
            results.append({
                "form":       form,
                "filed":      dates[i] if i < len(dates) else "",
                "period":     report_dates[i] if i < len(report_dates) else dates[i],
                "accession":  accessions[i].replace("-", ""),
                "accession_fmt": accessions[i],
                "primary_doc":   primary_docs[i] if i < len(primary_docs) else "",
            })
        if len(results) >= n:
            break
    return results


def _filing_index_url(cik: str, accession: str) -> str:
    padded = cik.zfill(10)
    acc_fmt = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    return f"{EDGAR_FILING}/cgi-bin/browse-edgar?action=getcompany&CIK={padded}&type=10-K&dateb=&owner=include&count=10"


def _primary_doc_url(cik: str, accession: str, primary_doc: str) -> str:
    padded = cik.zfill(10)
    acc_slash = accession  # already stripped of dashes
    return f"{EDGAR_FILING}/Archives/edgar/data/{int(padded)}/{acc_slash}/{primary_doc}"


def _get_filing_index(cik: str, accession: str) -> list[dict]:
    """Fetch the filing index JSON from EDGAR to find all documents."""
    padded = cik.zfill(10)
    acc_fmt = f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    url = f"{EDGAR_BASE}/submissions/CIK{padded}.json"  # already cached
    # Use the index endpoint instead
    idx_url = f"{EDGAR_FILING}/Archives/edgar/data/{int(padded)}/{accession}/index.json"
    try:
        raw = _fetch(idx_url)
        data = json.loads(raw)
        return data.get("directory", {}).get("item", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# HTML Schedule-of-Investments parser
# ---------------------------------------------------------------------------

def _clean_num(s: str) -> Optional[float]:
    """Parse numeric string like '(1,234.5)' or '$1.2' → float in millions.

    SEC filings often express amounts in $thousands or $millions.
    We return the raw numeric value; caller must scale.
    """
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").replace("\xa0", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _detect_scale(html_text: str) -> float:
    """Detect the $ scale factor used in the SOI table (thousands vs millions vs dollars)."""
    # Look for "(in thousands)" or "(in millions)" near SOI section
    low = html_text.lower()
    if "in thousands" in low:
        return 0.001   # divide by 1000 to get millions
    if "in millions" in low:
        return 1.0
    # Some filings (e.g. FSK equity section) report in actual dollars — detected
    # heuristically when "in dollars" or "dollar amounts" appears
    if "in dollar" in low or "dollar amounts" in low:
        return 0.000001  # actual dollars → millions
    # Default assumption: most BDC SOIs express in thousands
    return 0.001


def _map_col_headers(headers: list[str]) -> dict[int, str]:
    """Map column indices to standardised field names."""
    mapping: dict[int, str] = {}
    for i, h in enumerate(headers):
        h_clean = h.lower().strip()
        for pattern, field_name in COL_PATTERNS.items():
            if re.search(pattern, h_clean):
                if field_name not in mapping.values():  # first match wins
                    mapping[i] = field_name
                break
    # Col-0 override: in SOI tables, column 0 is always the portfolio-company/issuer column.
    # Some funds use "Investments" (e.g. SCM) or "Investments (1)(19)" (e.g. BXSL) as the
    # col-0 header.  The bare "Investments" accidentally maps to invest_type via ^investments?$
    # while the footnoted variant goes unmapped.  Both should be treated as the issuer column.
    if headers:
        h0 = headers[0].lower().strip() if headers else ""
        if re.match(r'investments?\b', h0) and "type" not in h0 and "activity" not in h0:
            # Regardless of whether col 0 was mapped to invest_type or not mapped at all,
            # override to issuer when the header starts with "investment(s)".
            mapping[0] = "issuer"
    return mapping


def _recalibrate_col_map(col_map: dict[int, str], data_rows: list[list[str]]) -> dict[int, str]:
    """Shift numeric column pointers if the header-mapped positions are consistently empty.

    Some iXBRL filings use merged header cells that span multiple <td> columns while
    the data rows fill them with individual cells — causing a systematic off-by-N offset
    for cost/fv/par/maturity columns.  This function samples up to 10 data rows and, for
    each mapped numeric field, searches adjacent columns (+1, +2, +3) if the mapped
    position is empty in most rows.
    """
    NUMERIC_FIELDS = ("par_str", "cost_str", "fv_str")
    DATE_FIELDS    = ("maturity",)

    sample = [r for r in data_rows[:30] if len([c for c in r if c.strip()]) >= 3][:10]
    if not sample:
        return col_map

    new_map = dict(col_map)
    changed_cols: set[int] = set()  # positions already reassigned

    def _score(idx: int, field: str) -> int:
        vals = [r[idx] if idx < len(r) else "" for r in sample]
        if field in DATE_FIELDS:
            return sum(1 for v in vals if re.search(r'\d{1,2}[/\-]\d{1,4}', v))
        return sum(1 for v in vals if _clean_num(v) is not None)

    for field in NUMERIC_FIELDS + DATE_FIELDS:
        # Find where this field currently sits in new_map
        col_idx = next((k for k, v in new_map.items() if v == field), None)

        if col_idx is not None and col_idx in changed_cols:
            continue  # already moved — don't move it again

        if col_idx is None:
            # Field was displaced when a prior field was remapped to this position.
            # Use the original col_map position as the search anchor.
            col_idx = next((k for k, v in col_map.items() if v == field), None)
            if col_idx is None:
                continue
            current_score = 0  # displaced: treat original position as score 0
        else:
            current_score = _score(col_idx, field)
            if current_score >= len(sample) * 0.25:
                continue  # good enough — no recalibration needed

        # Search adjacent columns (wider range for Workiva iXBRL with many empty spacer cells)
        # fv_str is allowed to displace pct_nav_str from its position — FV is essential;
        # pct_nav is optional and the two often share the same header-row column index in
        # filings (e.g. TCPC) where FairValue and "% of Total" are adjacent with a
        # dollar-sign spacer cell causing a systematic +N offset only in data rows.
        _DISPLACEABLE = {"pct_nav_str"}
        best_idx, best_score = col_idx, current_score
        for offset in (1, 2, 3, 4, -1, -2):
            alt = col_idx + offset
            if alt < 0 or alt in changed_cols:
                continue
            if alt in new_map and not (field == "fv_str" and new_map[alt] in _DISPLACEABLE):
                continue
            s = _score(alt, field)
            if s > best_score:
                best_score, best_idx = s, alt

        if best_idx != col_idx and best_score > current_score:
            # Remove old mapping only if it still belongs to this field
            if col_idx in new_map and new_map.get(col_idx) == field:
                del new_map[col_idx]
            # If displacing a lower-priority field (e.g. pct_nav_str), remove it first
            if best_idx in new_map and new_map[best_idx] in _DISPLACEABLE:
                del new_map[best_idx]
            new_map[best_idx] = field
            changed_cols.add(best_idx)

    return new_map


def _parse_rate(rate_str: str) -> tuple[str, Optional[int], bool]:
    """Extract base rate, spread in bps, and PIK flag from rate string."""
    s = rate_str.lower()
    is_pik = "pik" in s or "payment-in-kind" in s or "payment in kind" in s
    base = ""
    spread_bps = None

    if "sofr" in s:
        base = "SOFR"
    elif "libor" in s:
        base = "LIBOR"
    elif "prime" in s:
        base = "Prime"
    else:
        base = "Fixed"

    # Extract spread: look for "+ X.XX" or "X.XX%" patterns
    spread_match = re.search(r'\+\s*([\d.]+)\s*%', s)
    if spread_match:
        try:
            spread_bps = round(float(spread_match.group(1)) * 100)
        except ValueError:
            pass

    return base, spread_bps, is_pik


def _is_non_accrual(row_text: str, na_footnote_marks: set[str] | None = None) -> bool:
    low = row_text.lower()
    if any(x in low for x in ["non-accrual", "non accrual", "nonaccrual"]):
        return True
    # Check against fund-specific footnote markers (e.g. "(1)", "(a)")
    if na_footnote_marks:
        for mark in na_footnote_marks:
            if mark in row_text:
                return True
    return False


def _extract_footnote_legend(soup: BeautifulSoup, soi_tag: Tag,
                             html_text: str = "") -> dict[str, str]:
    """Extract footnote legend from the SOI section.

    Returns {marker: meaning} e.g. {"(7)": "non-accrual", "(2)": "PIK"}.

    Uses three strategies in order of reliability:
    1. Span-sibling scan on the full soup: finds <span>(N)</span> where the
       parent element's text is just the marker + definition (iXBRL style).
    2. Regex on raw HTML text after the SOI heading (inline definitions).
    3. Tag-based scan with larger limit (fallback for traditional HTML).
    """
    legend: dict[str, str] = {}

    # ── Strategy 1: span-sibling pattern (handles iXBRL inline footnotes) ──
    # In iXBRL filings the legend looks like:
    #   <p><span>(7)</span><span>Debt is on non-accrual status...</span></p>
    # Also handles alpha markers: (z), (aa), (ab) etc.
    for span in soup.find_all("span"):
        t = span.get_text().strip()
        m = re.fullmatch(r'\(([a-z0-9]{1,3})\)', t, re.IGNORECASE)
        if not m:
            continue
        marker = f"({m.group(1).lower()})"
        if marker in legend:
            continue
        parent_text = span.parent.get_text(separator="").strip() if span.parent else ""
        if parent_text.startswith(t) and 10 < len(parent_text) < 700:
            definition = parent_text[len(t):].strip().lower()
            if len(definition) > 5:
                legend[marker] = definition

    # ── Strategy 2: regex on raw HTML after SOI heading ───────────────────
    if not legend and html_text:
        soi_pos = html_text.lower().find("schedule of investments")
        if soi_pos >= 0:
            chunk = html_text[soi_pos: soi_pos + 3_500_000]
            # Handles both numeric (1) and alpha (z)/(aa) markers
            for m in re.finditer(
                r'\(([a-z0-9]{1,3})\)\s{0,2}([A-Z][^<\n]{10,400})',
                chunk, re.IGNORECASE
            ):
                marker  = f"({m.group(1).lower()})"
                meaning = m.group(2).strip().lower()
                if marker not in legend:
                    legend[marker] = meaning

    # ── Strategy 3: tag-based scan (traditional HTML fallback) ────────────
    if not legend and soi_tag is not None:
        for tag in soi_tag.find_all_next(
            ["p", "div", "td", "li"], limit=5000
        ):
            text = tag.get_text(separator=" ").strip()
            if not text or len(text) > 600:
                continue
            m = re.match(r'^\(?([a-z0-9]{1,3})\)?\s+(.+)$', text, re.IGNORECASE)
            if m and 5 < len(m.group(2)) < 600:
                marker  = f"({m.group(1).lower()})"
                meaning = m.group(2).lower()
                if marker not in legend:
                    legend[marker] = meaning

    # ── Strategy 4: concatenated multi-entry legend (FSK-style) ──────────
    # Some funds put all footnote definitions in one block:
    #   "(z) Asset is on non-accrual status. (aa) Security is Level 1/2..."
    # Strategy 3 skips these blocks because they exceed 600 chars.
    # Strategy 4 finds such blocks and splits on the marker pattern.
    if not legend and soi_tag is not None:
        _MULTI_MARKER_RE = re.compile(
            r'\(([a-z]{1,3})\)\s+([^()]{5,300}?)(?=\s*\([a-z]|$)',
            re.IGNORECASE
        )
        for tag in soi_tag.find_all_next(["p", "div", "td", "span", "li"], limit=8000):
            text = tag.get_text(separator=" ").strip()
            if len(text) < 30 or len(text) > 5000:
                continue
            pairs = _MULTI_MARKER_RE.findall(text)
            if len(pairs) >= 2:  # must look like a multi-entry legend
                for marker_char, definition in pairs:
                    mk = f"({marker_char.lower()})"
                    if mk not in legend:
                        legend[mk] = definition.strip().lower()
                if legend:
                    break

    return legend


def _na_footnote_marks_from_legend(legend: dict[str, str]) -> set[str]:
    """Return footnote markers whose meaning asserts the investment IS on non-accrual.

    Filters out definitions that merely *mention* non-accrual in a negative context
    (e.g. "interest rate excludes investments on non-accrual status") — these describe
    a rate-presentation convention, not non-accrual status of the investment itself.
    """
    marks = set()
    na_terms = ["non-accrual", "non accrual", "nonaccrual", "not accruing", "placed on non"]

    # Phrases that indicate the marker is about something OTHER than the investment
    # being on non-accrual (e.g. rate-format footnotes that reference excluded NAs)
    _EXCLUDE_PHRASES = [
        "excludes", "excluding", "except", "other than",
        "does not include", "not include",
    ]

    for marker, meaning in legend.items():
        if not any(t in meaning for t in na_terms):
            continue
        # Skip if the non-accrual mention is inside a negative/exclusionary context
        # Check within a 60-char window before the first na_term hit
        skip = False
        for t in na_terms:
            pos = meaning.find(t)
            if pos < 0:
                continue
            window = meaning[max(0, pos - 60):pos]
            if any(ep in window for ep in _EXCLUDE_PHRASES):
                skip = True
                break
        if not skip:
            marks.add(marker)
    return marks


def _pik_footnote_marks_from_legend(legend: dict[str, str]) -> set[str]:
    """Return footnote markers whose meaning relates to PIK."""
    marks = set()
    pik_terms = ["payment-in-kind", "payment in kind", "pik", "paid in kind"]
    for marker, meaning in legend.items():
        if any(t in meaning for t in pik_terms):
            marks.add(marker)
    return marks


def _clean_issuer_name(raw: str) -> tuple[str, str, set[str]]:
    """Split 'Company Name (footnotes) - Instrument Type' → (name, instrument_type, markers).

    Returns the cleaned name, any embedded instrument type, and the set of
    footnote markers found (e.g. {"(1)", "(7)"}) so callers can check NA/PIK flags.
    """
    # Collect all trailing/embedded footnote markers before stripping them.
    # Handles numeric (1)-(99), single-letter (a)-(z), and multi-char (aa)/(ab)/(z) etc.
    # Normalize to lowercase so marker sets from the legend (always lowercase) intersect correctly.
    markers: set[str] = {m.lower() for m in re.findall(r'\(\d{1,2}\)', raw)}
    markers |= {m.lower() for m in re.findall(r'\([a-z]{1,3}\)', raw, re.IGNORECASE)}

    # Remove ALL footnote references from the name (not just trailing)
    cleaned = re.sub(r'\s*\(\d{1,2}\)\s*', ' ', raw).strip()
    cleaned = re.sub(r'\s*\([a-z]{1,3}\)\s*', ' ', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Split embedded instrument descriptors off the borrower name. Some funds use
    # ASCII hyphens, some use unicode dashes, and some put the instrument after a
    # comma (e.g. "Issuer, Revolver").
    match = re.search(
        r'(?P<sep>\s*[\u2013\u2014-]\s*|,\s*)'
        r'(?P<suffix>('
        r'line of credit|unfunded revolver|revolver|term debt|term loan|'
        r'delayed draw|delayed draw term loan|first lien|second lien|'
        r'unitranche|mezzanine|structured mezzanine|bridge loan|'
        r'senior note|secured note|unsecured note'
        r')\b.*)$',
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return cleaned[:match.start()].strip(" ,;"), match.group("suffix").strip(), markers
    return cleaned.strip(), "", markers


# Matches strings that look like investment-type labels rather than company names.
# Used to prevent instrument-type sub-headers from polluting current_issuer.
_TYPE_LABEL_RE = re.compile(
    r'^(first lien|second lien|third lien|senior secured|junior secured|'
    r'subordinated|mezzanine|unitranche|bridge loan|delayed draw|'
    r'term loan( [a-z0-9][-]?)?|revolving loan|revolving credit|'
    r'revolver|priority revolver|super senior revolver|'
    r'last.out|first.out|'
    r'llc interest|lp interest|membership interest|partnership interest|partnership unit|'
    r'equity interest|residual interest|income note|income unit|structured note|'
    r'floating rate note|fixed rate note|unsecured note|secured note|unsecured facility|'
    r'unsecured debt|debt investment|equity investment|credit investment|'
    r'specialty finance|non-qualifying|'
    r'common equity|common stock|common unit|'
    r'preferred equity|preferred stock|preferred unit|'
    r'class [a-z0-9].*(unit|share|stock|warrant)|'
    r'series [a-z0-9].*(preferred|common|warrant|stock|unit)|'
    r'senior [a-z0-9].*(preferred|common|unit)|'
    r'extended series|'
    r'controlled.{0,20}affiliated|affiliated.{0,20}controlled)',
    re.IGNORECASE
)

# Used to post-filter na_issuers / pik_issuers: strip entries that look like
# generic section/type labels that entered via col[0] in certain iXBRL filings.
_GENERIC_LABEL_RE = re.compile(
    r'\b(debt investments?|equity investments?|credit investments?|'
    r'non[- ]qualifying|controlled.{0,15}affiliated|affiliated.{0,15}controlled|'
    r'specialty finance|'
    r'first lien|second lien|third lien|senior secured|junior secured|'
    r'subordinated|mezzanine|unitranche|bridge loan|'
    r'term loan|revolving|delayed draw|'
    r'llc (interest|units?)|lp (interest|units?)|membership interest|partnership (interest|unit)|'
    r'common (unit|equity|stock)|preferred (unit|equity|stock)|'
    r'class [a-z0-9][-. ]*(common|preferred|unit|share|warrant)|'
    r'series [a-z0-9][-. ]*(preferred|common|warrant|stock)|'
    r'senior [a-z0-9][-. ]*(preferred|common|unit)|'
    r'extended series .{0,10}warrants?|'
    r'^warrants?$|^one stop|one.stop (debt|loan|first|senior)|'
    r'\(continued\)$|continued\)$|'
    r'unsecured (note|facility|debt)|secured note|'
    r'senior convertible note|convertible note|'
    r'floating rate note|fixed rate note|income note|structured note)\b',
    re.IGNORECASE
)


def _is_equity_investment(invest_type: str) -> bool:
    low = invest_type.lower()
    return any(x in low for x in ["equity", "warrant", "preferred", "common stock",
                                    "lp interest", "membership", "residual"])


def _find_soi_section(soup: BeautifulSoup) -> Optional[Tag]:
    """Find the Schedule of Investments section in the parsed HTML.

    Handles both traditional HTML heading tags and modern iXBRL <span>/<p> elements
    used in SEC inline XBRL filings.

    Tags *inside* a <table> element are skipped in all passes — in iXBRL filings
    (e.g. ARCC, BXSL) the SOI heading text is repeated in every table header row,
    so the first match would otherwise land inside the SOI table itself rather than
    before it.
    """
    def _in_table(tag) -> bool:
        return tag.find_parent("table") is not None

    # First pass: traditional heading tags (fast, preferred)
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "b", "strong"]):
        if _in_table(tag):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if any(h in text for h in SOI_HEADINGS) and len(text) < 150:
            return tag

    def _is_standalone_heading(text: str) -> bool:
        """True if one of the SOI headings is the primary content of the text
        (not embedded inside a longer prose sentence like 'See the schedule...')."""
        for h in SOI_HEADINGS:
            if h not in text:
                continue
            # Require the heading to comprise at least 60% of the text, OR
            # be at the very start/end of the text (allowing minor suffixes like dates).
            ratio = len(h) / max(len(text), 1)
            if ratio >= 0.60 or text.startswith(h) or text.rstrip().endswith(h):
                return True
        return False

    # Second pass: <p> tags (common in older filings)
    for tag in soup.find_all("p"):
        if _in_table(tag):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if _is_standalone_heading(text) and len(text) < 150:
            return tag

    # Signals that indicate a cross-reference prose sentence rather than a real heading
    _CROSS_REF_SIGNALS = (
        "for more information", "see the consolidated", "see the schedule",
        "see our consolidated", "see note", "in our consolidated financial statements",
        "please refer", "as further described", "described in note",
        "incorporated by reference", "see item", "as of the date",
        "in our financial statements", "in the financial statements",
    )

    def _is_cross_ref(tag) -> bool:
        """True if this tag or its parent element reads like a cross-reference sentence."""
        own_text = tag.get_text(separator=" ").lower()
        if any(s in own_text for s in _CROSS_REF_SIGNALS):
            return True
        parent_text = tag.parent.get_text(separator=" ").lower() if tag.parent else ""
        if any(s in parent_text for s in _CROSS_REF_SIGNALS):
            return True
        return False

    # Third pass: <span> tags (iXBRL / modern EDGAR filings), not inside tables
    for tag in soup.find_all("span"):
        if _in_table(tag):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if _is_standalone_heading(text) and 10 < len(text) < 150:
            if _is_cross_ref(tag):
                continue
            style = tag.get("style", "")
            # Check specifically for bold weight (700 or "bold"), not just any font-weight
            is_bold = ("font-weight:700" in style or "font-weight: 700" in style
                       or "font-weight:bold" in style or "font-weight: bold" in style
                       or "font-weight:800" in style or "font-weight:900" in style)
            if is_bold or len(text) < 80:
                return tag

    # Fourth pass: any non-table, non-script tag (last resort)
    # Use _is_standalone_heading to avoid picking up cross-reference prose
    for tag in soup.find_all(True):
        if tag.name in ("script", "style", "table", "tr", "td", "th"):
            continue
        if _in_table(tag):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if _is_standalone_heading(text) and len(text) < 150:
            if not _is_cross_ref(tag):
                return tag

    # Fifth pass: heading may be INSIDE the SOI table itself (e.g. BXSL where the
    # section title is a merged header row).  Return the in-table tag so the caller
    # can detect it and start from that table rather than the next one.
    for tag in soup.find_all(["span", "div", "b", "strong", "p"]):
        if not _in_table(tag):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if _is_standalone_heading(text) and 10 < len(text) < 150:
            if not _is_cross_ref(tag):
                style = tag.get("style", "")
                is_bold = ("font-weight:700" in style or "font-weight: 700" in style
                           or "font-weight:bold" in style or "font-weight: bold" in style
                           or "font-weight:800" in style or "font-weight:900" in style
                           or tag.name in ("b", "strong"))
                if is_bold or len(text) < 80:
                    return tag

    return None


def _extract_table_rows(table: Tag) -> list[list[str]]:
    """Extract all text cells from an HTML table."""
    rows = []
    for tr in table.find_all("tr"):
        cells = []
        for cell in tr.find_all(["td", "th"]):
            text = cell.get_text(separator=" ").strip()
            text = re.sub(r'\s+', ' ', text)
            cells.append(text)
        if cells:
            rows.append(cells)
    return rows


def _extract_soi_chunk(html: str, max_bytes: int = 4_000_000) -> str:
    """For large filings, extract the full SOI section (potentially multi-page).

    For iXBRL filings with "Continued" pages, this collects all SOI-related
    sections up to the end of the statement.  Returns stitched HTML suitable
    for BeautifulSoup parsing.

    Strategy:
    - Find all positions of SOI headings (including "Continued" variants)
    - Skip the first occurrence if it's a Table-of-Contents link
    - Extract ~700KB after each heading position, stitch together
    """
    low = html.lower()

    CONTINUED_HEADINGS = frozenset([
        "schedule of investments (continued)",
        "schedule of portfolio investments (continued)",
        "consolidated schedule of investments (continued)",
        "schedule of investments — continued",
        "schedule of investments - continued",
    ])

    # All positions; also track whether each is a "continued" variant
    all_positions: list[tuple[int, bool]] = []  # (pos, is_continued)
    for h in SOI_HEADINGS + list(CONTINUED_HEADINGS):
        is_cont = h in CONTINUED_HEADINGS
        start = 0
        while True:
            idx = low.find(h, start)
            if idx == -1:
                break
            all_positions.append((idx, is_cont))
            start = idx + 1

    # Deduplicate by position.
    # If both a base heading ("consolidated schedule of investments") and its
    # "(continued)" variant match at the same position, trust is_cont=True — the
    # base heading is a prefix of the continued heading so both fire at the same pos.
    pos_map: dict[int, bool] = {}
    for pos, is_cont in all_positions:
        if pos not in pos_map:
            pos_map[pos] = is_cont
        elif is_cont:          # any continued-match wins over a base-match at same pos
            pos_map[pos] = True
    all_positions = sorted(pos_map.items())

    if not all_positions:
        return html[:max_bytes]  # fallback

    # Filter out TOC-style links (those followed by </a> within 200 chars and
    # preceded by href= within 250 chars — some filings wrap the heading in a long
    # <a href="..."><span style="...">TEXT</span></a> with the href many chars back).
    data_positions: list[tuple[int, bool]] = []
    for pos, is_cont in all_positions:
        window = html[pos:pos + 300].lower()
        is_toc = '</a>' in window[:150] and ('<table of contents' in low[max(0, pos-500):pos]
                                              or 'href' in html[max(0, pos-250):pos].lower())
        if not is_toc:
            data_positions.append((pos, is_cont))

    if not data_positions:
        data_positions = [(p, c) for p, c in pos_map.items()]
        data_positions.sort()

    # Find the boundary of the prior-year SOI in 10-K filings.
    # Strategy: consecutive heading occurrences within 500KB are treated as continuation
    # pages of the SAME SOI (OBDC-style multi-page iXBRL).  A gap > 500KB from the last
    # included heading signals a new (prior-year) section — stop there.
    _MAX_CONTINUATION_GAP = 500_000  # bytes
    stop_pos: int = len(html)
    current_period_positions: list[int] = []
    all_pos_sorted = sorted(pos for pos, _ in data_positions)

    for pos, is_cont in data_positions:
        if not current_period_positions:
            current_period_positions.append(pos)
            continue
        gap = pos - current_period_positions[-1]
        if is_cont or gap <= _MAX_CONTINUATION_GAP:
            # Continuation page — include it
            current_period_positions.append(pos)
        else:
            # Large gap — this is the prior-year SOI; stop before it
            stop_pos = pos
            break

    # Compute non-overlapping ranges for each data section.
    # Each section runs from this heading to the next heading (or stop_pos).
    # Use a 500-char symmetric lookback so the <p> / <tr> opening tags before
    # the heading text are fully included — a 200-char lookback can cut into a
    # long style="..." attribute mid-string, producing malformed HTML for the
    # lxml parser (observed with TCPC where the heading <p> tag is ~280 chars).
    _LOOKBACK = 500
    data_positions_sorted = current_period_positions
    chunks = []
    total_bytes = 0

    for i, pos in enumerate(data_positions_sorted):
        if total_bytes >= max_bytes:
            break
        start = max(0, pos - _LOOKBACK)
        # End at the next heading position, the prior-year-SOI boundary, or max_bytes
        if i + 1 < len(data_positions_sorted):
            raw_end = data_positions_sorted[i + 1] - _LOOKBACK
        else:
            raw_end = stop_pos  # don't cross into the prior-year SOI
        end = min(raw_end, start + max_bytes)  # hard cap at max_bytes total
        if end <= start:
            continue
        chunks.append(html[start:end])
        total_bytes += (end - start)

    stitched = "<html><body>" + "".join(chunks) + "</body></html>"
    return stitched


def parse_soi_html(html: str, fund_ticker: str, period: str, filing_type: str,
                   verbose: bool = False) -> list[Investment]:
    """Parse a complete 10-K/10-Q HTML filing and extract all SOI investments."""
    if not _BS4_OK:
        raise RuntimeError("beautifulsoup4 not installed — run: pip install beautifulsoup4 lxml")

    scale = _detect_scale(html)

    # For large filings (>3MB), extract just the SOI section(s) first to avoid
    # parsing tens of megabytes of iXBRL boilerplate
    if len(html) > 3_000_000:
        html_chunk = _extract_soi_chunk(html, max_bytes=20_000_000)
        if verbose:
            print(f"    Large filing ({len(html)//1000}KB) — using SOI chunk "
                  f"({len(html_chunk)//1000}KB)")
    else:
        html_chunk = html

    soup = BeautifulSoup(html_chunk, "lxml")

    soi_tag = _find_soi_section(soup)
    if soi_tag is None:
        if verbose:
            print(f"  [!] SOI heading not found in {fund_ticker} {period}")
        return []

    # Extract footnote legend to detect fund-specific non-accrual / PIK markers
    legend = _extract_footnote_legend(soup, soi_tag, html_text=html)
    na_marks  = _na_footnote_marks_from_legend(legend)
    pik_marks = _pik_footnote_marks_from_legend(legend)
    if verbose:
        print(f"    Footnote legend ({len(legend)} entries): NA={na_marks}  PIK={pik_marks}")
        if legend:
            for mk, mv in sorted(legend.items()):
                print(f"      {mk}: {mv[:80]}")

    # Gather tables after the SOI heading (take up to 3 to handle multi-page SOIs)
    investments: list[Investment] = []
    tables_processed = 0
    found_content = False
    # Issuer-level NA/PIK tracking — accumulates across all tables so that issuers
    # whose markers appear in par-only rows (column-shift artefact) are still flagged.
    na_issuers:  set[str] = set()
    pik_issuers: set[str] = set()

    # Walk forward from the SOI heading to find tables.
    # Always use find_next — even when the SOI heading is inside a table row
    # (e.g. BXSL title row), the next nested/sibling table is the SOI content table.
    sibling = soi_tag.find_next("table")
    while sibling and tables_processed < 60:
        rows = _extract_table_rows(sibling)
        if len(rows) < 3:
            sibling = sibling.find_next("table")
            continue

        # Detect header row
        col_map: dict[int, str] = {}
        data_start = 0
        for ri, row in enumerate(rows[:5]):
            if not row:
                continue
            col_map = _map_col_headers(row)
            if len(col_map) >= 3:
                data_start = ri + 1
                break

        if len(col_map) < 2:
            # No useful column headers — try next table
            sibling = sibling.find_next("table")
            tables_processed += 1
            continue

        # Recalibrate column positions ONLY when FV/cost columns appear misaligned.
        # Applying unconditionally breaks tables that already have correct mappings.
        # Heuristic: sample a few data rows — if the mapped FV column has < 20% hit
        # rate, the header is likely offset from the data cells (Workiva iXBRL pattern).
        _fv_col  = next((k for k, v in col_map.items() if v == "fv_str"), None)
        _smpl    = [r for r in rows[data_start:data_start + 20]
                    if any(c.strip() for c in r)][:8]
        _fv_hits = sum(
            1 for r in _smpl
            if _fv_col is not None and _fv_col < len(r)
            and _clean_num(r[_fv_col].strip()) is not None
        ) if _smpl else 0
        if not _smpl or _fv_hits < len(_smpl) * 0.20:
            col_map = _recalibrate_col_map(col_map, rows[data_start:data_start + 30])

        # Auto-detect issuer column when headers didn't expose one (e.g. GBDC where
        # col 0 is an empty spacer and col 1 holds the company name, both unlabeled).
        if "issuer" not in col_map.values():
            _already_mapped = set(col_map.keys())
            # Sample real data rows (multi-cell, not section headers)
            _sample_rows = [
                r for r in rows[data_start:data_start + 40]
                if len([c for c in r if c.strip()]) >= 3
            ][:10]
            # Candidate columns: leftmost that are not already mapped to a numeric field
            # and that consistently hold non-numeric, non-empty text (company names)
            _numeric_re = re.compile(r'^[\d\.,\-\+\$\%\(\)\/\s]+$')
            _date_re    = re.compile(r'\d{1,2}[/\-]\d{2,4}')
            for _cand in range(min(4, min((len(r) for r in _sample_rows), default=0))):
                if _cand in _already_mapped:
                    continue
                _hits = 0
                for _sr in _sample_rows:
                    _v = _sr[_cand].strip() if _cand < len(_sr) else ""
                    if (len(_v) >= 3
                            and not _numeric_re.match(_v)
                            and not _date_re.search(_v)
                            and not _v.startswith("$")):
                        _hits += 1
                if _hits >= max(2, len(_sample_rows) * 0.4):
                    col_map[_cand] = "issuer"
                    break

        # Does this table look like an SOI? Need at least cost or fv col
        has_value_col = "cost_str" in col_map.values() or "fv_str" in col_map.values()
        if not has_value_col:
            sibling = sibling.find_next("table")
            tables_processed += 1
            continue

        found_content = True
        current_issuer  = ""
        current_industry = ""
        current_type    = ""
        current_issuer_markers: set[str] = set()  # carry-forward of issuer footnote marks
        # Per-table NA/PIK sets: scoped to the current table so that comparison-period
        # SOI sections (e.g. prior-year columns in a 10-K) cannot pollute current-period
        # positions.  global na_issuers/pik_issuers are kept only for verbose logging.
        _tbl_na:  set[str] = set()
        _tbl_pik: set[str] = set()
        _tbl_start = len(investments)  # index of first investment from this table

        for row in rows[data_start:]:
            if not any(row):
                continue

            # Try to detect section headers (no numeric data, just text)
            non_empty = [c for c in row if c.strip()]
            if len(non_empty) == 1:
                txt = non_empty[0].strip()
                _txt_low = txt.lower()
                # "(continued)" labels and known section separators → always industry, never issuer
                _is_section_label = (
                    re.search(r'\(continued\)', txt, re.IGNORECASE)
                    or _txt_low.startswith("first lien debt")
                    or _txt_low.startswith("second lien debt")
                    or _txt_low.startswith("controlled")
                    or _txt_low.startswith("non-controlled")
                    or _txt_low == "equity"
                    or _txt_low == "warrants"
                )
                if _is_section_label or (len(txt) < 80 and not re.search(r'[\d,\$\(\)]', txt)):
                    # Plain industry/sector sub-header — update carry-forward
                    current_industry = txt
                else:
                    # Could be an issuer name-only row (iXBRL multi-row layout) OR an
                    # investment-type label (e.g. "First lien senior secured loan(28)").
                    # Investment-type labels must not become current_issuer — they would
                    # pollute carry-forward and cause all subsequent positions to be
                    # misidentified (and potentially mass-NA-flagged).
                    _clean, _, _solo_markers = _clean_issuer_name(txt)
                    if _clean:
                        if _TYPE_LABEL_RE.match(_clean) or _GENERIC_LABEL_RE.search(_clean):
                            # It's an instrument-type sub-header, not a company name
                            current_type = _clean
                        else:
                            current_issuer = _clean
                            current_issuer_markers = _solo_markers
                            _row_text_solo = txt
                            _row_is_na = _is_non_accrual(_row_text_solo, na_marks) or bool(
                                na_marks and _solo_markers and (_solo_markers & na_marks)
                            )
                            if _row_is_na:
                                _tbl_na.add(_clean)
                                na_issuers.add(_clean)
                            if pik_marks and (
                                any(m in _row_text_solo for m in pik_marks)
                                or bool(_solo_markers & pik_marks)
                            ):
                                _tbl_pik.add(_clean)
                                pik_issuers.add(_clean)
                continue

            # "Total" row handling:
            #   - Known end-of-table totals → break
            #   - Industry / sector subtotals → skip (continue) without breaking
            #     e.g. "Total Internet/Software — 12.3%" should not stop the loop
            first_cell = row[0].strip().lower() if row else ""
            _TOTAL_PATTERNS = (
                "total investments", "total debt", "total equity", "total portfolio",
                "total first lien", "total second lien", "total subordinated",
                "total preferred", "total secured", "total unsecured",
            )
            if first_cell.startswith("total"):
                if any(first_cell.startswith(p) for p in _TOTAL_PATTERNS):
                    break   # End of this SOI table section
                else:
                    continue  # Section subtotal — skip row, keep processing

            # Map cells to fields
            inv = Investment(
                fund_ticker=fund_ticker,
                period=period,
                filing_type=filing_type,
            )

            row_text = " ".join(row)

            for col_idx, field_name in col_map.items():
                if col_idx >= len(row):
                    continue
                val = row[col_idx].strip()
                setattr(inv, field_name, val)

            # Clean issuer: strip footnote markers and split off instrument type
            issuer_markers: set[str] = set()
            if inv.issuer:
                clean_name, embedded_type, issuer_markers = _clean_issuer_name(inv.issuer)
                inv.issuer = clean_name
                if embedded_type and not inv.invest_type:
                    inv.invest_type = embedded_type

            # Also extract markers from dedicated footnote column (e.g. FSK uses a
            # "Footnotes" column with concatenated markers like "(ac)(v)(y)(z)")
            if inv.footnote_col:
                foot_markers = set(re.findall(r'\([a-z0-9]{1,3}\)', inv.footnote_col, re.IGNORECASE))
                issuer_markers |= foot_markers

            # Also extract markers from the rate/description string.
            # Some funds (e.g. GLAD) append footnote markers to the interest-rate cell:
            #   "S+2.0%, 7.0% Cash, Due 12/2026) (E)(P)"  ← (P) = non-accrual
            # Only collect markers that are in the known legend to avoid false positives
            # from numeric-style rate tokens like "(1)" embedded in rate expressions.
            if inv.rate_str and (na_marks or pik_marks):
                rate_markers = set(re.findall(r'\([a-z]{1,3}\)', inv.rate_str, re.IGNORECASE))
                # Keep only those that actually appear in the legend
                known_marks = (na_marks | pik_marks)
                issuer_markers |= {m.lower() for m in rate_markers if m.lower() in known_marks}

            # Guard: if the issuer cell actually contains an investment-type label
            # (e.g. "First lien senior secured loan", "LLC Interest"), treat it as
            # invest_type and fall through to carry-forward for the real issuer name.
            # This prevents instrument-type sub-headers from polluting current_issuer
            # and causing mass NA false-positives via na_issuers carry-forward.
            if inv.issuer and _TYPE_LABEL_RE.match(inv.issuer):
                if not inv.invest_type:
                    inv.invest_type = inv.issuer
                current_type = inv.invest_type
                inv.issuer = ""  # fall through to carry-forward below

            # Use carry-forward for issuer / industry if blank
            if not inv.issuer and current_issuer:
                inv.issuer = current_issuer
                # Inherit the markers from the name row (the data rows won't have them)
                if not issuer_markers:
                    issuer_markers = current_issuer_markers
            elif inv.issuer:
                current_issuer = inv.issuer
                current_issuer_markers = issuer_markers  # save for data rows below

            if not inv.industry:
                inv.industry = current_industry
            else:
                current_industry = inv.industry

            if not inv.invest_type and current_type:
                inv.invest_type = current_type

            # Dollar-sign cell bypass: iXBRL filings sometimes insert a bare "$" cell
            # immediately before the monetary value (e.g. BXSL Format-A rows).
            # When a mapped field contains just "$", advance to the next parseable cell.
            # Track if cost_str was a "$" that got bypassed — used later in FV recovery.
            _cost_was_dollar_sign = False
            for _ds_field in ("par_str", "cost_str", "fv_str"):
                _ds_val = getattr(inv, _ds_field)
                if _ds_val == "$":
                    _ds_col = next((k for k, v in col_map.items() if v == _ds_field), None)
                    if _ds_col is not None:
                        for _dc in range(1, 5):
                            _nxt_c = _ds_col + _dc
                            _nxt = row[_nxt_c].strip() if _nxt_c < len(row) else ""
                            if _nxt and _nxt != "$" and _clean_num(_nxt) is not None:
                                setattr(inv, _ds_field, _nxt)
                                if _ds_field == "cost_str":
                                    _cost_was_dollar_sign = True
                                break
                        else:
                            setattr(inv, _ds_field, "")  # couldn't resolve; clear "$"

            # Targeted column-shift recovery: when par is populated but cost/fv are
            # non-numeric (empty OR "$"), some iXBRL filings have a colspan artefact
            # where data cells are 1-3 columns to the right of where the header mapped
            # them.  _clean_num returns None for dates/rates, so non-numeric neighbors
            # are safe to probe.
            _par_ok  = _clean_num(inv.par_str)  is not None
            _cost_ok = _clean_num(inv.cost_str) is not None
            _fv_ok   = _clean_num(inv.fv_str)   is not None
            if inv.par_str and _par_ok and not _cost_ok and not _fv_ok:
                cost_col = next((k for k, v in col_map.items() if v == "cost_str"), None)
                fv_col   = next((k for k, v in col_map.items() if v == "fv_str"), None)
                if cost_col is not None:
                    for delta in (1, 2, 3):
                        c = cost_col + delta
                        alt = row[c].strip() if c < len(row) else ""
                        if alt and _clean_num(alt) is not None:
                            inv.cost_str = alt
                            _cost_ok = True
                            break
                if fv_col is not None:
                    for delta in (1, 2, 3, 4):
                        c = fv_col + delta
                        alt = row[c].strip() if c < len(row) else ""
                        if alt and _clean_num(alt) is not None:
                            inv.fv_str = alt
                            _fv_ok = True
                            break

            # Format-B recovery: when fv is set but cost is not (e.g. BXSL rows where
            # the FV column contains cost data due to a consistent +2 column shift without
            # dollar-sign cells), try to find the real FV 2-4 columns further right and
            # promote the misidentified value to cost.
            if _fv_ok and not _cost_ok:
                fv_col = next((k for k, v in col_map.items() if v == "fv_str"), None)
                if fv_col is not None:
                    for delta in range(2, 7):
                        c = fv_col + delta
                        alt = row[c].strip() if c < len(row) else ""
                        if alt and _clean_num(alt) is not None:
                            inv.cost_str = inv.fv_str   # current fv was actually cost
                            inv.fv_str   = alt          # real FV is here
                            _cost_ok, _fv_ok = True, True
                            break

            # Format-A FV recovery: when cost is set but fv is still missing (e.g. BXSL
            # rows with "$" prefix cells where cost was extracted but FV is 2 more columns
            # further right past another "$" cell).  Skip any numeric cell that equals the
            # already-captured cost value to avoid double-capturing cost as FV.
            if _cost_ok and not _fv_ok:
                fv_col = next((k for k, v in col_map.items() if v == "fv_str"), None)
                if fv_col is not None:
                    for delta in range(1, 9):
                        c = fv_col + delta
                        alt = row[c].strip() if c < len(row) else ""
                        if (alt and alt != "$"
                                and (not _cost_was_dollar_sign or alt != inv.cost_str)
                                and _clean_num(alt) is not None):
                            inv.fv_str = alt
                            _fv_ok = True
                            break

            # Maturity recovery: maturity often shifts +1 in iXBRL (same dollar-sign artefact)
            if not inv.maturity:
                mat_col = next((k for k, v in col_map.items() if v == "maturity"), None)
                if mat_col is not None:
                    for delta in (1, 2, -1):
                        c = mat_col + delta
                        if c < 0: continue
                        nxt = row[c].strip() if c < len(row) else ""
                        if nxt and re.search(r'\d{1,2}[/\-]\d{1,4}', nxt):
                            inv.maturity = nxt
                            break

            # Track NA/PIK issuers from this row BEFORE the value-filter skip.
            # Some iXBRL filings have a column-shift artefact where the header and data
            # rows use different <td> widths, so cost/fv land at wrong positions.  Those
            # rows still carry correct issuer + footnote markers → extract NA/PIK info here.

            # Identify "metadata-empty" rows: par, rate, and pct_nav are all blank.
            # These are almost always prior-year comparison-column entries or subtotal rows
            # (e.g. OBDC's iXBRL SOI includes a Dec 31 prior-year column alongside the
            # current-period column in the same HTML table; the parser captures both).
            # We must NOT use these rows to populate _tbl_na / _tbl_pik — doing so causes
            # prior-period non-accrual/PIK flags to contaminate current-period data via
            # the issuer-level carry-forward.  The flag on the row itself is still set
            # correctly if the row text directly asserts NA/PIK, but the issuer is not
            # added to the table-level tracking sets.
            _metadata_empty = (
                not (inv.par_str or "").strip()
                and not (inv.rate_str or "").strip()
                and not (inv.pct_nav_str or "").strip()
            )

            row_is_na = _is_non_accrual(row_text, na_marks)
            if not row_is_na and na_marks and issuer_markers:
                row_is_na = bool(issuer_markers & na_marks)
            if row_is_na and inv.issuer and not _metadata_empty:
                _tbl_na.add(inv.issuer)
                na_issuers.add(inv.issuer)
            row_is_pik = bool(pik_marks and (
                any(m in row_text for m in pik_marks) or bool(issuer_markers & pik_marks)
            )) if pik_marks else False
            if row_is_pik and inv.issuer and not _metadata_empty:
                _tbl_pik.add(inv.issuer)
                pik_issuers.add(inv.issuer)

            # Skip rows with no meaningful issuer or value
            if not inv.issuer or (not inv.cost_str and not inv.fv_str):
                continue

            # Parse numeric values
            raw_cost = _clean_num(inv.cost_str)
            raw_fv   = _clean_num(inv.fv_str)
            raw_pnav = _clean_num(inv.pct_nav_str)

            if raw_cost is not None:
                inv.cost_mm = round(raw_cost * scale, 4)
            if raw_fv is not None:
                inv.fv_mm = round(raw_fv * scale, 4)
            if raw_pnav is not None:
                inv.pct_nav = round(raw_pnav, 4)

            # Flags — check row text AND issuer-embedded markers against legend
            # NA / PIK flags on the captured investment (uses already-computed issuer-level
            # sets from the pre-skip block above, plus a per-row text check).
            inv.is_non_accrual = (
                inv.issuer in _tbl_na
                or _is_non_accrual(row_text, na_marks)
                or bool(na_marks and issuer_markers and (issuer_markers & na_marks))
            )
            inv.is_equity      = _is_equity_investment(inv.invest_type)
            base, spread, pik  = _parse_rate(inv.rate_str)
            if not pik and pik_marks:
                pik = (
                    any(m in row_text for m in pik_marks)
                    or bool(issuer_markers & pik_marks)
                    or inv.issuer in _tbl_pik
                )
            inv.is_pik         = pik
            inv.rate_base      = base
            inv.spread_bps     = spread

            # Quality filter: skip rows where fv is obviously 0 or noise
            if inv.fv_mm is not None and abs(inv.fv_mm) < 0.0001:
                continue
            # Cap implausibly large single-position values (>$500B per position is impossible;
            # the prior threshold of $5B was too low and incorrectly nulled out dollar-scale
            # filings like TCPC before the median-based scale fix could correct them).
            if inv.fv_mm is not None and inv.fv_mm > 500_000:
                inv.fv_mm = None
            if inv.cost_mm is not None and inv.cost_mm > 500_000:
                inv.cost_mm = None

            investments.append(inv)

        # Per-table scale fix: if the median fv_mm of THIS table's non-equity positions is
        # implausibly large (>5000, i.e. >$5B per position), the table reports in raw dollars
        # rather than thousands.  Apply a /1000 correction scoped to just this table so that
        # mixed-scale tables (e.g. TCPC 10-K with Dec 2025 dollar-scale data alongside notes
        # tables with smaller values) don't suppress the correction via a diluted global median.
        _tbl_fvs = [
            i.fv_mm for i in investments[_tbl_start:]
            if i.fv_mm is not None and not i.is_equity and i.fv_mm > 0
        ]
        if len(_tbl_fvs) >= 3:
            # Use max rather than median: TCPC-style dollar-scale tables have small positions
            # ($1-2M raw → fv_mm ~1000-2000) that pull the median below 5000 even when
            # large positions (fv_mm ~13000) clearly indicate dollar-scale representation.
            # A max > 5000 signals that at least one position is priced at >$5B, which is
            # impossible in any real BDC portfolio and therefore a scale indicator.
            _tbl_max = max(_tbl_fvs)
            if _tbl_max > 5_000:
                for i in investments[_tbl_start:]:
                    if i.fv_mm is not None:
                        i.fv_mm = round(i.fv_mm * 0.001, 4)
                    if i.cost_mm is not None:
                        i.cost_mm = round(i.cost_mm * 0.001, 4)

        # Retroactively apply per-table NA/PIK flags to investments from THIS table only.
        # This ensures name-only rows (iXBRL multi-row format) whose NA/PIK markers were
        # discovered during the loop correctly flag subsequent data rows for the same issuer,
        # WITHOUT contaminating investments from other SOI periods (e.g. prior-year 10-K).
        _continued_re_tbl = re.compile(r'\(\s*continued\s*\)', re.IGNORECASE)
        _tbl_na  = {s for s in _tbl_na  if not _GENERIC_LABEL_RE.search(s) and not _continued_re_tbl.search(s)}
        _tbl_pik = {s for s in _tbl_pik if not _GENERIC_LABEL_RE.search(s) and not _continued_re_tbl.search(s)}
        for inv in investments[_tbl_start:]:
            # Do not carry-forward NA/PIK to metadata-empty rows (prior-year comparison
            # column entries or subtotal rows).  Their flags should only come from direct
            # row-text or footnote-marker matches, not from the issuer-level carry-forward.
            _inv_meta_empty = (
                not (inv.par_str or "").strip()
                and not (inv.rate_str or "").strip()
                and not (inv.pct_nav_str or "").strip()
            )
            if inv.issuer in _tbl_na and not _inv_meta_empty:
                inv.is_non_accrual = True
            if inv.issuer in _tbl_pik and not _inv_meta_empty:
                inv.is_pik = True

        sibling = sibling.find_next("table")
        tables_processed += 1

        # Stop once we've processed the main SOI content (for non-chunked mode)
        # In chunked mode, continue through all tables
        if found_content and tables_processed >= 60:
            break

    # Deduplicate: same issuer + same fv_str + same cost_str = duplicate from overlapping chunks
    seen: set[tuple] = set()
    deduped: list[Investment] = []
    for inv in investments:
        key = (inv.issuer[:40], inv.fv_str[:20], inv.cost_str[:20], inv.maturity[:10])
        if key not in seen:
            seen.add(key)
            deduped.append(inv)
        # Also skip the header row that got captured as data
        if inv.issuer.strip().lower() in ("issuer", "company", "portfolio company",
                                           "borrower", "investment"):
            deduped.pop()
            seen.discard(key)

    investments = deduped

    # Secondary deduplication: remove metadata-empty rows whose (issuer, cost_mm, fv_mm)
    # exactly duplicates a filled row for the same issuer in this filing.
    # This catches prior-year comparison column entries that slipped through: they have
    # the same numeric values as the prior-period row but lack par/rate/pct_nav.
    # Only remove the metadata-empty copy; keep the filled copy.
    _filled_numeric: set[tuple] = set()
    for inv in investments:
        _inv_me = (
            not (inv.par_str or "").strip()
            and not (inv.rate_str or "").strip()
            and not (inv.pct_nav_str or "").strip()
        )
        if not _inv_me and inv.cost_mm is not None and inv.fv_mm is not None:
            _filled_numeric.add((inv.issuer[:60], inv.cost_mm, inv.fv_mm))

    investments = [
        inv for inv in investments
        if not (
            not (inv.par_str or "").strip()
            and not (inv.rate_str or "").strip()
            and not (inv.pct_nav_str or "").strip()
            and inv.cost_mm is not None
            and inv.fv_mm is not None
            and (inv.issuer[:60], inv.cost_mm, inv.fv_mm) in _filled_numeric
        )
    ]

    # Post-filter global na_issuers for verbose logging only.
    # Per-position NA/PIK flags are now applied per-table (above) so there is no
    # need to override them here.  The global sets are filtered for display only.
    _continued_re = re.compile(r'\(\s*continued\s*\)', re.IGNORECASE)
    na_issuers  = {s for s in na_issuers  if not _GENERIC_LABEL_RE.search(s) and not _continued_re.search(s)}
    pik_issuers = {s for s in pik_issuers if not _GENERIC_LABEL_RE.search(s) and not _continued_re.search(s)}
    if verbose:
        print(f"  [na_issuers] {sorted(na_issuers)}")

    # Final pass: clear NA/PIK flags from positions whose "issuer" is a generic
    # section/type label (e.g. "Warrants", "Senior convertible notes", or
    # industry "(continued)" labels). These are misidentified via carry-forward.
    for inv in investments:
        if inv.issuer and (
            _GENERIC_LABEL_RE.search(inv.issuer)
            or _continued_re.search(inv.issuer)
        ):
            inv.is_non_accrual = False
            inv.is_pik = False

    # Sanity-check scale: if median fv_mm or cost_mm among non-equity positions is
    # implausibly large (>5000, i.e. $5B per single debt position), the filing likely
    # reports in actual dollars rather than thousands. Apply a /1000 correction.
    debt_fvs = [
        i.fv_mm for i in investments
        if i.fv_mm and not i.is_equity and i.fv_mm > 0
    ]
    if len(debt_fvs) >= 5:
        import statistics
        med = statistics.median(debt_fvs)
        if med > 5_000:
            # Values appear to be in thousands of dollars rather than millions
            correction = 0.001
            for i in investments:
                if i.fv_mm is not None:
                    i.fv_mm = round(i.fv_mm * correction, 4)
                if i.cost_mm is not None:
                    i.cost_mm = round(i.cost_mm * correction, 4)
            if verbose:
                print(f"  [scale-fix] Median debt fv=${med:.0f}M → applied 0.001 correction")

    if verbose:
        na = sum(1 for i in investments if i.is_non_accrual)
        pik = sum(1 for i in investments if i.is_pik)
        print(f"  Parsed {len(investments)} investments, {na} non-accrual, {pik} PIK")

    return investments


# ---------------------------------------------------------------------------
# Portfolio collector
# ---------------------------------------------------------------------------

class PortfolioCollector:
    def __init__(self, cache_dir: Path = PORTFOLIO_CACHE):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._universe = self._load_universe()

    def _load_universe(self) -> list[dict]:
        if not UNIVERSE_PATH.exists():
            return []
        data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
        return data.get("funds", [])

    def _cik_for(self, ticker: str) -> Optional[str]:
        for f in self._universe:
            if f["ticker"] == ticker:
                return f.get("sec_cik")
        return None

    def collect_fund(
        self,
        ticker: str,
        n_filings: int = 2,
        force_refresh: bool = False,
        verbose: bool = True,
    ) -> list[dict]:
        """Collect SOI data for a fund's n most recent 10-K/10-Q filings.

        Returns list of investment dicts (one per portfolio position).
        Also saves to cache.
        """
        cik = self._cik_for(ticker)
        if not cik:
            print(f"  [!] CIK not found for {ticker}")
            return []

        filings = _get_recent_10kq(cik, n=n_filings)
        if not filings:
            print(f"  [!] No 10-K/10-Q filings found for {ticker}")
            return []

        all_investments = []
        for filing in filings:
            period   = filing["period"]
            form     = filing["form"]
            accession = filing["accession"]
            primary  = filing["primary_doc"]

            cache_key = self.cache_dir / f"{ticker}_{period}.json"
            if cache_key.exists() and not force_refresh:
                if verbose:
                    print(f"  {ticker} {period} {form}: loaded from cache ({cache_key.name})")
                data = json.loads(cache_key.read_text(encoding="utf-8"))
                all_investments.extend(data)
                continue

            if verbose:
                print(f"  {ticker} {period} {form}: fetching from EDGAR...")

            # Build document URL
            doc_url = _primary_doc_url(cik, accession, primary)

            try:
                html = _fetch(doc_url, timeout=60)
            except Exception as e:
                if verbose:
                    print(f"    [!] Failed to download: {e}")
                # Try to find the .htm document from index
                try:
                    index_items = _get_filing_index(cik, accession)
                    htm_items = [it for it in index_items
                                 if isinstance(it, dict) and
                                 it.get("name", "").lower().endswith((".htm", ".html")) and
                                 it.get("type", "") not in ("EX-", "XML")]
                    if htm_items:
                        alt_url = (f"{EDGAR_FILING}/Archives/edgar/data/"
                                   f"{int(cik.zfill(10))}/{accession}/{htm_items[0]['name']}")
                        html = _fetch(alt_url, timeout=60)
                    else:
                        continue
                except Exception as e2:
                    if verbose:
                        print(f"    [!] Index fallback also failed: {e2}")
                    continue

            investments = parse_soi_html(html, ticker, period, form, verbose=verbose)
            if not investments:
                if verbose:
                    print(f"    [!] No investments parsed from {ticker} {period}")
                continue

            data = [inv.to_dict() for inv in investments]
            cache_key.write_text(json.dumps(data, indent=2), encoding="utf-8")
            all_investments.extend(data)

            if verbose:
                print(f"    -> {len(investments)} positions cached to {cache_key.name}")

        return all_investments

    def collect_universe(
        self,
        tickers: Optional[list[str]] = None,
        n_filings: int = 2,
        force_refresh: bool = False,
    ) -> dict[str, list[dict]]:
        """Collect SOI for all (or specified) universe funds."""
        targets = tickers or [f["ticker"] for f in self._universe
                               if f.get("sec_cik") and f.get("type") == "listed_bdc"]
        results: dict[str, list[dict]] = {}
        for ticker in targets:
            print(f"\nCollecting {ticker}...")
            results[ticker] = self.collect_fund(ticker, n_filings=n_filings,
                                                force_refresh=force_refresh)
        return results


# ---------------------------------------------------------------------------
# Borrower database builder
# ---------------------------------------------------------------------------

_BORROWER_SUFFIX_RE = re.compile(
    r"\b(llc|inc|corp|corporation|ltd|lp|co|company|holdco|holdings|topco|top|"
    r"parent|borrower|intermediate|ultimate|acquisition|merger|finco|spv|dac|sarl)\b",
    re.IGNORECASE,
)
_BORROWER_GENERIC_TOKENS = {
    "the",
    "hold",
    "holdco",
    "holdings",
    "holding",
    "top",
    "topco",
    "parent",
    "borrower",
    "intermediate",
    "ultimate",
    "acquisition",
    "merger",
    "finco",
    "spv",
    "dac",
    "sarl",
    "buyer",
    "purchaser",
    "aggregator",
    "bidco",
    "midco",
    "blocker",
    "project",
    "unblocked",
    "issuer",
    "interco",
}
_BORROWER_RATE_LIKE_RE = re.compile(
    r"^(?:fixed|floating|sofr|libor|euribor|base|prime)?\s*\+?\s*\d+(?:\.\d+)?\s*%$",
    re.IGNORECASE,
)
_FAMILY_PREFIX_TOKENS = {
    "north",
    "south",
    "east",
    "west",
    "new",
    "global",
    "world",
    "first",
    "national",
    "community",
    "united",
    "international",
    "us",
    "uk",
}


def _normalize_borrower_text(value: str) -> str:
    text = value.replace("\u2013", " - ").replace("\u2014", " - ").replace("\u2212", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;:+")


def _substantive_borrower_tokens(name: str) -> set[str]:
    token_source = _normalize_borrower_text(name).lower()
    token_source = re.sub(r"[&/+,()]", " ", token_source)
    token_source = _BORROWER_SUFFIX_RE.sub(" ", token_source)
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", token_source)
        if len(token) >= 3 and token not in _BORROWER_GENERIC_TOKENS
    }
    return tokens


def _collapse_related_entity_name(name: str) -> str:
    parts = [part.strip(" ,;") for part in re.split(r"\s+and\s+", name, flags=re.IGNORECASE) if part.strip(" ,;")]
    if len(parts) < 2 or len(parts) > 4:
        return name

    token_sets = [(_substantive_borrower_tokens(part), part) for part in parts]
    shared_counts = Counter(
        token
        for tokens, _ in token_sets
        for token in tokens
    )
    shared_tokens = {token for token, count in shared_counts.items() if count >= 2}
    if not shared_tokens:
        return name

    candidates = [
        part
        for tokens, part in token_sets
        if tokens & shared_tokens
    ]
    if not candidates:
        return name
    return min(candidates, key=lambda part: (len(part), part.lower()))


def _normalize_borrower_name(raw: str) -> str:
    if not raw:
        return ""

    dba_match = re.search(r"\((?:d/b/a|dba)\s+([^)]+)\)", raw, flags=re.IGNORECASE)
    if dba_match:
        alias = _normalize_borrower_text(dba_match.group(1))
        if alias:
            return alias

    cleaned, _, _ = _clean_issuer_name(raw)
    cleaned = re.sub(r"\((?:f/k/a|fka)[^)]+\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("+", " ")
    cleaned = _normalize_borrower_text(cleaned)
    cleaned = _collapse_related_entity_name(cleaned)
    return _normalize_borrower_text(cleaned)


def _clean_position_exposure(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    # Single-position SOI values above $500M are typically parse/scale artifacts,
    # not real borrower-level loan marks.
    if numeric > 500:
        return None
    return numeric


def _is_borrower_noise(issuer: str) -> bool:
    low = _normalize_borrower_text(issuer).lower()
    if not low:
        return True
    if _BORROWER_RATE_LIKE_RE.fullmatch(low):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\s*%", low):
        return True
    if "unfunded" in low and "commitment" in low:
        return True
    if low in {"asset based finance commitments", "unfunded asset based finance commitments"}:
        return True
    return False


def _has_meaningful_borrower_exposure(rec: dict) -> bool:
    for app in rec.get("appearances", []):
        if (app.get("fv_mm") or 0) > 0:
            return True
        if (app.get("cost_mm") or 0) > 0:
            return True
        if app.get("is_non_accrual") or app.get("is_pik"):
            return True
    return False


def _borrower_key(issuer: str) -> str:
    normalized = _normalize_borrower_name(issuer)
    key = re.sub(r"\s+", " ", normalized.lower().strip())
    key = re.sub(r"[,\.;]", "", key)
    key = re.sub(
        r"(?:\s+\b(?:llc|inc|corp|corporation|ltd|lp|co|company)\b)+$",
        "",
        key,
    ).strip()
    return key


def _borrower_family_key(issuer: str) -> str:
    normalized = _normalize_borrower_name(issuer).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    split_tokens = [token for token in normalized.split() if token]
    raw_tokens: list[str] = []
    idx = 0
    while idx < len(split_tokens):
        token = split_tokens[idx]
        if len(token) == 1 and token.isalpha():
            letters = [token]
            j = idx + 1
            while j < len(split_tokens) and len(split_tokens[j]) == 1 and split_tokens[j].isalpha():
                letters.append(split_tokens[j])
                j += 1
            if len(letters) >= 2:
                raw_tokens.append("".join(letters))
                idx = j
                continue
        raw_tokens.append(token)
        idx += 1
    legal_tokens = {"llc", "inc", "corp", "corporation", "ltd", "limited", "lp", "co", "company"}
    raw_non_legal = [token for token in raw_tokens if token not in legal_tokens]
    family_tokens = [
        token
        for token in raw_tokens
        if token not in _BORROWER_GENERIC_TOKENS
        and token not in legal_tokens
        and not token.isdigit()
    ]
    if len(family_tokens) >= 2:
        token_count = 3 if family_tokens[0] in _FAMILY_PREFIX_TOKENS and len(family_tokens) >= 3 else 2
        chosen = family_tokens[:token_count]
    elif family_tokens:
        if raw_non_legal and raw_non_legal[0] in _FAMILY_PREFIX_TOKENS and len(raw_non_legal) >= 2:
            chosen = raw_non_legal[:2]
        else:
            chosen = family_tokens[:1]
    else:
        chosen = raw_non_legal[:2] if raw_non_legal else raw_tokens[:2]
    return " ".join(chosen).strip()


def _load_fund_metadata(universe_path: Path = UNIVERSE_PATH) -> dict[str, dict]:
    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    funds = payload.get("funds", [])
    return {
        fund.get("ticker", "").upper(): {
            "name": fund.get("name", ""),
            "manager": fund.get("manager", ""),
            "type": fund.get("type", ""),
            "sector_focus": fund.get("sector_focus", ""),
        }
        for fund in funds
        if fund.get("ticker")
    }


def _load_family_alias_overrides(alias_path: Path = BORROWER_FAMILY_ALIASES) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(alias_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    overrides = payload.get("borrower_key_overrides", {})
    clean_overrides: dict[str, dict[str, str]] = {}
    for borrower_key, config in overrides.items():
        if not borrower_key or not isinstance(config, dict):
            continue
        family_key = str(config.get("family_key", "")).strip().lower()
        family_name = str(config.get("family_name", "")).strip()
        if not family_key:
            continue
        clean_overrides[str(borrower_key).strip().lower()] = {
            "family_key": family_key,
            "family_name": family_name,
        }
    return clean_overrides


def _parse_rate_pct(rate_str: str) -> Optional[float]:
    if not rate_str:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", rate_str)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _parse_maturity_date(maturity: str) -> Optional[date]:
    if not maturity:
        return None
    parts = maturity.split("/")
    try:
        if len(parts) == 2:
            month, year = int(parts[0]), int(parts[1])
            return date(year, month, 15)
        if len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
            return date(year, month, day)
    except ValueError:
        return None
    return None


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _weighted_average(pairs: list[tuple[float | None, float]]) -> float | None:
    usable = [(value, weight) for value, weight in pairs if value is not None and weight > 0]
    if not usable:
        return None
    total_weight = sum(weight for _, weight in usable)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in usable) / total_weight


def _build_borrower_history(cache_dir: Path, current_keys: set[str]) -> dict[str, list[dict]]:
    history_index: dict[str, dict[str, dict[str, Any]]] = {}

    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.name.startswith("_"):
            continue
        try:
            positions = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        for pos in positions:
            issuer = _normalize_borrower_name(pos.get("issuer", ""))
            if not issuer or len(issuer) < 2 or _is_equity_noise(issuer) or _is_borrower_noise(issuer):
                continue

            key = _borrower_key(issuer)
            if key not in current_keys:
                continue

            period = pos.get("period", "")
            fund = pos.get("fund_ticker", "")
            if not period or not fund:
                continue

            period_rec = history_index.setdefault(key, {}).setdefault(period, {
                "period": period,
                "funds": set(),
                "total_fv_mm": 0.0,
                "total_cost_mm": 0.0,
                "non_accrual_funds": set(),
                "pik_funds": set(),
            })
            period_rec["funds"].add(fund)
            period_rec["total_fv_mm"] += _clean_position_exposure(pos.get("fv_mm")) or 0.0
            period_rec["total_cost_mm"] += _clean_position_exposure(pos.get("cost_mm")) or 0.0
            if pos.get("is_non_accrual"):
                period_rec["non_accrual_funds"].add(fund)
            if pos.get("is_pik"):
                period_rec["pik_funds"].add(fund)

    history_rows: dict[str, list[dict]] = {}
    for key, period_map in history_index.items():
        rows = []
        for period in sorted(period_map):
            row = period_map[period]
            total_cost = row["total_cost_mm"]
            total_fv = row["total_fv_mm"]
            unrealized_pct = None
            if total_cost > 0 and total_fv > 0:
                unrealized_pct = round((total_fv - total_cost) / total_cost, 4)
            rows.append({
                "period": period,
                "fund_count": len(row["funds"]),
                "funds": sorted(row["funds"]),
                "total_fv_mm": round(row["total_fv_mm"], 4),
                "total_cost_mm": round(row["total_cost_mm"], 4),
                "unrealized_pct": unrealized_pct,
                "non_accrual_funds": sorted(row["non_accrual_funds"]),
                "pik_funds": sorted(row["pik_funds"]),
            })
        history_rows[key] = rows

    return history_rows


def _enrich_borrower_record(rec: dict, history_rows: list[dict], fund_meta: dict[str, dict]) -> None:
    by_fund: dict[str, list[dict]] = {}
    for app in rec.get("appearances", []):
        fund = app.get("fund")
        if fund:
            by_fund.setdefault(fund, []).append(app)

    current_by_fund: dict[str, dict] = {}
    nearest_maturity_date: date | None = None
    nearest_maturity_str = ""
    weighted_rate_pairs: list[tuple[float | None, float]] = []
    weighted_spread_pairs: list[tuple[float | None, float]] = []

    for fund, apps in sorted(by_fund.items()):
        meta = fund_meta.get(fund, {})
        total_fv = sum(app.get("fv_mm") or 0.0 for app in apps)
        total_cost = sum(app.get("cost_mm") or 0.0 for app in apps)
        industries = sorted({app.get("industry", "") for app in apps if app.get("industry")})
        invest_types = sorted({app.get("invest_type", "") for app in apps if app.get("invest_type")})
        forms = sorted({app.get("form", "") for app in apps if app.get("form")})
        maturities = [(app.get("maturity", ""), _parse_maturity_date(app.get("maturity", ""))) for app in apps]
        maturity_pairs = [(raw, mat_date) for raw, mat_date in maturities if mat_date is not None]
        fund_nearest_str = ""
        fund_nearest_date: date | None = None
        if maturity_pairs:
            fund_nearest_str, fund_nearest_date = min(maturity_pairs, key=lambda item: item[1])
            if nearest_maturity_date is None or fund_nearest_date < nearest_maturity_date:
                nearest_maturity_date = fund_nearest_date
                nearest_maturity_str = fund_nearest_str

        for app in apps:
            weight = app.get("fv_mm") or app.get("cost_mm") or 0.0
            weighted_rate_pairs.append((_parse_rate_pct(app.get("rate_str", "")), weight))
            spread = app.get("spread_bps")
            weighted_spread_pairs.append((float(spread) if spread is not None else None, weight))

        fund_unrealized_pct = None
        if total_cost > 0 and total_fv > 0:
            fund_unrealized_pct = round((total_fv - total_cost) / total_cost, 4)

        current_by_fund[fund] = {
            "fund": fund,
            "fund_name": meta.get("name", ""),
            "manager": meta.get("manager", ""),
            "fund_type": meta.get("type", ""),
            "sector_focus": meta.get("sector_focus", ""),
            "period": max((app.get("period", "") for app in apps), default=""),
            "form": forms[0] if len(forms) == 1 else ", ".join(forms),
            "position_count": len(apps),
            "fv_mm": round(total_fv, 4),
            "cost_mm": round(total_cost, 4),
            "unrealized_pct": fund_unrealized_pct,
            "is_non_accrual": any(app.get("is_non_accrual") for app in apps),
            "is_pik": any(app.get("is_pik") for app in apps),
            "nearest_maturity": fund_nearest_str,
            "nearest_maturity_date": fund_nearest_date.isoformat() if fund_nearest_date else "",
            "industries": industries,
            "invest_types": invest_types,
        }

    managers = sorted({summary["manager"] for summary in current_by_fund.values() if summary.get("manager")})
    fund_type_counter = Counter(
        summary["fund_type"] for summary in current_by_fund.values() if summary.get("fund_type")
    )
    largest_fund = None
    if current_by_fund:
        largest_fund = max(current_by_fund.values(), key=lambda summary: summary.get("fv_mm") or 0.0)

    rec["current_by_fund"] = current_by_fund
    rec["managers"] = managers
    rec["manager_count"] = len(managers)
    rec["fund_type_breakdown"] = dict(sorted(fund_type_counter.items()))
    rec["nearest_maturity"] = nearest_maturity_str
    rec["nearest_maturity_date"] = nearest_maturity_date.isoformat() if nearest_maturity_date else ""
    rec["weighted_avg_rate_pct"] = _round_or_none(_weighted_average(weighted_rate_pairs), 2)
    rec["weighted_avg_spread_bps"] = _round_or_none(_weighted_average(weighted_spread_pairs), 1)
    rec["largest_fund_exposure"] = {
        "fund": largest_fund["fund"],
        "manager": largest_fund.get("manager", ""),
        "fv_mm": largest_fund.get("fv_mm", 0.0),
    } if largest_fund else None

    periods_seen = [row["period"] for row in history_rows]
    rec["history_by_period"] = history_rows
    rec["periods_seen"] = periods_seen
    rec["period_count"] = len(periods_seen)
    rec["first_seen_period"] = periods_seen[0] if periods_seen else ""
    rec["last_seen_period"] = periods_seen[-1] if periods_seen else ""
    rec["peak_fund_count"] = max((row["fund_count"] for row in history_rows), default=rec.get("fund_count", 0))
    rec["peak_total_fv_mm"] = _round_or_none(max((row["total_fv_mm"] for row in history_rows), default=0.0), 4)


def _borrower_surveillance_score(rec: dict) -> int:
    score = int(rec.get("stress_score") or 0) * 2
    score += min(4, rec.get("fund_count", 0))
    score += min(3, rec.get("manager_count", 0))

    if rec.get("is_non_accrual_any"):
        score += 3
    if len(rec.get("non_accrual_funds") or []) >= 2:
        score += 2
    if rec.get("is_pik_any") and rec.get("fund_count", 0) >= 2:
        score += 1

    urg = rec.get("unrealized_pct")
    if urg is not None:
        if urg <= -0.25:
            score += 2
        elif urg <= -0.10:
            score += 1

    nearest = rec.get("nearest_maturity_date")
    if nearest:
        try:
            maturity_date = date.fromisoformat(nearest)
            days_to_maturity = (maturity_date - date.today()).days
            if days_to_maturity <= 540:
                score += 1
        except ValueError:
            pass

    if rec.get("peak_fund_count", 0) > rec.get("fund_count", 0):
        score += 1

    return score


def _build_borrower_families(
    borrowers: dict[str, dict],
    family_alias_overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict]:
    families: dict[str, dict] = {}
    alias_overrides = family_alias_overrides or {}

    for borrower_key, rec in borrowers.items():
        override = alias_overrides.get(borrower_key, {})
        family_key = override.get("family_key") or _borrower_family_key(rec.get("canonical_name", ""))
        if not family_key:
            family_key = borrower_key
        rec["family_key"] = family_key
        rec["family_override_applied"] = bool(override)
        if override.get("family_name"):
            rec["family_name_override"] = override["family_name"]

        family = families.setdefault(
            family_key,
            {
                "family_key": family_key,
                "family_name": rec.get("canonical_name", ""),
                "members": [],
                "member_keys": [],
                "borrower_count": 0,
                "funds": set(),
                "managers": set(),
                "non_accrual_funds": set(),
                "pik_funds": set(),
                "industries": Counter(),
                "total_fv_mm": 0.0,
                "total_cost_mm": 0.0,
                "periods_seen": set(),
                "peak_fund_count": 0,
                "peak_total_fv_mm": 0.0,
                "nearest_maturity_date": "",
                "nearest_maturity": "",
                "weighted_avg_rate_pairs": [],
                "weighted_avg_spread_pairs": [],
                "top_member_name": rec.get("canonical_name", ""),
                "top_member_fv_mm": rec.get("total_fv_mm") or 0.0,
                "preferred_family_name": override.get("family_name", ""),
                "override_applied": bool(override),
                "stress_score": 0,
                "surveillance_score": 0,
                "is_non_accrual_any": False,
                "is_pik_any": False,
                "current_by_fund": {},
            },
        )
        if override.get("family_name"):
            family["preferred_family_name"] = override["family_name"]
        if override:
            family["override_applied"] = True

        family["members"].append(rec.get("canonical_name", ""))
        family["member_keys"].append(borrower_key)
        family["funds"].update(rec.get("funds", []))
        family["managers"].update(rec.get("managers", []))
        family["non_accrual_funds"].update(rec.get("non_accrual_funds", []))
        family["pik_funds"].update(rec.get("pik_funds", []))
        family["total_fv_mm"] += rec.get("total_fv_mm") or 0.0
        family["total_cost_mm"] += rec.get("total_cost_mm") or 0.0
        family["periods_seen"].update(rec.get("periods_seen", []))
        family["peak_fund_count"] = max(family["peak_fund_count"], rec.get("peak_fund_count", 0))
        family["peak_total_fv_mm"] = max(family["peak_total_fv_mm"], rec.get("peak_total_fv_mm") or 0.0)
        family["stress_score"] = max(family["stress_score"], rec.get("stress_score", 0))
        family["surveillance_score"] = max(family["surveillance_score"], rec.get("surveillance_score", 0))
        family["is_non_accrual_any"] = family["is_non_accrual_any"] or rec.get("is_non_accrual_any", False)
        family["is_pik_any"] = family["is_pik_any"] or rec.get("is_pik_any", False)

        if (rec.get("total_fv_mm") or 0.0) > family["top_member_fv_mm"]:
            family["top_member_name"] = rec.get("canonical_name", "")
            family["top_member_fv_mm"] = rec.get("total_fv_mm") or 0.0

        nearest_date = rec.get("nearest_maturity_date") or ""
        if nearest_date and (not family["nearest_maturity_date"] or nearest_date < family["nearest_maturity_date"]):
            family["nearest_maturity_date"] = nearest_date
            family["nearest_maturity"] = rec.get("nearest_maturity", "")

        for industry in rec.get("industries", []):
            if industry:
                family["industries"][industry] += 1

        for app in rec.get("appearances", []):
            weight = app.get("fv_mm") or app.get("cost_mm") or 0.0
            if weight > 0:
                family["weighted_avg_rate_pairs"].append((_parse_rate_pct(app.get("rate_str", "")), weight))
                spread = app.get("spread_bps")
                family["weighted_avg_spread_pairs"].append((float(spread) if spread is not None else None, weight))

        for fund, summary in rec.get("current_by_fund", {}).items():
            fund_rec = family["current_by_fund"].setdefault(
                fund,
                {
                    "fund": fund,
                    "fund_name": summary.get("fund_name", ""),
                    "manager": summary.get("manager", ""),
                    "fund_type": summary.get("fund_type", ""),
                    "sector_focus": summary.get("sector_focus", ""),
                    "period": summary.get("period", ""),
                    "form": summary.get("form", ""),
                    "position_count": 0,
                    "fv_mm": 0.0,
                    "cost_mm": 0.0,
                    "is_non_accrual": False,
                    "is_pik": False,
                    "member_names": set(),
                },
            )
            if summary.get("period", "") > fund_rec.get("period", ""):
                fund_rec["period"] = summary.get("period", "")
                fund_rec["form"] = summary.get("form", "")
            fund_rec["position_count"] += summary.get("position_count", 0)
            fund_rec["fv_mm"] += summary.get("fv_mm") or 0.0
            fund_rec["cost_mm"] += summary.get("cost_mm") or 0.0
            fund_rec["is_non_accrual"] = fund_rec["is_non_accrual"] or summary.get("is_non_accrual", False)
            fund_rec["is_pik"] = fund_rec["is_pik"] or summary.get("is_pik", False)
            if rec.get("canonical_name"):
                fund_rec["member_names"].add(rec["canonical_name"])

    family_records: dict[str, dict] = {}
    for family_key, family in families.items():
        total_cost = family["total_cost_mm"]
        total_fv = family["total_fv_mm"]
        unrealized_pct = None
        if total_cost > 0 and total_fv >= 0:
            unrealized_pct = round((total_fv - total_cost) / total_cost, 4)

        members = sorted(set(family["members"]))
        member_keys = sorted(set(family["member_keys"]))
        funds = sorted(family["funds"])
        managers = sorted(family["managers"])
        non_accrual_funds = sorted(family["non_accrual_funds"])
        pik_funds = sorted(family["pik_funds"])
        periods_seen = sorted(family["periods_seen"])
        industries = [name for name, _ in family["industries"].most_common()]
        current_by_fund = {}
        for fund, summary in sorted(family["current_by_fund"].items()):
            current_by_fund[fund] = {
                **summary,
                "fv_mm": round(summary["fv_mm"], 4),
                "cost_mm": round(summary["cost_mm"], 4),
                "member_names": sorted(summary["member_names"]),
            }

        family_records[family_key] = {
            "family_key": family_key,
            "family_name": (
                family.get("preferred_family_name")
                or family["top_member_name"]
                or (members[0] if members else family_key.title())
            ),
            "borrower_count": len(member_keys),
            "borrower_names": members,
            "borrower_keys": member_keys,
            "fund_count": len(funds),
            "funds": funds,
            "manager_count": len(managers),
            "managers": managers,
            "total_fv_mm": round(total_fv, 4),
            "total_cost_mm": round(total_cost, 4),
            "unrealized_pct": unrealized_pct,
            "nearest_maturity_date": family["nearest_maturity_date"],
            "nearest_maturity": family["nearest_maturity"],
            "weighted_avg_rate_pct": _round_or_none(_weighted_average(family["weighted_avg_rate_pairs"]), 2),
            "weighted_avg_spread_bps": _round_or_none(_weighted_average(family["weighted_avg_spread_pairs"]), 1),
            "is_non_accrual_any": family["is_non_accrual_any"],
            "non_accrual_funds": non_accrual_funds,
            "is_pik_any": family["is_pik_any"],
            "pik_funds": pik_funds,
            "first_seen_period": periods_seen[0] if periods_seen else "",
            "last_seen_period": periods_seen[-1] if periods_seen else "",
            "period_count": len(periods_seen),
            "peak_fund_count": family["peak_fund_count"],
            "peak_total_fv_mm": _round_or_none(family["peak_total_fv_mm"], 4),
            "industries": industries,
            "stress_score": family["stress_score"],
            "stress_tier": _stress_tier(family["stress_score"]),
            "surveillance_score": family["surveillance_score"] + min(3, max(0, len(member_keys) - 1)),
            "current_by_fund": current_by_fund,
            "override_applied": family.get("override_applied", False),
        }

    return family_records


def _review_token_signature(name: str) -> set[str]:
    return _substantive_borrower_tokens(_normalize_borrower_name(name))


def _name_contains(a: str, b: str) -> bool:
    left = re.sub(r"[^a-z0-9]+", " ", _normalize_borrower_name(a).lower()).strip()
    right = re.sub(r"[^a-z0-9]+", " ", _normalize_borrower_name(b).lower()).strip()
    shorter, longer = sorted([left, right], key=len)
    return bool(shorter) and shorter in longer


def _suggest_family_key(rec_a: dict, rec_b: dict, shared_tokens: set[str]) -> str:
    if shared_tokens:
        tokens = sorted(shared_tokens)
        return " ".join(tokens[:2])
    family_keys = [rec_a.get("family_key", ""), rec_b.get("family_key", "")]
    family_keys = [key for key in family_keys if key]
    return min(family_keys, key=len) if family_keys else ""


def _build_family_review_candidates(
    borrowers: dict[str, dict],
    families: dict[str, dict],
) -> dict[str, list[dict]]:
    merge_candidates: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    token_index: dict[str, set[str]] = {}
    token_signatures: dict[str, set[str]] = {}

    for borrower_key, rec in borrowers.items():
        tokens = _review_token_signature(rec.get("canonical_name", ""))
        token_signatures[borrower_key] = tokens
        for token in tokens:
            token_index.setdefault(token, set()).add(borrower_key)

    for borrower_key, rec in borrowers.items():
        candidate_keys: set[str] = set()
        for token in token_signatures.get(borrower_key, set()):
            if len(token_index.get(token, ())) <= 25:
                candidate_keys.update(token_index.get(token, set()))

        for other_key in candidate_keys:
            if other_key <= borrower_key:
                continue
            other = borrowers.get(other_key)
            if other is None:
                continue
            if rec.get("family_key") == other.get("family_key"):
                continue

            pair = (borrower_key, other_key)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            tokens_a = token_signatures.get(borrower_key, set())
            tokens_b = token_signatures.get(other_key, set())
            shared_tokens = tokens_a & tokens_b
            if not shared_tokens:
                continue

            similarity = len(shared_tokens) / max(1, min(len(tokens_a), len(tokens_b)))
            shared_funds = sorted(set(rec.get("funds", [])) & set(other.get("funds", [])))
            shared_managers = sorted(set(rec.get("managers", [])) & set(other.get("managers", [])))
            industry_match = bool(set(rec.get("industries", [])) & set(other.get("industries", [])))
            contains = _name_contains(rec.get("canonical_name", ""), other.get("canonical_name", ""))
            combined_fv = (rec.get("total_fv_mm") or 0.0) + (other.get("total_fv_mm") or 0.0)
            single_token_match = len(shared_tokens) == 1

            if not (
                similarity >= 0.75
                or (similarity >= 0.5 and (shared_funds or shared_managers or industry_match))
                or (contains and (shared_funds or shared_managers or industry_match))
            ):
                continue
            if single_token_match and not (contains or industry_match):
                continue
            if combined_fv < 5 and not (shared_funds or shared_managers):
                continue

            merge_candidates.append(
                {
                    "Borrower A": rec.get("canonical_name", ""),
                    "Borrower B": other.get("canonical_name", ""),
                    "Family A": rec.get("family_key", ""),
                    "Family B": other.get("family_key", ""),
                    "Similarity": round(similarity, 3),
                    "Shared Tokens": ", ".join(sorted(shared_tokens)),
                    "Shared Fund Count": len(shared_funds),
                    "Shared Funds": ", ".join(shared_funds),
                    "Shared Manager Count": len(shared_managers),
                    "Shared Managers": ", ".join(shared_managers),
                    "Industry Match": industry_match,
                    "Combined FV ($M)": round(combined_fv, 4),
                    "Suggested Family Key": _suggest_family_key(rec, other, shared_tokens),
                    "Override Present": rec.get("family_override_applied", False) or other.get("family_override_applied", False),
                }
            )

    split_candidates: list[dict] = []
    for family in families.values():
        member_keys = family.get("borrower_keys", [])
        if len(member_keys) < 2:
            continue

        max_similarity = 0.0
        shared_fund_pairs = 0
        for idx, left_key in enumerate(member_keys):
            left = borrowers.get(left_key, {})
            left_tokens = token_signatures.get(left_key, set())
            left_funds = set(left.get("funds", []))
            for right_key in member_keys[idx + 1:]:
                right = borrowers.get(right_key, {})
                right_tokens = token_signatures.get(right_key, set())
                right_funds = set(right.get("funds", []))
                shared_tokens = left_tokens & right_tokens
                if shared_tokens:
                    similarity = len(shared_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
                    max_similarity = max(max_similarity, similarity)
                if left_funds & right_funds:
                    shared_fund_pairs += 1

        if max_similarity >= 0.75 and shared_fund_pairs > 0:
            continue
        if shared_fund_pairs == 0 and max_similarity >= 0.9:
            continue

        reason = "Low token cohesion"
        if shared_fund_pairs == 0:
            reason = "No shared fund overlap"
        elif max_similarity < 0.35:
            reason = "Low token cohesion"

        split_candidates.append(
            {
                "Family": family.get("family_name", ""),
                "Family Key": family.get("family_key", ""),
                "Borrower Count": family.get("borrower_count", 0),
                "Borrowers": ", ".join(family.get("borrower_names", [])),
                "Fund Count": family.get("fund_count", 0),
                "Funds": ", ".join(family.get("funds", [])),
                "Max Pair Similarity": round(max_similarity, 3),
                "Shared Fund Pairs": shared_fund_pairs,
                "Total FV ($M)": round(family.get("total_fv_mm") or 0.0, 4),
                "Override Applied": family.get("override_applied", False),
                "Reason": reason,
            }
        )

    merge_candidates.sort(
        key=lambda row: (
            -(row["Similarity"] or 0),
            -(row["Shared Fund Count"] or 0),
            -(row["Shared Manager Count"] or 0),
            -(row["Combined FV ($M)"] or 0),
            row["Borrower A"],
        )
    )
    split_candidates.sort(
        key=lambda row: (
            row["Override Applied"],
            row["Max Pair Similarity"] or 0,
            row["Shared Fund Pairs"] or 0,
            -(row["Total FV ($M)"] or 0),
            row["Family"],
        )
    )

    return {
        "merge_candidates": merge_candidates,
        "split_candidates": split_candidates,
    }


def _write_review_csv(rows: list[dict], output_path: Path, fallback_fields: list[str]) -> list[dict]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(rows[0].keys()) if rows else fallback_fields
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_borrower_family_watchlist(
    db: dict,
    output_path: Path = BORROWER_FAMILY_WATCHLIST,
) -> list[dict]:
    rows: list[dict] = []
    families = db.get("families", {})

    for rec in families.values():
        industries = rec.get("industries", [])
        rows.append({
            "Family": rec.get("family_name", ""),
            "Family Key": rec.get("family_key", ""),
            "Surveillance Score": rec.get("surveillance_score", 0),
            "Stress Tier": rec.get("stress_tier", "GREEN"),
            "Stress Score": rec.get("stress_score", 0),
            "Borrower Count": rec.get("borrower_count", 0),
            "Fund Count": rec.get("fund_count", 0),
            "Manager Count": rec.get("manager_count", 0),
            "Borrowers": ", ".join(rec.get("borrower_names", [])),
            "Funds": ", ".join(rec.get("funds", [])),
            "Managers": ", ".join(rec.get("managers", [])),
            "Primary Industry": industries[0] if industries else "",
            "Total FV ($M)": rec.get("total_fv_mm"),
            "Total Cost ($M)": rec.get("total_cost_mm"),
            "Unrealized %": rec.get("unrealized_pct"),
            "Nearest Maturity": rec.get("nearest_maturity", ""),
            "Weighted Avg Rate %": rec.get("weighted_avg_rate_pct"),
            "Weighted Avg Spread (bps)": rec.get("weighted_avg_spread_bps"),
            "Non-Accrual": rec.get("is_non_accrual_any", False),
            "Non-Accrual Funds": ", ".join(rec.get("non_accrual_funds", [])),
            "PIK": rec.get("is_pik_any", False),
            "PIK Funds": ", ".join(rec.get("pik_funds", [])),
            "First Seen": rec.get("first_seen_period", ""),
            "Last Seen": rec.get("last_seen_period", ""),
            "Period Count": rec.get("period_count", 0),
        })

    rows.sort(
        key=lambda row: (
            -(row["Surveillance Score"] or 0),
            -(row["Borrower Count"] or 0),
            -(row["Fund Count"] or 0),
            -(row["Total FV ($M)"] or 0),
            row["Family"],
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(rows[0].keys()) if rows else [
            "Family", "Family Key", "Surveillance Score", "Stress Tier", "Stress Score"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows


def write_family_review_candidates(
    db: dict,
    merge_output_path: Path = BORROWER_FAMILY_MERGE_CANDIDATES,
    split_output_path: Path = BORROWER_FAMILY_SPLIT_CANDIDATES,
) -> dict[str, list[dict]]:
    review = db.get("family_review", {})
    merge_rows = _write_review_csv(
        review.get("merge_candidates", []),
        merge_output_path,
        [
            "Borrower A", "Borrower B", "Family A", "Family B", "Similarity",
            "Shared Tokens", "Shared Fund Count", "Shared Funds", "Shared Manager Count",
            "Shared Managers", "Industry Match", "Combined FV ($M)", "Suggested Family Key",
            "Override Present",
        ],
    )
    split_rows = _write_review_csv(
        review.get("split_candidates", []),
        split_output_path,
        [
            "Family", "Family Key", "Borrower Count", "Borrowers", "Fund Count", "Funds",
            "Max Pair Similarity", "Shared Fund Pairs", "Total FV ($M)", "Override Applied", "Reason",
        ],
    )
    return {"merge_candidates": merge_rows, "split_candidates": split_rows}


def write_borrower_watchlist(db: dict, output_path: Path = BORROWER_WATCHLIST) -> list[dict]:
    rows: list[dict] = []
    borrowers = db.get("borrowers", {})

    for rec in borrowers.values():
        largest = rec.get("largest_fund_exposure") or {}
        primary_industry = rec.get("industries", [])
        rows.append({
            "Issuer": rec.get("canonical_name", ""),
            "Family Key": rec.get("family_key", ""),
            "Surveillance Score": rec.get("surveillance_score", 0),
            "Stress Tier": rec.get("stress_tier", "GREEN"),
            "Stress Score": rec.get("stress_score", 0),
            "Fund Count": rec.get("fund_count", 0),
            "Peak Fund Count": rec.get("peak_fund_count", 0),
            "Manager Count": rec.get("manager_count", 0),
            "Funds": ", ".join(rec.get("funds", [])),
            "Managers": ", ".join(rec.get("managers", [])),
            "Primary Industry": primary_industry[0] if primary_industry else "",
            "Total FV ($M)": rec.get("total_fv_mm"),
            "Total Cost ($M)": rec.get("total_cost_mm"),
            "Unrealized %": rec.get("unrealized_pct"),
            "Nearest Maturity": rec.get("nearest_maturity", ""),
            "Weighted Avg Rate %": rec.get("weighted_avg_rate_pct"),
            "Weighted Avg Spread (bps)": rec.get("weighted_avg_spread_bps"),
            "Non-Accrual": rec.get("is_non_accrual_any", False),
            "Non-Accrual Funds": ", ".join(rec.get("non_accrual_funds", [])),
            "PIK": rec.get("is_pik_any", False),
            "PIK Funds": ", ".join(rec.get("pik_funds", [])),
            "First Seen": rec.get("first_seen_period", ""),
            "Last Seen": rec.get("last_seen_period", ""),
            "Period Count": rec.get("period_count", 0),
            "Largest Fund": largest.get("fund", ""),
            "Largest Fund FV ($M)": largest.get("fv_mm"),
        })

    rows.sort(
        key=lambda row: (
            -(row["Surveillance Score"] or 0),
            -(row["Fund Count"] or 0),
            -(row["Manager Count"] or 0),
            -(row["Total FV ($M)"] or 0),
            row["Issuer"],
        )
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(rows[0].keys()) if rows else [
            "Issuer", "Surveillance Score", "Stress Tier", "Stress Score"
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows

def build_borrower_db(
    cache_dir: Path = PORTFOLIO_CACHE,
    output_path: Path = BORROWER_DB,
    universe_path: Path = UNIVERSE_PATH,
    watchlist_path: Path = BORROWER_WATCHLIST,
    family_watchlist_path: Path = BORROWER_FAMILY_WATCHLIST,
    family_alias_path: Path = BORROWER_FAMILY_ALIASES,
    family_merge_candidates_path: Path = BORROWER_FAMILY_MERGE_CANDIDATES,
    family_split_candidates_path: Path = BORROWER_FAMILY_SPLIT_CANDIDATES,
) -> dict[str, Any]:
    """Aggregate all cached SOI files into a cross-fund borrower database.

    Returns dict with:
      borrowers:  dict[issuer_name, BorrowerRecord]
      meta:       {build_time, funds_included, total_positions}
    """
    fund_meta = _load_fund_metadata(universe_path)
    family_alias_overrides = _load_family_alias_overrides(family_alias_path)

    # Keep only the most recent period per fund ticker (TICKER_YYYY-MM-DD.json).
    # Without this, aggregating Q3 + Q4 files would double-count every position.
    _ticker_files: dict[str, Path] = {}
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.name.startswith("_"):
            continue
        parts = fpath.stem.split("_", 1)
        if len(parts) != 2:
            _ticker_files.setdefault(fpath.stem, fpath)
            continue
        ticker, period = parts[0].upper(), parts[1]
        if ticker not in _ticker_files or period > _ticker_files[ticker].stem.split("_", 1)[1]:
            _ticker_files[ticker] = fpath
    files = sorted(_ticker_files.values())

    # issuer_key -> record
    borrowers: dict[str, dict] = {}
    total_positions = 0

    for fpath in files:
        try:
            positions = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        for pos in positions:
            issuer = _normalize_borrower_name(pos.get("issuer", ""))
            if not issuer or len(issuer) < 2:
                continue
            # Skip equity/instrument-type noise before indexing
            if _is_equity_noise(issuer) or _is_borrower_noise(issuer):
                continue
            # Normalize issuer name for matching
            key = _borrower_key(issuer)

            if key not in borrowers:
                borrowers[key] = {
                    "canonical_name": issuer,
                    "appearances": [],
                    "fund_count": 0,
                    "funds": [],
                    "total_fv_mm": 0.0,
                    "total_cost_mm": 0.0,
                    "is_pik_any": False,
                    "is_non_accrual_any": False,
                    "non_accrual_funds": [],
                    "pik_funds": [],
                    "industries": [],
                    "invest_types": [],
                }

            rec = borrowers[key]
            ticker = pos.get("fund_ticker", "")
            period = pos.get("period", "")

            app = {
                "fund": ticker,
                "period": period,
                "form": pos.get("filing_type", ""),
                "industry": pos.get("industry", ""),
                "invest_type": pos.get("invest_type", ""),
                "rate_str": pos.get("rate_str", ""),
                "maturity": pos.get("maturity", ""),
                "cost_mm": _clean_position_exposure(pos.get("cost_mm")),
                "fv_mm": _clean_position_exposure(pos.get("fv_mm")),
                "pct_nav": pos.get("pct_nav"),
                "is_pik": pos.get("is_pik", False),
                "is_non_accrual": pos.get("is_non_accrual", False),
                "is_equity": pos.get("is_equity", False),
                "spread_bps": pos.get("spread_bps"),
            }
            rec["appearances"].append(app)

            if ticker not in rec["funds"]:
                rec["funds"].append(ticker)
                rec["fund_count"] = len(rec["funds"])

            if app["fv_mm"] is not None:
                rec["total_fv_mm"] = round(rec["total_fv_mm"] + app["fv_mm"], 4)
                rec["_fv_count"] = rec.get("_fv_count", 0) + 1
            if app["cost_mm"] is not None:
                rec["total_cost_mm"] = round(rec["total_cost_mm"] + app["cost_mm"], 4)
                rec["_cost_count"] = rec.get("_cost_count", 0) + 1

            if pos.get("is_pik"):
                rec["is_pik_any"] = True
                if ticker not in rec["pik_funds"]:
                    rec["pik_funds"].append(ticker)
            if pos.get("is_non_accrual"):
                rec["is_non_accrual_any"] = True
                if ticker not in rec["non_accrual_funds"]:
                    rec["non_accrual_funds"].append(ticker)

            ind = pos.get("industry", "")
            if ind and ind not in rec["industries"]:
                rec["industries"].append(ind)
            inv_type = pos.get("invest_type", "")
            if inv_type and inv_type not in rec["invest_types"]:
                rec["invest_types"].append(inv_type)
            total_positions += 1

    borrowers = {
        key: rec
        for key, rec in borrowers.items()
        if _has_meaningful_borrower_exposure(rec)
    }
    total_positions = sum(len(rec.get("appearances", [])) for rec in borrowers.values())

    history = _build_borrower_history(cache_dir, set(borrowers.keys()))

    # Compute unrealized gain/loss % — only when BOTH cost and FV were actually parsed
    for rec in borrowers.values():
        cost = rec["total_cost_mm"]
        fv   = rec["total_fv_mm"]
        fv_count = rec.get("_fv_count", 0)
        cost_count = rec.get("_cost_count", 0)
        # Require at least one actual FV value AND one actual cost value
        if cost and cost > 0 and fv_count > 0 and cost_count > 0:
            rec["unrealized_pct"] = round((fv - cost) / cost, 4)
        else:
            rec["unrealized_pct"] = None
        # Clean up internal counters
        rec.pop("_fv_count", None)
        rec.pop("_cost_count", None)

        _enrich_borrower_record(rec, history.get(_borrower_key(rec["canonical_name"]), []), fund_meta)

    # Compute borrower stress tier for each record
    for rec in borrowers.values():
        rec["stress_score"] = _borrower_stress_score(rec)
        rec["stress_tier"] = _stress_tier(rec["stress_score"])
        rec["surveillance_score"] = _borrower_surveillance_score(rec)

    families = _build_borrower_families(borrowers, family_alias_overrides=family_alias_overrides)
    family_review = _build_family_review_candidates(borrowers, families)

    db = {
        "meta": {
            "build_time": datetime.now().isoformat(),
            "total_positions": total_positions,
            "unique_borrowers": len(borrowers),
            "unique_families": len(families),
            "cached_periods_indexed": sorted({
                period
                for hist_rows in history.values()
                for period in [row["period"] for row in hist_rows]
            }),
            "funds_included": sorted({
                app["fund"]
                for rec in borrowers.values()
                for app in rec["appearances"]
            }),
            "watchlist_path": str(watchlist_path),
            "family_watchlist_path": str(family_watchlist_path),
            "family_alias_path": str(family_alias_path),
            "family_alias_count": len(family_alias_overrides),
            "family_merge_candidates_path": str(family_merge_candidates_path),
            "family_split_candidates_path": str(family_split_candidates_path),
            "family_merge_candidate_count": len(family_review.get("merge_candidates", [])),
            "family_split_candidate_count": len(family_review.get("split_candidates", [])),
        },
        "borrowers": borrowers,
        "families": families,
        "family_review": family_review,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(db, indent=2), encoding="utf-8")
    write_borrower_watchlist(db, watchlist_path)
    write_borrower_family_watchlist(db, family_watchlist_path)
    write_family_review_candidates(
        db,
        merge_output_path=family_merge_candidates_path,
        split_output_path=family_split_candidates_path,
    )
    return db


def _borrower_stress_score(rec: dict) -> int:
    """Compute a 0-10 stress score for a single borrower record.

    Dimensions:
      - Unrealized loss depth (0-4 pts)
      - Non-accrual status     (0-3 pts)
      - PIK income             (0-1 pt)
      - Multi-fund contagion   (0-2 pts: 1pt for 2 funds, 2pts for 3+ funds)
    """
    score = 0
    urg = rec.get("unrealized_pct")
    if urg is not None:
        if urg < -0.90:
            score += 4
        elif urg < -0.50:
            score += 3
        elif urg < -0.30:
            score += 2
        elif urg < -0.15:
            score += 1

    if rec.get("is_non_accrual_any"):
        n_na_funds = len(rec.get("non_accrual_funds") or [])
        score += min(3, 1 + n_na_funds)

    if rec.get("is_pik_any"):
        score += 1

    n_funds = rec.get("fund_count", 0)
    if n_funds >= 3:
        score += 2
    elif n_funds >= 2:
        score += 1

    return min(score, 10)


def _stress_tier(score: int) -> str:
    if score >= 5:
        return "RED"
    elif score >= 3:
        return "ORANGE"
    elif score >= 1:
        return "YELLOW"
    return "GREEN"


# ---------------------------------------------------------------------------
# Live NA-rate computation (for red_flag_screener integration)
# ---------------------------------------------------------------------------

def latest_portfolio_cache_files(
    cache_dir: Path = PORTFOLIO_CACHE,
) -> dict[str, Path]:
    """Return the most recent cached SOI file for each ticker."""
    latest: dict[str, tuple[str, Path]] = {}
    for fpath in cache_dir.glob("*.json"):
        if fpath.name.startswith("_"):
            continue
        stem = fpath.stem
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        ticker, period = parts[0].upper(), parts[1]
        current = latest.get(ticker)
        if current is None or period > current[0]:
            latest[ticker] = (period, fpath)
    return {ticker: path for ticker, (_, path) in latest.items()}


def compute_live_na_rates(
    cache_dir: Path = PORTFOLIO_CACHE,
) -> dict[str, float]:
    """Compute non-accrual rate (NA FV / total FV) for each fund from cached SOI data.

    For each ticker, uses only the most recent cached period.  Returns a dict
    mapping ticker -> rate (0.0–1.0).  Tickers with no FV data are excluded.

    Suitable for injecting live nonaccrual_pct_fair_value into the screener
    in place of the static value from bdc_universe.json.
    """
    result: dict[str, float] = {}
    for ticker, fpath in latest_portfolio_cache_files(cache_dir).items():
        try:
            positions = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        total_fv = 0.0
        na_fv = 0.0
        for pos in positions:
            fv = pos.get("fv_mm")
            if fv is None or fv <= 0:
                continue
            total_fv += fv
            if pos.get("is_non_accrual"):
                na_fv += fv

        if total_fv > 0:
            result[ticker] = round(na_fv / total_fv, 6)

    return result


# ---------------------------------------------------------------------------
# Cross-fund analysis
# ---------------------------------------------------------------------------

def _is_equity_noise(issuer: str) -> bool:
    """Return True for equity/warrant/CLO/instrument positions that aren't named borrowers."""
    low = issuer.lower().strip()
    # Equity/structured finance positions (generic, non-company names)
    if any(x in low for x in [
        "common stock", "preferred stock", "warrants", "clo", "liquidating trust",
        "units)", "shares)", "class a units", "class b units", "class c units",
        "class a common", "series a preferred", "series b preferred",
        "net revenues interest", "preferred units", "membership interest",
        "partnership units", "series a-", "series b-",
        "common units", "preferred equity", "convertible preferred",
        "redeemable preferred", "residual profit interest",
        "funding 20",  # CLO vintages: "funding 2014-", "funding 2015-"
        "advisors funding", "loan trust", "loan advisors",
    ]):
        return True
    # Standalone generic equity terms (exact or near-exact matches)
    if low in ("common units", "preferred equity", "equity", "warrants",
               "membership units", "class a", "class b", "class c",
               "units", "shares"):
        return True
    # Instrument-type descriptions parsed as issuer names (OBDC/ARCC/FSK style)
    if any(x in low for x in [
        "first lien senior secured", "second lien senior secured",
        "senior secured revolving", "senior secured term", "delayed draw term",
        "revolving loan", "term loan", "senior note", "subordinated note",
        "subordinated loan", "mezzanine loan", "unsecured loan",
        "unsecured facility", "abf equity", "private equity",
        "second out", "third out", "super priority",
    ]):
        return True
    return False


def _is_reasonable_position(rec: dict) -> bool:
    """Return True if a position looks like a real company (not a parsing artifact)."""
    cost = rec.get("total_cost_mm", 0) or 0
    # Single-company positions shouldn't have cost > $500M (scale error indicator)
    if cost > 500:
        return False
    return True


def analyze_borrower_db(db: dict, min_funds: int = 2) -> None:
    """Print cross-fund concentration and stress analysis."""
    borrowers = db["borrowers"]
    families = db.get("families", {})
    meta = db["meta"]

    print(f"\nBorrower Database Summary")
    print(f"  Built:          {meta['build_time'][:19]}")
    print(f"  Total positions: {meta['total_positions']}")
    print(f"  Unique borrowers: {meta['unique_borrowers']}")
    print(f"  Unique families:  {meta.get('unique_families', 0)}")
    print(f"  Funds included:   {', '.join(meta['funds_included'])}")

    family_watchlist = sorted(
        families.values(),
        key=lambda rec: (
            -(rec.get("surveillance_score", 0)),
            -(rec.get("borrower_count", 0)),
            -(rec.get("fund_count", 0)),
            -(rec.get("total_fv_mm") or 0),
            rec["family_name"],
        ),
    )
    print(f"\n--- Top Borrower Families (15) ---")
    for rec in family_watchlist[:15]:
        industry = rec["industries"][0] if rec.get("industries") else "n/a"
        nearest = rec.get("nearest_maturity") or "n/a"
        urg = f"{rec['unrealized_pct']*100:+.1f}%" if rec.get("unrealized_pct") is not None else "n/a"
        print(
            f"  {rec['family_name'][:44]:<44}  "
            f"Score={rec.get('surveillance_score', 0):>2}  "
            f"Borrowers={rec.get('borrower_count', 0)}  "
            f"Funds={rec.get('fund_count', 0)}  "
            f"Mgrs={rec.get('manager_count', 0)}  "
            f"FV=${(rec.get('total_fv_mm') or 0):.1f}M  "
            f"URG={urg:<7}  "
            f"Mat={nearest:<8}  "
            f"{industry}"
        )

    watchlist = sorted(
        borrowers.values(),
        key=lambda rec: (
            -(rec.get("surveillance_score", 0)),
            -(rec.get("fund_count", 0)),
            -(rec.get("manager_count", 0)),
            -(rec.get("total_fv_mm") or 0),
            rec["canonical_name"],
        ),
    )
    print(f"\n--- Top Surveillance Watchlist (20) ---")
    for rec in watchlist[:20]:
        industry = rec["industries"][0] if rec.get("industries") else "n/a"
        nearest = rec.get("nearest_maturity") or "n/a"
        urg = f"{rec['unrealized_pct']*100:+.1f}%" if rec.get("unrealized_pct") is not None else "n/a"
        print(
            f"  {rec['canonical_name'][:44]:<44}  "
            f"Score={rec.get('surveillance_score', 0):>2}  "
            f"Stress={rec.get('stress_tier', 'GREEN'):<6}  "
            f"Funds={rec.get('fund_count', 0)}  "
            f"Mgrs={rec.get('manager_count', 0)}  "
            f"FV=${(rec.get('total_fv_mm') or 0):.1f}M  "
            f"URG={urg:<7}  "
            f"Mat={nearest:<8}  "
            f"{industry}"
        )

    # 1. Multi-lender issuers
    multi = [(k, r) for k, r in borrowers.items() if r["fund_count"] >= min_funds]
    multi.sort(key=lambda x: -x[1]["fund_count"])
    print(f"\n--- Issuers in {min_funds}+ BDC portfolios ({len(multi)}) ---")
    for key, rec in multi[:25]:
        fv_str = f"${rec['total_fv_mm']:.1f}M" if rec["total_fv_mm"] else "n/a"
        na_str = " [NON-ACCRUAL at " + "+".join(rec["non_accrual_funds"]) + "]" if rec["is_non_accrual_any"] else ""
        pik_str = " [PIK at " + "+".join(rec["pik_funds"]) + "]" if rec["is_pik_any"] else ""
        mgr_str = "  Mgrs=" + "/".join(rec.get("managers", [])) if rec.get("managers") else ""
        unr_str = ""
        if rec["unrealized_pct"] is not None:
            unr_str = f"  URG/L: {rec['unrealized_pct']*100:+.1f}%"
        print(f"  {rec['canonical_name'][:50]:<50}  "
              f"{rec['fund_count']}x  FV={fv_str}{unr_str}{na_str}{pik_str}{mgr_str}")

    # 2. Non-accrual crossover (any fund)
    non_acc = [(k, r) for k, r in borrowers.items() if r["is_non_accrual_any"]]
    non_acc.sort(key=lambda x: -len(x[1]["non_accrual_funds"]))
    print(f"\n--- Non-Accrual Borrowers ({len(non_acc)}) ---")
    for key, rec in non_acc[:20]:
        funds = ", ".join(rec["non_accrual_funds"])
        fv_str = f"${rec['total_fv_mm']:.1f}M" if rec["total_fv_mm"] else "n/a"
        unr = f"{rec['unrealized_pct']*100:+.1f}%" if rec["unrealized_pct"] is not None else "n/a"
        print(f"  {rec['canonical_name'][:50]:<50}  FV={fv_str}  URG={unr}  "
              f"Funds: {funds}")

    # 3. PIK borrowers across multiple funds
    pik_multi = [(k, r) for k, r in borrowers.items()
                 if r["is_pik_any"] and r["fund_count"] >= 2]
    pik_multi.sort(key=lambda x: -x[1]["fund_count"])
    if pik_multi:
        print(f"\n--- PIK Borrowers in 2+ Funds ({len(pik_multi)}) ---")
        for key, rec in pik_multi[:15]:
            funds = ", ".join(rec["pik_funds"])
            fv_str = f"${rec['total_fv_mm']:.1f}M" if rec["total_fv_mm"] else "n/a"
            print(f"  {rec['canonical_name'][:50]:<50}  FV={fv_str}  PIK at: {funds}")

    # 4. Largest unrealized losses (multi-fund only)
    losses = [(k, r) for k, r in borrowers.items()
              if r["unrealized_pct"] is not None and r["unrealized_pct"] < -0.10
              and r["fund_count"] >= 1 and r["total_cost_mm"] is not None and r["total_cost_mm"] > 5
              and not _is_equity_noise(r["canonical_name"])
              and _is_reasonable_position(r)]
    losses.sort(key=lambda x: x[1]["unrealized_pct"])
    if losses:
        print(f"\n--- Largest Unrealized Losses (>10% down, cost>$5M) ({len(losses)}) ---")
        for key, rec in losses[:20]:
            fv_str = f"${rec['total_fv_mm']:.1f}M" if rec["total_fv_mm"] else "n/a"
            cost_str = f"${rec['total_cost_mm']:.1f}M" if rec["total_cost_mm"] else "n/a"
            na = " [NON-ACCRUAL]" if rec["is_non_accrual_any"] else ""
            funds = "+".join(rec["funds"])
            print(f"  {rec['canonical_name'][:45]:<45}  "
                  f"Cost={cost_str}  FV={fv_str}  "
                  f"URG={rec['unrealized_pct']*100:+.1f}%  Funds={funds}{na}")


def search_borrower(db: dict, query: str) -> None:
    """Search borrower DB by partial issuer name (case-insensitive)."""
    q = query.lower()
    family_matches = [
        (k, r) for k, r in db.get("families", {}).items()
        if q in k or q in r.get("family_name", "").lower()
    ]
    if family_matches:
        print(f"\nFamily match(es) for '{query}':")
        for key, rec in sorted(family_matches, key=lambda item: (-item[1].get("fund_count", 0), item[0]))[:10]:
            print(f"  {rec['family_name']}  "
                  f"Borrowers={rec.get('borrower_count', 0)}  "
                  f"Funds={rec.get('fund_count', 0)}  "
                  f"FV=${rec.get('total_fv_mm') or 0:.1f}M  "
                  f"Members: {', '.join(rec.get('borrower_names', [])[:5])}")

    matches = [(k, r) for k, r in db["borrowers"].items()
               if q in k or q in r["canonical_name"].lower()]
    if not matches:
        print(f"No borrowers matching '{query}'")
        return
    print(f"\n{len(matches)} match(es) for '{query}':")
    for key, rec in sorted(matches, key=lambda x: -x[1]["fund_count"]):
        print(f"\n  {rec['canonical_name']}")
        if rec.get("family_key"):
            print(f"    Family key: {rec['family_key']}")
        print(f"    Funds ({rec['fund_count']}): {', '.join(rec['funds'])}")
        if rec.get("managers"):
            print(f"    Managers ({rec.get('manager_count', 0)}): {', '.join(rec['managers'])}")
        print(f"    Total FV: ${rec['total_fv_mm']:.1f}M  "
              f"Cost: ${rec['total_cost_mm']:.1f}M  "
              f"URG/L: {rec['unrealized_pct']*100:+.1f}%" if rec["unrealized_pct"] else "")
        if rec.get("nearest_maturity"):
            print(f"    Nearest maturity: {rec['nearest_maturity']}  "
                  f"Weighted avg rate: {rec.get('weighted_avg_rate_pct') or 'n/a'}%  "
                  f"Spread: {rec.get('weighted_avg_spread_bps') or 'n/a'} bps")
        if rec.get("periods_seen"):
            print(f"    History: {rec['first_seen_period']} -> {rec['last_seen_period']}  "
                  f"({rec.get('period_count', 0)} period(s), peak fund count {rec.get('peak_fund_count', 0)})")
        if rec["is_non_accrual_any"]:
            print(f"    [NON-ACCRUAL at {', '.join(rec['non_accrual_funds'])}]")
        if rec["is_pik_any"]:
            print(f"    [PIK at {', '.join(rec['pik_funds'])}]")
        for app in rec["appearances"]:
            print(f"    - {app['fund']} {app['period']}  "
                  f"{app['invest_type'][:40]}  "
                  f"FV=${app.get('fv_mm') or 0:.1f}M  "
                  f"{'PIK' if app['is_pik'] else ''}  "
                  f"{'NON-ACCRUAL' if app['is_non_accrual'] else ''}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect BDC portfolio / borrower data from EDGAR filings."
    )
    parser.add_argument("--ticker", help="Collect SOI for a single fund (e.g. PNNT)")
    parser.add_argument("--tickers", nargs="+", help="Collect SOI for specific tickers")
    parser.add_argument("--all", action="store_true", help="Collect SOI for all listed BDCs")
    parser.add_argument("--max-filings", type=int, default=2,
                        help="Number of most-recent filings per fund (default 2)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Bypass cache and re-download filings")
    parser.add_argument("--build-db", action="store_true",
                        help="Build/rebuild borrower database from all cached SOI files")
    parser.add_argument("--analyze", action="store_true",
                        help="Load borrower DB and run cross-fund analysis")
    parser.add_argument("--min-funds", type=int, default=2,
                        help="Minimum fund count for multi-lender analysis (default 2)")
    parser.add_argument("--borrower", metavar="NAME",
                        help="Search borrower database by issuer name")
    args = parser.parse_args()

    collector = PortfolioCollector()

    if args.ticker:
        collector.collect_fund(args.ticker.upper(), n_filings=args.max_filings,
                               force_refresh=args.force_refresh)
        args.build_db = True  # auto rebuild after collect

    elif args.tickers:
        for t in args.tickers:
            collector.collect_fund(t.upper(), n_filings=args.max_filings,
                                   force_refresh=args.force_refresh)
        args.build_db = True

    elif args.all:
        collector.collect_universe(n_filings=args.max_filings,
                                   force_refresh=args.force_refresh)
        args.build_db = True

    if args.build_db:
        print("\nBuilding borrower database...")
        db = build_borrower_db()
        print(f"  {db['meta']['unique_borrowers']} unique borrowers "
              f"from {db['meta']['total_positions']} positions")

    if args.analyze:
        if not BORROWER_DB.exists():
            print("Building borrower DB first...")
            db = build_borrower_db()
        else:
            db = json.loads(BORROWER_DB.read_text(encoding="utf-8"))
        analyze_borrower_db(db, min_funds=args.min_funds)

    if args.borrower:
        if not BORROWER_DB.exists():
            print("No borrower DB found. Run --build-db first.")
            return
        db = json.loads(BORROWER_DB.read_text(encoding="utf-8"))
        search_borrower(db, args.borrower)


if __name__ == "__main__":
    main()
