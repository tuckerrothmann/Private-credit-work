"""
Red Flag Screener for BDCs and Private Credit Funds
====================================================
Systematic risk-scoring system that identifies potentially problematic
BDCs and private-credit interval funds based on publicly disclosed metrics.

Each fund is scored on nine dimensions; scores are summed to a composite
risk score (0–23 scale, higher = more concern).  Individual flag details
are preserved alongside the composite for explainability.

Scoring rubric
--------------
1. PIK Creep              (0–2): >10% of income = 1; >20% = 2
2. Distribution Coverage  (0–3): NII/Dist <1.0x = 1; <0.85x = 2; <0.70x = 3
3. NAV Erosion            (0–3): <−3% YoY = 1; <−7% = 2; <−15% = 3
4. Non-accrual Rate       (0–3): >3% FV = 1; >6% FV = 2; >12% FV = 3
5. Leverage               (0–2): D/E >1.25x = 1; >1.50x = 2
6. Market Discount        (0–2): Price/NAV <0.90 = 1; <0.75 = 2
7. Flow Pressure          (0–2): Net quarterly outflow >−1% = 1; >−3% = 2
8. Override Flags         (0–1): Management flags from manual review
9. Trend Deterioration    (0–5): From trend_signals.py momentum analysis

Risk tiers:
   0–4   GREEN   Routine monitoring
   5–7   YELLOW  Elevated — watch list
   8–11  ORANGE  Significant concern — detailed review warranted
  12+    RED     Critical — potential deterioration / investor harm

Usage
-----
    from red_flag_screener import screen_universe, load_universe, FundScore

    funds = load_universe("data/bdc_universe.json")
    scores = screen_universe(funds)
    for score in scores:
        print(score.summary())

    # With trend signals integrated:
    from red_flag_screener import load_universe_with_trends
    funds = load_universe_with_trends()
    scores = screen_universe(funds)
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Trend signal integration (imported lazily to avoid hard dep when not available)
_TREND_SIGNALS_AVAILABLE = True
try:
    from trend_signals import compute_all_trend_signals, enrich_fund_with_trends
except ImportError:
    _TREND_SIGNALS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Flag definitions
# ---------------------------------------------------------------------------

# (flag_key, human_label, severity_adjective)
FLAG_DEFINITIONS = [
    ("pik_creep_moderate",          "PIK income >10% of total income",         "moderate"),
    ("pik_creep_severe",            "PIK income >20% of total income",          "severe"),
    ("coverage_below_1x",           "NII covers <1.0x distributions",           "moderate"),
    ("coverage_below_085x",         "NII covers <0.85x distributions",          "significant"),
    ("coverage_below_070x",         "NII covers <0.70x distributions",          "critical"),
    ("nav_erosion_mild",            "NAV down >3% YoY",                         "mild"),
    ("nav_erosion_moderate",        "NAV down >7% YoY",                         "significant"),
    ("nav_erosion_severe",          "NAV down >15% YoY",                        "critical"),
    ("nonaccrual_elevated",         "Non-accruals >3% of fair value",           "elevated"),
    ("nonaccrual_high",             "Non-accruals >6% of fair value",           "high"),
    ("nonaccrual_critical",         "Non-accruals >12% of fair value",          "critical"),
    ("leverage_moderate",           "Debt/equity >1.25x",                       "moderate"),
    ("leverage_high",               "Debt/equity >1.50x",                       "high"),
    ("discount_moderate",           "Price/NAV discount >10%",                  "moderate"),
    ("discount_severe",             "Price/NAV discount >25%",                  "significant"),
    ("net_outflow_mild",            "Quarterly net investor outflow >1% NAV",   "mild"),
    ("net_outflow_severe",          "Quarterly net investor outflow >3% NAV",   "significant"),
    ("related_party_concern",       "Related-party loan concentration flagged",  "governance"),
    ("persistent_nav_erosion",      "Multi-year NAV erosion pattern",           "governance"),
    ("high_pik_dependency",         "Reliant on PIK for distribution coverage", "governance"),
    ("distribution_cut_history",    "Prior distribution cut(s) on record",      "history"),
    ("predecessor_fund_issues",     "Predecessor fund had material issues",     "history"),
    ("distribution_cut_risk",       "Distribution cut risk elevated",           "risk"),
    ("sector_concentration_stress", "Concentrated sector under stress",         "risk"),
    ("severe_nav_erosion",          "Severe multi-period NAV decline",          "critical"),
    ("critical_nonaccruals",        "Non-accruals at critical levels",          "critical"),
    ("net_redemption_period",       "Interval fund in net redemption",          "liquidity"),
    ("distribution_not_nii_covered","Distributions partially funded non-NII",   "structural"),
    ("elevated_nonaccruals",        "Non-accruals persistently elevated",       "elevated"),
    ("high_leverage",               "Leverage above peer median",               "moderate"),
    ("redemption_gate_history",     "Prior redemption gate or queue imposed",   "history"),
    # Trend momentum flags (injected by trend_signals)
    ("trend_coverage_collapse",     "NII coverage collapsing (>0.40x drop, 4Q)", "trend"),
    ("trend_coverage_declining",    "NII coverage declining trend (>0.20x, 4Q)", "trend"),
    ("trend_leverage_surge",        "Leverage surging (>0.40x D/E increase, 4Q)", "trend"),
    ("trend_leverage_creep",        "Leverage creeping higher (>0.20x, 4Q)",    "trend"),
    ("trend_pik_escalation",        "PIK% rising sharply (>10ppt over 4Q)",     "trend"),
    ("trend_pik_rising",            "PIK% rising (>4ppt over 4Q)",              "trend"),
    ("trend_nav_freefall",          "NAV declining >5%/quarter recently",        "trend"),
    ("trend_nav_declining",         "NAV declining >2%/quarter recently",        "trend"),
    ("trend_nav_accelerating",      "Rate of NAV decline worsening",            "trend"),
    ("trend_dual_deterioration",    "Coverage AND leverage both deteriorating",  "trend"),
    # Leverage headroom flags (regulatory asset-coverage buffer)
    ("headroom_tight",    "Asset coverage <175% — tight regulatory buffer",   "critical"),
    ("headroom_limited",  "Asset coverage <200% — limited regulatory buffer", "moderate"),
]

FLAG_LABELS = {k: label for k, label, _ in FLAG_DEFINITIONS}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_fund(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compute a red-flag score for a single fund from its metrics dict.

    The metrics dict should match the schema in data/bdc_universe.json.
    Missing values are treated conservatively (no score contribution).

    Returns a dict with:
      - composite_score: int  (sum of all dimension scores)
      - dimension_scores: dict[str, int]
      - flags_triggered: list[str]  (flag keys)
      - risk_tier: "GREEN" | "YELLOW" | "ORANGE" | "RED"
    """
    dims: dict[str, int] = {}
    flags: list[str] = []

    def _add(dim: str, points: int, *flag_keys: str) -> None:
        dims[dim] = dims.get(dim, 0) + points
        flags.extend(flag_keys)

    pik = metrics.get("pik_pct_of_income")
    if pik is not None:
        if pik >= 0.20:
            _add("pik_creep", 2, "pik_creep_severe")
        elif pik >= 0.10:
            _add("pik_creep", 1, "pik_creep_moderate")

    cov = metrics.get("nii_coverage")
    if cov is not None and not math.isnan(float(cov)):
        cov = float(cov)
        if cov < 0.70:
            _add("distribution_coverage", 3, "coverage_below_1x", "coverage_below_085x", "coverage_below_070x")
        elif cov < 0.85:
            _add("distribution_coverage", 2, "coverage_below_1x", "coverage_below_085x")
        elif cov < 1.00:
            _add("distribution_coverage", 1, "coverage_below_1x")

    nav_chg = metrics.get("nav_change_yoy_pct")
    if nav_chg is not None:
        if nav_chg <= -0.15:
            _add("nav_erosion", 3, "nav_erosion_mild", "nav_erosion_moderate", "nav_erosion_severe")
        elif nav_chg <= -0.07:
            _add("nav_erosion", 2, "nav_erosion_mild", "nav_erosion_moderate")
        elif nav_chg <= -0.03:
            _add("nav_erosion", 1, "nav_erosion_mild")

    na_fv = metrics.get("nonaccrual_pct_fair_value")
    if na_fv is not None:
        if na_fv >= 0.12:
            _add("nonaccruals", 3, "nonaccrual_elevated", "nonaccrual_high", "nonaccrual_critical")
        elif na_fv >= 0.06:
            _add("nonaccruals", 2, "nonaccrual_elevated", "nonaccrual_high")
        elif na_fv >= 0.03:
            _add("nonaccruals", 1, "nonaccrual_elevated")

    lev = metrics.get("leverage_de")
    if lev is not None:
        if lev >= 1.50:
            _add("leverage", 2, "leverage_moderate", "leverage_high")
        elif lev >= 1.25:
            _add("leverage", 1, "leverage_moderate")

    p2n = metrics.get("price_to_nav")
    if p2n is not None:
        if p2n <= 0.75:
            _add("market_discount", 2, "discount_moderate", "discount_severe")
        elif p2n <= 0.90:
            _add("market_discount", 1, "discount_moderate")

    # Flow pressure (interval / non-traded only)
    net_flow = metrics.get("net_flow_quarterly")
    if net_flow is not None:
        if net_flow <= -0.03:
            _add("flow_pressure", 2, "net_outflow_mild", "net_outflow_severe")
        elif net_flow <= -0.01:
            _add("flow_pressure", 1, "net_outflow_mild")

    # Leverage headroom: BDC regulatory minimum is 150% asset coverage (assets/debt)
    # Derive from D/E as primary — asset_cov = 1 + 1/D_E = (nav+debt)/debt
    # Fall back to gross_assets/debt when D/E is unavailable.
    _de = metrics.get("leverage_de")
    _gross = metrics.get("gross_assets_bn")
    _debt  = metrics.get("total_debt_bn")
    if _de and float(_de) > 0:
        asset_cov_ratio = 1.0 + 1.0 / float(_de)
    elif _gross and _debt and float(_debt) > 0:
        asset_cov_ratio = float(_gross) / float(_debt)
    else:
        asset_cov_ratio = None
    if asset_cov_ratio is not None:
        if asset_cov_ratio < 1.75:
            _add("leverage_headroom", 2, "headroom_tight", "headroom_limited")
        elif asset_cov_ratio < 2.00:
            _add("leverage_headroom", 1, "headroom_limited")

    # Manual override flags — each adds 1 composite point and the flag itself
    overrides = metrics.get("red_flag_overrides", {})
    override_points = 0
    for key, active in overrides.items():
        if active and key in FLAG_LABELS:
            flags.append(key)
            override_points += 1
    if override_points:
        dims["override_flags"] = override_points

    # Trend deterioration dimension (0–5) — pre-computed by trend_signals.py
    # Injected as "trend_score" and "trend_flags" keys by enrich_fund_with_trends()
    trend_pts = metrics.get("trend_score", 0) or 0
    if trend_pts > 0:
        dims["trend_deterioration"] = int(min(trend_pts, 5))
        for tf in (metrics.get("trend_flags") or []):
            # Map trend signal flag names to our flag namespace (prefix with "trend_")
            mapped = f"trend_{tf}" if not tf.startswith("trend_") else tf
            if mapped in FLAG_LABELS:
                flags.append(mapped)

    composite = sum(dims.values())

    if composite >= 12:
        tier = "RED"
    elif composite >= 8:
        tier = "ORANGE"
    elif composite >= 5:
        tier = "YELLOW"
    else:
        tier = "GREEN"

    return {
        "composite_score":  composite,
        "dimension_scores": dims,
        "flags_triggered":  sorted(set(flags)),
        "risk_tier":        tier,
    }


