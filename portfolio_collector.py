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
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
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
    # The distinguishing feature: the PARENT element text starts with "(N)"
    # immediately followed by a substantial definition (not table row content).
    for span in soup.find_all("span"):
        t = span.get_text().strip()
        m = re.fullmatch(r'\((\d{1,2})\)', t)
        if not m:
            continue
        marker = f"({m.group(1)})"
        if marker in legend:
            continue
        # Get the text of the parent element (span + siblings combined)
        parent_text = span.parent.get_text(separator="").strip() if span.parent else ""
        # Must start with the marker and have a real definition (10-600 chars total)
        if parent_text.startswith(t) and 10 < len(parent_text) < 700:
            definition = parent_text[len(t):].strip().lower()
            if len(definition) > 5:
                legend[marker] = definition

    # ── Strategy 2: regex on raw HTML after SOI heading ───────────────────
    if not legend and html_text:
        soi_pos = html_text.lower().find("schedule of investments")
        if soi_pos >= 0:
            chunk = html_text[soi_pos: soi_pos + 3_500_000]
            # Look for "(N)text" patterns concatenated with no space (iXBRL joined)
            # or "(N) text" with a space
            for m in re.finditer(
                r'\((\d{1,2})\)\s{0,2}([A-Z][^<\n]{10,400})',
                chunk
            ):
                marker  = f"({m.group(1)})"
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
            m = re.match(r'^\(?([a-z0-9]{1,2})\)?\s+(.+)$', text, re.IGNORECASE)
            if m and 5 < len(m.group(2)) < 600:
                marker  = f"({m.group(1)})"
                meaning = m.group(2).lower()
                if marker not in legend:
                    legend[marker] = meaning

    return legend


