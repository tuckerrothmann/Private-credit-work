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
    "schedule of portfolio investments",
    "portfolio of investments",
]

# Column header patterns → standardised field name
COL_PATTERNS = {
    r"portfolio\s*company|issuer|investment|borrower|company\s*name": "issuer",
    r"industry|sector|type\s*of\s*business":                          "industry",
    r"investment\s*type|security\s*type|asset\s*type|type":           "invest_type",
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
    return mapping


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


def _extract_footnote_legend(soup: BeautifulSoup, soi_tag: Tag) -> dict[str, str]:
    """Extract footnote legend from the SOI section.

    Returns {marker: meaning} e.g. {"(1)": "non-accrual", "(2)": "PIK"}.
    Searches the text near the SOI table for footnote definitions.
    """
    legend: dict[str, str] = {}
    # Look for paragraphs/cells after the SOI tables that look like footnotes
    candidates = soi_tag.find_all_next(["p", "div", "td", "li"], limit=200)
    for tag in candidates:
        text = tag.get_text(separator=" ").strip()
        if len(text) > 400:
            continue
        # Pattern: "(1) Non-accrual" or "(a) Loans on non-accrual status"
        m = re.match(r'^\(?([a-z0-9]{1,2})\)?\s+(.+)$', text, re.IGNORECASE)
        if m:
            marker = f"({m.group(1)})"
            meaning = m.group(2).lower()
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


def _clean_issuer_name(raw: str) -> tuple[str, str]:
    """Split 'Company Name - Instrument Type (footnote)' into (name, instrument_type)."""
    # Remove trailing footnote references like "(1)", "(a)", "(7)"
    raw = re.sub(r'\s*\(\d+\)\s*$', '', raw).strip()
    raw = re.sub(r'\s*\([a-z]\)\s*$', '', raw, flags=re.IGNORECASE).strip()

    # Split on " - " to separate company from instrument type
    if " - " in raw:
        parts = raw.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    return raw.strip(), ""


def _is_equity_investment(invest_type: str) -> bool:
    low = invest_type.lower()
    return any(x in low for x in ["equity", "warrant", "preferred", "common stock",
                                    "lp interest", "membership", "residual"])


def _find_soi_section(soup: BeautifulSoup) -> Optional[Tag]:
    """Find the Schedule of Investments section in the parsed HTML.

    Handles both traditional HTML heading tags and modern iXBRL <span>/<p> elements
    used in SEC inline XBRL filings.
    """
    # First pass: traditional heading tags (fast, preferred)
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "b", "strong"])
    for tag in heading_tags:
        text = tag.get_text(separator=" ").lower().strip()
        if any(h in text for h in SOI_HEADINGS) and len(text) < 150:
            return tag

    # Second pass: <p> tags (common in older filings)
    for tag in soup.find_all("p"):
        text = tag.get_text(separator=" ").lower().strip()
        if any(h in text for h in SOI_HEADINGS) and len(text) < 150:
            return tag

    # Third pass: <span> tags (iXBRL / modern EDGAR filings)
    # Filter to spans with font-weight:bold or that are standalone heading-like spans
    for tag in soup.find_all("span"):
        text = tag.get_text(separator=" ").lower().strip()
        if any(h in text for h in SOI_HEADINGS) and 10 < len(text) < 150:
            # Prefer spans that look like headings (bold styling or short text)
            style = tag.get("style", "")
            if "bold" in style or "font-weight" in style or len(text) < 80:
                return tag

    # Fourth pass: any tag containing exact SOI text (last resort)
    for tag in soup.find_all(True):
        if tag.name in ("script", "style"):
            continue
        text = tag.get_text(separator=" ").lower().strip()
        if any(h in text for h in SOI_HEADINGS) and len(text) < 120:
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

    # All positions containing any SOI heading text
    all_positions: list[int] = []
    for h in SOI_HEADINGS + ["schedule of investments (continued)",
                               "schedule of portfolio investments (continued)"]:
        start = 0
        while True:
            idx = low.find(h, start)
            if idx == -1:
                break
            all_positions.append(idx)
            start = idx + 1

    all_positions = sorted(set(all_positions))

    if not all_positions:
        return html[:max_bytes]  # fallback

    # Filter out TOC-style links (those followed by </a> within 200 chars)
    data_positions = []
    for pos in all_positions:
        window = html[pos:pos + 300].lower()
        # TOC entries usually have </a> right after the text
        is_toc = '</a>' in window[:150] and ('<table of contents' in low[max(0, pos-500):pos]
                                              or 'href' in html[max(0, pos-100):pos].lower())
        if not is_toc:
            data_positions.append(pos)

    if not data_positions:
        data_positions = all_positions  # fallback

    # Compute non-overlapping ranges for each data section.
    # Each section runs from this heading to the next heading (or end).
    data_positions = sorted(data_positions)
    chunks = []
    total_bytes = 0

    for i, pos in enumerate(data_positions):
        if total_bytes >= max_bytes:
            break
        start = max(0, pos - 200)
        # End at the next heading position (so no overlap) or 1MB cap
        if i + 1 < len(data_positions):
            raw_end = data_positions[i + 1] - 200
        else:
            raw_end = len(html)
        end = min(raw_end, start + 1_500_000)  # cap at 1.5MB per section
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
    legend = _extract_footnote_legend(soup, soi_tag)
    na_marks  = _na_footnote_marks_from_legend(legend)
    pik_marks = _pik_footnote_marks_from_legend(legend)
    if verbose and (na_marks or pik_marks):
        print(f"    Footnote legend: NA={na_marks}  PIK={pik_marks}")

    # Gather tables after the SOI heading (take up to 3 to handle multi-page SOIs)
    investments: list[Investment] = []
    tables_processed = 0
    found_content = False

    # Walk forward from the SOI heading to find tables
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

        for row in rows[data_start:]:
            if not any(row):
                continue

            # Try to detect section headers (no numeric data, just text)
            non_empty = [c for c in row if c.strip()]
            if len(non_empty) == 1:
                # Might be an industry/sector sub-header
                txt = non_empty[0].strip()
                if len(txt) < 80 and not re.search(r'[\d,\$\(\)]', txt):
                    current_industry = txt
                continue

            # Try "Total" sentinel — stop when we see totals row
            first_cell = row[0].strip().lower() if row else ""
            _TOTAL_PATTERNS = (
                "total investments", "total debt", "total equity", "total portfolio",
                "total first lien", "total second lien", "total subordinated",
                "total preferred", "total secured", "total unsecured",
            )
            if first_cell.startswith("total") and (
                len(non_empty) <= 4 or any(first_cell.startswith(p) for p in _TOTAL_PATTERNS)
            ):
                break  # End of this SOI table section

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
            if inv.issuer:
                clean_name, embedded_type = _clean_issuer_name(inv.issuer)
                inv.issuer = clean_name
                if embedded_type and not inv.invest_type:
                    inv.invest_type = embedded_type

            # Use carry-forward for issuer / industry if blank
            if not inv.issuer and current_issuer:
                inv.issuer = current_issuer
            elif inv.issuer:
                current_issuer = inv.issuer

            if not inv.industry:
                inv.industry = current_industry
            else:
                current_industry = inv.industry

            if not inv.invest_type and current_type:
                inv.invest_type = current_type

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

            # Flags
            inv.is_non_accrual = _is_non_accrual(row_text, na_marks)
            inv.is_equity      = _is_equity_investment(inv.invest_type)
            base, spread, pik  = _parse_rate(inv.rate_str)
            # Also check PIK footnote marks
            if not pik and pik_marks:
                pik = any(m in row_text for m in pik_marks)
            inv.is_pik         = pik
            inv.rate_base      = base
            inv.spread_bps     = spread

            # Quality filter: skip rows where fv is obviously 0 or noise
            if inv.fv_mm is not None and abs(inv.fv_mm) < 0.0001:
                continue
            # Cap implausibly large single-position values (>$5B means parsing artifact)
            if inv.fv_mm is not None and inv.fv_mm > 5_000:
                inv.fv_mm = None
            if inv.cost_mm is not None and inv.cost_mm > 5_000:
                inv.cost_mm = None

            investments.append(inv)

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