# ---------------------------------------------------------------------------
# Fund score dataclass
# ---------------------------------------------------------------------------

@dataclass
class FundScore:
    ticker: str
    name: str
    fund_type: str
    manager: str
    nav_bn: Optional[float]
    composite_score: int
    dimension_scores: dict[str, int]
    flags_triggered: list[str]
    risk_tier: str
    analyst_notes: str = ""
    metrics: dict[str, Any] = field(default_factory=dict, repr=False)

    def flag_labels(self) -> list[str]:
        """Human-readable labels for all triggered flags."""
        return [FLAG_LABELS.get(f, f) for f in self.flags_triggered]

    def summary(self) -> str:
        nav_str = f"${self.nav_bn:.1f}B" if self.nav_bn else "n/a"
        lines = [
            f"{'─' * 70}",
            f"[{self.risk_tier:6s}]  {self.ticker:12s}  {self.name}",
            f"           Score: {self.composite_score}/18  |  NAV: {nav_str}  |  "
            f"Type: {self.fund_type}  |  Manager: {self.manager}",
        ]
        if self.flags_triggered:
            lines.append("           Flags:")
            for lbl in self.flag_labels():
                lines.append(f"             • {lbl}")
        if self.analyst_notes:
            # wrap analyst notes to ~80 chars
            note_words = self.analyst_notes.split()
            line_buf, note_lines = [], []
            for word in note_words:
                line_buf.append(word)
                if sum(len(w) + 1 for w in line_buf) > 72:
                    note_lines.append("           " + " ".join(line_buf[:-1]))
                    line_buf = [word]
            if line_buf:
                note_lines.append("           " + " ".join(line_buf))
            lines.append("           Notes:")
            lines.extend(note_lines)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Universe screening
