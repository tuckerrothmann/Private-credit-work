"""
EDGAR Data Collector
====================
Pulls filing metadata and XBRL financial facts from SEC EDGAR for BDCs
and private-credit interval funds.

EDGAR public APIs used (no API key required; rate-limit to ≤10 req/sec):
  - Company tickers:  https://www.sec.gov/files/company_tickers.json
  - Submissions:      https://data.sec.gov/submissions/CIK{cik:010d}.json
  - Company facts:    https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json
  - EFTS search:      https://efts.sec.gov/LATEST/search-index

All results cached locally in data/edgar_cache/ as JSON files.
Cache TTL is 24 hours by default; pass force_refresh=True to bypass.

Usage
-----
    from edgar_collector import EdgarClient
    client = EdgarClient()

    cik = client.lookup_cik("ARCC")
    metrics = client.get_bdc_metrics(cik)
    filings = client.get_recent_filings(cik, ["10-K", "10-Q"])
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------------------------

_CACHE_DIR = Path(__file__).parent / "data" / "edgar_cache"
_CACHE_TTL_HOURS = 24

_EDGAR_BASE   = "https://data.sec.gov"
_EFTS_BASE    = "https://efts.sec.gov"
_TICKERS_URL  = "https://www.sec.gov/files/company_tickers.json"

_HEADERS = {
    "User-Agent": "private-credit-analysis research@example.com",  # SEC requires User-Agent
    "Accept-Encoding": "gzip, deflate",
}

# Rate-limit: SEC asks for no more than 10 requests/second
_REQUEST_DELAY_S = 0.15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, cache_path: Path, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch a JSON URL, using a local file cache.

    The cache file is considered fresh if it is less than _CACHE_TTL_HOURS old.
    Returns the parsed JSON dict.  Raises RuntimeError on HTTP errors.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # Check cache freshness
    if not force_refresh and cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=_CACHE_TTL_HOURS):
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # Fetch from EDGAR
    time.sleep(_REQUEST_DELAY_S)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc.reason}") from exc

    # Handle gzip transparently (Python's urllib does NOT auto-decompress)
    content_encoding = ""
    if hasattr(raw, "headers"):
        content_encoding = raw.headers.get("Content-Encoding", "")
    # urllib returns bytes; decompress if needed
    import io
    if isinstance(raw, bytes) and raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)

    text = raw.decode("utf-8", errors="replace")
    data = json.loads(text)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Metric extraction helpers (XBRL company facts)
# ---------------------------------------------------------------------------

def _latest_value(
    facts: dict[str, Any],
    taxonomy: str,
    concept: str,
    unit: str = "USD",
    form_types: tuple[str, ...] = ("10-K", "10-Q"),
) -> Optional[float]:
    """Return the most recent reported value for an XBRL concept.

    Parameters
    ----------
    facts:
        The 'facts' dict from the EDGAR company facts API response.
    taxonomy:
        Either 'us-gaap' or 'dei' (or another taxonomy).
    concept:
        XBRL concept name, e.g. 'Assets', 'NetAssets'.
    unit:
        Unit label, e.g. 'USD' or 'shares'.
    form_types:
        Only consider values reported in these form types.
    """
    try:
        entries = (
            facts.get(taxonomy, {})
            .get(concept, {})
            .get("units", {})
            .get(unit, [])
        )
    except AttributeError:
        return None

    # Filter to desired form types, sort by end date descending
    valid = [
        e for e in entries
        if e.get("form", "") in form_types
        and e.get("val") is not None
    ]
    if not valid:
        return None

    valid.sort(key=lambda e: e.get("end", ""), reverse=True)
    return float(valid[0]["val"])


def _value_series(
    facts: dict[str, Any],
    taxonomy: str,
    concept: str,
    unit: str = "USD",
    form_types: tuple[str, ...] = ("10-K", "10-Q"),
    n: int = 8,
) -> list[dict[str, Any]]:
    """Return the n most-recent reported values for an XBRL concept as a list of dicts."""
    try:
        entries = (
            facts.get(taxonomy, {})
            .get(concept, {})
            .get("units", {})
            .get(unit, [])
        )
    except AttributeError:
        return []

    valid = [
        e for e in entries
        if e.get("form", "") in form_types
        and e.get("val") is not None
    ]
    valid.sort(key=lambda e: e.get("end", ""), reverse=True)
    return valid[:n]


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

@dataclass
class EdgarClient:
    """Client for the SEC EDGAR REST APIs.

    All network calls are cached in `cache_dir`.  Pass force_refresh=True to
    individual method calls to bypass the local cache.
    """

    cache_dir: Path = field(default_factory=lambda: _CACHE_DIR)
    _ticker_map: dict[str, str] = field(default_factory=dict, repr=False)

    # ── CIK lookup ─────────────────────────────────────────────────────────

    def _load_ticker_map(self, force_refresh: bool = False) -> None:
        """Load or refresh the SEC company_tickers.json map (ticker → CIK)."""
        if self._ticker_map and not force_refresh:
            return
        cache_path = self.cache_dir / "company_tickers.json"
        raw = _fetch_json(_TICKERS_URL, cache_path, force_refresh=force_refresh)
        # Format: {"0": {"cik_str": "827054", "ticker": "MSFT", "title": "..."}, ...}
        self._ticker_map = {
            v["ticker"].upper(): str(v["cik_str"])
            for v in raw.values()
            if "ticker" in v and "cik_str" in v
        }

    def lookup_cik(self, ticker: str, force_refresh: bool = False) -> str:
        """Return the 10-digit zero-padded CIK string for a given ticker.

        Raises KeyError if the ticker is not found in EDGAR.
        """
        self._load_ticker_map(force_refresh=force_refresh)
        raw_cik = self._ticker_map.get(ticker.upper())
        if raw_cik is None:
            raise KeyError(f"Ticker '{ticker}' not found in EDGAR company_tickers.json")
        return raw_cik.zfill(10)

    # ── Submissions (filing list) ──────────────────────────────────────────

    def get_submissions(self, cik: str, force_refresh: bool = False) -> dict[str, Any]:
        """Fetch the submissions JSON for an entity (filing history + metadata)."""
        cik_padded = cik.zfill(10)
        url = f"{_EDGAR_BASE}/submissions/CIK{cik_padded}.json"
        cache_path = self.cache_dir / "submissions" / f"CIK{cik_padded}.json"
        return _fetch_json(url, cache_path, force_refresh=force_refresh)

    def get_recent_filings(
        self,
        cik: str,
        form_types: list[str] | None = None,
        n: int = 20,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return the n most-recent filings for an entity, optionally filtered by form type.

        Each dict includes: accessionNumber, filingDate, form, primaryDocument, description.
        """
        data = self.get_submissions(cik, force_refresh=force_refresh)
        recent = data.get("filings", {}).get("recent", {})

        # Zip parallel arrays into list of dicts
        keys = ["accessionNumber", "filingDate", "form", "primaryDocument", "reportDate"]
        entries = []
        for i in range(len(recent.get("accessionNumber", []))):
            entry = {k: recent.get(k, [None] * (i + 1))[i] for k in keys}
            entries.append(entry)

        if form_types:
            form_set = {f.upper() for f in form_types}
            entries = [e for e in entries if (e.get("form") or "").upper() in form_set]

        entries.sort(key=lambda e: e.get("filingDate") or "", reverse=True)
        return entries[:n]

    def filing_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Build the EDGAR viewer URL for a specific filing document."""
        acc = accession_number.replace("-", "")
        cik_padded = cik.zfill(10)
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik_padded)}/{acc}/{primary_document}"

    # ── XBRL company facts ────────────────────────────────────────────────

    def get_company_facts(self, cik: str, force_refresh: bool = False) -> dict[str, Any]:
        """Fetch the full XBRL company facts JSON for an entity.

        This is a large payload (~5–50 MB) containing all reported XBRL
        data across all filings.  Cached aggressively.
        """
        cik_padded = cik.zfill(10)
        url = f"{_EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json"
        cache_path = self.cache_dir / "facts" / f"CIK{cik_padded}.json"
        return _fetch_json(url, cache_path, force_refresh=force_refresh)

    # ── BDC-specific metric extraction ────────────────────────────────────

    def get_bdc_metrics(
        self,
        cik: str,
        ticker: str = "",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Extract key BDC financial metrics from EDGAR XBRL data.

        Returns a dict with standardised fields (all monetary in USD, not $B):
          net_assets, total_assets, total_liabilities, leverage_de,
          shares_outstanding, nav_per_share,
          net_investment_income_ttm, dividends_paid_ttm,
          nii_coverage_ratio, as_of_date, entity_name.

        Note: BDC-specific disclosures (non-accruals, PIK breakdown, unfunded
        commitments) are typically in text narrative, not XBRL, and cannot be
        extracted by this method.  Those fields require PDF/HTML parsing.
        """
        data = self.get_company_facts(cik, force_refresh=force_refresh)
        facts = data.get("facts", {})
        entity = data.get("entityName", ticker or cik)

        # Net assets / NAV: BDCs use StockholdersEquity; mutual funds / closed-end funds
        # use NetAssets.  Try both so the method works across vehicle types.
        net_assets = (
            _latest_value(facts, "us-gaap", "StockholdersEquity")
            or _latest_value(facts, "us-gaap", "NetAssets")
            or _latest_value(facts, "us-gaap", "LimitedPartnersCapitalAccount")
        )
        total_assets = _latest_value(facts, "us-gaap", "Assets")
        total_liab   = (
            _latest_value(facts, "us-gaap", "Liabilities")
            or (
                (total_assets - net_assets)
                if (total_assets is not None and net_assets is not None)
                else None
            )
        )

        # Shares outstanding — prefer 'shares' unit
        shares = _latest_value(facts, "us-gaap", "CommonStockSharesOutstanding", unit="shares")
        if shares is None:
            shares = _latest_value(facts, "dei", "EntityCommonStockSharesOutstanding", unit="shares")
        if shares is None:
            shares = _latest_value(facts, "us-gaap", "CommonStockSharesIssued", unit="shares")

        nav_per_share = (
            net_assets / shares
            if (net_assets and shares and shares > 0)
            else None
        )

        # Leverage: total_debt / net_assets (not total liabilities / equity, since
        # BDC liabilities include accruals; LongTermDebt is a cleaner numerator)
        long_term_debt = _latest_value(facts, "us-gaap", "LongTermDebt")
        leverage_de = (
            long_term_debt / net_assets
            if (long_term_debt is not None and net_assets and net_assets > 0)
            else (
                (total_assets - net_assets) / net_assets
                if (total_assets and net_assets and net_assets > 0)
                else None
            )
        )

        # NII — BDCs typically use NetInvestmentIncome (annual / period concept)
        nii = (
            _latest_value(facts, "us-gaap", "NetInvestmentIncome")
            or _latest_value(facts, "us-gaap", "InvestmentIncomeOperatingAfterExpenseAndTax")
        )

        # Gross investment income
        gross_income = _latest_value(facts, "us-gaap", "GrossInvestmentIncomeOperating")

        # PIK (payment-in-kind) income
        pik_income = _latest_value(facts, "us-gaap", "DividendsPaidinkind")

        # Dividends / distributions paid
        divs = (
            _latest_value(facts, "us-gaap", "PaymentsOfDividends")
            or _latest_value(facts, "us-gaap", "InvestmentCompanyDividendDistribution")
            or _latest_value(facts, "us-gaap", "DividendsCommonStockCash")
        )

        # Portfolio fair value and cost
        portfolio_fv   = _latest_value(facts, "us-gaap", "InvestmentOwnedAtFairValue")
        portfolio_cost = _latest_value(facts, "us-gaap", "InvestmentOwnedAtCost")

        # NII coverage (both annualised from latest period)
        nii_coverage = (
            abs(nii / divs) if (nii is not None and divs is not None and divs != 0) else None
        )

        # Determine the as-of date — try the same concepts used for net_assets
        as_of: Optional[str] = None
        for _nav_concept in ("StockholdersEquity", "NetAssets", "LimitedPartnersCapitalAccount"):
            _series = _value_series(facts, "us-gaap", _nav_concept)
            if _series:
                as_of = _series[0].get("end")
                break

        return {
            "ticker":              ticker,
            "cik":                 cik,
            "entity_name":        entity,
            "as_of_date":         as_of,
            "net_assets_usd":     net_assets,
            "total_assets_usd":   total_assets,
            "total_liab_usd":     total_liab,
            "long_term_debt_usd": long_term_debt,
            "shares_outstanding": shares,
            "nav_per_share_usd":  nav_per_share,
            "leverage_de":        leverage_de,
            "gross_income_usd":   gross_income,
            "nii_usd":            nii,
            "pik_income_usd":     pik_income,
            "portfolio_fv_usd":   portfolio_fv,
            "portfolio_cost_usd": portfolio_cost,
            "dividends_paid_usd": divs,
            "nii_coverage_ratio": nii_coverage,
            "pik_pct_of_income":  (
                pik_income / gross_income
                if (pik_income is not None and gross_income and gross_income > 0)
                else None
            ),
            "unrealized_depreciation_pct": (
                (portfolio_fv - portfolio_cost) / portfolio_cost
                if (portfolio_fv is not None and portfolio_cost and portfolio_cost > 0)
                else None
            ),
            "source":             "EDGAR XBRL (automated)",
        }

    # ── EFTS full-text search ─────────────────────────────────────────────

    def search_filings(
        self,
        query: str,
        form_types: list[str] | None = None,
        start_date: str = "2023-01-01",
        end_date: str | None = None,
        n: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search across EDGAR filings using the EFTS API.

        Parameters
        ----------
        query:
            Text to search for (e.g. 'non-accrual', 'payment in kind').
        form_types:
            Filter to these form types (e.g. ['10-K', '10-Q']).
        start_date / end_date:
            ISO date strings (YYYY-MM-DD).

        Returns a list of hit dicts with entity, form, date, accession.
        """
        import urllib.parse

        params: dict[str, str] = {
            "q":          f'"{query}"',
            "dateRange":  "custom",
            "startdt":    start_date,
            "forms":      ",".join(form_types) if form_types else "",
        }
        if end_date:
            params["enddt"] = end_date

        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v})
        url = f"{_EFTS_BASE}/LATEST/search-index?{qs}&hits.hits.total.value=1&hits.hits._source.period_of_report=1"

        cache_key = url.replace("https://", "").replace("/", "_").replace("?", "_")[:120]
        cache_path = self.cache_dir / "efts" / f"{cache_key}.json"

        try:
            data = _fetch_json(url, cache_path)
        except RuntimeError:
            return []

        hits = data.get("hits", {}).get("hits", [])
        results = []
        for h in hits[:n]:
            src = h.get("_source", {})
            results.append({
                "entity":     src.get("entity_name", ""),
                "form":       src.get("file_type", ""),
                "date":       src.get("period_of_report", ""),
                "filed":      src.get("file_date", ""),
                "accession":  src.get("accession_no", ""),
                "description": src.get("description", ""),
            })
        return results


# ---------------------------------------------------------------------------
# Batch collection
# ---------------------------------------------------------------------------

def collect_universe_metrics(
    universe_path: Path = Path("data/bdc_universe.json"),
    cache_dir: Path = _CACHE_DIR,
    force_refresh: bool = False,
    tickers: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch EDGAR XBRL metrics for every fund in the BDC universe file.

    Returns a dict of {ticker: metrics_dict}.  Funds without a sec_cik or
    with EDGAR fetch errors are skipped; the error message is stored under
    the 'error' key.

    Parameters
    ----------
    tickers:
        If provided, only collect for these tickers (useful for incremental runs).
    """
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    client = EdgarClient(cache_dir=cache_dir)
    results: dict[str, dict[str, Any]] = {}

    funds = universe.get("funds", [])
    if tickers:
        ticker_set = {t.upper() for t in tickers}
        funds = [f for f in funds if f.get("ticker", "").upper() in ticker_set]

    for fund in funds:
        ticker = fund.get("ticker", "")
        cik_raw = fund.get("sec_cik")

        if not cik_raw:
            # Try lookup by ticker
            try:
                cik_raw = client.lookup_cik(ticker)
            except KeyError:
                results[ticker] = {"ticker": ticker, "error": "CIK not found in EDGAR"}
                continue

        try:
            cik = str(cik_raw).zfill(10)
            metrics = client.get_bdc_metrics(cik, ticker=ticker, force_refresh=force_refresh)
            results[ticker] = metrics
            print(f"  OK  {ticker:12s}  NAV=${_fmt_bn(metrics.get('net_assets_usd'))}"
                  f"  Lev={_fmt_ratio(metrics.get('leverage_de'))}")
        except Exception as exc:  # noqa: BLE001
            results[ticker] = {"ticker": ticker, "cik": str(cik_raw), "error": str(exc)}
            print(f"  ERR {ticker:12s}  {exc}")

    # Persist to cache
    out_path = cache_dir / "universe_metrics.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\nSaved universe metrics -> {out_path}")
    return results


