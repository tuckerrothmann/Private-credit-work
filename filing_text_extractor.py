#!/usr/bin/env python3
"""
Filing Text Extractor
=====================
Extracts non-accrual commentary from Item 7 (MD&A) of BDC 10-K and 10-Q
filings on EDGAR, and attempts to parse key statistics from the prose.

This module reuses the same EDGAR fetch infrastructure as portfolio_collector.py
(same constants, rate-limiting, CIK lookup), but focuses on narrative text
rather than financial table parsing.

What it extracts
----------------
- Full Item 7 / MD&A text (or the non-accrual sub-section if Item 7 is huge)
- All paragraphs containing "non-accrual" within Item 7
- Parsed stats where possible:
    - na_count       : number of non-accrual investments
    - na_pct_fv      : % of portfolio FV on non-accrual
    - na_pct_cost    : % of portfolio cost on non-accrual
    - na_fv_mm       : fair value of non-accruals ($M)
    - na_cost_mm     : amortized cost of non-accruals ($M)
    - na_companies   : list of company names mentioned near "non-accrual"

Usage
-----
    python filing_text_extractor.py TPVG
    python filing_text_extractor.py PSEC PFLT PNNT
    python filing_text_extractor.py --all
    python filing_text_extractor.py ARCC --form 10-Q
    python filing_text_extractor.py PFLT --raw        # dump raw Item 7 text
    python filing_text_extractor.py --csv out.csv     # write CSV summary
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants — mirror portfolio_collector.py so we share the same cache dirs
# ---------------------------------------------------------------------------

EDGAR_BASE   = "https://data.sec.gov"
EDGAR_FILING = "https://www.sec.gov"
HEADERS      = {"User-Agent": "private-research/1.0 jroth@example.com"}
RATE_DELAY   = 0.15

PORTFOLIO_CACHE = Path("data/portfolio_cache")
UNIVERSE_PATH   = Path("data/bdc_universe.json")

# Cache for filing text extracts (separate from SOI portfolio cache)
TEXT_CACHE = Path("data/text_cache")

# Max bytes to fetch for a filing before we fall back to a targeted search.
# 10MB covers most BDC 10-Ks fully; larger filings get the targeted Item 7 slice.
_MAX_FULL_FETCH_BYTES = 10 * 1024 * 1024   # 10 MB
_ITEM7_MAX_CHARS = 80_000                   # max chars to store from Item 7


# ---------------------------------------------------------------------------
# HTTP / cache helpers (minimal copy from portfolio_collector.py)
# ---------------------------------------------------------------------------

_LAST_REQUEST: float = 0.0


def _fetch(url: str, binary: bool = False, timeout: int = 60) -> Any:
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
        age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        if age < timedelta(hours=ttl_hours):
            return json.loads(cache_path.read_text(encoding="utf-8"))
    raw = _fetch(url)
    data = json.loads(raw)
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _get_submissions(cik: str) -> dict:
    padded = cik.zfill(10)
    url = f"{EDGAR_BASE}/submissions/CIK{padded}.json"
    cache = PORTFOLIO_CACHE / f"_sub_{padded}.json"
    return _fetch_json(url, cache, ttl_hours=12)


def _get_recent_10kq(cik: str, n: int = 3) -> list[dict]:
    subs = _get_submissions(cik)
    filings = subs.get("filings", {}).get("recent", {})
    forms    = filings.get("form", [])
    dates    = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])
    report_dates = filings.get("reportDate", [])

    results = []
    for i, form in enumerate(forms):
        if form in ("10-K", "10-Q"):
            results.append({
                "form":          form,
                "filed":         dates[i] if i < len(dates) else "",
                "period":        report_dates[i] if i < len(report_dates) else dates[i],
                "accession":     accessions[i].replace("-", ""),
                "accession_fmt": accessions[i],
                "primary_doc":   primary_docs[i] if i < len(primary_docs) else "",
            })
        if len(results) >= n:
            break
    return results


def _primary_doc_url(cik: str, accession: str, primary_doc: str) -> str:
    padded = cik.zfill(10)
    return f"{EDGAR_FILING}/Archives/edgar/data/{int(padded)}/{accession}/{primary_doc}"


def _get_filing_index(cik: str, accession: str) -> list[dict]:
    padded = cik.zfill(10)
    idx_url = (f"{EDGAR_FILING}/Archives/edgar/data/{int(padded)}"
               f"/{accession}/index.json")
    try:
        raw = _fetch(idx_url)
        data = json.loads(raw)
        return data.get("directory", {}).get("item", [])
    except Exception:
        return []


def _lookup_cik(ticker: str) -> Optional[str]:
    """Return CIK string for a ticker, or None if not found."""
    cache = PORTFOLIO_CACHE / "_tickers.json"
    try:
        data = _fetch_json(
            "https://www.sec.gov/files/company_tickers.json",
            cache, ttl_hours=48
        )
    except Exception:
        return None
    target = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == target:
            return str(entry["cik_str"])
    return None


# ---------------------------------------------------------------------------
# HTML → plain text stripping
# ---------------------------------------------------------------------------

# Remove <script> and <style> blocks entirely
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
)
# Remove iXBRL / ix: namespace tags (keep their text content)
_IXBRL_RE = re.compile(
    r"</?ix:[^>]*>", re.IGNORECASE
)
# Strip any remaining HTML tag
_TAG_RE = re.compile(r"<[^>]+>")
# Collapse whitespace
_WS_RE = re.compile(r"[ \t]+")
# Collapse multiple blank lines
_BLANKLINES_RE = re.compile(r"\n{3,}")
# Remove Private Use Area characters (Wingdings, Webdings, etc.) and other non-printable
_PUA_RE = re.compile(r"[\ue000-\uf8ff\U000f0000-\U000fffff\U00100000-\U0010ffff]")


def _decode_entities(text: str) -> str:
    """Decode HTML entities including numeric character references."""
    # Named entities
    text = (text
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
            .replace("&thinsp;", " ")
            .replace("&ensp;", " ")
            .replace("&emsp;", " ")
            .replace("&ldquo;", '"')
            .replace("&rdquo;", '"')
            .replace("&lsquo;", "\u2018")
            .replace("&rsquo;", "\u2019")
            .replace("&mdash;", "\u2014")
            .replace("&ndash;", "\u2013")
            .replace("&trade;", "\u2122")
            .replace("&reg;", "\u00ae")
            .replace("&copy;", "\u00a9")
            )
    # Decimal numeric references: &#NNNN;
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    # Hex numeric references: &#xHHHH;
    text = re.sub(r"&#x([0-9A-Fa-f]+);", lambda m: chr(int(m.group(1), 16)), text)
    # Normalize curly apostrophes/quotes to ASCII for regex matching
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text


def _html_to_text(html: str) -> str:
    """Strip HTML and return clean plain text."""
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _IXBRL_RE.sub("", text)
    # Preserve paragraph breaks
    text = re.sub(r"<(?:p|div|br|tr|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", text)
    # Decode all HTML entities (including numeric)
    text = _decode_entities(text)
    text = _WS_RE.sub(" ", text)
    text = _BLANKLINES_RE.sub("\n\n", text)
    # Remove Private Use Area / Wingdings / other unprintable Unicode
    text = _PUA_RE.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Item 7 section extraction
# ---------------------------------------------------------------------------

# Patterns that mark the START of Item 7 in 10-K filings.
# We look for the first occurrence AFTER the table of contents.
_ITEM7_START_RE = re.compile(
    r"(?:ITEM\s+7[\.\s—–-]*(?:MANAGEMENT[\s']*S\s+DISCUSSION|MD&?A)|"
    r"Item\s+7[\.\s—–-]*(?:Management[\s']*s\s+Discussion|MD&?A))",
    re.IGNORECASE
)

# Patterns that mark the END of Item 7 (start of Item 7A or Item 8).
_ITEM7_END_RE = re.compile(
    r"(?:ITEM\s+7A[\.\s—–-]|Item\s+7A[\.\s—–-]|"
    r"ITEM\s+8[\.\s—–-]|Item\s+8[\.\s—–-])",
    re.IGNORECASE
)

# For 10-Q filings MD&A may appear as Item 2
_ITEM2_START_RE = re.compile(
    r"(?:ITEM\s+2[\.\s—–-]*(?:MANAGEMENT[\s']*S\s+DISCUSSION|MD&?A)|"
    r"Item\s+2[\.\s—–-]*(?:Management[\s']*s\s+Discussion|MD&?A))",
    re.IGNORECASE
)
_ITEM2_END_RE = re.compile(
    r"(?:ITEM\s+3[\.\s—–-]|Item\s+3[\.\s—–-])",
    re.IGNORECASE
)

# Minimum characters between start and end to be a real Item 7 body
# (not just a table-of-contents entry)
_MIN_ITEM7_BODY = 500


def _find_item7_bounds(text: str, form: str = "10-K") -> Optional[tuple[int, int]]:
    """
    Find Item 7 / MD&A section boundaries (start, end) in plain text.

    Returns (body_start, body_end) character positions, or None if not found.

    Strategy:
    1. Find all candidate start positions matching the Item 7 heading regex.
    2. Skip TOC entries (end marker follows immediately within ~200 chars).
    3. Use the first substantial occurrence.
    4. Find the next Item 7A or Item 8 boundary as the end marker.
    """
    start_re = _ITEM7_START_RE if form == "10-K" else _ITEM2_START_RE
    end_re   = _ITEM7_END_RE   if form == "10-K" else _ITEM2_END_RE

    candidates = [(m.start(), m.end()) for m in start_re.finditer(text)]
    if not candidates:
        return None

    for cand_start, cand_end in candidates:
        window = text[cand_end:cand_end + 200]
        if end_re.search(window):
            continue  # TOC row listing items side-by-side
        next_end = end_re.search(text, cand_end)
        section_len = (next_end.start() if next_end else len(text)) - cand_end
        if section_len < _MIN_ITEM7_BODY:
            continue
        body_end = next_end.start() if next_end else len(text)
        return (cand_end, body_end)

    # Fall back: last candidate
    cand_start, cand_end = candidates[-1]
    next_end = end_re.search(text, cand_end)
    body_end = next_end.start() if next_end else len(text)
    return (cand_end, body_end)


def _find_item7(text: str, form: str = "10-K") -> Optional[str]:
    """Return Item 7 text slice (up to _ITEM7_MAX_CHARS). Used when raw text is needed."""
    bounds = _find_item7_bounds(text, form)
    if bounds is None:
        return None
    start, end = bounds
    return text[start:end].strip()[:_ITEM7_MAX_CHARS]


# ---------------------------------------------------------------------------
# Non-accrual paragraph extraction
# ---------------------------------------------------------------------------

_NONACCRUAL_RE = re.compile(r"non[- ]?accrual", re.IGNORECASE)

# Regexes to parse key stats from non-accrual prose
_NA_COUNT_RE = re.compile(
    r"(\d+)\s+(?:loans?|investments?|debt\s+investments?|portfolio\s+companies?|issuers?|positions?)"
    r"\s+(?:(?:were|are|totaling|with)\s+)?(?:placed\s+on\s+)?(?:on\s+)?non[- ]?accrual",
    re.IGNORECASE
)
_NA_COUNT_RE2 = re.compile(
    r"non[- ]?accrual\s+(?:status\s+)?(?:investments?|loans?|debt)\s+.*?(\d+)\s+(?:companies|issuers?|borrowers?)",
    re.IGNORECASE
)
# Word-form counts: "four portfolio companies ... on non-accrual"
_NA_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_NA_COUNT_WORD_RE = re.compile(
    r"\b(" + "|".join(_NA_COUNT_WORDS.keys()) + r")\b",
    re.IGNORECASE
)

_NA_PCT_FV_RE = re.compile(
    r"(?:representing|comprised?|totaling|equal(?:ing)?)\s+"
    r"([\d.]+)\s*%\s+(?:of\s+)?(?:our\s+|the\s+|total\s+)?(?:portfolio\s+)?(?:at\s+)?(?:fair\s+value|fv)",
    re.IGNORECASE
)
_NA_PCT_FV_RE2 = re.compile(
    r"([\d.]+)\s*%\s+(?:of\s+)?(?:our\s+|the\s+|total\s+)?(?:portfolio\s+)?(?:at\s+)?fair\s+value",
    re.IGNORECASE
)
_NA_PCT_COST_RE = re.compile(
    r"([\d.]+)\s*%\s+(?:"
    r"(?:of\s+)?(?:our\s+|the\s+)?(?:total\s+)?(?:investments?\s+)?(?:at\s+)?(?:amortized\s+)?cost(?:\s+basis)?"
    r"|at\s+(?:amortized\s+)?cost"
    r")",
    re.IGNORECASE
)
# Specific pattern for common BDC format: "X% of the portfolio at fair value and Y% at cost"
_NA_PCT_FV_AND_COST_RE = re.compile(
    r"([\d.]+)\s*%\s+(?:of\s+)?(?:our\s+|the\s+)?(?:total\s+|overall\s+)?portfolio\s+at\s+fair\s+value"
    r"\s+and\s+([\d.]+)\s*%\s+at\s+(?:amortized\s+)?cost",
    re.IGNORECASE
)
# PFLT/PNNT format: "X% and Y% [percent] of our overall portfolio on a cost and fair value basis"
# Here group 1 = cost%, group 2 = FV% (reversed order!)
_NA_PCT_COST_AND_FV_RE = re.compile(
    r"([\d.]+)\s*%\s+and\s+([\d.]+)\s*%\s+(?:percent\s+)?of\s+(?:our\s+|the\s+)?(?:overall\s+|total\s+)?portfolio"
    r"\s+on\s+a\s+cost\s+and\s+fair\s+value\s+basis",
    re.IGNORECASE
)
_DOLLAR_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+\.?\d*)\s*(million|billion|M\b|B\b)?",
    re.IGNORECASE
)

# Pattern: "aggregate cost and fair value of $X and $Y, respectively"
# Common BDC non-accrual disclosure format
_COST_AND_FV_RE = re.compile(
    r"(?:aggregate\s+)?cost\s+and\s+fair\s+value\s+of\s+"
    r"\$([\d,]+\.?\d*)\s*(million|billion)?\s+and\s+\$([\d,]+\.?\d*)\s*(million|billion)?",
    re.IGNORECASE
)
# Pattern: "fair value and amortized cost of $X and $Y"
_FV_AND_COST_RE = re.compile(
    r"fair\s+value\s+and\s+(?:amortized\s+)?cost\s+of\s+"
    r"\$([\d,]+\.?\d*)\s*(million|billion)?\s+and\s+\$([\d,]+\.?\d*)\s*(million|billion)?",
    re.IGNORECASE
)
# Pattern: "fair value of $X" standalone
_FV_ONLY_RE = re.compile(
    r"(?:aggregate\s+)?fair\s+value\s+of\s+\$([\d,]+\.?\d*)\s*(million|billion)?",
    re.IGNORECASE
)
# Pattern: "amortized cost of $X" standalone
_COST_ONLY_RE = re.compile(
    r"(?:aggregate\s+)?(?:amortized\s+)?cost\s+(?:basis\s+)?of\s+\$([\d,]+\.?\d*)\s*(million|billion)?",
    re.IGNORECASE
)


def _parse_dollar(m_val: str, m_unit: str) -> float:
    """Convert matched dollar string + unit to $millions."""
    val = float(m_val.replace(",", ""))
    unit = (m_unit or "").lower()
    if unit in ("billion", "b"):
        return val * 1000.0
    if unit in ("million", "m"):
        return val
    # No unit: assume millions if < 10,000, else thousands
    return val if val < 10_000 else val / 1000.0


def _extract_na_paragraphs(text: str, context_chars: int = 400) -> list[str]:
    """
    Return text snippets containing 'non-accrual'.

    For short paragraphs (<= 600 chars), returns the full paragraph.
    For long paragraphs (e.g. footnote blocks or large table sections),
    returns a context window centered on the 'non-accrual' mention.
    De-duplicates snippets that have identical non-accrual mentions.
    """
    paragraphs = re.split(r"\n{2,}", text)
    results = []
    seen_mentions: set[str] = set()

    for para in paragraphs:
        m = _NONACCRUAL_RE.search(para)
        if not m:
            continue
        clean = re.sub(r"\s+", " ", para).strip()
        if len(clean) <= 20:
            continue

        if len(clean) <= 600:
            snippet = clean
        else:
            # Extract a window around the mention
            # Find position of the mention in the cleaned paragraph
            cm = _NONACCRUAL_RE.search(clean)
            if cm:
                s = max(0, cm.start() - context_chars // 2)
                e = min(len(clean), cm.end() + context_chars // 2)
                snippet = ("..." if s > 0 else "") + clean[s:e] + ("..." if e < len(clean) else "")
            else:
                snippet = clean[:context_chars] + "..."

        # De-duplicate: extract the mention-specific key (50 chars around mention)
        km = _NONACCRUAL_RE.search(snippet)
        key = snippet[max(0, km.start()-30):km.end()+50] if km else snippet[:80]
        if key in seen_mentions:
            continue
        seen_mentions.add(key)
        results.append(snippet)

    return results


def _parse_na_stats(paragraphs: list[str]) -> dict:
    """Convenience wrapper: join paragraphs and parse stats from the combined text."""
    return _parse_na_stats_from_text("\n\n".join(paragraphs))


def _parse_na_stats_from_text(full_text: str) -> dict:
    """
    Attempt to parse numeric non-accrual stats from Item 7 text.

    Only parses dollar amounts from sentences where the structure clearly
    attributes the amount to non-accrual investments (not incidental mentions).

    Returns a dict with keys: na_count, na_pct_fv, na_pct_cost, na_fv_mm,
    na_cost_mm, na_companies.
    """

    na_count: Optional[int] = None
    na_pct_fv: Optional[float] = None
    na_pct_cost: Optional[float] = None
    na_fv_mm: Optional[float] = None
    na_cost_mm: Optional[float] = None

    # ---- Investment count ----
    m = _NA_COUNT_RE.search(full_text)
    if m:
        try:
            na_count = int(m.group(1))
        except (ValueError, IndexError):
            pass
    if na_count is None:
        m = _NA_COUNT_RE2.search(full_text)
        if m:
            try:
                na_count = int(m.group(1))
            except (ValueError, IndexError):
                pass
    # Word-form count: search within a 300-char window around each NA mention
    if na_count is None:
        for nm in _NONACCRUAL_RE.finditer(full_text):
            window = full_text[max(0, nm.start() - 250):nm.start() + 50]
            # Check window contains investment/company type word
            if not re.search(r"\b(?:companies|investments?|loans?|positions?|issuers?)\b",
                             window, re.IGNORECASE):
                continue
            m = _NA_COUNT_WORD_RE.search(window)
            if m:
                candidate = _NA_COUNT_WORDS.get(m.group(1).lower())
                if candidate:
                    na_count = candidate
                    break

    # ---- % FV / % Cost (from pct-of-portfolio sentences) ----
    for match in _NONACCRUAL_RE.finditer(full_text):
        window = full_text[max(0, match.start() - 50):match.start() + 600]

        # Try combined percentage patterns first (most specific)
        if na_pct_fv is None or na_pct_cost is None:
            # TCPC format: "X% of portfolio at FV and Y% at cost"
            m = _NA_PCT_FV_AND_COST_RE.search(window)
            if m:
                try:
                    if na_pct_fv is None:
                        na_pct_fv = float(m.group(1))
                    if na_pct_cost is None:
                        na_pct_cost = float(m.group(2))
                    continue
                except (ValueError, IndexError):
                    pass
            # PFLT/PNNT format: "X% and Y% of portfolio on a cost and fair value basis"
            # (group 1 = cost, group 2 = FV)
            m = _NA_PCT_COST_AND_FV_RE.search(window)
            if m:
                try:
                    if na_pct_cost is None:
                        na_pct_cost = float(m.group(1))
                    if na_pct_fv is None:
                        na_pct_fv = float(m.group(2))
                    continue
                except (ValueError, IndexError):
                    pass

        if na_pct_fv is None:
            m = _NA_PCT_FV_RE.search(window)
            if not m:
                m = _NA_PCT_FV_RE2.search(window)
            if m:
                try:
                    na_pct_fv = float(m.group(1))
                except (ValueError, IndexError):
                    pass
        if na_pct_cost is None:
            m = _NA_PCT_COST_RE.search(window)
            if m:
                try:
                    na_pct_cost = float(m.group(1))
                except (ValueError, IndexError):
                    pass

    # ---- Dollar amounts — parse only from sentences clearly about NA ----
    # Look for the specific "cost and fair value of $X and $Y" pattern first
    # (most BDC 10-K disclosures use this exact phrasing)
    for match in _NONACCRUAL_RE.finditer(full_text):
        # Use a generous 600-char window centered on the mention
        window = full_text[max(0, match.start() - 100):match.start() + 600]

        # Pattern 1: "aggregate cost and fair value of $X and $Y" (most common)
        m = _COST_AND_FV_RE.search(window)
        if m:
            try:
                cost_mm = _parse_dollar(m.group(1), m.group(2))
                fv_mm   = _parse_dollar(m.group(3), m.group(4))
                if 0 < cost_mm < 50_000 and 0 < fv_mm < 50_000:
                    if na_cost_mm is None:
                        na_cost_mm = cost_mm
                    if na_fv_mm is None:
                        na_fv_mm = fv_mm
                    break
            except (ValueError, IndexError):
                pass

        # Pattern 2: "fair value and amortized cost of $X and $Y"
        m = _FV_AND_COST_RE.search(window)
        if m and na_fv_mm is None:
            try:
                fv_mm   = _parse_dollar(m.group(1), m.group(2))
                cost_mm = _parse_dollar(m.group(3), m.group(4))
                if 0 < fv_mm < 50_000 and 0 < cost_mm < 50_000:
                    na_fv_mm   = fv_mm
                    na_cost_mm = cost_mm
                    break
            except (ValueError, IndexError):
                pass

    # Pattern 3: standalone "fair value of $X" only within closely-scoped NA sentence
    if na_fv_mm is None:
        for match in _NONACCRUAL_RE.finditer(full_text):
            # Only look within the same sentence: find sentence containing the match
            sent_start = full_text.rfind("\n", 0, match.start())
            sent_end   = full_text.find("\n", match.end())
            if sent_start == -1:
                sent_start = 0
            if sent_end == -1:
                sent_end = len(full_text)
            sentence = full_text[sent_start:sent_end]
            # Only proceed if "non-accrual" is in a sentence that explicitly
            # talks about dollar values (not just "including non-accrual")
            if "non-accrual" not in sentence.lower():
                continue
            m = _FV_ONLY_RE.search(sentence)
            if m:
                try:
                    val = _parse_dollar(m.group(1), m.group(2))
                    if 0.1 < val < 50_000:
                        na_fv_mm = val
                        break
                except (ValueError, IndexError):
                    pass

    # ---- Named companies ----
    na_companies: list[str] = []
    company_re = re.compile(
        r"\b([A-Z][A-Za-z&,\. ]{2,50}(?:Inc\.|LLC|Corp\.|Ltd\.?|Holdings?|"
        r"Partners?|Group|Capital|Acquisition|Buyer|Solutions|Services|"
        r"Technologies?|Systems?|Communications?))\b"
    )
    for match in _NONACCRUAL_RE.finditer(full_text):
        window = full_text[max(0, match.start() - 100):match.start() + 300]
        for cm in company_re.finditer(window):
            name = cm.group(1).strip(" ,.")
            if name not in na_companies and len(name) > 4:
                na_companies.append(name)

    return {
        "na_count":    na_count,
        "na_pct_fv":   na_pct_fv,
        "na_pct_cost": na_pct_cost,
        "na_fv_mm":    na_fv_mm,
        "na_cost_mm":  na_cost_mm,
        "na_companies": na_companies[:20],
    }


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class MdaExtract:
    ticker: str
    period: str
    form: str
    filing_url: str = ""

    # Extraction status
    found_item7: bool = False
    item7_chars: int = 0
    na_mentions: int = 0

    # Raw text (truncated)
    nonaccrual_paragraphs: list[str] = field(default_factory=list)

    # Parsed stats
    na_count: Optional[int] = None
    na_pct_fv: Optional[float] = None
    na_pct_cost: Optional[float] = None
    na_fv_mm: Optional[float] = None
    na_cost_mm: Optional[float] = None
    na_companies: list[str] = field(default_factory=list)

    # Full Item 7 text (only populated if --raw flag used)
    item7_text: str = ""

    def summary(self) -> str:
        lines = [
            f"{self.ticker} {self.period} ({self.form})",
            f"  Item 7 found: {self.found_item7}  ({self.item7_chars:,} chars)",
            f"  Non-accrual mentions: {self.na_mentions}",
        ]
        if self.na_count is not None:
            lines.append(f"  Investments on NA: {self.na_count}")
        if self.na_pct_fv is not None:
            lines.append(f"  NA % FV: {self.na_pct_fv:.1f}%")
        if self.na_pct_cost is not None:
            lines.append(f"  NA % Cost: {self.na_pct_cost:.1f}%")
        if self.na_fv_mm is not None:
            lines.append(f"  NA FV: ${self.na_fv_mm:.1f}M")
        if self.na_cost_mm is not None:
            lines.append(f"  NA Cost: ${self.na_cost_mm:.1f}M")
        if self.na_companies:
            lines.append(f"  Companies mentioned: {', '.join(self.na_companies[:5])}"
                         + (" ..." if len(self.na_companies) > 5 else ""))
        if self.nonaccrual_paragraphs:
            lines.append("\n  --- Non-accrual paragraphs ---")
            for i, para in enumerate(self.nonaccrual_paragraphs[:3], 1):
                truncated = para[:300] + "..." if len(para) > 300 else para
                lines.append(f"\n  [{i}] {truncated}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_mda(
    ticker: str,
    form_filter: str = "10-K",
    force_refresh: bool = False,
    include_raw: bool = False,
    verbose: bool = True,
) -> Optional[MdaExtract]:
    """
    Fetch and parse the most-recent 10-K (or 10-Q) for *ticker*,
    returning an MdaExtract with non-accrual commentary.

    Results are cached in data/text_cache/{ticker}_{period}_{form}_mda.json.
    """
    cik = _lookup_cik(ticker)
    if not cik:
        if verbose:
            print(f"[!] CIK not found for {ticker}")
        return None

    # Determine target form
    target_forms = [form_filter] if form_filter else ["10-K", "10-Q"]
    filings = _get_recent_10kq(cik, n=5)
    filing = next((f for f in filings if f["form"] in target_forms), None)
    if not filing:
        if verbose:
            print(f"[!] No {form_filter} filing found for {ticker}")
        return None

    period   = filing["period"]
    form     = filing["form"]
    accession = filing["accession"]
    primary  = filing["primary_doc"]

    # Check text cache
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    cache_key = TEXT_CACHE / f"{ticker}_{period}_{form}_mda.json"
    if cache_key.exists() and not force_refresh:
        data = json.loads(cache_key.read_text(encoding="utf-8"))
        result = MdaExtract(**data)
        if not include_raw:
            result.item7_text = ""
        if verbose:
            print(f"  {ticker} {period} {form}: loaded from text cache")
        return result

    doc_url = _primary_doc_url(cik, accession, primary)
    if verbose:
        print(f"  {ticker} {period} {form}: fetching from EDGAR ({doc_url.split('/')[-1]})...")

    # Fetch filing HTML
    html = None
    try:
        html = _fetch(doc_url, timeout=90)
    except Exception as e:
        if verbose:
            print(f"    [!] Primary doc failed: {e}")
        # Try index fallback — look for the main HTM file
        try:
            items = _get_filing_index(cik, accession)
            htm_items = [
                it for it in items
                if isinstance(it, dict)
                and it.get("name", "").lower().endswith((".htm", ".html"))
                and it.get("type", "") in ("10-K", "10-Q", "")
            ]
            if htm_items:
                padded = cik.zfill(10)
                alt_url = (f"{EDGAR_FILING}/Archives/edgar/data/{int(padded)}"
                           f"/{accession}/{htm_items[0]['name']}")
                if verbose:
                    print(f"    Trying index fallback: {htm_items[0]['name']}")
                html = _fetch(alt_url, timeout=90)
                doc_url = alt_url
        except Exception as e2:
            if verbose:
                print(f"    [!] Index fallback also failed: {e2}")

    if not html:
        return None

    filing_size_kb = len(html) // 1024
    if verbose:
        print(f"    Filing size: {filing_size_kb:,} KB — extracting Item 7...")

    # Convert to plain text
    text = _html_to_text(html)
    del html  # release memory

    # Find Item 7 section bounds
    bounds = _find_item7_bounds(text, form=form)

    result = MdaExtract(
        ticker=ticker,
        period=period,
        form=form,
        filing_url=doc_url,
    )

    # Minimum Item 7 section length to consider it valid (anything shorter
    # is likely a cross-reference entry, not the actual MD&A body)
    _MIN_USEFUL_ITEM7 = 2_000

    search_text = None  # text to search for NA mentions

    if bounds:
        start, end = bounds
        section_len = end - start
        result.found_item7 = True
        result.item7_chars = section_len

        if verbose:
            print(f"    Item 7 section: {section_len:,} chars "
                  f"(pos {start:,}–{end:,})")

        if section_len >= _MIN_USEFUL_ITEM7:
            search_text = text[start:end]
        else:
            if verbose:
                print(f"    [!] Item 7 too short ({section_len} chars) — falling back to full-text NA search")
    else:
        if verbose:
            print(f"    [!] Item 7 not found — falling back to full-text NA search")

    # Full-text fallback: search entire filing for non-accrual mentions
    # (used when Item 7 is missing or too short)
    if search_text is None:
        na_count_in_full = len(_NONACCRUAL_RE.findall(text))
        if na_count_in_full > 0:
            if verbose:
                print(f"    Full-text fallback: {na_count_in_full} non-accrual mention(s) in filing")
            search_text = text
        # else: no NA mentions anywhere, nothing to do

    if search_text is not None:
        result.na_mentions = len(_NONACCRUAL_RE.findall(search_text))
        result.nonaccrual_paragraphs = _extract_na_paragraphs(search_text)
        stats = _parse_na_stats_from_text(search_text)
        result.na_count      = stats["na_count"]
        result.na_pct_fv     = stats["na_pct_fv"]
        result.na_pct_cost   = stats["na_pct_cost"]
        result.na_fv_mm      = stats["na_fv_mm"]
        result.na_cost_mm    = stats["na_cost_mm"]
        result.na_companies  = stats["na_companies"]
        if include_raw and search_text is not text:
            result.item7_text = search_text[:_ITEM7_MAX_CHARS]

    del text  # release memory

    # Cache the result (without raw item7_text to keep cache small)
    cache_data = asdict(result)
    cache_data["item7_text"] = ""   # don't persist raw text
    cache_key.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")

    return result


def extract_all_mda(
    form_filter: str = "10-K",
    force_refresh: bool = False,
    verbose: bool = True,
) -> dict[str, MdaExtract]:
    """Extract MD&A for every fund in the BDC universe."""
    if not UNIVERSE_PATH.exists():
        raise FileNotFoundError(f"Universe file not found: {UNIVERSE_PATH}")

    data = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    tickers = [f["ticker"] for f in data.get("funds", []) if "ticker" in f]

    results: dict[str, MdaExtract] = {}
    for ticker in tickers:
        r = extract_mda(ticker, form_filter=form_filter,
                        force_refresh=force_refresh, verbose=verbose)
        if r:
            results[ticker] = r
    return results


def get_mda_na_rates(
    form_filter: str = "10-K",
    force_refresh: bool = False,
) -> dict[str, float]:
    """
    Return dict[ticker, na_pct_fv] from the MD&A text cache.

    Only returns tickers where na_pct_fv was successfully parsed (not None)
    and where the Item 7 section was at least 2,000 chars (to filter out
    filings where parsing was unreliable).

    Intended as a supplement to SOI-based live NA rates — especially useful
    for funds where SOI parsing gives 0 NA (FSK, SCM, TCPC) but MD&A has
    explicit % disclosures.
    """
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)

    # Load from cache files directly (no EDGAR fetch, uses already-cached extracts)
    rates: dict[str, float] = {}
    for cache_file in TEXT_CACHE.glob("*_10-K_mda.json"):
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        ticker = data.get("ticker", "")
        if not ticker:
            continue
        na_pct_fv = data.get("na_pct_fv")
        item7_chars = data.get("item7_chars", 0)
        if na_pct_fv is not None and item7_chars >= 2_000:
            rates[ticker] = na_pct_fv

    return rates


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    import csv
    import sys

    parser = argparse.ArgumentParser(
        description="Extract MD&A non-accrual commentary from BDC 10-K filings."
    )
    parser.add_argument("tickers", nargs="*", help="Ticker(s) to extract (e.g. TPVG PSEC)")
    parser.add_argument("--all", action="store_true", help="Extract all funds in universe")
    parser.add_argument("--form", default="10-K", choices=["10-K", "10-Q"],
                        help="Filing form type (default: 10-K)")
    parser.add_argument("--raw", action="store_true",
                        help="Print the full Item 7 text (truncated to 80K chars)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Ignore text cache and re-fetch from EDGAR")
    parser.add_argument("--csv", metavar="FILE",
                        help="Write summary CSV to FILE")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet

    if args.all:
        results = extract_all_mda(
            form_filter=args.form,
            force_refresh=args.force_refresh,
            verbose=verbose,
        )
    elif args.tickers:
        results = {}
        for t in args.tickers:
            r = extract_mda(
                t.upper(),
                form_filter=args.form,
                force_refresh=args.force_refresh,
                include_raw=args.raw,
                verbose=verbose,
            )
            if r:
                results[t.upper()] = r
    else:
        parser.print_help()
        sys.exit(1)

    # Print summaries
    print()
    for ticker, r in sorted(results.items()):
        # Encode for Windows terminal compatibility (replace unmappable chars)
        summary = r.summary()
        try:
            print(summary)
        except UnicodeEncodeError:
            print(summary.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
        if args.raw and r.item7_text:
            print("\n--- Full Item 7 text ---")
            print(r.item7_text[:10_000])
            if len(r.item7_text) > 10_000:
                print(f"\n[... {len(r.item7_text) - 10_000:,} more chars truncated ...]")
        print()

    # CSV output
    if args.csv:
        fieldnames = [
            "ticker", "period", "form", "found_item7", "item7_chars",
            "na_mentions", "na_count", "na_pct_fv", "na_pct_cost",
            "na_fv_mm", "na_cost_mm", "na_companies", "filing_url",
        ]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in results.values():
                row = asdict(r)
                row["na_companies"] = "; ".join(row.get("na_companies", []))
                row.pop("nonaccrual_paragraphs", None)
                row.pop("item7_text", None)
                w.writerow(row)
        print(f"\nCSV written to {args.csv}")

    # Summary stats
    total = len(results)
    found = sum(1 for r in results.values() if r.found_item7)
    with_na = sum(1 for r in results.values() if r.na_mentions > 0)
    print(f"{total} ticker(s) processed: {found} Item 7 found, {with_na} with non-accrual text.")


if __name__ == "__main__":
    main()