# ---------------------------------------------------------------------------

def load_universe(path: Path | str = "data/bdc_universe.json") -> list[dict[str, Any]]:
    """Load the BDC universe JSON and return the list of fund dicts."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("funds", [])


def load_universe_with_trends(
    path: Path | str = "data/bdc_universe.json",
    history_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Load universe JSON and enrich each fund with trend signals from parquet history
    and fresh EDGAR XBRL metrics from universe_metrics.json.

    Falls back gracefully if trend_signals module is unavailable or parquets are missing.
    EDGAR enrichment is applied first, then trend signals on top.
    """
    funds = load_universe(path)

    # Overlay fresh EDGAR XBRL metrics (nii_coverage, leverage_de, nav_per_share, etc.)
    funds = enrich_funds_with_edgar_metrics(funds)

    if not _TREND_SIGNALS_AVAILABLE:
        return funds
    try:
        from pathlib import Path as _Path
        hdir = history_dir or _Path("data/edgar_cache/history")
        from trend_signals import compute_all_trend_signals, enrich_fund_with_trends
        signals = compute_all_trend_signals(history_dir=hdir, universe_path=_Path(path))
        return [enrich_fund_with_trends(f, signals) for f in funds]
    except Exception:
        return funds


def enrich_funds_with_edgar_metrics(
    funds: list[dict[str, Any]],
    cache_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Overlay fresh EDGAR XBRL metrics from universe_metrics.json onto each fund dict.

    Field mappings (EDGAR → fund dict):
      nii_coverage_ratio  → nii_coverage
      leverage_de         → leverage_de
      pik_pct_of_income   → pik_pct_of_income
      nav_per_share_usd   → nav_per_share
      net_assets_usd/1e9  → nav_bn
      total_assets_usd/1e9 → gross_assets_bn
      long_term_debt_usd/1e9 → total_debt_bn
      as_of_date          → edgar_as_of
      unrealized_depreciation_pct → unrealized_gain_loss_pct

    Only overwrites with EDGAR values that are non-None (preserves static values
    for funds where EDGAR returned an error or missing field).
    """
    _default = Path("data/edgar_cache/universe_metrics.json")
    cache_path = (Path(cache_dir) / "universe_metrics.json") if cache_dir else _default
    if not cache_path.exists():
        return funds

    try:
        edgar: dict[str, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return funds

    enriched: list[dict[str, Any]] = []
    for fund in funds:
        ticker = fund.get("ticker", "").upper()
        m = edgar.get(ticker)
        if not m or m.get("error"):
            enriched.append(fund)
            continue

        fund = dict(fund)
        # nii_coverage: only use EDGAR value when no static value is present.
        # The EDGAR NII / dividends-paid ratio can mix annual NII with a single
        # quarterly distribution period, producing unreliable coverage ratios.
        # Static values in bdc_universe.json are manually curated; prefer them.
        if m.get("nii_coverage_ratio") is not None and fund.get("nii_coverage") is None:
            fund["nii_coverage"] = m["nii_coverage_ratio"]
        if m.get("leverage_de") is not None:
            fund["leverage_de"] = m["leverage_de"]
        if m.get("pik_pct_of_income") is not None:
            fund["pik_pct_of_income"] = m["pik_pct_of_income"]
        if m.get("nav_per_share_usd") is not None:
            fund["nav_per_share"] = m["nav_per_share_usd"]
        if m.get("net_assets_usd") is not None:
            fund["nav_bn"] = m["net_assets_usd"] / 1e9
        if m.get("total_assets_usd") is not None:
            fund["gross_assets_bn"] = m["total_assets_usd"] / 1e9
        if m.get("long_term_debt_usd") is not None:
            fund["total_debt_bn"] = m["long_term_debt_usd"] / 1e9
        if m.get("as_of_date"):
            fund["edgar_as_of"] = m["as_of_date"]
        if m.get("unrealized_depreciation_pct") is not None:
            fund["unrealized_gain_loss_pct"] = m["unrealized_depreciation_pct"]
        enriched.append(fund)

    return enriched


def enrich_funds_with_live_na(
    funds: list[dict[str, Any]],
    cache_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Overwrite nonaccrual_pct_fair_value in each fund dict using live SOI cache data,
    supplemented by MD&A text-extracted rates for tickers with unreliable SOI parsing.

    Tickers without cache data, or tickers with known unreliable NA parsing,
    retain their existing (static) value unless MD&A extraction has a valid rate.
    """
    # Tickers where NA detection is known to be unreliable due to parsing issues:
    # FSK/SCM: non-standard footnote markers → zero NA detected
    # TCPC: col_map issues → zero NA detected
    # PFLT: most-recent cache is 10-Q (shows 0 NA); 10-K shows 147 NA but is older
    # OBDC/GBDC: fixed — issuer detection repaired; live rates now reliable
    _UNRELIABLE_NA = {"FSK", "SCM", "TCPC", "PFLT"}

    try:
        from portfolio_collector import compute_live_na_rates
        from pathlib import Path as _Path
        kw = {"cache_dir": _Path(cache_dir)} if cache_dir else {}
        live = compute_live_na_rates(**kw)
    except Exception as exc:
        print(f"[live-na] Warning: could not compute live NA rates: {exc}")
        live = {}

    # Load MD&A-extracted NA rates as supplement for unreliable SOI tickers
    mda_rates: dict[str, float] = {}
    try:
        from filing_text_extractor import get_mda_na_rates
        mda_rates = get_mda_na_rates()
    except Exception as exc:
        print(f"[live-na] Warning: could not load MD&A NA rates: {exc}")

    enriched = []
    for fund in funds:
        ticker = fund.get("ticker", "").upper()
        fund = dict(fund)
        if ticker in live and ticker not in _UNRELIABLE_NA:
            fund["nonaccrual_pct_fair_value"] = live[ticker]
            fund["_na_source"] = "live"
        elif ticker in _UNRELIABLE_NA and ticker in mda_rates:
            # MD&A rates are stored as percentages (e.g. 4.1 = 4.1%);
            # scorer expects decimals (e.g. 0.041); divide by 100.
            fund["nonaccrual_pct_fair_value"] = mda_rates[ticker] / 100.0
            fund["_na_source"] = "mda_text"
        enriched.append(fund)
    return enriched


def load_scoring_funds(
    path: Path | str = "data/bdc_universe.json",
    history_dir: Path | None = None,
    live_na_cache_dir: Path | str | None = None,
    include_prices: bool = True,
) -> list[dict[str, Any]]:
    """Load the canonical enriched fund universe used for scoring workflows."""
    funds = load_universe_with_trends(path, history_dir=history_dir)
    funds = enrich_funds_with_live_na(funds, cache_dir=live_na_cache_dir)
    if include_prices:
        from price_feed import enrich_funds_with_prices

        funds = enrich_funds_with_prices(funds)
    return funds


def screen_universe(
    funds: list[dict[str, Any]],
    min_score: int = 0,
    tiers: list[str] | None = None,
) -> list[FundScore]:
    """Score all funds in the universe and return FundScore objects, ranked by score.

    Parameters
    ----------
    funds:
        List of fund dicts from the universe JSON (or compatible dicts).
    min_score:
        Only return funds with composite_score >= min_score.
    tiers:
        If specified, only return funds in these risk tiers
        (e.g. ["RED", "ORANGE"]).
    """
    results: list[FundScore] = []
    for fund in funds:
        scored = score_fund(fund)
        fs = FundScore(
            ticker=fund.get("ticker", ""),
            name=fund.get("name", ""),
            fund_type=fund.get("type", ""),
            manager=fund.get("manager", ""),
            nav_bn=fund.get("nav_bn"),
            composite_score=scored["composite_score"],
            dimension_scores=scored["dimension_scores"],
            flags_triggered=scored["flags_triggered"],
            risk_tier=scored["risk_tier"],
            analyst_notes=fund.get("analyst_notes", ""),
            metrics=fund,
        )
        results.append(fs)

    results.sort(key=lambda x: -x.composite_score)

    if tiers:
        tier_set = {t.upper() for t in tiers}
        results = [r for r in results if r.risk_tier in tier_set]
    if min_score > 0:
        results = [r for r in results if r.composite_score >= min_score]

    return results


def screen_to_dataframe(scores: list[FundScore]) -> "pd.DataFrame":  # type: ignore[name-defined]
    """Convert FundScore list to a pandas DataFrame for display / export."""
    import pandas as pd
    rows = []
    for s in scores:
        rows.append({
            "Ticker": s.ticker,
            "Name": s.name,
            "Type": s.fund_type,
            "Manager": s.manager,
            "NAV ($B)": f"{s.nav_bn:.1f}" if s.nav_bn else "n/a",
            "Score": s.composite_score,
            "Risk Tier": s.risk_tier,
            "PIK %": _pct(s.metrics.get("pik_pct_of_income")),
            "NII Cov.": _ratio(s.metrics.get("nii_coverage")),
            "NAV Chg YoY": _pct(s.metrics.get("nav_change_yoy_pct")),
            "Non-Accruals (FV)": _pct(s.metrics.get("nonaccrual_pct_fair_value")),
            "D/E": _ratio(s.metrics.get("leverage_de")),
            "P/NAV": _ratio(s.metrics.get("price_to_nav")),
            "Asset Cov.": _asset_cov(s.metrics.get("gross_assets_bn"), s.metrics.get("total_debt_bn"), s.metrics.get("leverage_de")),
            "Net Flow (Qtly)": _pct(s.metrics.get("net_flow_quarterly")),
            "Flags": "; ".join(s.flag_labels()),
            "Analyst Notes (excerpt)": s.analyst_notes[:120] + ("..." if len(s.analyst_notes) > 120 else ""),
        })
    return pd.DataFrame(rows)


def _pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _ratio(v: Any) -> str:
    try:
        return f"{float(v):.2f}x"
    except (TypeError, ValueError):
        return "—"


def _asset_cov(gross: Any, debt: Any, de: Any = None) -> str:
    try:
        if de is not None and float(de) > 0:
            v = 1.0 + 1.0 / float(de)
        else:
            v = float(gross) / float(debt)
        return f"{v * 100:.0f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "—"


# ---------------------------------------------------------------------------
# Comparative analysis helpers
# ---------------------------------------------------------------------------

def peer_percentile(
    scores: list[FundScore],
    ticker: str,
    metric_key: str,
) -> Optional[float]:
    """Return the percentile rank (0–100) of a fund's metric within the universe.

    Higher percentile = better rank.  For metrics where lower is worse
    (non-accruals, PIK, leverage), the caller should invert (100 - result).
    """
    vals = []
    target = None
    for s in scores:
        v = s.metrics.get(metric_key)
        if v is not None:
            vals.append(float(v))
            if s.ticker == ticker:
                target = float(v)
    if target is None or not vals:
        return None
    vals.sort()
    rank = vals.index(target)
    return (rank / max(len(vals) - 1, 1)) * 100


def flag_frequency_table(scores: list[FundScore]) -> dict[str, int]:
    """Return a dict of {flag_key: count} sorted by frequency descending."""
    freq: dict[str, int] = {}
    for s in scores:
        for f in s.flags_triggered:
            freq[f] = freq.get(f, 0) + 1
    return dict(sorted(freq.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Screen BDC universe for red flags."
    )
    parser.add_argument("--universe", default="data/bdc_universe.json",
                        help="Path to BDC universe JSON.")
    parser.add_argument("--min-score", type=int, default=0,
                        help="Only show funds with composite score >= N.")
    parser.add_argument("--tier", nargs="*", choices=["RED", "ORANGE", "YELLOW", "GREEN"],
                        help="Filter to specific risk tiers.")
    parser.add_argument("--csv", metavar="PATH",
                        help="Write results table to CSV.")
    parser.add_argument("--no-trends", action="store_true",
                        help="Skip trend signal enrichment (static metrics only).")
    parser.add_argument("--live-na", action="store_true",
                        help="Override static non-accrual rates with live values from SOI cache.")
    args = parser.parse_args()

    if args.no_trends:
        funds = load_universe(args.universe)
    else:
        funds = load_universe_with_trends(args.universe)

    if args.live_na:
        funds = enrich_funds_with_live_na(funds)
        live_count = sum(1 for f in funds if f.get("_na_source") == "live")
        print(f"[live-na] Injected live NA rates for {live_count} ticker(s) from SOI cache.\n")

    scores = screen_universe(funds, min_score=args.min_score, tiers=args.tier)

    tier_labels = {"RED": "[RED]   ", "ORANGE": "[ORANGE]", "YELLOW": "[YELLOW]", "GREEN": "[GREEN] "}
    print(f"\nBDC / Private Credit Red Flag Screener -- {len(scores)} fund(s) shown\n")
    for s in scores:
        label = tier_labels.get(s.risk_tier, "[?]    ")
        # Encode to ASCII with replacement for Windows cp1252 terminals
        summary = s.summary().encode("ascii", errors="replace").decode("ascii")
        print(f"{label} {summary}\n")

    print(f"\nFlag frequency across universe:")
    for flag, count in flag_frequency_table(scores).items():
        flag_label = FLAG_LABELS.get(flag, flag)
        flag_label_ascii = flag_label.encode("ascii", errors="replace").decode("ascii")
        print(f"  {count:2d}x  {flag_label_ascii}")

    if args.csv:
        import pandas as pd
        df = screen_to_dataframe(scores)
        df.to_csv(args.csv, index=False)
        print(f"\nWrote screener results -> {args.csv}")


if __name__ == "__main__":
    main()
