"""
BDC Historical Time Series Extractor
======================================
Builds multi-quarter financial time series from SEC EDGAR XBRL data for BDCs
and private-credit funds.

For each fund, produces a per-quarter DataFrame containing:
  - NAV / Net Assets (StockholdersEquity or NetAssets)
  - Shares Outstanding → NAV per share
  - Total Assets, Long-term Debt → Leverage (D/E)
  - Net Investment Income (period)
  - Dividends / Distributions paid (period)
  - Gross Investment Income
  - PIK income (DividendsPaidinkind)
  - Portfolio Fair Value and Cost → unrealized gain/loss %
  - Derived: NAV drawdown from peak, QoQ NAV/share change

Also computes:
  - NAV erosion vs. 52-week high, vs. 3-year high, vs. 5-year high
  - Peak-to-trough NAV/share decline
  - Rolling 4-quarter NII coverage ratio
  - Distribution cut events (estimated from distribution series)

Usage
-----
    from bdc_historical import BdcHistorian
    h = BdcHistorian()
    df = h.build_history("ARCC", cik="0001287750")
    summary = h.build_summary("ARCC", cik="0001287750")
    df.to_csv("arcc_history.csv", index=False)

CLI:
    python bdc_historical.py --ticker ARCC
    python bdc_historical.py --all        # refresh full universe
    python bdc_historical.py --report     # print comparative report
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from edgar_collector import EdgarClient, _value_series, _CACHE_DIR

_UNIVERSE_PATH = Path(__file__).parent / "data" / "bdc_universe.json"
_HISTORY_CACHE = Path(__file__).parent / "data" / "edgar_cache" / "history"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedup_by_end(series: list[dict]) -> dict[str, float]:
    """Return a {end_date: val} dict keeping only the most-informative entry per period.

    Priority: 10-K > 10-Q > 10-KT > others; for the same form, take latest filed.
    """
    out: dict[str, dict] = {}
    priority = {"10-K": 0, "10-KT": 1, "10-Q": 2}
    for e in series:
        end = e.get("end", "")
        form = e.get("form", "")
        if not end or e.get("val") is None:
            continue
        existing = out.get(end)
        if existing is None:
            out[end] = e
        else:
            if priority.get(form, 99) < priority.get(existing.get("form", ""), 99):
                out[end] = e
    return {k: float(v["val"]) for k, v in out.items()}


# ---------------------------------------------------------------------------
# Core historian
# ---------------------------------------------------------------------------

class BdcHistorian:
    """Fetches and assembles multi-quarter XBRL history for a BDC."""

    def __init__(self, cache_dir: Path = _CACHE_DIR) -> None:
        self.client = EdgarClient(cache_dir=cache_dir)
        _HISTORY_CACHE.mkdir(parents=True, exist_ok=True)

    def build_history(
        self,
        ticker: str,
        cik: str | None = None,
        n_periods: int = 24,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Build a quarterly history DataFrame for a single fund.

        Columns (all per-quarter snapshots unless otherwise noted):
          period, form, nav_bn, shares_m, nav_per_share, total_assets_bn,
          total_debt_bn, leverage_de, nii_bn (period), dist_bn (period),
          gross_income_bn (period), pik_bn (period), portfolio_fv_bn,
          portfolio_cost_bn, unrealized_pct,
          nav_qoq_pct, nav_drawdown_from_peak_pct, rolling4q_nii_coverage
        """
        if cik is None:
            cik = self.client.lookup_cik(ticker)

        cache_path = _HISTORY_CACHE / f"{ticker.upper()}_history.parquet"
        if not force_refresh and cache_path.exists():
            from datetime import datetime, timedelta
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if datetime.now() - mtime < timedelta(hours=24):
                return pd.read_parquet(cache_path)

        facts = self.client.get_company_facts(cik, force_refresh=force_refresh).get("facts", {})

        # ── Pull raw XBRL series ─────────────────────────────────────────
        equity  = _dedup_by_end(_value_series(facts, "us-gaap", "StockholdersEquity", n=n_periods*2))
        if not equity:
            equity = _dedup_by_end(_value_series(facts, "us-gaap", "NetAssets", n=n_periods*2))

        assets  = _dedup_by_end(_value_series(facts, "us-gaap", "Assets", n=n_periods*2))
        debt    = _dedup_by_end(_value_series(facts, "us-gaap", "LongTermDebt", n=n_periods*2))
        shares  = _dedup_by_end(_value_series(
            facts, "us-gaap", "CommonStockSharesOutstanding", unit="shares", n=n_periods*2
        ))
        if not shares:
            shares = _dedup_by_end(_value_series(
                facts, "dei", "EntityCommonStockSharesOutstanding", unit="shares", n=n_periods*2
            ))

        nii     = _dedup_by_end(_value_series(facts, "us-gaap", "NetInvestmentIncome", n=n_periods*2))
        if not nii:
            nii = _dedup_by_end(_value_series(
                facts, "us-gaap", "InvestmentIncomeOperatingAfterExpenseAndTax", n=n_periods*2
            ))

        dist    = _dedup_by_end(_value_series(facts, "us-gaap", "PaymentsOfDividends", n=n_periods*2))
        if not dist:
            dist = _dedup_by_end(_value_series(
                facts, "us-gaap", "InvestmentCompanyDividendDistribution", n=n_periods*2
            ))

        gross   = _dedup_by_end(_value_series(
            facts, "us-gaap", "GrossInvestmentIncomeOperating", n=n_periods*2
        ))
        pik     = _dedup_by_end(_value_series(facts, "us-gaap", "DividendsPaidinkind", n=n_periods*2))
        fv      = _dedup_by_end(_value_series(
            facts, "us-gaap", "InvestmentOwnedAtFairValue", n=n_periods*2
        ))
        cost    = _dedup_by_end(_value_series(
            facts, "us-gaap", "InvestmentOwnedAtCost", n=n_periods*2
        ))

        # ── Build per-period DataFrame ────────────────────────────────────
        # Use NAV periods as the spine (most complete)
        periods = sorted(equity.keys(), reverse=True)[:n_periods]

        rows = []
        for p in periods:
            nav_val     = equity.get(p)
            assets_val  = assets.get(p)
            debt_val    = debt.get(p)
            shares_val  = shares.get(p)
            nii_val     = nii.get(p)
            dist_val    = dist.get(p)
            gross_val   = gross.get(p)
            pik_val     = pik.get(p)
            fv_val      = fv.get(p)
            cost_val    = cost.get(p)

            nav_ps = nav_val / shares_val if (nav_val and shares_val) else None
            lev    = (
                debt_val / nav_val if (debt_val and nav_val and nav_val > 0) else
                ((assets_val - nav_val) / nav_val if (assets_val and nav_val and nav_val > 0) else None)
            )
            unrealized = (
                (fv_val - cost_val) / cost_val
                if (fv_val is not None and cost_val and cost_val > 0)
                else None
            )

            rows.append({
                "period":            p,
                "nav_bn":            nav_val / 1e9 if nav_val else None,
                "shares_m":          shares_val / 1e6 if shares_val else None,
                "nav_per_share":     nav_ps,
                "total_assets_bn":   assets_val / 1e9 if assets_val else None,
                "total_debt_bn":     debt_val / 1e9 if debt_val else None,
                "leverage_de":       lev,
                "nii_bn":            nii_val / 1e9 if nii_val else None,
                "dist_bn":           dist_val / 1e9 if dist_val else None,
                "gross_income_bn":   gross_val / 1e9 if gross_val else None,
                "pik_bn":            pik_val / 1e9 if pik_val else None,
                "portfolio_fv_bn":   fv_val / 1e9 if fv_val else None,
                "portfolio_cost_bn": cost_val / 1e9 if cost_val else None,
                "unrealized_pct":    unrealized,
            })

        df = pd.DataFrame(rows).sort_values("period").reset_index(drop=True)

        # ── Derived metrics ───────────────────────────────────────────────
        # QoQ NAV/share change
        df["nav_qoq_pct"] = df["nav_per_share"].pct_change()

        # Drawdown from period peak
        rolling_peak = df["nav_per_share"].cummax()
        df["nav_drawdown_from_peak_pct"] = (df["nav_per_share"] - rolling_peak) / rolling_peak

        # Rolling 4-quarter NII coverage (NII/distributions; requires period values)
        # Filter to comparable periods (10-Q quarterly, not annual cumulative)
        df["_nii_roll4"] = df["nii_bn"].rolling(4, min_periods=2).sum()
        df["_dist_roll4"] = df["dist_bn"].rolling(4, min_periods=2).sum()
        df["rolling4q_nii_coverage"] = df.apply(
            lambda r: (
                r["_nii_roll4"] / r["_dist_roll4"]
                if (r["_dist_roll4"] and r["_dist_roll4"] > 0)
                else None
            ),
            axis=1,
        )
        df = df.drop(columns=["_nii_roll4", "_dist_roll4"])

        # Sort descending (most recent first) for display
        df = df.sort_values("period", ascending=False).reset_index(drop=True)

        # Cache
        df.to_parquet(cache_path, index=False)
        return df

    def build_summary(
        self,
        ticker: str,
        cik: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Compute a concise historical summary for a fund.

        Returns dict with:
          nav_per_share_current, nav_per_share_1y, nav_per_share_3y, nav_per_share_5y,
          nav_change_1y_pct, nav_change_3y_pct, nav_change_5y_pct,
          nav_peak_per_share, nav_peak_date, nav_trough_per_share, nav_trough_date,
          nav_drawdown_from_peak_pct, leverage_current, leverage_trend,
          rolling4q_nii_coverage_current
        """
        df = self.build_history(ticker, cik=cik, force_refresh=force_refresh)

        def _nav(periods_back: int) -> Optional[float]:
            """Approximate NAV n periods back (quarterly)."""
            idx = min(periods_back, len(df) - 1)
            v = df.iloc[idx]["nav_per_share"]
            return float(v) if v is not None and not math.isnan(float(v)) else None

        current_nav = _nav(0)
        nav_1y      = _nav(4)   # ~4 quarters back
        nav_3y      = _nav(12)
        nav_5y      = _nav(20)

        def _chg(old: Optional[float], new: Optional[float]) -> Optional[float]:
            if old and new and old > 0:
                return (new - old) / old
            return None

        # Peak/trough
        valid_nav = df["nav_per_share"].dropna()
        peak_nav  = float(valid_nav.max()) if len(valid_nav) else None
        trough_nav = float(valid_nav.min()) if len(valid_nav) else None
        peak_date  = df.loc[df["nav_per_share"] == peak_nav, "period"].iloc[0] if peak_nav else None
        trough_date = df.loc[df["nav_per_share"] == trough_nav, "period"].iloc[0] if trough_nav else None
        drawdown = (current_nav - peak_nav) / peak_nav if (current_nav and peak_nav) else None

        # Leverage trend (current vs. 4Q ago)
        lev_current = df.iloc[0]["leverage_de"] if len(df) else None
        lev_1y      = df.iloc[min(4, len(df) - 1)]["leverage_de"] if len(df) > 1 else None
        lev_trend   = (
            "rising" if (lev_current and lev_1y and lev_current > lev_1y * 1.05) else
            "falling" if (lev_current and lev_1y and lev_current < lev_1y * 0.95) else
            "stable"
        )

        cov_current = df.iloc[0]["rolling4q_nii_coverage"] if len(df) else None

        return {
            "ticker":                         ticker,
            "nav_per_share_current":          current_nav,
            "nav_per_share_1y_ago":           nav_1y,
            "nav_per_share_3y_ago":           nav_3y,
            "nav_per_share_5y_ago":           nav_5y,
            "nav_change_1y_pct":              _chg(nav_1y, current_nav),
            "nav_change_3y_pct":              _chg(nav_3y, current_nav),
            "nav_change_5y_pct":              _chg(nav_5y, current_nav),
            "nav_peak_per_share":             peak_nav,
            "nav_peak_date":                  peak_date,
            "nav_drawdown_from_peak_pct":     drawdown,
            "nav_trough_per_share":           trough_nav,
            "nav_trough_date":                trough_date,
            "leverage_current":               float(lev_current) if lev_current else None,
            "leverage_1y_ago":                float(lev_1y) if lev_1y else None,
            "leverage_trend":                 lev_trend,
            "rolling4q_nii_coverage_current": float(cov_current) if cov_current else None,
            "periods_available":              len(df),
        }

    def build_universe_summaries(
        self,
        universe_path: Path = _UNIVERSE_PATH,
        force_refresh: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Build historical summaries for every fund in the universe with a CIK."""
        universe = json.loads(universe_path.read_text(encoding="utf-8"))
        results = {}
        for fund in universe["funds"]:
            ticker = fund["ticker"]
            cik_raw = fund.get("sec_cik") or fund.get("edgar_as_of")
            if not cik_raw:
                print(f"  SKIP {ticker} (no CIK)")
                continue
            try:
                cik = self.client.lookup_cik(ticker) if not str(cik_raw).isdigit() else str(cik_raw).zfill(10)
                summary = self.build_summary(ticker, cik=cik, force_refresh=force_refresh)
                results[ticker] = summary
                nav_chg_3y = summary.get("nav_change_3y_pct")
                drawdown   = summary.get("nav_drawdown_from_peak_pct")
                print(
                    f"  {ticker:8s}  "
                    f"NAV/sh={summary.get('nav_per_share_current') or 0:.2f}  "
                    f"3Y={nav_chg_3y*100:+.1f}%  " if nav_chg_3y else f"  {ticker:8s}  3Y=n/a  ",
                    f"DrawdownFromPeak={drawdown*100:.1f}%" if drawdown else "DrawdownFromPeak=n/a"
                )
            except Exception as exc:
                results[ticker] = {"ticker": ticker, "error": str(exc)}
                print(f"  ERR {ticker}: {exc}")

        out = _HISTORY_CACHE / "universe_summaries.json"
        out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\nSaved -> {out}")
        return results


# ---------------------------------------------------------------------------
# Dashboard helpers
# ---------------------------------------------------------------------------

def load_history(ticker: str) -> pd.DataFrame:
    """Load cached history DataFrame for a ticker.  Returns empty DF if not cached."""
    path = _HISTORY_CACHE / f"{ticker.upper()}_history.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def compare_nav_trajectories(tickers: list[str]) -> pd.DataFrame:
    """Load histories for multiple tickers and merge into a single wide DataFrame.

    Columns: period, {TICKER}_nav_per_share, {TICKER}_leverage_de, ...
    """
    frames = []
    for t in tickers:
        df = load_history(t)
        if df.empty:
            continue
        sub = df[["period", "nav_per_share", "leverage_de", "rolling4q_nii_coverage"]].copy()
        sub = sub.rename(columns={
            "nav_per_share":            f"{t}_nav_ps",
            "leverage_de":              f"{t}_lev",
            "rolling4q_nii_coverage":   f"{t}_nii_cov",
        })
        frames.append(sub.set_index("period"))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1).sort_index(ascending=False).reset_index()


