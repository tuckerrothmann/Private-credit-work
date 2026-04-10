"""
Trend Signal Computation for BDCs
==================================
Derives forward-looking momentum signals from the quarterly EDGAR XBRL
history files produced by bdc_historical.py.  These signals capture
*direction of travel* — deteriorating coverage, rising leverage, escalating
PIK, accelerating NAV decline — which the point-in-time snapshot metrics
in red_flag_screener.py cannot detect.

Signal dimensions
-----------------
1. Coverage Momentum   -- rolling 4Q NII coverage: direction and rate of change
2. Leverage Creep      -- D/E trend over 4 quarters
3. PIK Escalation      -- PIK% as fraction of gross income trend
4. NAV Velocity        -- quarter-over-quarter NAV % change trend (momentum)
5. NAV Acceleration    -- is the rate of NAV decline *worsening*?
6. Trend Composite     -- 0–5 point score feeding into the screener

Usage
-----
    from trend_signals import compute_all_trend_signals, TrendSignal, HISTORY_DIR

    signals = compute_all_trend_signals()          # dict[ticker, TrendSignal]
    sig = signals["PNNT"]
    print(sig.summary())

The module is pure-pandas; it reads existing parquet files and produces no
side effects.  Call compute_all_trend_signals() once per screener run; it
is fast (<0.1s) because the parquet cache already exists.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

HISTORY_DIR = Path("data/edgar_cache/history")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slope(series: pd.Series) -> Optional[float]:
    """OLS slope (units/period) of a numeric series, NaN-dropped.  None if <3 points."""
    s = series.dropna()
    if len(s) < 3:
        return None
    x = np.arange(len(s), dtype=float)
    # simple OLS
    xm, ym = x.mean(), s.values.mean()
    denom = ((x - xm) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((x - xm) * (s.values - ym)).sum() / denom)


def _change(series: pd.Series, n: int = 4) -> Optional[float]:
    """Change between the most recent value and n periods ago, NaN-safe."""
    s = series.dropna()
    if len(s) < 2:
        return None
    n_actual = min(n, len(s) - 1)
    return float(s.iloc[-1]) - float(s.iloc[-1 - n_actual])


def _recent_mean(series: pd.Series, n: int = 2) -> Optional[float]:
    """Mean of the n most recent non-NaN values."""
    s = series.dropna().tail(n)
    if s.empty:
        return None
    return float(s.mean())


def _acceleration(series: pd.Series) -> Optional[float]:
    """Second derivative: slope of the first-diff series.  Negative = worsening decline."""
    s = series.dropna()
    if len(s) < 4:
        return None
    diffs = s.diff().dropna()
    return _slope(diffs)


# ---------------------------------------------------------------------------
# TrendSignal dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrendSignal:
    ticker: str

    # ---- Coverage ----
    coverage_current: Optional[float] = None        # most recent rolling 4Q coverage
    coverage_4q_change: Optional[float] = None      # change over last 4 quarters
    coverage_slope: Optional[float] = None          # OLS slope (units/quarter)
    coverage_flag: str = "ok"                       # "ok" | "watch" | "warn" | "critical"

    # ---- Leverage ----
    leverage_current: Optional[float] = None
    leverage_4q_change: Optional[float] = None
    leverage_slope: Optional[float] = None
    leverage_flag: str = "ok"

    # ---- PIK ----
    pik_current: Optional[float] = None             # latest PIK % of gross income
    pik_4q_change: Optional[float] = None
    pik_slope: Optional[float] = None               # pct points / quarter
    pik_flag: str = "ok"

    # ---- NAV velocity ----
    nav_velocity_recent: Optional[float] = None     # mean QoQ % last 2Q
    nav_velocity_prev: Optional[float] = None       # mean QoQ % prior 2Q
    nav_acceleration: Optional[float] = None        # slope of QoQ % series (neg = worsening)
    nav_velocity_flag: str = "ok"

    # ---- Composite ----
    trend_score: int = 0                            # 0–5; added to screener composite
    trend_flags: list[str] = field(default_factory=list)

    # ---- Meta ----
    periods_available: int = 0
    as_of_period: str = ""

    def summary(self) -> str:
        lines = [
            f"Trend Signals: {self.ticker}  (score {self.trend_score}/5, {self.periods_available}Q available)",
        ]
        def _fmt(v, fmt=".3f"):
            return f"{v:{fmt}}" if v is not None else "n/a"

        lines.append(f"  Coverage  : current={_fmt(self.coverage_current)}"
                     f"  4Q-chg={_fmt(self.coverage_4q_change)}"
                     f"  slope={_fmt(self.coverage_slope)}  [{self.coverage_flag}]")
        lines.append(f"  Leverage  : current={_fmt(self.leverage_current)}"
                     f"  4Q-chg={_fmt(self.leverage_4q_change)}"
                     f"  slope={_fmt(self.leverage_slope)}  [{self.leverage_flag}]")
        lines.append(f"  PIK%      : current={_fmt(self.pik_current)}"
                     f"  4Q-chg={_fmt(self.pik_4q_change)}"
                     f"  slope={_fmt(self.pik_slope)}  [{self.pik_flag}]")
        lines.append(f"  NAV vel.  : recent={_fmt(self.nav_velocity_recent)}"
                     f"  prev={_fmt(self.nav_velocity_prev)}"
                     f"  accel={_fmt(self.nav_acceleration)}  [{self.nav_velocity_flag}]")
        if self.trend_flags:
            lines.append(f"  Flags     : {', '.join(self.trend_flags)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_trend_signals(ticker: str, df: pd.DataFrame) -> TrendSignal:
    """Compute trend signals for one fund from its quarterly history DataFrame.

    Expects columns produced by bdc_historical.BdcHistorian.build_history():
      period, rolling4q_nii_coverage, leverage_de, nav_per_share,
      nav_qoq_pct, gross_income_bn, pik_bn
    """
    sig = TrendSignal(ticker=ticker)
    if df.empty:
        return sig

    df = df.sort_values("period").reset_index(drop=True)
    sig.periods_available = len(df)
    sig.as_of_period = str(df["period"].iloc[-1]) if not df.empty else ""

    flags: list[str] = []
    score = 0

    # ------------------------------------------------------------------ #
    # 1. Coverage momentum
    # ------------------------------------------------------------------ #
    if "rolling4q_nii_coverage" in df.columns:
        cov_s = df["rolling4q_nii_coverage"]
        sig.coverage_current = _recent_mean(cov_s, 1)
        sig.coverage_4q_change = _change(cov_s, 4)
        sig.coverage_slope = _slope(cov_s)

        chg = sig.coverage_4q_change
        cur = sig.coverage_current

        if chg is not None and cur is not None:
            if chg <= -0.40 or (chg <= -0.25 and cur < 0.80):
                sig.coverage_flag = "critical"
                flags.append("coverage_collapse")
                score += 2
            elif chg <= -0.20 or (chg <= -0.10 and cur < 0.90):
                sig.coverage_flag = "warn"
                flags.append("coverage_declining")
                score += 1
            elif chg <= -0.10:
                sig.coverage_flag = "watch"
            else:
                sig.coverage_flag = "ok"
        elif cur is not None and cur < 0.75:
            sig.coverage_flag = "warn"

    # ------------------------------------------------------------------ #
    # 2. Leverage creep
    # ------------------------------------------------------------------ #
    if "leverage_de" in df.columns:
        lev_s = df["leverage_de"]
        sig.leverage_current = _recent_mean(lev_s, 1)
        sig.leverage_4q_change = _change(lev_s, 4)
        sig.leverage_slope = _slope(lev_s)

        chg = sig.leverage_4q_change
        cur = sig.leverage_current

        if chg is not None and cur is not None:
            if chg >= 0.40 or (chg >= 0.20 and cur >= 1.70):
                sig.leverage_flag = "critical"
                flags.append("leverage_surge")
                score += 2
            elif chg >= 0.20 or (chg >= 0.10 and cur >= 1.50):
                sig.leverage_flag = "warn"
                flags.append("leverage_creep")
                score += 1
            elif chg >= 0.10:
                sig.leverage_flag = "watch"
            else:
                sig.leverage_flag = "ok"

    # ------------------------------------------------------------------ #
    # 3. PIK escalation
    # ------------------------------------------------------------------ #
    # Compute PIK% from component columns if not already present
    pik_col = None
    if "pik_bn" in df.columns and "gross_income_bn" in df.columns:
        gross = df["gross_income_bn"].where(df["gross_income_bn"] > 0)
        pik_col = (df["pik_bn"] / gross).astype(float)

    if pik_col is not None:
        sig.pik_current = _recent_mean(pik_col, 1)
        sig.pik_4q_change = _change(pik_col, 4)
        sig.pik_slope = _slope(pik_col)

        chg = sig.pik_4q_change
        cur = sig.pik_current

        if chg is not None and cur is not None:
            if chg >= 0.10 or (chg >= 0.05 and cur >= 0.20):
                sig.pik_flag = "critical"
                flags.append("pik_escalation")
                score += 1
            elif chg >= 0.04 or (chg >= 0.02 and cur >= 0.12):
                sig.pik_flag = "warn"
                flags.append("pik_rising")
            elif chg >= 0.02:
                sig.pik_flag = "watch"
            else:
                sig.pik_flag = "ok"

    # ------------------------------------------------------------------ #
    # 4. NAV velocity / acceleration
    # ------------------------------------------------------------------ #
    if "nav_qoq_pct" in df.columns:
        vel_s = df["nav_qoq_pct"]
        sig.nav_velocity_recent = _recent_mean(vel_s, 2)
        sig.nav_velocity_prev = _recent_mean(vel_s.iloc[:-2], 2) if len(vel_s) >= 4 else None
        sig.nav_acceleration = _acceleration(vel_s)

        vel = sig.nav_velocity_recent
        accel = sig.nav_acceleration

        if vel is not None:
            if vel <= -0.05:                # >5% quarterly NAV decline
                sig.nav_velocity_flag = "critical"
                flags.append("nav_freefall")
                score += 2
            elif vel <= -0.02:              # 2-5% quarterly decline
                sig.nav_velocity_flag = "warn"
                flags.append("nav_declining")
                score += 1
            elif vel <= -0.01:
                sig.nav_velocity_flag = "watch"
            else:
                sig.nav_velocity_flag = "ok"

            # Acceleration: worsening decline even if not yet at threshold
            if accel is not None and accel <= -0.01 and vel <= -0.01:
                if "nav_declining" not in flags and "nav_freefall" not in flags:
                    flags.append("nav_accelerating")
                    score += 1

    # ------------------------------------------------------------------ #
    # 5. Compounding penalty: coverage + leverage both deteriorating
    # ------------------------------------------------------------------ #
    cov_bad = sig.coverage_flag in ("warn", "critical")
    lev_bad = sig.leverage_flag in ("warn", "critical")
    if cov_bad and lev_bad:
        flags.append("dual_deterioration")
        score += 1  # additional compounding point

    # cap at 5
    sig.trend_score = min(score, 5)
    sig.trend_flags = sorted(set(flags))
    return sig


# ---------------------------------------------------------------------------
# Batch loader
# ---------------------------------------------------------------------------

def load_history(ticker: str, history_dir: Path = HISTORY_DIR) -> Optional[pd.DataFrame]:
    """Load a fund's parquet history, return None if not found."""
    path = history_dir / f"{ticker}_history.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def compute_all_trend_signals(
    history_dir: Path = HISTORY_DIR,
    universe_path: Path = Path("data/bdc_universe.json"),
) -> dict[str, TrendSignal]:
    """Compute trend signals for every fund in the universe that has parquet data.

    Returns dict mapping ticker -> TrendSignal.
    """
    # Load universe for ticker list
    tickers: list[str] = []
    if universe_path.exists():
        data = json.loads(universe_path.read_text(encoding="utf-8"))
        tickers = [f["ticker"] for f in data.get("funds", []) if "ticker" in f]

    # Also pick up any parquet files not in the universe JSON
    existing = {p.stem.replace("_history", "") for p in history_dir.glob("*_history.parquet")}
    all_tickers = list(dict.fromkeys(tickers + sorted(existing - set(tickers))))

    signals: dict[str, TrendSignal] = {}
    for ticker in all_tickers:
        df = load_history(ticker, history_dir)
        if df is not None:
            signals[ticker] = compute_trend_signals(ticker, df)
        else:
            signals[ticker] = TrendSignal(ticker=ticker)

    return signals