def _na_footnote_marks_from_legend(legend: dict[str, str]) -> set[str]:
    """Return footnote markers whose meaning relates to non-accrual."""
    marks = set()
    na_terms = ["non-accrual", "non accrual", "nonaccrual", "accrual basis",
                "not accruing", "placed on non"]
    for marker, meaning in legend.items():
        if any(t in meaning for t in na_terms):
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
    # Collect all trailing/embedded footnote markers before stripping them
    markers: set[str] = set(re.findall(r'\(\d{1,2}\)', raw))
    markers |= set(re.findall(r'\([a-z]\)', raw, re.IGNORECASE))

    # Remove ALL footnote references from the name (not just trailing)
    cleaned = re.sub(r'\s*\(\d{1,2}\)\s*', ' ', raw).strip()
    cleaned = re.sub(r'\s*\([a-z]\)\s*', ' ', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Split on " - " to separate company from instrument type
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        return parts[0].strip(), parts[1].strip(), markers
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
            row_is_na = _is_non_accrual(row_text, na_marks)
            if not row_is_na and na_marks and issuer_markers:
                row_is_na = bool(issuer_markers & na_marks)
            if row_is_na and inv.issuer:
                _tbl_na.add(inv.issuer)
                na_issuers.add(inv.issuer)
            row_is_pik = bool(pik_marks and (
                any(m in row_text for m in pik_marks) or bool(issuer_markers & pik_marks)
            )) if pik_marks else False
            if row_is_pik and inv.issuer:
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
            if inv.issuer in _tbl_na:
                inv.is_non_accrual = True
            if inv.issuer in _tbl_pik:
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

def build_borrower_db(
    cache_dir: Path = PORTFOLIO_CACHE,
    output_path: Path = BORROWER_DB,
) -> dict[str, Any]:
    """Aggregate all cached SOI files into a cross-fund borrower database.

    Returns dict with:
      borrowers:  dict[issuer_name, BorrowerRecord]
      meta:       {build_time, funds_included, total_positions}
    """
    files = sorted(cache_dir.glob("*.json"))
    files = [f for f in files if not f.name.startswith("_")]

    # issuer_key -> record
    borrowers: dict[str, dict] = {}
    total_positions = 0

    for fpath in files:
        try:
            positions = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue

        for pos in positions:
            issuer = pos.get("issuer", "").strip()
            if not issuer or len(issuer) < 2:
                continue
            # Skip equity/instrument-type noise before indexing
            if _is_equity_noise(issuer):
                continue
            # Normalize issuer name for matching
            key = re.sub(r'\s+', ' ', issuer.lower().strip())
            key = re.sub(r'[,\.;]', '', key)
            key = re.sub(r'\s*(llc|inc|corp|ltd|lp|co\b)', '', key).strip()

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
                "cost_mm": pos.get("cost_mm"),
                "fv_mm": pos.get("fv_mm"),
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

            if pos.get("fv_mm") is not None:
                rec["total_fv_mm"] = round(rec["total_fv_mm"] + pos["fv_mm"], 4)
                rec["_fv_count"] = rec.get("_fv_count", 0) + 1
            if pos.get("cost_mm") is not None:
                rec["total_cost_mm"] = round(rec["total_cost_mm"] + pos["cost_mm"], 4)
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

    # Compute borrower stress tier for each record
    for rec in borrowers.values():
        rec["stress_score"] = _borrower_stress_score(rec)
        rec["stress_tier"] = _stress_tier(rec["stress_score"])

    db = {
        "meta": {
            "build_time": datetime.now().isoformat(),
            "total_positions": total_positions,
            "unique_borrowers": len(borrowers),
            "funds_included": sorted({
                app["fund"]
                for rec in borrowers.values()
                for app in rec["appearances"]
            }),
        },
        "borrowers": borrowers,
    }

    output_path.write_text(json.dumps(db, indent=2), encoding="utf-8")
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

def compute_live_na_rates(
    cache_dir: Path = PORTFOLIO_CACHE,
) -> dict[str, float]:
    """Compute non-accrual rate (NA FV / total FV) for each fund from cached SOI data.

    For each ticker, uses only the most recent cached period.  Returns a dict
    mapping ticker -> rate (0.0–1.0).  Tickers with no FV data are excluded.

    Suitable for injecting live nonaccrual_pct_fair_value into the screener
    in place of the static value from bdc_universe.json.
    """
    # Group cache files by ticker, pick most recent period per ticker
    ticker_files: dict[str, Path] = {}
    for fpath in sorted(cache_dir.glob("*.json")):
        if fpath.name.startswith("_"):
            continue
        # File names are like TICKER_YYYY-MM-DD.json
        stem = fpath.stem  # e.g. "ARCC_2024-12-31"
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        ticker, period = parts[0].upper(), parts[1]
        # Keep most recent period (string compare works for YYYY-MM-DD)
        if ticker not in ticker_files or period > ticker_files[ticker].stem.split("_", 1)[1]:
            ticker_files[ticker] = fpath

    result: dict[str, float] = {}
    for ticker, fpath in ticker_files.items():
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
    meta = db["meta"]

    print(f"\nBorrower Database Summary")
    print(f"  Built:          {meta['build_time'][:19]}")
    print(f"  Total positions: {meta['total_positions']}")
    print(f"  Unique borrowers: {meta['unique_borrowers']}")
    print(f"  Funds included:   {', '.join(meta['funds_included'])}")

    # 1. Multi-lender issuers
    multi = [(k, r) for k, r in borrowers.items() if r["fund_count"] >= min_funds]
    multi.sort(key=lambda x: -x[1]["fund_count"])
    print(f"\n--- Issuers in {min_funds}+ BDC portfolios ({len(multi)}) ---")
    for key, rec in multi[:25]:
        fv_str = f"${rec['total_fv_mm']:.1f}M" if rec["total_fv_mm"] else "n/a"
        na_str = " [NON-ACCRUAL at " + "+".join(rec["non_accrual_funds"]) + "]" if rec["is_non_accrual_any"] else ""
        pik_str = " [PIK at " + "+".join(rec["pik_funds"]) + "]" if rec["is_pik_any"] else ""
        unr_str = ""
        if rec["unrealized_pct"] is not None:
            unr_str = f"  URG/L: {rec['unrealized_pct']*100:+.1f}%"
        print(f"  {rec['canonical_name'][:50]:<50}  "
              f"{rec['fund_count']}x  FV={fv_str}{unr_str}{na_str}{pik_str}")

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
    matches = [(k, r) for k, r in db["borrowers"].items()
               if q in k or q in r["canonical_name"].lower()]
    if not matches:
        print(f"No borrowers matching '{query}'")
        return
    print(f"\n{len(matches)} match(es) for '{query}':")
    for key, rec in sorted(matches, key=lambda x: -x[1]["fund_count"]):
        print(f"\n  {rec['canonical_name']}")
        print(f"    Funds ({rec['fund_count']}): {', '.join(rec['funds'])}")
        print(f"    Total FV: ${rec['total_fv_mm']:.1f}M  "
              f"Cost: ${rec['total_cost_mm']:.1f}M  "
              f"URG/L: {rec['unrealized_pct']*100:+.1f}%" if rec["unrealized_pct"] else "")
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