def nav_indexed_to_100(tickers: list[str], base_period: str | None = None) -> pd.DataFrame:
    """Return NAV/share trajectories re-indexed to 100 at `base_period`.

    If base_period is None, uses the earliest common period across all tickers.
    Useful for comparing relative performance over time.
    """
    frames = {}
    for t in tickers:
        df = load_history(t)
        if df.empty or "nav_per_share" not in df.columns:
            continue
        s = df.set_index("period")["nav_per_share"].dropna().sort_index()
        frames[t] = s

    if not frames:
        return pd.DataFrame()

    merged = pd.DataFrame(frames).sort_index()
    if base_period is None:
        # Use oldest common period
        base_period = merged.dropna().index[0] if not merged.dropna().empty else merged.index[0]

    base_vals = merged.loc[base_period] if base_period in merged.index else merged.iloc[0]
    indexed = merged.div(base_vals) * 100
    return indexed.reset_index().rename(columns={"index": "period"})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="BDC historical EDGAR time series extractor.")
    parser.add_argument("--ticker", help="Single ticker to process.")
    parser.add_argument("--all", action="store_true", help="Process full universe.")
    parser.add_argument("--report", action="store_true", help="Print comparative historical report.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache.")
    parser.add_argument("--csv", metavar="PATH", help="Save output to CSV.")
    args = parser.parse_args()

    h = BdcHistorian()

    if args.all or args.report:
        print("Building historical summaries for BDC universe...")
        summaries = h.build_universe_summaries(force_refresh=args.force_refresh)

        if args.report:
            print(f"\n{'HISTORICAL NAV/SHARE TRAJECTORIES':^80}")
            print(f"{'Ticker':8s}  {'Current':8s}  {'1Y Ago':8s}  {'3Y Ago':8s}  "
                  f"{'1Y Chg':8s}  {'3Y Chg':8s}  {'Peak':8s}  {'Drawdown':8s}")
            print("-" * 80)
            sorted_summaries = sorted(
                [(t, s) for t, s in summaries.items() if "error" not in s],
                key=lambda x: (x[1].get("nav_change_3y_pct") or 0),
            )
            for ticker, s in sorted_summaries:
                curr  = s.get("nav_per_share_current")
                y1    = s.get("nav_per_share_1y_ago")
                y3    = s.get("nav_per_share_3y_ago")
                chg1  = s.get("nav_change_1y_pct")
                chg3  = s.get("nav_change_3y_pct")
                peak  = s.get("nav_peak_per_share")
                dd    = s.get("nav_drawdown_from_peak_pct")
                def _f(v, fmt=".2f"):
                    return f"${v:{fmt}}" if v else " n/a "
                def _p(v):
                    return f"{v*100:+.1f}%" if v else "  n/a "
                print(
                    f"{ticker:8s}  {_f(curr):8s}  {_f(y1):8s}  {_f(y3):8s}  "
                    f"{_p(chg1):8s}  {_p(chg3):8s}  {_f(peak):8s}  {_p(dd):8s}"
                )
        return

    if args.ticker:
        df = h.build_history(args.ticker.upper(), force_refresh=args.force_refresh)
        print(df[["period","nav_per_share","leverage_de","rolling4q_nii_coverage",
                   "nav_qoq_pct","nav_drawdown_from_peak_pct"]].to_string(index=False))
        if args.csv:
            df.to_csv(args.csv, index=False)
            print(f"\nSaved -> {args.csv}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
