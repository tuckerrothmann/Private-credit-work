"""
price_feed.py — Live price fetcher for listed BDCs.

Uses yfinance to pull current market prices and compute price/NAV discounts.
Results are cached to data/price_cache.json with a configurable TTL (default: 4 hours).
Interval funds (CCLFX, etc.) are skipped since they don't trade on exchanges.

Usage:
    python price_feed.py              # refresh all listed BDCs and print table
    python price_feed.py --refresh    # force cache bypass
    python price_feed.py --tickers ARCC MAIN HTGC
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PRICE_CACHE = Path("data/price_cache.json")
_CACHE_TTL_SECONDS = 4 * 3600  # 4 hours


@dataclass
class PriceQuote:
    ticker: str
    price: float
    nav_per_share: Optional[float]
    price_to_nav: Optional[float]       # price / nav_per_share
    nav_discount_pct: Optional[float]   # (price/nav - 1)*100; negative = discount
    fetched_at: float                   # unix timestamp


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current close prices for *tickers* via yfinance.

    Returns dict[ticker, price]. Tickers with no data are omitted.
    Falls back to individual fetches if batch fails.
    """
    import yfinance as yf

    if not tickers:
        return {}

    prices: dict[str, float] = {}

    try:
        if len(tickers) == 1:
            hist = yf.Ticker(tickers[0]).history(period="2d")
            if not hist.empty:
                prices[tickers[0]] = float(hist["Close"].iloc[-1])
        else:
            data = yf.download(
                tickers, period="2d", interval="1d",
                group_by="ticker", auto_adjust=True, progress=False,
            )
            for t in tickers:
                try:
                    close = data[t]["Close"].dropna()
                    if not close.empty:
                        prices[t] = float(close.iloc[-1])
                except (KeyError, IndexError):
                    pass
    except Exception:
        # Per-ticker fallback
        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="2d")
                if not hist.empty:
                    prices[t] = float(hist["Close"].iloc[-1])
            except Exception:
                pass

    return prices


def load_price_cache() -> dict[str, dict]:
    """Load cached price data from disk. Returns dict[ticker, entry]."""
    if not PRICE_CACHE.exists():
        return {}
    try:
        return json.loads(PRICE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_price_cache(data: dict[str, dict]) -> None:
    PRICE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PRICE_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_quotes(
    funds: list[dict],
    force_refresh: bool = False,
    ttl_seconds: int = _CACHE_TTL_SECONDS,
) -> dict[str, PriceQuote]:
    """Return a PriceQuote for each listed BDC in *funds*.

    Reads from cache if fresh; fetches from yfinance otherwise.
    Interval/non-traded funds (type != "listed_bdc") are skipped.
    """
    now = time.time()
    cache = {} if force_refresh else load_price_cache()

    listed = [f for f in funds if f.get("type") == "listed_bdc" and f.get("ticker")]

    stale = [
        f["ticker"].upper() for f in listed
        if force_refresh
        or now - cache.get(f["ticker"].upper(), {}).get("fetched_at", 0) > ttl_seconds
        or "price" not in cache.get(f["ticker"].upper(), {})
    ]

    if stale:
        fresh = fetch_prices(stale)
        for t, price in fresh.items():
            cache[t] = {"price": price, "fetched_at": now}
        if fresh:
            save_price_cache(cache)

    nav_lookup = {f["ticker"].upper(): f.get("nav_per_share") for f in funds}

    quotes: dict[str, PriceQuote] = {}
    for f in listed:
        t = f["ticker"].upper()
        entry = cache.get(t, {})
        price = entry.get("price")
        if price is None:
            continue
        nav = nav_lookup.get(t)
        p2n = price / nav if nav else None
        disc = (p2n - 1.0) * 100 if p2n is not None else None
        quotes[t] = PriceQuote(
            ticker=t,
            price=price,
            nav_per_share=nav,
            price_to_nav=p2n,
            nav_discount_pct=disc,
            fetched_at=entry.get("fetched_at", 0),
        )

    return quotes


def enrich_funds_with_prices(
    funds: list[dict],
    force_refresh: bool = False,
) -> list[dict]:
    """Return new fund dicts with live price_to_nav injected where available.

    Non-listed funds are returned unchanged.
    Sets _price, price_to_nav, _nav_discount_pct, _price_source on enriched funds.
    """
    quotes = get_quotes(funds, force_refresh=force_refresh)
    result = []
    for fund in funds:
        t = fund.get("ticker", "").upper()
        if t in quotes:
            fund = dict(fund)
            q = quotes[t]
            fund["price_to_nav"] = q.price_to_nav
            fund["_price"] = q.price
            fund["_nav_discount_pct"] = q.nav_discount_pct
            fund["_price_source"] = "live"
        result.append(fund)
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch live BDC market prices.")
    parser.add_argument("--tickers", nargs="*", help="Limit to specific tickers.")
    parser.add_argument("--refresh", action="store_true", help="Force cache refresh.")
    args = parser.parse_args()

    from red_flag_screener import load_universe
    funds = load_universe()
    if args.tickers:
        want = {t.upper() for t in args.tickers}
        funds = [f for f in funds if f.get("ticker", "").upper() in want]

    quotes = get_quotes(funds, force_refresh=args.refresh)

    hdr = f"{'Ticker':<8} {'Price':>8} {'NAV/sh':>8} {'P/NAV':>7} {'Disc/Prem':>11}"
    print(f"\n{hdr}")
    print("-" * len(hdr))
    for t, q in sorted(quotes.items()):
        nav_s  = f"${q.nav_per_share:.2f}" if q.nav_per_share else "    n/a"
        p2n_s  = f"{q.price_to_nav:.3f}x" if q.price_to_nav is not None else "   n/a"
        disc_s = f"{q.nav_discount_pct:+.1f}%" if q.nav_discount_pct is not None else "    n/a"
        print(f"{t:<8} ${q.price:>7.2f} {nav_s:>8} {p2n_s:>7} {disc_s:>11}")

    import time as _t
    oldest = min((q.fetched_at for q in quotes.values()), default=0)
    age_min = (_t.time() - oldest) / 60
    print(f"\n{len(quotes)} prices  |  cache age <={age_min:.0f} min")


if __name__ == "__main__":
    main()
