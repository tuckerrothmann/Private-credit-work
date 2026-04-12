"""
distribution_model.py — Distribution sustainability + rate sensitivity models.

For each BDC, projects NII coverage forward 8 quarters using current coverage
and the trailing trend from quarterly EDGAR history.  Flags distribution cut
risk based on how quickly coverage is projected to breach the 0.85x / 0.70x
thresholds.

Also models NII sensitivity to SOFR rate changes using gross asset and debt
figures, adjusted for floating-rate exposure on both the asset and liability sides.

Asset floating rate:  per-fund "floating_rate_pct" in bdc_universe.json
Liability floating:   per-fund "floating_liability_pct" (default 0.40)

Usage:
    python distribution_model.py                    # full sustainability table
    python distribution_model.py --rate -100        # highlight -100bps scenario
    python distribution_model.py --no-trends        # static metrics only
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Coverage thresholds for distribution-cut risk tiers
_MODERATE_CUT_THRESH = 0.85   # probable trim
_SEVERE_CUT_THRESH   = 0.70   # probable significant cut / suspension

# Default fraction of total debt that is floating-rate (revolving facilities)
_DEFAULT_FLOAT_LIAB = 0.40


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class DistributionOutlook:
    ticker: str
    name: str
    current_coverage: float
    coverage_trend_per_q: float         # quarterly linear slope (neg = deteriorating)
    projected_8q: list[float]           # projected coverage each of next 8 quarters
    quarters_to_moderate_cut: Optional[int]   # first Q where projected < 0.85
    quarters_to_severe_cut:   Optional[int]   # first Q where projected < 0.70
    cut_risk: str                       # "HIGH" | "MEDIUM" | "LOW" | "STABLE"
    # Rate sensitivity (NII $ change for SOFR move)
    rate_nii_impact_100bps_mm: float    # $M NII change for -100bps SOFR
    rate_nii_impact_200bps_mm: float
    # Coverage impact of rate moves (delta applied uniformly to projected path)
    rate_cov_impact_100bps: float
    rate_cov_impact_200bps: float
    notes: str = ""

    @property
    def cut_risk_icon(self) -> str:
        return {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟡", "STABLE": "🟢"}.get(
            self.cut_risk, "⚪"
        )

    def coverage_at_q(self, q: int, rate_delta_bps: int = 0) -> float:
        """Return projected coverage at quarter *q* (1-based) under a rate scenario."""
        base = self.projected_8q[q - 1] if 1 <= q <= 8 else self.current_coverage
        rate_adj = (rate_delta_bps / -100) * self.rate_cov_impact_100bps
        return max(0.0, base + rate_adj)


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------

def _project_coverage(current: float, trend_per_q: float, n: int = 8) -> list[float]:
    return [max(0.0, current + trend_per_q * (i + 1)) for i in range(n)]


def _rate_nii_impact_mm(
    gross_assets_bn: float,
    total_debt_bn: float,
    float_asset_pct: float,
    float_liab_pct: float,
    delta_bps: int,
) -> float:
    """NII change in $M for *delta_bps* SOFR move (negative = rate decrease)."""
    asset_sens = gross_assets_bn * float_asset_pct * (delta_bps / 10_000)
    liab_sens  = total_debt_bn  * float_liab_pct  * (delta_bps / 10_000)
    return (asset_sens - liab_sens) * 1_000   # $B → $M


def _annual_dist_mm(fund: dict) -> Optional[float]:
    """Annual distribution run-rate in $M, or None if data is insufficient."""
    dist_q = fund.get("distribution_per_share_quarterly")
    nav_bn = fund.get("nav_bn")
    nav_ps = fund.get("nav_per_share")
    if not (dist_q and nav_bn and nav_ps and nav_ps > 0):
        return None
    shares = nav_bn * 1e9 / nav_ps
    return dist_q * 4 * shares / 1e6


def compute_distribution_outlook(
    fund: dict,
    trend_data: dict | None = None,
) -> Optional[DistributionOutlook]:
    """Compute a DistributionOutlook for *fund*.

    *trend_data* is the per-ticker dict from trend_signals (keys: coverage_4q_change,
    coverage_current, etc.).  Handles both plain dicts and dataclass instances.
    Returns None if the fund lacks required metrics.
    """
    cov = fund.get("nii_coverage")
    if cov is None:
        return None
    cov = float(cov)

    gross = fund.get("gross_assets_bn")
    debt  = fund.get("total_debt_bn")
    if not gross or not debt or debt <= 0:
        return None

    # Extract trend from trend_signals output (dataclass or dict)
    td: dict = {}
    if trend_data is not None:
        td = trend_data.__dict__ if hasattr(trend_data, "__dict__") else trend_data

    cov_4q_chg = td.get("coverage_4q_change")
    trend_per_q = float(cov_4q_chg) / 4.0 if cov_4q_chg is not None else 0.0

    projected = _project_coverage(cov, trend_per_q)

    q_mod = next((i + 1 for i, v in enumerate(projected) if v < _MODERATE_CUT_THRESH), None)
    q_sev = next((i + 1 for i, v in enumerate(projected) if v < _SEVERE_CUT_THRESH),   None)

    # Cut risk tier
    if cov < _SEVERE_CUT_THRESH or (q_sev is not None and q_sev <= 2):
        cut_risk = "HIGH"
    elif cov < _MODERATE_CUT_THRESH or (q_mod is not None and q_mod <= 3):
        cut_risk = "MEDIUM"
    elif q_mod is not None:
        cut_risk = "LOW"
    else:
        cut_risk = "STABLE"

    float_asset = float(fund.get("floating_rate_pct", 0.92))
    float_liab  = float(fund.get("floating_liability_pct", _DEFAULT_FLOAT_LIAB))

    nii_100 = _rate_nii_impact_mm(gross, debt, float_asset, float_liab, -100)
    nii_200 = _rate_nii_impact_mm(gross, debt, float_asset, float_liab, -200)

    # Coverage impact = NII delta / annual distributions
    ann_dist = _annual_dist_mm(fund)
    cov_d100 = nii_100 / ann_dist if ann_dist else 0.0
    cov_d200 = nii_200 / ann_dist if ann_dist else 0.0

    # Build notes string
    notes_parts: list[str] = []
    if trend_per_q < -0.04:
        notes_parts.append(f"Deteriorating {trend_per_q * 4:.2f}x/yr")
    if cov < _MODERATE_CUT_THRESH:
        notes_parts.append("Already below 0.85x")
    if q_mod and q_mod <= 4:
        notes_parts.append(f"Breach 0.85x at Q{q_mod}")
    if q_sev and q_sev <= 4:
        notes_parts.append(f"Breach 0.70x at Q{q_sev}")

    return DistributionOutlook(
        ticker=fund.get("ticker", ""),
        name=fund.get("name", ""),
        current_coverage=cov,
        coverage_trend_per_q=trend_per_q,
        projected_8q=projected,
        quarters_to_moderate_cut=q_mod,
        quarters_to_severe_cut=q_sev,
        cut_risk=cut_risk,
        rate_nii_impact_100bps_mm=nii_100,
        rate_nii_impact_200bps_mm=nii_200,
        rate_cov_impact_100bps=cov_d100,
        rate_cov_impact_200bps=cov_d200,
        notes="; ".join(notes_parts),
    )


def compute_all_outlooks(
    funds: list[dict],
    trend_signals: dict | None = None,
) -> dict[str, DistributionOutlook]:
    """Compute outlooks for all funds. Returns dict[ticker, DistributionOutlook]."""
    signals = trend_signals or {}
    result: dict[str, DistributionOutlook] = {}
    for fund in funds:
        t = fund.get("ticker", "")
        outlook = compute_distribution_outlook(fund, trend_data=signals.get(t))
        if outlook:
            result[t] = outlook
    return result


def load_trend_signals() -> dict:
    """Load trend signals from parquet history. Returns dict[ticker, TrendSignal]."""
    try:
        from trend_signals import compute_all_trend_signals
        return compute_all_trend_signals(
            history_dir=Path("data/edgar_cache/history"),
            universe_path=Path("data/bdc_universe.json"),
        )
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Peer comparison helpers
# ---------------------------------------------------------------------------

_PEER_METRICS = [
    ("nii_coverage",             "NII Coverage",      False),  # higher = better
    ("leverage_de",              "D/E Leverage",      True),   # lower = better
    ("nonaccrual_pct_fair_value","Non-Accrual % FV",  True),
    ("pik_pct_of_income",        "PIK % Income",      True),
    ("nav_change_yoy_pct",       "NAV Chg YoY",       False),
    ("price_to_nav",             "P/NAV",             False),
]


def compute_peer_rankings(funds: list[dict]) -> "pd.DataFrame":  # type: ignore[name-defined]
    """Return a DataFrame with cross-sectional percentile rankings for all funds.

    For each metric, Rank=1 is best (highest NII coverage, lowest leverage, etc.).
    Includes raw values and percentile ranks (0-100, 100 = best).
    """
    import pandas as pd
    import numpy as np

    rows = []
    for f in funds:
        row: dict = {
            "Ticker": f.get("ticker", ""),
            "Name": f.get("name", ""),
            "Type": f.get("type", ""),
        }
        for key, label, lower_is_better in _PEER_METRICS:
            v = f.get(key)
            row[label] = v
        rows.append(row)

    df = pd.DataFrame(rows)

    # Add percentile columns (higher percentile = better)
    for key, label, lower_is_better in _PEER_METRICS:
        col = df[label].dropna()
        if col.empty:
            continue
        pct_col = label + " Pct"
        def _pct(v, series=col, inv=lower_is_better):
            if pd.isna(v):
                return np.nan
            rank = (series < v).sum() / max(len(series) - 1, 1) * 100
            return (100 - rank) if inv else rank
        df[pct_col] = df[label].apply(_pct)

    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Distribution sustainability analysis.")
    parser.add_argument("--rate", type=int, default=0,
                        help="SOFR delta in bps to overlay (e.g. -100).")
    parser.add_argument("--no-trends", action="store_true",
                        help="Use static metrics only (skip EDGAR parquet history).")
    args = parser.parse_args()

    from red_flag_screener import load_universe, load_universe_with_trends
    funds = load_universe() if args.no_trends else load_universe_with_trends()
    signals = {} if args.no_trends else load_trend_signals()

    outlooks = compute_all_outlooks(funds, trend_signals=signals)

    _ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "STABLE": 3}
    rows = sorted(outlooks.values(), key=lambda o: (_ORDER.get(o.cut_risk, 9), o.current_coverage))

    _enc = lambda s: s.encode("ascii", errors="replace").decode("ascii")
    print(f"\nDistribution Sustainability -- {len(rows)} funds\n")
    hdr = (f"{'Ticker':<8} {'NII Cov':>8} {'Trend/Q':>8} {'Q to 0.85':>10} "
           f"{'Cut Risk':<10} {'NII@-100':>10} {'NII@-200':>10}  Notes")
    print(hdr)
    print("-" * len(hdr))
    for o in rows:
        q85   = f"Q{o.quarters_to_moderate_cut}" if o.quarters_to_moderate_cut else "   >8Q"
        n100  = f"${o.rate_nii_impact_100bps_mm:+.0f}M"
        n200  = f"${o.rate_nii_impact_200bps_mm:+.0f}M"
        trend = f"{o.coverage_trend_per_q:+.3f}x"
        line  = (f"{o.ticker:<8} {o.current_coverage:>8.3f}x {trend:>8} {q85:>10} "
                 f"  {o.cut_risk:<8} {n100:>10} {n200:>10}  {o.notes}")
        print(_enc(line))

    if args.rate != 0:
        print(f"\n── Scenario: SOFR {args.rate:+d}bps ─────────────────────────────────")
        for o in rows:
            cov_adj = o.current_coverage + (args.rate / -100) * o.rate_cov_impact_100bps
            delta   = cov_adj - o.current_coverage
            print(f"  {o.ticker:<8}  base {o.current_coverage:.3f}x  "
                  f"→ scenario {cov_adj:.3f}x  ({delta:+.3f}x)")


if __name__ == "__main__":
    main()
