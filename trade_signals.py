"""
trade_signals.py — BDC trade signal generator.

Maps each fund's risk score + price-to-NAV valuation to an actionable signal
using a 4×4 matrix.  Signals are intended as starting points for further
diligence, not buy/sell recommendations.

Risk tiers  (based on composite_score from red_flag_screener):
  LOW       0–4    GREEN
  MODERATE  5–7    YELLOW/low-ORANGE
  ELEVATED  8–11   ORANGE/high-ORANGE
  HIGH      12+    RED

Valuation buckets  (based on price_to_nav; NAV=1.0 for non-listed funds):
  DEEP_DISCOUNT   P/NAV < 0.80   (> 20% discount)
  DISCOUNT        0.80 ≤ P/NAV < 0.95
  FAIR            0.95 ≤ P/NAV ≤ 1.05
  PREMIUM         P/NAV > 1.05

Signal matrix:
               DEEP_DISC   DISCOUNT    FAIR        PREMIUM
  LOW (0-4)    STRONG_BUY  BUY         HOLD        HOLD
  MOD (5-7)    BUY         MONITOR     MONITOR     REDUCE
  ELEV (8-11)  CAUTION     CAUTION     AVOID       AVOID
  HIGH (12+)   AVOID       AVOID       AVOID       AVOID

Non-listed funds (CCLFX, BCRED, BREIT, PIMCO-FCI) have no market price;
they are assessed on risk score alone with a note that trading is restricted.

Usage:
    python trade_signals.py                    # print signal table
    python trade_signals.py --csv signals.csv  # write CSV
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

SIGNAL_ORDER = ["STRONG_BUY", "BUY", "HOLD", "MONITOR", "CAUTION", "REDUCE", "AVOID"]

# Colour codes for display
SIGNAL_COLOR: dict[str, str] = {
    "STRONG_BUY": "darkgreen",
    "BUY":        "green",
    "HOLD":       "steelblue",
    "MONITOR":    "goldenrod",
    "CAUTION":    "darkorange",
    "REDUCE":     "orangered",
    "AVOID":      "firebrick",
}

# Human-readable labels
SIGNAL_LABEL: dict[str, str] = {
    "STRONG_BUY": "Strong Buy",
    "BUY":        "Buy",
    "HOLD":       "Hold",
    "MONITOR":    "Monitor",
    "CAUTION":    "Caution",
    "REDUCE":     "Reduce",
    "AVOID":      "Avoid",
}

# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------

_SCORE_LOW       = 4    # 0–4 → LOW
_SCORE_MODERATE  = 7    # 5–7 → MODERATE
_SCORE_ELEVATED  = 11   # 8–11 → ELEVATED; 12+ → HIGH

_P2N_DEEP_DISC   = 0.80   # < 0.80 → DEEP DISCOUNT
_P2N_DISCOUNT    = 0.95   # 0.80–0.95 → DISCOUNT
_P2N_PREMIUM     = 1.05   # > 1.05 → PREMIUM; else FAIR

# Signal lookup table: (risk_bucket, val_bucket) → signal
_MATRIX: dict[tuple[str, str], str] = {
    ("LOW",      "DEEP_DISCOUNT"): "STRONG_BUY",
    ("LOW",      "DISCOUNT"):      "BUY",
    ("LOW",      "FAIR"):          "HOLD",
    ("LOW",      "PREMIUM"):       "HOLD",

    ("MODERATE", "DEEP_DISCOUNT"): "BUY",
    ("MODERATE", "DISCOUNT"):      "MONITOR",
    ("MODERATE", "FAIR"):          "MONITOR",
    ("MODERATE", "PREMIUM"):       "REDUCE",

    ("ELEVATED", "DEEP_DISCOUNT"): "CAUTION",
    ("ELEVATED", "DISCOUNT"):      "CAUTION",
    ("ELEVATED", "FAIR"):          "AVOID",
    ("ELEVATED", "PREMIUM"):       "AVOID",

    ("HIGH",     "DEEP_DISCOUNT"): "AVOID",
    ("HIGH",     "DISCOUNT"):      "AVOID",
    ("HIGH",     "FAIR"):          "AVOID",
    ("HIGH",     "PREMIUM"):       "AVOID",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TradeSignal:
    ticker: str
    name: str
    signal: str                      # e.g. "BUY"
    risk_score: int
    risk_bucket: str                 # LOW / MODERATE / ELEVATED / HIGH
    val_bucket: str                  # DEEP_DISCOUNT / DISCOUNT / FAIR / PREMIUM
    price_to_nav: Optional[float]
    nav_discount_pct: Optional[float]  # negative = discount
    key_flags: list[str]
    listed: bool                     # False for interval/non-traded funds
    rationale: str

    @property
    def signal_label(self) -> str:
        return SIGNAL_LABEL.get(self.signal, self.signal)

    @property
    def signal_rank(self) -> int:
        """Lower = more bullish."""
        return SIGNAL_ORDER.index(self.signal) if self.signal in SIGNAL_ORDER else 99


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _risk_bucket(score: int) -> str:
    if score <= _SCORE_LOW:
        return "LOW"
    if score <= _SCORE_MODERATE:
        return "MODERATE"
    if score <= _SCORE_ELEVATED:
        return "ELEVATED"
    return "HIGH"


def _val_bucket(p2n: Optional[float], listed: bool) -> str:
    if not listed or p2n is None:
        return "FAIR"   # treat NAV=1.0 for non-listed
    if p2n < _P2N_DEEP_DISC:
        return "DEEP_DISCOUNT"
    if p2n < _P2N_DISCOUNT:
        return "DISCOUNT"
    if p2n > _P2N_PREMIUM:
        return "PREMIUM"
    return "FAIR"


def _build_rationale(
    signal: str,
    risk_bucket: str,
    val_bucket: str,
    score: int,
    p2n: Optional[float],
    flags: list[str],
    listed: bool,
) -> str:
    parts: list[str] = []

    disc_str = ""
    if p2n is not None:
        pct = (p2n - 1.0) * 100
        disc_str = f"{abs(pct):.0f}% {'discount' if pct < 0 else 'premium'} to NAV"

    if signal == "STRONG_BUY":
        parts.append(f"Low risk score ({score}/18) with {disc_str}.")
        parts.append("Quality franchise trading well below fair value.")
    elif signal == "BUY":
        if risk_bucket == "LOW":
            parts.append(f"Low risk score ({score}/18) near fair value{' with ' + disc_str if disc_str else ''}.")
        else:
            parts.append(f"Moderate risk ({score}/18) but {disc_str} prices in elevated concerns.")
    elif signal == "HOLD":
        if p2n and p2n > _P2N_PREMIUM:
            parts.append(f"Solid fundamentals but {disc_str}. Limited upside from current level.")
        else:
            parts.append(f"Low risk ({score}/18) trading near NAV. No clear catalyst to add.")
    elif signal == "MONITOR":
        parts.append(f"Mixed picture: risk score {score}/18 with {disc_str or 'fair valuation'}.")
        parts.append("Watch for deterioration before sizing up.")
    elif signal == "CAUTION":
        parts.append(f"Elevated risk ({score}/18) but {disc_str} may be pricing in stress.")
        parts.append("Potential value trap — confirm thesis before acting.")
    elif signal == "REDUCE":
        parts.append(f"Moderate concerns ({score}/18) trading at {disc_str}.")
        parts.append("Risk/reward unfavorable; trim on strength.")
    elif signal == "AVOID":
        parts.append(f"High risk score ({score}/18).")
        if p2n and p2n > _P2N_PREMIUM:
            parts.append(f"Trading at {disc_str} — expensive given fundamental risk.")
        parts.append("Wait for material improvement in credit quality before re-evaluating.")

    if not listed:
        parts.append("(Non-listed: no market price, trading restricted.)")

    if flags:
        top = flags[:3]
        parts.append(f"Key flags: {', '.join(top)}" + (" ..." if len(flags) > 3 else "."))

    return " ".join(parts)


def compute_signals(
    funds: list[dict],
    score_overrides: Optional[dict[str, dict]] = None,
) -> list[TradeSignal]:
    """Compute a TradeSignal for every fund.

    Parameters
    ----------
    funds:
        Fund dicts (from load_universe / enrich_funds_with_prices).
        Each dict should have: ticker, name, type, price_to_nav,
        _nav_discount_pct, composite_score (or we'll call score_fund).
    score_overrides:
        Optional pre-computed score dicts keyed by ticker (from score_fund).
        If not supplied, score_fund is called internally.
    """
    from red_flag_screener import score_fund

    signals: list[TradeSignal] = []
    for fund in funds:
        ticker = fund.get("ticker", "").upper()
        ftype  = fund.get("type", "")
        listed = ftype == "listed_bdc"

        sc = (score_overrides or {}).get(ticker) or score_fund(fund)
        score  = sc["composite_score"]
        flags  = sc["flags_triggered"]

        p2n  = fund.get("price_to_nav")
        disc = fund.get("_nav_discount_pct")

        rb = _risk_bucket(score)
        vb = _val_bucket(p2n, listed)

        signal = _MATRIX[(rb, vb)]

        rationale = _build_rationale(signal, rb, vb, score, p2n, flags, listed)

        signals.append(TradeSignal(
            ticker=ticker,
            name=fund.get("name", ticker),
            signal=signal,
            risk_score=score,
            risk_bucket=rb,
            val_bucket=vb,
            price_to_nav=p2n,
            nav_discount_pct=disc,
            key_flags=flags,
            listed=listed,
            rationale=rationale,
        ))

    signals.sort(key=lambda s: (s.signal_rank, -s.risk_score))
    return signals


def signals_to_dataframe(signals: list[TradeSignal]):
    """Convert signal list to a pandas DataFrame for display."""
    import pandas as pd

    rows = []
    for s in signals:
        disc_s = f"{s.nav_discount_pct:+.1f}%" if s.nav_discount_pct is not None else "n/a"
        p2n_s  = f"{s.price_to_nav:.3f}x" if s.price_to_nav is not None else "n/a"
        rows.append({
            "Ticker":    s.ticker,
            "Signal":    s.signal_label,
            "Score":     s.risk_score,
            "Risk":      s.risk_bucket.title(),
            "Valuation": s.val_bucket.replace("_", " ").title(),
            "P/NAV":     p2n_s,
            "Disc/Prem": disc_s,
            "Key Flags": ", ".join(s.key_flags[:3]) + (" ..." if len(s.key_flags) > 3 else ""),
        })
    return pd.DataFrame(rows)


def build_signal_matrix_df(signals: list[TradeSignal]):
    """Return a pivot DataFrame showing the signal grid with fund tickers in each cell."""
    import pandas as pd

    risk_order = ["LOW", "MODERATE", "ELEVATED", "HIGH"]
    val_order  = ["DEEP_DISCOUNT", "DISCOUNT", "FAIR", "PREMIUM"]
    val_labels = {
        "DEEP_DISCOUNT": "Deep Discount\n(<0.80x)",
        "DISCOUNT":      "Discount\n(0.80–0.95x)",
        "FAIR":          "Fair Value\n(0.95–1.05x)",
        "PREMIUM":       "Premium\n(>1.05x)",
    }
    risk_labels = {
        "LOW":      "Low (0–4)",
        "MODERATE": "Moderate (5–7)",
        "ELEVATED": "Elevated (8–11)",
        "HIGH":     "High (12+)",
    }

    cells: dict[tuple[str, str], list[str]] = {(r, v): [] for r in risk_order for v in val_order}
    for s in signals:
        cells[(s.risk_bucket, s.val_bucket)].append(s.ticker)

    data = {}
    for v in val_order:
        col = []
        for r in risk_order:
            tickers = cells[(r, v)]
            signal  = _MATRIX[(r, v)]
            col.append(f"[{SIGNAL_LABEL[signal]}]\n" + ", ".join(tickers) if tickers else f"[{SIGNAL_LABEL[signal]}]")
        data[val_labels[v]] = col

    return pd.DataFrame(data, index=[risk_labels[r] for r in risk_order])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse, csv, sys

    parser = argparse.ArgumentParser(description="BDC trade signal generator.")
    parser.add_argument("--csv", metavar="FILE", help="Write output to CSV file.")
    parser.add_argument("--matrix", action="store_true", help="Print 2x2 signal matrix.")
    args = parser.parse_args()

    from red_flag_screener import load_universe
    from price_feed import enrich_funds_with_prices

    funds = enrich_funds_with_prices(load_universe())
    signals = compute_signals(funds)

    if args.matrix:
        df = build_signal_matrix_df(signals)
        print("\n=== BDC Trade Signal Matrix ===\n")
        print(df.to_string())
        return

    # Table output
    hdr = f"{'Ticker':<8} {'Signal':<12} {'Score':>5} {'Risk':<10} {'Valuation':<15} {'P/NAV':>7} {'Disc/Prem':>10}"
    print(f"\n{hdr}")
    print("-" * len(hdr))
    for s in signals:
        p2n  = f"{s.price_to_nav:.3f}x" if s.price_to_nav is not None else "   n/a"
        disc = f"{s.nav_discount_pct:+.1f}%" if s.nav_discount_pct is not None else "    n/a"
        vb   = s.val_bucket.replace("_", " ").title()
        print(f"{s.ticker:<8} {s.signal_label:<12} {s.risk_score:>5} {s.risk_bucket.title():<10} {vb:<15} {p2n:>7} {disc:>10}")

    print(f"\n{len(signals)} funds  |  {sum(s.signal in ('STRONG_BUY','BUY') for s in signals)} buy signals  "
          f"|  {sum(s.signal == 'AVOID' for s in signals)} avoids")

    if args.csv:
        df = signals_to_dataframe(signals)
        df.to_csv(args.csv, index=False)
        print(f"Saved to {args.csv}")


if __name__ == "__main__":
    main()