# ---------------------------------------------------------------------------
# Convenience: merge trend scores into a universe fund dict
# ---------------------------------------------------------------------------

def enrich_fund_with_trends(fund: dict, signals: dict[str, "TrendSignal"]) -> dict:
    """Return a copy of fund dict with trend_score and trend_flags injected."""
    ticker = fund.get("ticker", "")
    sig = signals.get(ticker)
    enriched = dict(fund)
    if sig is not None:
        enriched["trend_score"] = sig.trend_score
        enriched["trend_flags"] = sig.trend_flags
        enriched["trend_coverage_flag"] = sig.coverage_flag
        enriched["trend_leverage_flag"] = sig.leverage_flag
        enriched["trend_pik_flag"] = sig.pik_flag
        enriched["trend_nav_flag"] = sig.nav_velocity_flag
        # Expose underlying values for screener NII coverage override
        if sig.coverage_current is not None:
            # Only override if EDGAR rolling is more recent/reliable than static snapshot
            if fund.get("nii_coverage") is None:
                enriched["nii_coverage"] = sig.coverage_current
    else:
        enriched["trend_score"] = 0
        enriched["trend_flags"] = []
    return enriched


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Compute BDC trend signals from EDGAR history.")
    parser.add_argument("--ticker", help="Single ticker to report (default: all)")
    parser.add_argument("--min-score", type=int, default=0,
                        help="Only show tickers with trend_score >= N")
    parser.add_argument("--sort", choices=["score", "ticker"], default="score",
                        help="Sort output by score (desc) or ticker (asc)")
    args = parser.parse_args()

    print("Computing trend signals from parquet history...\n")
    signals = compute_all_trend_signals()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = list(signals.keys())

    results = [(t, signals[t]) for t in tickers if t in signals]
    results = [(t, s) for t, s in results if s.trend_score >= args.min_score]

    if args.sort == "score":
        results.sort(key=lambda x: -x[1].trend_score)
    else:
        results.sort(key=lambda x: x[0])

    tier_map = {
        0: "[OK]     ",
        1: "[WATCH]  ",
        2: "[WARN]   ",
        3: "[WARN]   ",
        4: "[ALERT]  ",
        5: "[ALERT]  ",
    }

    print(f"{'Ticker':<8}  {'Score':>5}  {'CovFlg':<8}  {'LevFlg':<8}  "
          f"{'PIKFlg':<8}  {'NAVFlg':<8}  Flags")
    print("-" * 90)
    for ticker, sig in results:
        label = tier_map.get(sig.trend_score, "[?]")
        flags_str = ", ".join(sig.trend_flags) if sig.trend_flags else "—"
        print(f"{label}{ticker:<8}  {sig.trend_score:>5}  "
              f"{sig.coverage_flag:<8}  {sig.leverage_flag:<8}  "
              f"{sig.pik_flag:<8}  {sig.nav_velocity_flag:<8}  {flags_str}")

    print(f"\n{len(results)} ticker(s) shown.\n")

    if args.ticker:
        for ticker, sig in results:
            print(sig.summary())


if __name__ == "__main__":
    main()