def load_cached_universe_metrics(
    cache_dir: Path = _CACHE_DIR,
) -> dict[str, dict[str, Any]]:
    """Load previously collected universe metrics from cache."""
    path = cache_dir / "universe_metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Formatting helpers (used in CLI output)
# ---------------------------------------------------------------------------

def _fmt_bn(value: Any) -> str:
    try:
        return f"${float(value) / 1e9:.1f}B"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_ratio(value: Any) -> str:
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "n/a"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect EDGAR XBRL metrics for the BDC universe."
    )
    parser.add_argument(
        "--tickers", nargs="*",
        help="Only collect for these tickers (default: all).",
    )
    parser.add_argument(
        "--force-refresh", action="store_true",
        help="Bypass the local cache and re-fetch from EDGAR.",
    )
    parser.add_argument(
        "--lookup", metavar="TICKER",
        help="Look up the CIK for a single ticker and exit.",
    )
    parser.add_argument(
        "--filings", metavar="TICKER",
        help="Show recent 10-K/10-Q filings for a ticker and exit.",
    )
    args = parser.parse_args()

    client = EdgarClient()

    if args.lookup:
        cik = client.lookup_cik(args.lookup)
        subs = client.get_submissions(cik)
        print(f"{args.lookup.upper()} -> CIK {cik}  ({subs.get('entityType', '')})")
        return

    if args.filings:
        cik = client.lookup_cik(args.filings)
        filings = client.get_recent_filings(cik, form_types=["10-K", "10-Q", "N-2", "N-CSR"])
        print(f"\nRecent filings for {args.filings.upper()} (CIK {cik}):")
        for f in filings:
            print(f"  {f['filingDate']}  {f['form']:8s}  {f['accessionNumber']}")
        return

    print("Collecting EDGAR metrics for BDC universe...")
    collect_universe_metrics(
        force_refresh=args.force_refresh,
        tickers=args.tickers,
    )


if __name__ == "__main__":
    main()
