#!/usr/bin/env python3
"""
Streamlit dashboard for BDC / private-credit liquidity scenarios.

Run with:
    streamlit run dashboard.py
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from io import StringIO
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cclf_liquidity_model import (
    ScenarioConfig, find_breakeven_distribution_rate, run_scenario, summarize,
)
from red_flag_screener import (
    load_universe, load_universe_with_trends, screen_universe, screen_to_dataframe,
    flag_frequency_table, FLAG_LABELS, enrich_funds_with_edgar_metrics,
)
from trend_signals import compute_all_trend_signals, TrendSignal
from edgar_collector import EdgarClient, load_cached_universe_metrics, collect_universe_metrics
from bdc_historical import BdcHistorian, load_history, nav_indexed_to_100, compare_nav_trajectories
from dashboard_helpers import (
    build_borrower_heatmap_records,
    build_monthly_watchlist_rows,
    build_parser_health_rows,
    build_borrower_stress_rows,
    build_family_merge_candidate_rows,
    build_family_non_accrual_rows,
    build_family_pik_rows,
    build_family_split_candidate_rows,
    build_family_stress_rows,
    build_family_summary_rows,
    build_family_unrealized_loss_rows,
    build_non_accrual_rows,
    build_pik_rows,
    build_unrealized_loss_rows,
    compute_maturity_wall,
    load_csv_records,
    summarize_portfolio_cache,
)

st.set_page_config(page_title="BDC Liquidity Dashboard", layout="wide")

# ---------------------------------------------------------------------------
# Fund profiles
# Approximate balance-sheet starting points derived from public filings.
# CCLFX calibrated to Annual Report, year ended March 31 2025.
# HTGC and OBDC: most recently available 10-K / 10-Q filings.
# All monetary values in dollars; rates in annual decimals unless noted.
# redemption_rate and subscription_rate are quarterly fractions.
# ---------------------------------------------------------------------------
FUND_PROFILES: Dict[str, Dict[str, object]] = {
    "CCLF — Cliffwater Corporate Lending": {
        "nav_start":                 28.1e9,   # FY2025 annual report
        "senior_notes":              5.65e9,
        "senior_credit_outstanding": 1.19e9,
        "senior_credit_limit":       2.5e9,
        "distribution_rate":         0.1075,
        "redemption_rate":           0.05,     # quarterly; formal repurchase cap
        "subscription_rate":         0.055,    # quarterly; Bloomberg Q1 2026 figure
        "portfolio_yield":           0.088,    # $2,992M income / ~$34B gross assets
        "scheduled_repayment_rate":  0.03,
        "annual_default_rate":       0.02,
        "loss_given_default":        0.35,
        "unfunded_commitments":      4.0e9,
        "unfunded_draw_rate":        0.10,
        "starting_cash":             0.297e9,  # balance sheet
        "min_cash_buffer":           0.0,
        "max_leverage":              2.0,
        "quarters":                  8,
        "borrowing_cost_rate":       0.054,    # ~$726M interest / ~$6.84B avg debt
        "management_fee_rate":       0.008,    # $226M / $28.1B NAV
        "other_expense_rate":        0.002,
        "pik_income_fraction":       0.03,
    },
    "HTGC — Hercules Capital": {
        "nav_start":                 2.8e9,
        "senior_notes":              1.3e9,
        "senior_credit_outstanding": 0.5e9,
        "senior_credit_limit":       1.4e9,
        "distribution_rate":         0.10,
        "redemption_rate":           0.01,     # quarterly; listed BDC repurchase
        "subscription_rate":         0.0,      # listed BDC; equity via ATM (immaterial)
        "portfolio_yield":           0.125,    # high-yield venture / tech lending on gross
        "scheduled_repayment_rate":  0.025,
        "annual_default_rate":       0.03,
        "loss_given_default":        0.35,
        "unfunded_commitments":      1.5e9,
        "unfunded_draw_rate":        0.10,
        "starting_cash":             0.15e9,
        "min_cash_buffer":           0.0,
        "max_leverage":              1.0,
        "quarters":                  8,
        "borrowing_cost_rate":       0.062,
        "management_fee_rate":       0.015,
        "other_expense_rate":        0.004,
        "pik_income_fraction":       0.05,
    },
    "OBDC — Blue Owl Capital Corp.": {
        "nav_start":                 7.5e9,
        "senior_notes":              2.5e9,
        "senior_credit_outstanding": 2.0e9,
        "senior_credit_limit":       4.5e9,
        "distribution_rate":         0.095,
        "redemption_rate":           0.01,     # quarterly; listed BDC
        "subscription_rate":         0.0,
        "portfolio_yield":           0.105,    # gross asset yield
        "scheduled_repayment_rate":  0.03,
        "annual_default_rate":       0.02,
        "loss_given_default":        0.40,
        "unfunded_commitments":      3.5e9,
        "unfunded_draw_rate":        0.10,
        "starting_cash":             0.30e9,
        "min_cash_buffer":           0.0,
        "max_leverage":              2.0,
        "quarters":                  8,
        "borrowing_cost_rate":       0.055,
        "management_fee_rate":       0.015,
        "other_expense_rate":        0.003,
        "pik_income_fraction":       0.04,
    },
    "Custom": {
        "nav_start":                 5.0e9,
        "senior_notes":              1.0e9,
        "senior_credit_outstanding": 0.5e9,
        "senior_credit_limit":       2.0e9,
        "distribution_rate":         0.10,
        "redemption_rate":           0.02,
        "subscription_rate":         0.02,
        "portfolio_yield":           0.09,
        "scheduled_repayment_rate":  0.03,
        "annual_default_rate":       0.02,
        "loss_given_default":        0.35,
        "unfunded_commitments":      1.0e9,
        "unfunded_draw_rate":        0.10,
        "starting_cash":             0.25e9,
        "min_cash_buffer":           0.0,
        "max_leverage":              2.0,
        "quarters":                  8,
        "borrowing_cost_rate":       0.055,
        "management_fee_rate":       0.010,
        "other_expense_rate":        0.002,
        "pik_income_fraction":       0.03,
    },
}

# ---------------------------------------------------------------------------
# Stress presets  (layered on top of the fund's balance-sheet profile)
# All keys must match ScenarioConfig dataclass field names exactly.
# redemption_rate and subscription_rate are quarterly fractions.
# ---------------------------------------------------------------------------
PRESETS: Dict[str, Dict[str, float]] = {
    "Base": {},
    "Tide Turning (Current)": {
        # Bloomberg / Robert A. Stanger & Co., data through March 23 2026:
        # CCLFX quarterly redemptions ~8 % of NAV; subscriptions ~5.5 % of NAV
        "subscription_rate":    0.055,
        "redemption_rate":      0.08,
    },
    "Mild stress": {
        "redemption_rate":      0.075,
        "annual_default_rate":  0.04,
        "loss_given_default":   0.45,
        "unfunded_draw_rate":   0.12,
        "portfolio_yield":      0.082,
        "pik_income_fraction":  0.06,
    },
    "Severe stress": {
        "redemption_rate":      0.12,
        "subscription_rate":    0.01,
        "annual_default_rate":  0.08,
        "loss_given_default":   0.55,
        "unfunded_draw_rate":   0.18,
        "portfolio_yield":      0.072,
        "pik_income_fraction":  0.10,
        "borrowing_cost_rate":  0.062,
    },
    "Distribution cut": {
        "distribution_rate":    0.06,
        "redemption_rate":      0.08,
        "annual_default_rate":  0.04,
        "loss_given_default":   0.45,
    },
    "Funding squeeze": {
        "redemption_rate":      0.09,
        "subscription_rate":    0.02,
        "unfunded_draw_rate":   0.20,
        "scheduled_repayment_rate": 0.02,
        "starting_cash":        0.15e9,
    },
    "Historical growth (2023)": {
        # 2023: CCLFX subscriptions ran ~10-13 % of NAV per quarter
        "subscription_rate":    0.12,
        "redemption_rate":      0.02,
        "annual_default_rate":  0.015,
        "portfolio_yield":      0.095,
    },
}

SENSITIVITY_REDEMPTIONS    = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15]
SENSITIVITY_DEFAULTS       = [0.01, 0.02, 0.04, 0.06, 0.08, 0.10]
SENSITIVITY_SUBSCRIPTIONS  = [0.00, 0.02, 0.04, 0.055, 0.08, 0.10, 0.12]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def bn(value: float) -> str:
    return f"{value:,.2f}bn"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def quarter_label(value: int | str) -> str:
    return str(value) if isinstance(value, str) else f"Q{value}"


def rows_to_csv(df: pd.DataFrame) -> bytes:
    buf = StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def build_config(name: str, overrides: Dict[str, object]) -> ScenarioConfig:
    return ScenarioConfig.from_dict({"name": name, **overrides})


def scenario_outputs(cfg: ScenarioConfig) -> Tuple[pd.DataFrame, Dict[str, float | str]]:
    df  = pd.DataFrame(run_scenario(cfg))
    smry = summarize(df.to_dict(orient="records"))
    return df, smry


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

_PALETTE = ["#9CA3AF", "#2563EB", "#DC2626", "#059669"]
_DASH    = ["solid", "dash", "dot", "dashdot"]


def line_chart(
    scenarios: List[Tuple[str, pd.DataFrame]],
    columns: List[str],
    title: str,
    y_title: str,
) -> go.Figure:
    fig = go.Figure()
    for idx, (name, df) in enumerate(scenarios):
        color = _PALETTE[idx % len(_PALETTE)]
        dash  = _DASH[idx % len(_DASH)]
        for col in columns:
            fig.add_trace(go.Scatter(
                x=df["Quarter"],
                y=df[col],
                mode="lines",
                name=f"{col.replace('_Bn', '').replace('_x', '')} — {name}",
                line=dict(color=color, dash=dash),
            ))
    fig.update_layout(
        title=title, xaxis_title="Quarter", yaxis_title=y_title,
        legend_title="Series", height=420,
    )
    return fig


def waterfall_chart(df: pd.DataFrame) -> go.Figure:
    """Quarterly cash-flow and income bar chart.

    Positive bars (inflows): cash NII, subscriptions, scheduled repayments.
    Negative bars (outflows): redemptions, distributions, interest expense, fees,
    credit losses, unfunded draws.
    """
    fig = go.Figure()
    # Outflows — shown as negative
    for col, color, label in [
        ("Redemptions_Bn",      "#DC2626", "Redemptions"),
        ("Distributions_Bn",    "#F59E0B", "Distributions"),
        ("Interest_Expense_Bn", "#EF4444", "Interest expense"),
        ("Fees_Bn",             "#F97316", "Mgmt & other fees"),
        ("Credit_Losses_Bn",    "#7C3AED", "Credit losses"),
        ("Unfunded_Draw_Bn",    "#2563EB", "Unfunded draws"),
    ]:
        fig.add_trace(go.Bar(
            x=df["Quarter"], y=-df[col],
            name=label, marker_color=color,
        ))
    # Inflows — shown as positive
    for col, color, label in [
        ("NII_Cash_Bn",             "#10B981", "Cash NII"),
        ("Subscriptions_Bn",        "#34D399", "Subscriptions"),
        ("Scheduled_Repayments_Bn", "#6EE7B7", "Repayments"),
    ]:
        fig.add_trace(go.Bar(
            x=df["Quarter"], y=df[col],
            name=label, marker_color=color,
        ))
    fig.update_layout(
        barmode="relative",
        title="Quarterly cash-flow drivers (outflows negative, inflows positive)",
        xaxis_title="Quarter", yaxis_title="$bn", height=440,
    )
    return fig


def assumptions_table(cfg: ScenarioConfig) -> pd.DataFrame:
    pct_keys = {
        "distribution_rate", "redemption_rate", "subscription_rate",
        "portfolio_yield", "borrowing_cost_rate", "management_fee_rate",
        "other_expense_rate", "pik_income_fraction", "scheduled_repayment_rate",
        "annual_default_rate", "loss_given_default", "unfunded_draw_rate",
    }
    bn_keys = {
        "nav_start", "senior_notes", "senior_credit_outstanding",
        "senior_credit_limit", "unfunded_commitments", "starting_cash",
        "min_cash_buffer",
    }
    rows = []
    for key, value in asdict(cfg).items():
        label = key.replace("_", " ").title()
        if key in bn_keys:
            fmt = f"{value / 1e9:.2f}bn"
        elif key in pct_keys:
            fmt = pct(value)
        else:
            fmt = value
        rows.append({"Assumption": label, "Value": fmt})
    return pd.DataFrame(rows)


def build_sensitivity_grid(cfg: ScenarioConfig) -> pd.DataFrame:
    rows = []
    for redemption_rate in SENSITIVITY_REDEMPTIONS:
        for default_rate in SENSITIVITY_DEFAULTS:
            test_cfg = replace(cfg, redemption_rate=redemption_rate,
                               annual_default_rate=default_rate)
            _, smry = scenario_outputs(test_cfg)
            shortfall = smry["first_liquidity_shortfall_quarter"]
            score = cfg.quarters + 1 if shortfall == "none" else int(shortfall)
            rows.append({
                "Redemption rate": f"{redemption_rate * 100:.0f}%",
                "Default rate":    f"{default_rate * 100:.0f}%",
                "Shortfall score": score,
                "First shortfall": "No shortfall" if shortfall == "none" else f"Q{shortfall}",
            })
    return pd.DataFrame(rows)


def build_flow_sensitivity_grid(cfg: ScenarioConfig) -> pd.DataFrame:
    """Sweep subscription_rate × redemption_rate; return shortfall scores and NII coverage."""
    rows = []
    for sub_rate in SENSITIVITY_SUBSCRIPTIONS:
        for red_rate in SENSITIVITY_REDEMPTIONS:
            test_cfg = replace(cfg, subscription_rate=sub_rate, redemption_rate=red_rate)
            _, smry = scenario_outputs(test_cfg)
            shortfall = smry["first_liquidity_shortfall_quarter"]
            score = cfg.quarters + 1 if shortfall == "none" else int(shortfall)
            rows.append({
                "Subscription rate": f"{sub_rate * 100:.1f}%",
                "Redemption rate":   f"{red_rate * 100:.0f}%",
                "Shortfall score":   score,
                "NII coverage":      round(float(smry.get("nii_distribution_coverage", 0)), 3),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Narrative and callouts
# ---------------------------------------------------------------------------

def narrative(
    summary: Dict[str, float | str],
    cfg: ScenarioConfig,
    df: pd.DataFrame,
) -> str:
    totals = {
        "redemption / repurchase outflows": df["Redemptions_Bn"].sum(),
        "distribution outflows":            df["Distributions_Bn"].sum(),
        "credit losses":                    df["Credit_Losses_Bn"].sum(),
        "unfunded commitment draws":        df["Unfunded_Draw_Bn"].sum(),
        "interest expense and fees":        (df["Interest_Expense_Bn"] + df["Fees_Bn"]).sum(),
    }
    dominant = max(totals, key=lambda k: totals[k])
    coverage = float(summary.get("nii_distribution_coverage", 0))
    coverage_note = (
        f"Cash NII covers {coverage:.0%} of cumulative distributions over the horizon. "
        + ("Distribution coverage is adequate." if coverage >= 1.0
           else "Distributions are not fully covered by cash NII — the shortfall is drawn from "
                "portfolio repayments, subscriptions, or the revolving facility.")
    )

    if summary["first_liquidity_shortfall_quarter"] != "none":
        return (
            f"Under the **{cfg.name}** scenario, liquidity becomes constrained by "
            f"{quarter_label(summary['first_liquidity_shortfall_quarter'])}. "
            f"Starting cash of {cfg.starting_cash / 1e9:.2f}bn and facility headroom of "
            f"{(cfg.senior_credit_limit - cfg.senior_credit_outstanding) / 1e9:.2f}bn are "
            f"insufficient to offset combined pressures. Minimum cash reaches "
            f"{summary['min_cash_bn']:.2f}bn; minimum headroom compresses to "
            f"{summary['min_headroom_bn']:.2f}bn. The dominant cash drain is **{dominant}**. "
            + coverage_note
        )
    if summary["first_covenant_breach_quarter"] != "none":
        return (
            f"The **{cfg.name}** scenario avoids an immediate liquidity shortfall, but leverage "
            f"becomes the binding constraint by "
            f"{quarter_label(summary['first_covenant_breach_quarter'])}. "
            f"Peak leverage reaches {float(summary['peak_leverage_x']):.2f}x against a "
            f"{cfg.max_leverage:.2f}x ceiling. Financing flexibility, not pure cash depletion, "
            f"is the primary risk to monitor. " + coverage_note
        )
    return (
        f"The **{cfg.name}** scenario remains above the modelled liquidity floor throughout "
        f"the forecast horizon. Ending NAV is {summary['ending_nav_bn']:.2f}bn, ending cash is "
        f"{summary['ending_cash_bn']:.2f}bn, and peak leverage reaches "
        f"{float(summary['peak_leverage_x']):.2f}x. " + coverage_note
    )


def biggest_driver_callout(df: pd.DataFrame) -> str:
    totals = {
        "Redemption / repurchase outflows": df["Redemptions_Bn"].sum(),
        "Distributions":                    df["Distributions_Bn"].sum(),
        "Credit losses":                    df["Credit_Losses_Bn"].sum(),
        "Unfunded draws":                   df["Unfunded_Draw_Bn"].sum(),
        "Interest expense":                 df["Interest_Expense_Bn"].sum(),
        "Management and other fees":        df["Fees_Bn"].sum(),
    }
    label, value = max(totals.items(), key=lambda item: item[1])
    return f"Largest cumulative cash drain over the projection horizon: **{label}** at {value:.2f}bn."


# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------

def metric_cards(
    summary: Dict[str, float | str],
    baseline_summary: Dict[str, float | str] | None = None,
) -> None:
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    def _delta(key: str) -> float | None:
        if baseline_summary is None:
            return None
        base = baseline_summary.get(key)
        cur  = summary.get(key)
        if base is None or cur is None:
            return None
        if isinstance(base, str) or isinstance(cur, str):
            return None
        return float(cur) - float(base)

    min_cash_delta   = _delta("min_cash_bn")
    headroom_delta   = _delta("min_headroom_bn")
    leverage_delta   = _delta("peak_leverage_x")
    coverage         = float(summary.get("nii_distribution_coverage", float("nan")))

    col1.metric("First shortfall", quarter_label(summary["first_liquidity_shortfall_quarter"]))
    col2.metric("Min cash",      bn(float(summary["min_cash_bn"])),
                None if min_cash_delta is None else f"{min_cash_delta:+.2f}bn vs base")
    col3.metric("Max facility",  bn(float(summary["max_facility_utilization_bn"])))
    col4.metric("Min headroom",  bn(float(summary["min_headroom_bn"])),
                None if headroom_delta is None else f"{headroom_delta:+.2f}bn vs base")
    col5.metric("Peak leverage", f"{float(summary['peak_leverage_x']):.2f}x",
                None if leverage_delta is None else f"{leverage_delta:+.2f}x vs base")
    col6.metric("NII coverage",  f"{coverage:.2f}x" if not (coverage != coverage) else "n/a",
                help="Cumulative cash NII ÷ cumulative distributions. <1× means distributions "
                     "partially funded from repayments, subscriptions, or facility draws.")


_TIER_COLORS = {"RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡", "GREEN": "🟢"}
_UNIVERSE_PATH = Path(__file__).parent / "data" / "bdc_universe.json"
_PROFILES_PATH = Path(__file__).parent / "data" / "bdc_management_profiles.json"
_HISTORY_CACHE = Path(__file__).parent / "data" / "edgar_cache" / "history"


def _tier_badge(tier: str) -> str:
    return f"{_TIER_COLORS.get(tier, '⚪')} {tier}"


def _style_tier(val: str) -> str:
    """Return CSS color string for a risk-tier cell."""
    colors = {"🔴 RED": "#fee2e2", "🟠 ORANGE": "#ffedd5",
              "🟡 YELLOW": "#fefce8", "🟢 GREEN": "#f0fdf4"}
    return f"background-color: {colors.get(val, '')}"


@st.cache_data(ttl=3600)
def _load_screener_scores() -> "pd.DataFrame":
    """Load and score the BDC universe with trend signals; cached for 1 hour."""
    if not _UNIVERSE_PATH.exists():
        return pd.DataFrame()
    funds = load_universe_with_trends(_UNIVERSE_PATH, history_dir=_HISTORY_CACHE)
    scores = screen_universe(funds)
    return screen_to_dataframe(scores)


@st.cache_data(ttl=3600)
def _load_universe_raw() -> list[dict]:
    if not _UNIVERSE_PATH.exists():
        return []
    return load_universe(_UNIVERSE_PATH)


@st.cache_data(ttl=3600)
def _load_universe_with_trends() -> list[dict]:
    if not _UNIVERSE_PATH.exists():
        return []
    funds = load_universe_with_trends(_UNIVERSE_PATH, history_dir=_HISTORY_CACHE)
    # Inject live prices (4-hr cache via price_feed)
    try:
        from price_feed import enrich_funds_with_prices
        funds = enrich_funds_with_prices(funds)
    except Exception:
        pass
    return funds


@st.cache_data(ttl=3600)
def _load_trend_signals() -> dict[str, dict]:
    """Compute trend signals for all funds; return as plain dicts for caching."""
    try:
        signals = compute_all_trend_signals(
            history_dir=_HISTORY_CACHE, universe_path=_UNIVERSE_PATH
        )
        return {ticker: {
            "trend_score": s.trend_score,
            "trend_flags": s.trend_flags,
            "coverage_current": s.coverage_current,
            "coverage_4q_change": s.coverage_4q_change,
            "coverage_flag": s.coverage_flag,
            "leverage_current": s.leverage_current,
            "leverage_4q_change": s.leverage_4q_change,
            "leverage_flag": s.leverage_flag,
            "pik_current": s.pik_current,
            "pik_4q_change": s.pik_4q_change,
            "pik_flag": s.pik_flag,
            "nav_velocity_recent": s.nav_velocity_recent,
            "nav_acceleration": s.nav_acceleration,
            "nav_velocity_flag": s.nav_velocity_flag,
            "periods_available": s.periods_available,
            "as_of_period": s.as_of_period,
        } for ticker, s in signals.items()}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Market Overview tab
# ---------------------------------------------------------------------------

def render_market_overview() -> None:
    st.title("Private Credit Market Overview")
    st.write(
        "Cross-fund comparison of key financial metrics for major BDCs and private-credit "
        "interval funds. Data sourced from most-recent public filings "
        "(10-K, 10-Q, N-CSR, annual reports). All figures are point-in-time snapshots; "
        "always verify against current SEC filings."
    )

    funds = _load_universe_raw()
    if not funds:
        st.warning("BDC universe file not found. Expected at data/bdc_universe.json")
        return

    # Metric comparison table
    st.subheader("Metric Comparison Table")

    rows = []
    for f in funds:
        rows.append({
            "Ticker":           f.get("ticker", ""),
            "Name":             f.get("name", ""),
            "Type":             f.get("type", "").replace("_", " ").title(),
            "NAV ($B)":         f.get("nav_bn"),
            "D/E Leverage":     f.get("leverage_de"),
            "NII Coverage":     f.get("nii_coverage"),
            "PIK %":            f.get("pik_pct_of_income"),
            "Non-Accrual (FV)": f.get("nonaccrual_pct_fair_value"),
            "NAV Chg YoY":      f.get("nav_change_yoy_pct"),
            "P/NAV":            f.get("price_to_nav"),
            "Dist. Rate":       f.get("distribution_rate_annual"),
            "Net Flow (Qtly)":  f.get("net_flow_quarterly"),
            "As Of":            f.get("as_of", ""),
            "Manager":          f.get("manager", ""),
        })
    df = pd.DataFrame(rows)

    # Format for display
    def fmt_bn(v):
        return f"${float(v):.1f}B" if v is not None else "—"
    def fmt_pct(v):
        return f"{float(v)*100:.1f}%" if v is not None else "—"
    def fmt_x(v):
        return f"{float(v):.2f}x" if v is not None else "—"

    display_df = df.copy()
    display_df["NAV ($B)"]         = display_df["NAV ($B)"].map(fmt_bn)
    display_df["D/E Leverage"]     = display_df["D/E Leverage"].map(fmt_x)
    display_df["NII Coverage"]     = display_df["NII Coverage"].map(fmt_x)
    display_df["PIK %"]            = display_df["PIK %"].map(fmt_pct)
    display_df["Non-Accrual (FV)"] = display_df["Non-Accrual (FV)"].map(fmt_pct)
    display_df["NAV Chg YoY"]      = display_df["NAV Chg YoY"].map(fmt_pct)
    display_df["P/NAV"]            = display_df["P/NAV"].map(fmt_x)
    display_df["Dist. Rate"]       = display_df["Dist. Rate"].map(fmt_pct)
    display_df["Net Flow (Qtly)"]  = display_df["Net Flow (Qtly)"].map(
        lambda v: fmt_pct(v) if v is not None else "—"
    )
    st.dataframe(display_df.set_index("Ticker"), use_container_width=True)

    # Scatter charts
    st.subheader("NII Coverage vs. Non-Accrual Rate")
    chart_data = [
        f for f in funds
        if f.get("nii_coverage") is not None and f.get("nonaccrual_pct_fair_value") is not None
    ]
    if chart_data:
        chart_df = pd.DataFrame({
            "Ticker":         [f["ticker"] for f in chart_data],
            "NII Coverage":   [f["nii_coverage"] for f in chart_data],
            "Non-Accrual %":  [f["nonaccrual_pct_fair_value"] * 100 for f in chart_data],
            "NAV ($B)":       [f.get("nav_bn", 1) or 1 for f in chart_data],
            "Type":           [f.get("type", "") for f in chart_data],
        })
        fig = px.scatter(
            chart_df,
            x="Non-Accrual %",
            y="NII Coverage",
            size="NAV ($B)",
            color="Type",
            text="Ticker",
            labels={"Non-Accrual %": "Non-Accrual Rate (% FV)", "NII Coverage": "NII Coverage (×)"},
            title="NII Coverage vs. Non-Accrual Rate (bubble size = NAV)",
            height=500,
        )
        fig.add_hline(y=1.0, line_dash="dash", line_color="red",
                      annotation_text="1.0× coverage threshold")
        fig.add_vline(x=3.0, line_dash="dash", line_color="orange",
                      annotation_text="3% non-accrual threshold")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)

    # PIK vs NAV erosion
    st.subheader("PIK Income Fraction vs. YoY NAV Change")
    pik_data = [
        f for f in funds
        if f.get("pik_pct_of_income") is not None and f.get("nav_change_yoy_pct") is not None
    ]
    if pik_data:
        pik_df = pd.DataFrame({
            "Ticker":     [f["ticker"] for f in pik_data],
            "PIK %":      [f["pik_pct_of_income"] * 100 for f in pik_data],
            "NAV Δ YoY":  [f["nav_change_yoy_pct"] * 100 for f in pik_data],
            "NAV ($B)":   [f.get("nav_bn", 1) or 1 for f in pik_data],
            "Type":       [f.get("type", "") for f in pik_data],
        })
        fig2 = px.scatter(
            pik_df,
            x="PIK %",
            y="NAV Δ YoY",
            size="NAV ($B)",
            color="Type",
            text="Ticker",
            labels={"PIK %": "PIK Income (% of total)", "NAV Δ YoY": "NAV Change YoY (%)"},
            title="PIK Concentration vs. NAV Trajectory (bubble size = NAV)",
            height=500,
        )
        fig2.add_hline(y=0, line_dash="solid", line_color="gray")
        fig2.add_vline(x=10, line_dash="dash", line_color="orange",
                       annotation_text="10% PIK threshold")
        fig2.update_traces(textposition="top center")
        st.plotly_chart(fig2, use_container_width=True)

    # Distribution coverage distribution
    st.subheader("NII Distribution Coverage Distribution")
    cov_data = [f for f in funds if f.get("nii_coverage") is not None]
    if cov_data:
        cov_df = pd.DataFrame({
            "Ticker":   [f["ticker"] for f in cov_data],
            "Coverage": [f["nii_coverage"] for f in cov_data],
        }).sort_values("Coverage")
        fig3 = px.bar(
            cov_df,
            x="Ticker",
            y="Coverage",
            color="Coverage",
            color_continuous_scale="RdYlGn",
            range_color=[0.6, 1.4],
            title="NII Distribution Coverage by Fund (1.0× = break-even)",
            labels={"Coverage": "NII Coverage (×)"},
        )
        fig3.add_hline(y=1.0, line_dash="dash", line_color="black",
                       annotation_text="1.0×")
        st.plotly_chart(fig3, use_container_width=True)

    st.caption(
        "Data source: curated from most-recent available public filings. "
        "Interval fund metrics (CCLFX, BCRED, PIMCO-FCI) reflect semi-annual/annual reports "
        "and may lag listed BDC 10-Q reporting. P/NAV for non-listed funds = 1.00 by definition. "
        "This is not investment advice."
    )


# ---------------------------------------------------------------------------
# MD&A non-accrual panel (used in screener Fund Detail)
# ---------------------------------------------------------------------------

def _render_mda_panel(ticker: str) -> None:
    """Render Item 7 MD&A non-accrual commentary for *ticker* from text cache."""
    try:
        from filing_text_extractor import get_mda_na_rates, TEXT_CACHE
        import json as _json

        # Find the most recent cache file for this ticker
        cache_dir = TEXT_CACHE
        pattern = f"{ticker.lower()}_*_mda.json"
        matches = sorted(cache_dir.glob(pattern), reverse=True)
        if not matches:
            return

        cache_path = matches[0]
        with open(cache_path) as f:
            data = _json.load(f)

        paragraphs = data.get("nonaccrual_paragraphs", [])
        stats = {
            "na_count": data.get("na_count"),
            "na_pct_fv": data.get("na_pct_fv"),
            "na_pct_cost": data.get("na_pct_cost"),
            "na_fv_mm": data.get("na_fv_mm"),
            "na_cost_mm": data.get("na_cost_mm"),
            "item7_chars": data.get("item7_chars", 0),
            "period": data.get("period", ""),
            "form": data.get("form", ""),
        }

        if not paragraphs and not any(v is not None for v in [
            stats["na_count"], stats["na_pct_fv"], stats["na_pct_cost"]
        ]):
            return

        st.write("**MD&A Non-Accrual Commentary** (from Item 7, " +
                 f"{stats['form']} {stats['period']}):")

        # Stat summary row
        stat_parts = []
        if stats["na_count"] is not None:
            stat_parts.append(f"**Count:** {stats['na_count']} investments")
        if stats["na_pct_fv"] is not None:
            stat_parts.append(f"**NA % FV:** {stats['na_pct_fv']:.1f}%")
        if stats["na_pct_cost"] is not None:
            stat_parts.append(f"**NA % Cost:** {stats['na_pct_cost']:.1f}%")
        if stats["na_fv_mm"] is not None:
            stat_parts.append(f"**FV:** ${stats['na_fv_mm']:.1f}M")
        if stats["na_cost_mm"] is not None:
            stat_parts.append(f"**Cost:** ${stats['na_cost_mm']:.1f}M")
        if stat_parts:
            st.markdown("  |  ".join(stat_parts))

        if stats["item7_chars"] < 2_000:
            st.caption("Note: Item 7 section was short — results are from full-filing search.")

        for para in paragraphs:
            st.markdown(f"> {para}")

    except Exception:
        pass  # MD&A panel is supplementary — never break the screener


# ---------------------------------------------------------------------------
# Peer comparison helper (used in screener tab)
# ---------------------------------------------------------------------------

def _render_peer_ranking(funds: list) -> None:
    """Render cross-sectional peer comparison table with percentile ranks."""
    try:
        from distribution_model import compute_peer_rankings
        import numpy as np
        df = compute_peer_rankings(funds)
    except Exception as exc:
        st.warning(f"Peer ranking unavailable: {exc}")
        return

    st.write(
        "Each metric shows the raw value and a percentile rank (100 = best in universe). "
        "Ranks account for direction: high NII coverage = better; high non-accruals = worse."
    )

    sort_col = st.selectbox(
        "Sort by metric",
        ["NII Coverage", "D/E Leverage", "Non-Accrual % FV", "PIK % Income",
         "NAV Chg YoY", "P/NAV"],
        index=0,
        key="peer_sort_col",
    )
    sort_pct = sort_col + " Pct"
    asc = st.checkbox("Sort ascending (worst first)", value=False, key="peer_sort_asc")

    disp_df = df[["Ticker", "Name", "NII Coverage", "D/E Leverage",
                  "Non-Accrual % FV", "PIK % Income", "NAV Chg YoY", "P/NAV"]].copy()

    # Format raw values
    def _fmt(col, pct=False, ratio=False):
        if pct:
            disp_df[col] = disp_df[col].apply(
                lambda v: f"{v*100:+.1f}%" if not (v is None or (isinstance(v, float) and np.isnan(v))) else "—"
            )
        elif ratio:
            disp_df[col] = disp_df[col].apply(
                lambda v: f"{v:.2f}x" if not (v is None or (isinstance(v, float) and np.isnan(v))) else "—"
            )
        else:
            disp_df[col] = disp_df[col].apply(
                lambda v: f"{v*100:.1f}%" if not (v is None or (isinstance(v, float) and np.isnan(v))) else "—"
            )

    _fmt("NII Coverage", ratio=True)
    _fmt("D/E Leverage", ratio=True)
    _fmt("Non-Accrual % FV")
    _fmt("PIK % Income")
    _fmt("NAV Chg YoY", pct=True)
    _fmt("P/NAV", ratio=True)

    # Sort by percentile column (from original df)
    if sort_pct in df.columns:
        order_series = df[sort_pct].fillna(50)
        disp_df = disp_df.iloc[order_series.argsort().values if asc else order_series.argsort()[::-1].values]

    st.dataframe(disp_df.set_index("Ticker"), use_container_width=True)

    # Radar chart for a selected fund
    st.write("**Percentile radar — select a fund to visualize**")
    radar_tick = st.selectbox(
        "Fund", df["Ticker"].tolist(), key="peer_radar_ticker"
    )
    row = df[df["Ticker"] == radar_tick]
    if not row.empty:
        pct_cols = [c for c in df.columns if c.endswith(" Pct")]
        metric_labels = [c.replace(" Pct", "") for c in pct_cols]
        values = [row[c].values[0] for c in pct_cols]
        # Close the polygon
        fig_radar = go.Figure(go.Scatterpolar(
            r=values + [values[0]],
            theta=metric_labels + [metric_labels[0]],
            fill="toself",
            name=radar_tick,
        ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title=f"Peer Percentile Profile — {radar_tick}",
            height=420,
        )
        st.plotly_chart(fig_radar, use_container_width=True)


# ---------------------------------------------------------------------------
# Trade Signals tab
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _load_trade_signals():
    """Compute trade signals for all funds (cached 5 min)."""
    try:
        from trade_signals import load_all_signals
        return load_all_signals()
    except Exception as exc:
        return []


def render_trade_signals() -> None:
    st.title("Trade Signals")
    st.caption(
        "Signal = f(risk score, price-to-NAV). "
        "Not investment advice — a starting point for further diligence."
    )

    from trade_signals import (
        SIGNAL_COLOR, SIGNAL_LABEL, SIGNAL_ORDER,
        _MATRIX, _risk_bucket, _val_bucket,
        _P2N_DEEP_DISC, _P2N_DISCOUNT, _P2N_PREMIUM,
    )
    import plotly.graph_objects as go
    import pandas as pd

    signals = _load_trade_signals()
    if not signals:
        st.warning("Could not load trade signals.")
        return

    # ── Summary counts ─────────────────────────────────────────────────────
    from collections import Counter
    counts = Counter(s.signal for s in signals)
    cols = st.columns(len(SIGNAL_ORDER))
    for col, sig in zip(cols, SIGNAL_ORDER):
        n = counts.get(sig, 0)
        col.metric(SIGNAL_LABEL[sig], n)

    st.divider()

    # ── Scatter: P/NAV vs Risk Score ────────────────────────────────────────
    st.subheader("Risk vs. Valuation Map")

    listed   = [s for s in signals if s.listed and s.price_to_nav is not None]
    unlisted = [s for s in signals if not s.listed or s.price_to_nav is None]

    fig = go.Figure()

    # Quadrant background shading
    shapes = []
    # Deep Discount + Low = Strong Buy (green)
    shapes.append(dict(type="rect", xref="x", yref="y",
                       x0=0, x1=_P2N_DEEP_DISC, y0=0, y1=4.5,
                       fillcolor="rgba(0,128,0,0.08)", line_width=0))
    # Caution zone (Elevated risk, discount)
    shapes.append(dict(type="rect", xref="x", yref="y",
                       x0=0, x1=_P2N_DISCOUNT, y0=7.5, y1=11.5,
                       fillcolor="rgba(255,140,0,0.10)", line_width=0))
    # Avoid zone (High risk)
    shapes.append(dict(type="rect", xref="x", yref="y",
                       x0=0, x1=2.0, y0=11.5, y1=18,
                       fillcolor="rgba(178,34,34,0.08)", line_width=0))

    # Vertical lines for valuation buckets
    for xv, label in [(_P2N_DEEP_DISC, "Deep Disc / Disc"), (_P2N_DISCOUNT, "Disc / Fair"), (_P2N_PREMIUM, "Fair / Premium")]:
        shapes.append(dict(type="line", xref="x", yref="paper",
                           x0=xv, x1=xv, y0=0, y1=1,
                           line=dict(color="lightgray", dash="dot", width=1)))

    fig.update_layout(shapes=shapes)

    # Plot each signal group
    from itertools import groupby
    for sig in SIGNAL_ORDER:
        pts = [s for s in listed if s.signal == sig]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[s.price_to_nav for s in pts],
            y=[s.risk_score for s in pts],
            mode="markers+text",
            name=SIGNAL_LABEL[sig],
            text=[s.ticker for s in pts],
            textposition="top center",
            textfont=dict(size=10),
            marker=dict(
                color=SIGNAL_COLOR[sig],
                size=14,
                line=dict(color="white", width=1),
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "P/NAV: %{x:.3f}x<br>"
                "Score: %{y}<br>"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        height=520,
        xaxis=dict(title="Price / NAV", range=[0.35, 1.75], tickformat=".2f"),
        yaxis=dict(title="Risk Score (0–18)", range=[-0.5, 18.5]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=40, b=40),
        plot_bgcolor="white",
    )

    # Axis labels for quadrant zones
    for x, lbl in [
        (0.68, "Deep Discount"),
        (0.875, "Discount"),
        (1.0, "Fair Value"),
        (1.30, "Premium"),
    ]:
        fig.add_annotation(x=x, y=-0.3, text=lbl, showarrow=False,
                           font=dict(size=9, color="gray"), yref="y")

    st.plotly_chart(fig, use_container_width=True)

    # ── Signal table ────────────────────────────────────────────────────────
    st.subheader("Signal Details")

    from trade_signals import signals_to_dataframe
    df = signals_to_dataframe(signals)

    # Colour-code Signal column
    def _sig_style(val):
        sig_key = {v: k for k, v in SIGNAL_LABEL.items()}.get(val, "")
        color = SIGNAL_COLOR.get(sig_key, "black")
        return f"color: {color}; font-weight: bold"

    styled = df.style.applymap(_sig_style, subset=["Signal"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Rationale expander per fund ─────────────────────────────────────────
    st.subheader("Signal Rationale")
    for sig in SIGNAL_ORDER:
        group = [s for s in signals if s.signal == sig]
        if not group:
            continue
        with st.expander(f"{SIGNAL_LABEL[sig]} ({len(group)} fund{'s' if len(group)>1 else ''})",
                         expanded=sig in ("STRONG_BUY", "BUY")):
            for s in group:
                disc = (f"{s.nav_discount_pct:+.1f}%" if s.nav_discount_pct is not None
                        else "non-listed")
                st.markdown(
                    f"**{s.ticker}** — score {s.risk_score}/18, {disc}  \n"
                    f"*{s.rationale}*"
                )


# ---------------------------------------------------------------------------
# Macro Scenarios tab
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _load_distribution_outlooks():
    """Load distribution outlooks from distribution_model (cached 5 min)."""
    try:
        from distribution_model import compute_all_outlooks, load_trend_signals
        from red_flag_screener import load_universe_with_trends
        funds = load_universe_with_trends()
        signals = load_trend_signals()
        outlooks = compute_all_outlooks(funds, trend_signals=signals)
        return outlooks, funds
    except Exception:
        return {}, []


@st.cache_data(ttl=300)
def _load_live_prices():
    """Fetch live prices from yfinance (cached 5 min)."""
    try:
        from price_feed import get_quotes
        from red_flag_screener import load_universe
        funds = load_universe()
        return get_quotes(funds)
    except Exception:
        return {}


def render_macro_scenarios() -> None:
    st.title("Macro & Scenarios")
    st.write(
        "Live price/NAV discounts, distribution sustainability projections, "
        "and SOFR rate-sensitivity analysis across the BDC universe."
    )

    outlooks, funds = _load_distribution_outlooks()
    quotes = _load_live_prices()

    # ── Live Prices / NAV Discount ───────────────────────────────────────
    st.subheader("Live Price vs. NAV")
    if quotes:
        import time
        price_rows = []
        for t, q in sorted(quotes.items()):
            disc = q.nav_discount_pct
            badge = ("🔴 >30% discount" if disc is not None and disc < -30
                     else "🟠 20-30% discount" if disc is not None and disc < -20
                     else "🟡 10-20% discount" if disc is not None and disc < -10
                     else "🟢 Near/above NAV")
            price_rows.append({
                "Ticker": t,
                "Price": f"${q.price:.2f}",
                "NAV/sh": f"${q.nav_per_share:.2f}" if q.nav_per_share else "—",
                "P/NAV": f"{q.price_to_nav:.3f}x" if q.price_to_nav else "—",
                "Disc / Prem": f"{disc:+.1f}%" if disc is not None else "—",
                "Market Signal": badge,
            })
        price_df = pd.DataFrame(price_rows)
        st.dataframe(price_df.set_index("Ticker"), use_container_width=True)

        # Waterfall chart: discount/premium ranked
        pct_vals = [(r["Ticker"], q.nav_discount_pct) for t, q in quotes.items()
                    for r in [next((x for x in price_rows if x["Ticker"] == t), {})]
                    if q.nav_discount_pct is not None]
        pct_vals.sort(key=lambda x: x[1])
        ticks, vals = zip(*pct_vals) if pct_vals else ([], [])
        colors = ["#DC2626" if v < -30 else "#F97316" if v < -20 else "#EAB308" if v < -10
                  else "#22C55E" for v in vals]
        fig_disc = go.Figure(go.Bar(
            x=list(ticks), y=list(vals),
            marker_color=colors,
            text=[f"{v:+.1f}%" for v in vals],
            textposition="outside",
        ))
        fig_disc.add_hline(y=0, line_color="gray")
        fig_disc.update_layout(
            title="Price vs. NAV: Discount (negative) / Premium (positive)",
            yaxis_title="% vs. NAV", height=380,
        )
        st.plotly_chart(fig_disc, use_container_width=True)
        age = min(q.fetched_at for q in quotes.values()) if quotes else 0
        st.caption(f"Prices via yfinance. Cache age: {(time.time()-age)/60:.0f} min. "
                   "NAV/sh from most recent public filing — may lag current reported NAV.")
    else:
        st.info("Live prices unavailable. Run `python price_feed.py` to populate cache.")

    # ── Distribution Sustainability ──────────────────────────────────────
    st.divider()
    st.subheader("Distribution Sustainability")
    st.write(
        "Projects NII coverage 8 quarters forward using the trailing trend from EDGAR history. "
        "Cut risk tiers: 🔴 HIGH = already below 0.85x or breach within 2Q; "
        "🟠 MEDIUM = below 0.85x or breach within 3Q; 🟡 LOW = breach within 8Q; 🟢 STABLE."
    )
    if outlooks:
        _ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "STABLE": 3}
        sust_rows = []
        for t, o in sorted(outlooks.items(), key=lambda kv: _ORDER.get(kv[1].cut_risk, 9)):
            q85 = f"Q{o.quarters_to_moderate_cut}" if o.quarters_to_moderate_cut else ">8Q"
            q70 = f"Q{o.quarters_to_severe_cut}" if o.quarters_to_severe_cut else ">8Q"
            risk_label = f"{o.cut_risk_icon} {o.cut_risk}"
            proj_4q = f"{o.projected_8q[3]:.3f}x" if len(o.projected_8q) >= 4 else "—"
            sust_rows.append({
                "Ticker": t,
                "Current Coverage": f"{o.current_coverage:.3f}x",
                "Trend /Q": f"{o.coverage_trend_per_q:+.3f}x",
                "Proj. 4Q": proj_4q,
                "Breach 0.85x": q85,
                "Breach 0.70x": q70,
                "Cut Risk": risk_label,
                "NII Impact @ -100bps": f"${o.rate_nii_impact_100bps_mm:+.0f}M",
                "NII Impact @ -200bps": f"${o.rate_nii_impact_200bps_mm:+.0f}M",
                "Notes": o.notes,
            })
        sust_df = pd.DataFrame(sust_rows)
        st.dataframe(sust_df.set_index("Ticker"), use_container_width=True)

        # Forward coverage chart for a selected fund
        st.write("**8-Quarter forward projection — select a fund**")
        sel_tickers = [o.ticker for o in outlooks.values() if o.quarters_to_moderate_cut or o.coverage_trend_per_q < 0]
        sel_tickers = sorted(outlooks.keys())
        proj_ticker = st.selectbox("Fund", sel_tickers, key="sust_proj_ticker")
        if proj_ticker in outlooks:
            o = outlooks[proj_ticker]
            rate_delta = st.select_slider(
                "SOFR scenario (bps)", options=[-300, -200, -150, -100, -50, 0],
                value=0, key="sust_rate_slider",
            )
            quarters = [f"Q+{i+1}" for i in range(8)]
            base_proj = o.projected_8q
            rate_adj  = (rate_delta / -100) * o.rate_cov_impact_100bps
            adj_proj  = [max(0, v + rate_adj) for v in base_proj]
            fig_proj = go.Figure()
            fig_proj.add_trace(go.Scatter(
                x=quarters, y=base_proj,
                mode="lines+markers", name="Base (no rate change)",
                line=dict(color="#3B82F6", width=2),
            ))
            if rate_delta != 0:
                fig_proj.add_trace(go.Scatter(
                    x=quarters, y=adj_proj,
                    mode="lines+markers", name=f"SOFR {rate_delta:+d}bps",
                    line=dict(color="#F97316", width=2, dash="dash"),
                ))
            fig_proj.add_hline(y=0.85, line_dash="dot", line_color="orange",
                               annotation_text="0.85x (cut risk)")
            fig_proj.add_hline(y=0.70, line_dash="dot", line_color="red",
                               annotation_text="0.70x (severe cut risk)")
            fig_proj.add_hline(y=1.00, line_dash="dash", line_color="green",
                               annotation_text="1.00x (fully covered)")
            fig_proj.update_layout(
                title=f"{proj_ticker} — NII Coverage Projection",
                yaxis_title="NII Coverage (x)",
                yaxis=dict(range=[0, max(max(base_proj), 1.2) + 0.15]),
                height=380,
            )
            st.plotly_chart(fig_proj, use_container_width=True)
    else:
        st.info("Distribution outlooks unavailable. Run `python distribution_model.py`.")

    # ── Rate Sensitivity ─────────────────────────────────────────────────
    st.divider()
    st.subheader("SOFR Rate Sensitivity")
    st.write(
        "NII impact of SOFR rate changes, using each fund's floating-rate asset/liability "
        "mix. Negative = NII compression (rate decrease). Assumes ~40% of liabilities "
        "are floating-rate revolving facilities; balance is fixed-rate notes."
    )
    if outlooks:
        rate_rows = []
        for t, o in sorted(outlooks.items(), key=lambda kv: kv[1].rate_nii_impact_200bps_mm):
            rate_rows.append({
                "Ticker": t,
                "SOFR -50bps NII": f"${o.rate_nii_impact_100bps_mm/2:+.0f}M",
                "SOFR -100bps NII": f"${o.rate_nii_impact_100bps_mm:+.0f}M",
                "SOFR -200bps NII": f"${o.rate_nii_impact_200bps_mm:+.0f}M",
                "Cov. Δ @ -100bps": f"{o.rate_cov_impact_100bps:+.3f}x",
                "Cov. Δ @ -200bps": f"{o.rate_cov_impact_200bps:+.3f}x",
            })
        rate_df = pd.DataFrame(rate_rows)
        st.dataframe(rate_df.set_index("Ticker"), use_container_width=True)

        # Stacked bar: NII impact by fund under -100bps and -200bps
        tickers_r = [r["Ticker"] for r in rate_rows]
        nii_100   = [outlooks[t].rate_nii_impact_100bps_mm for t in tickers_r]
        nii_200   = [outlooks[t].rate_nii_impact_200bps_mm for t in tickers_r]
        # Sort by magnitude
        sorted_pairs = sorted(zip(tickers_r, nii_200), key=lambda x: x[1])
        tickers_s, _ = zip(*sorted_pairs) if sorted_pairs else ([], [])
        nii100_s = [outlooks[t].rate_nii_impact_100bps_mm for t in tickers_s]
        nii200_s = [outlooks[t].rate_nii_impact_200bps_mm for t in tickers_s]
        extra_s  = [nii200_s[i] - nii100_s[i] for i in range(len(tickers_s))]
        fig_rate = go.Figure()
        fig_rate.add_trace(go.Bar(
            name="SOFR -100bps", x=list(tickers_s), y=nii100_s,
            marker_color="#F97316",
        ))
        fig_rate.add_trace(go.Bar(
            name="Additional -100bps", x=list(tickers_s), y=extra_s,
            base=nii100_s, marker_color="#DC2626",
        ))
        fig_rate.update_layout(
            barmode="stack",
            title="NII Impact Under Rate Decline Scenarios (most exposed at left)",
            yaxis_title="NII Change ($M)",
            height=400,
        )
        st.plotly_chart(fig_rate, use_container_width=True)
        st.caption(
            "Floating rate asset exposure per bdc_universe.json estimates. "
            "For precise sensitivity, refer to each fund's 10-K 'Quantitative Disclosures "
            "about Market Risk' (Item 7A)."
        )
    else:
        st.info("Rate sensitivity unavailable. Ensure distribution_model.py is available.")


# ---------------------------------------------------------------------------
# Red Flag Screener tab
# ---------------------------------------------------------------------------

def render_screener() -> None:
    st.title("Red Flag Screener")
    st.write(
        "Systematic risk scoring across the BDC and private-credit universe. "
        "Each fund is evaluated on nine dimensions — eight point-in-time metrics plus "
        "a **Trend Deterioration** dimension (0–5 pts) derived from EDGAR quarterly history. "
        "Trend signals capture direction of travel: worsening coverage, leverage creep, "
        "PIK escalation, and accelerating NAV decline. Higher composite score = more concern."
    )

    with st.expander("Scoring rubric"):
        st.markdown("""
| Dimension | Score | Threshold |
|---|---|---|
| PIK Income | 1 | PIK >10% of income |
| PIK Income | 2 | PIK >20% of income |
| Distribution Coverage | 1 | NII/Dist <1.0× |
| Distribution Coverage | 2 | NII/Dist <0.85× |
| Distribution Coverage | 3 | NII/Dist <0.70× |
| NAV Erosion | 1 | NAV down >3% YoY |
| NAV Erosion | 2 | NAV down >7% YoY |
| NAV Erosion | 3 | NAV down >15% YoY |
| Non-Accruals (FV) | 1 | >3% fair value |
| Non-Accruals (FV) | 2 | >6% fair value |
| Non-Accruals (FV) | 3 | >12% fair value |
| Leverage (D/E) | 1 | >1.25× |
| Leverage (D/E) | 2 | >1.50× |
| Market Discount | 1 | P/NAV <0.90 |
| Market Discount | 2 | P/NAV <0.75 |
| Flow Pressure | 1 | Net quarterly outflow >1% NAV |
| Flow Pressure | 2 | Net quarterly outflow >3% NAV |
| Leverage Headroom | 1 | Asset coverage <200% (limited regulatory buffer) |
| Leverage Headroom | 2 | Asset coverage <175% (tight — only 25% above 150% minimum) |
| Manual Flags | +1 ea | Related party, prior distribution cuts, etc. |
| **Trend Deterioration** | 1 | Coverage declining >0.20× or leverage creep >0.20× |
| **Trend Deterioration** | 2 | Coverage collapse >0.40×, leverage surge >0.40×, or NAV declining >2%/Q |
| **Trend Deterioration** | +1 | Dual deterioration (coverage AND leverage both worsening) |
| **Trend Deterioration** | +1 | NAV freefall >5%/quarter |

**Risk Tiers:** 🟢 GREEN (0–3) · 🟡 YELLOW (4–6) · 🟠 ORANGE (7–10) · 🔴 RED (11+)
        """)

    # Filters
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        tier_filter = st.multiselect(
            "Risk Tier Filter",
            ["RED", "ORANGE", "YELLOW", "GREEN"],
            default=["RED", "ORANGE", "YELLOW", "GREEN"],
        )
    with col_f2:
        type_filter = st.multiselect(
            "Fund Type Filter",
            ["listed_bdc", "interval_fund", "non_traded_reit"],
            default=["listed_bdc", "interval_fund", "non_traded_reit"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
    with col_f3:
        min_score = st.slider("Minimum composite score", 0, 18, 0)

    df = _load_screener_scores()
    if df.empty:
        st.warning("Screener data unavailable. Check that data/bdc_universe.json exists.")
        return

    # Apply filters — reload with filters applied (trend-enriched)
    funds = _load_universe_with_trends()
    funds_filtered = [
        f for f in funds
        if f.get("type", "") in type_filter
    ]
    scores = screen_universe(funds_filtered, min_score=min_score, tiers=tier_filter)
    df_filtered = screen_to_dataframe(scores)

    if df_filtered.empty:
        st.info("No funds match the current filters.")
        return

    # Add tier badge column
    df_filtered.insert(
        df_filtered.columns.get_loc("Risk Tier") + 1,
        "Tier Badge",
        df_filtered["Risk Tier"].map(_tier_badge),
    )

    st.subheader(f"Screener Results ({len(df_filtered)} fund(s))")

    # Color-code by tier
    display_cols = [
        "Ticker", "Name", "Tier Badge", "Score", "PIK %", "NII Cov.",
        "NAV Chg YoY", "Non-Accruals (FV)", "D/E", "Asset Cov.", "P/NAV", "Net Flow (Qtly)",
    ]
    st.dataframe(
        df_filtered[display_cols].set_index("Ticker"),
        use_container_width=True,
    )

    # Score bar chart
    score_df = pd.DataFrame({
        "Ticker": [s.ticker for s in scores],
        "Score":  [s.composite_score for s in scores],
        "Tier":   [s.risk_tier for s in scores],
    })
    tier_color_map = {
        "RED": "#DC2626", "ORANGE": "#F97316", "YELLOW": "#EAB308", "GREEN": "#22C55E"
    }
    score_df["Color"] = score_df["Tier"].map(tier_color_map)
    fig_bar = px.bar(
        score_df,
        x="Ticker",
        y="Score",
        color="Tier",
        color_discrete_map=tier_color_map,
        title="Composite Red Flag Score by Fund",
        labels={"Score": "Composite Score (0–18)"},
        height=400,
    )
    fig_bar.add_hline(y=7, line_dash="dash", line_color="orange",
                      annotation_text="ORANGE threshold (7)")
    fig_bar.add_hline(y=11, line_dash="dash", line_color="red",
                      annotation_text="RED threshold (11)")
    st.plotly_chart(fig_bar, use_container_width=True)

    # Flag frequency
    st.subheader("Most Common Flags Across Screened Universe")
    freq = flag_frequency_table(scores)
    if freq:
        freq_df = pd.DataFrame([
            {"Flag": FLAG_LABELS.get(k, k), "Count": v}
            for k, v in list(freq.items())[:15]
        ])
        fig_freq = px.bar(
            freq_df, x="Count", y="Flag", orientation="h",
            title="Flag frequency (most common at top)", height=420,
        )
        fig_freq.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_freq, use_container_width=True)

    # Trend signal heatmap
    st.divider()
    st.subheader("Trend Signal Summary")
    st.write(
        "Leading indicators derived from EDGAR quarterly history (parquet cache). "
        "These signals reflect *direction of travel*, not current level. "
        "A fund scoring high on trend signals may be about to cross a threshold."
    )
    trend_data = _load_trend_signals()
    if trend_data:
        _flag_color = {"ok": "🟢", "watch": "🟡", "warn": "🟠", "critical": "🔴"}
        trend_rows = []
        for s in scores:
            td = trend_data.get(s.ticker, {})
            if not td:
                continue
            trend_rows.append({
                "Ticker": s.ticker,
                "Trend Score": td.get("trend_score", 0),
                "Coverage": f"{_flag_color.get(td.get('coverage_flag','ok'),'')} "
                            f"{td.get('coverage_current', 0) or 0:.2f}x "
                            f"({td.get('coverage_4q_change', 0) or 0:+.2f})",
                "Leverage": f"{_flag_color.get(td.get('leverage_flag','ok'),'')} "
                            f"{td.get('leverage_current', 0) or 0:.2f}x "
                            f"({td.get('leverage_4q_change', 0) or 0:+.2f})",
                "PIK": f"{_flag_color.get(td.get('pik_flag','ok'),'')} "
                       f"{(td.get('pik_current') or 0)*100:.1f}%",
                "NAV Vel.": f"{_flag_color.get(td.get('nav_velocity_flag','ok'),'')} "
                            f"{(td.get('nav_velocity_recent') or 0)*100:+.1f}%/Q",
                "Trend Flags": ", ".join(td.get("trend_flags", [])) or "—",
                "As Of": td.get("as_of_period", ""),
            })
        if trend_rows:
            trend_df = pd.DataFrame(trend_rows).set_index("Ticker")
            trend_df = trend_df.sort_values("Trend Score", ascending=False)
            st.dataframe(trend_df, use_container_width=True)
    else:
        st.info("Trend signals not available. Run `python bdc_historical.py --all` to build parquet history.")

    # Peer comparison table
    st.divider()
    with st.expander("Peer Comparison — cross-sectional rankings", expanded=False):
        _render_peer_ranking(funds)

    # Detail for selected fund
    st.divider()
    st.subheader("Fund Detail")
    tickers_in_results = [s.ticker for s in scores]
    if tickers_in_results:
        selected = st.selectbox("Select a fund for detail view", tickers_in_results)
        selected_score = next((s for s in scores if s.ticker == selected), None)
        if selected_score:
            tier_icon = _TIER_COLORS.get(selected_score.risk_tier, "⚪")
            st.markdown(
                f"### {tier_icon} {selected_score.ticker} — {selected_score.name}  \n"
                f"**Composite Score:** {selected_score.composite_score}/18  |  "
                f"**Risk Tier:** {selected_score.risk_tier}  |  "
                f"**Type:** {selected_score.fund_type.replace('_', ' ').title()}  |  "
                f"**Manager:** {selected_score.manager}"
            )

            # Dimension score breakdown
            dim_df = pd.DataFrame([
                {"Dimension": k.replace("_", " ").title(), "Points": v}
                for k, v in selected_score.dimension_scores.items()
                if v > 0
            ])
            if not dim_df.empty:
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Dimension scores:**")
                    st.dataframe(dim_df, use_container_width=True, hide_index=True)
                with c2:
                    fig_dim = px.pie(
                        dim_df, names="Dimension", values="Points",
                        title="Score composition",
                    )
                    st.plotly_chart(fig_dim, use_container_width=True)

            if selected_score.flags_triggered:
                st.write("**Triggered flags:**")
                for flag in selected_score.flags_triggered:
                    label = FLAG_LABELS.get(flag, flag)
                    st.markdown(f"- {label}")

            if selected_score.analyst_notes:
                st.write("**Analyst notes:**")
                st.write(selected_score.analyst_notes)

            # Trend signal detail for selected fund
            td = trend_data.get(selected_score.ticker, {})
            if td and td.get("trend_score", 0) > 0:
                st.write("**Trend signals (from EDGAR quarterly history):**")
                _flag_color = {"ok": "🟢", "watch": "🟡", "warn": "🟠", "critical": "🔴"}
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(
                    "Coverage (trailing 4Q)",
                    f"{td.get('coverage_current') or 0:.3f}x",
                    delta=f"{td.get('coverage_4q_change') or 0:+.3f}x vs 4Q ago",
                    delta_color="inverse",
                )
                c2.metric(
                    "Leverage D/E",
                    f"{td.get('leverage_current') or 0:.2f}x",
                    delta=f"{td.get('leverage_4q_change') or 0:+.2f}x vs 4Q ago",
                    delta_color="inverse",
                )
                c3.metric(
                    "NAV velocity",
                    f"{(td.get('nav_velocity_recent') or 0)*100:+.1f}%/Q",
                    delta=None,
                )
                c4.metric(
                    "Trend score",
                    f"{td.get('trend_score', 0)}/5",
                    delta=None,
                )
                if td.get("trend_flags"):
                    for tf in td["trend_flags"]:
                        label = FLAG_LABELS.get(f"trend_{tf}", tf.replace("_", " ").title())
                        icon = "🔴" if "collapse" in tf or "freefall" in tf or "surge" in tf else "🟠"
                        st.markdown(f"- {icon} {label}")

            # MD&A non-accrual commentary
            _render_mda_panel(selected_score.ticker)

    st.caption(
        "All metrics sourced from public filings. Composite scores are heuristic indicators "
        "to guide further research — not ratings and not investment advice. "
        "Verify all figures against current SEC filings before acting."
    )


# ---------------------------------------------------------------------------
# EDGAR Filings tab
# ---------------------------------------------------------------------------

def render_edgar_filings() -> None:
    st.title("EDGAR Filing Lookup")
    st.write(
        "Browse recent SEC filings for any BDC or private-credit fund. "
        "Fetches from the SEC EDGAR API (cached locally for 24 hours). "
        "Requires an internet connection."
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        ticker_input = st.text_input(
            "Ticker or CIK", value="ARCC",
            help="Enter a listed ticker (e.g. ARCC, HTGC, PSEC) or a numeric CIK.",
        ).strip().upper()
    with col2:
        form_types_sel = st.multiselect(
            "Form types",
            ["10-K", "10-Q", "N-2", "N-CSR", "N-CSRS", "N-CEN", "SC 13G", "DEF 14A"],
            default=["10-K", "10-Q"],
        )
    force_refresh = st.checkbox("Force refresh (bypass cache)")

    if st.button("Fetch filings", type="primary"):
        if not ticker_input:
            st.warning("Enter a ticker or CIK.")
            return
        client = EdgarClient()
        with st.spinner(f"Looking up {ticker_input} on EDGAR…"):
            try:
                if ticker_input.isdigit():
                    cik = ticker_input.zfill(10)
                else:
                    cik = client.lookup_cik(ticker_input, force_refresh=force_refresh)
                subs = client.get_submissions(cik, force_refresh=force_refresh)
                entity_name = subs.get("entityName", ticker_input)
                entity_type = subs.get("entityType", "")
                st.success(f"Found: **{entity_name}** (CIK: {cik}  |  Type: {entity_type})")
            except (KeyError, RuntimeError) as exc:
                st.error(f"Could not find entity: {exc}")
                return

        with st.spinner("Fetching recent filings…"):
            filings = client.get_recent_filings(
                cik,
                form_types=form_types_sel or None,
                n=50,
                force_refresh=force_refresh,
            )

        if not filings:
            st.info("No filings found for the selected form types.")
            return

        filings_df = pd.DataFrame(filings)
        filings_df["EDGAR Link"] = filings_df.apply(
            lambda row: (
                f"https://www.sec.gov/cgi-bin/browse-edgar"
                f"?action=getcompany&CIK={cik}&type={row.get('form', '')}"
                f"&dateb=&owner=include&count=5"
            ),
            axis=1,
        )

        st.subheader(f"Recent filings — {entity_name}")
        st.dataframe(
            filings_df[["filingDate", "form", "reportDate", "accessionNumber"]].rename(columns={
                "filingDate":     "Filed",
                "form":           "Form",
                "reportDate":     "Period",
                "accessionNumber": "Accession No.",
            }),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(
            f"[View all filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40)"
        )

        # XBRL metrics if available
        st.divider()
        if st.button("Fetch XBRL financial metrics"):
            with st.spinner("Loading XBRL company facts (this may take 10–30 seconds)…"):
                try:
                    metrics = client.get_bdc_metrics(
                        cik, ticker=ticker_input, force_refresh=force_refresh
                    )
                    non_null = {
                        k: v for k, v in metrics.items()
                        if v is not None and k not in ("ticker", "cik", "entity_name", "source")
                    }
                    st.subheader("XBRL Metrics")
                    col_a, col_b, col_c = st.columns(3)
                    net_assets = metrics.get("net_assets_usd")
                    total_assets = metrics.get("total_assets_usd")
                    lev = metrics.get("leverage_de")
                    nav_ps = metrics.get("nav_per_share_usd")
                    nii_cov = metrics.get("nii_coverage_ratio")

                    col_a.metric("Net Assets", f"${net_assets/1e9:.2f}B" if net_assets else "n/a")
                    col_a.metric("Total Assets", f"${total_assets/1e9:.2f}B" if total_assets else "n/a")
                    col_b.metric("D/E Leverage", f"{lev:.2f}x" if lev else "n/a")
                    col_b.metric("NAV/Share", f"${nav_ps:.2f}" if nav_ps else "n/a")
                    col_c.metric("NII Coverage", f"{nii_cov:.2f}x" if nii_cov else "n/a")
                    col_c.metric("As Of", metrics.get("as_of_date", "n/a"))

                    with st.expander("Raw XBRL metrics"):
                        st.json(metrics)
                except RuntimeError as exc:
                    st.warning(
                        f"XBRL data unavailable: {exc}. "
                        "Not all BDC/interval fund filings include structured XBRL."
                    )

    st.caption(
        "Data sourced from SEC EDGAR (data.sec.gov). "
        "The SEC requires a valid User-Agent header; this tool identifies as "
        "'private-credit-analysis'. Rate limited to ≤10 requests/second."
    )


# ---------------------------------------------------------------------------
# Historical Analysis & Management Profiles tab
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def _load_universe_summaries() -> dict:
    path = _HISTORY_CACHE / "universe_summaries.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(ttl=3600)
def _load_management_profiles() -> dict:
    if not _PROFILES_PATH.exists():
        return {}
    data = json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
    return data.get("profiles", {})


@st.cache_data(ttl=3600)
def _load_ticker_history(ticker: str) -> pd.DataFrame:
    return load_history(ticker)


def render_historical() -> None:
    st.title("Historical Analysis & Management Profiles")
    st.write(
        "Multi-year NAV trajectories from SEC EDGAR XBRL data, management team profiles, "
        "communication quality assessments, and underwriting track records. "
        "All data sourced from public filings."
    )

    summaries = _load_universe_summaries()
    profiles  = _load_management_profiles()

    if not summaries:
        st.info(
            "Historical data not yet collected. Run:\n"
            "```\npython bdc_historical.py --all\n```"
        )
        return

    # ── Summary comparison table ─────────────────────────────────────────
    st.subheader("NAV/Share Historical Performance (3-Year Ranking)")
    rows = []
    for ticker, s in summaries.items():
        if "error" in s:
            continue
        profile = profiles.get(ticker, {})
        rows.append({
            "Ticker":          ticker,
            "Current NAV/sh":  f"${s.get('nav_per_share_current') or 0:.2f}",
            "1Y Ago":          f"${s.get('nav_per_share_1y_ago') or 0:.2f}",
            "3Y Ago":          f"${s.get('nav_per_share_3y_ago') or 0:.2f}" if s.get('nav_per_share_3y_ago') else "n/a",
            "1Y Chg":          (
                f"{s['nav_change_1y_pct']*100:+.1f}%"
                if s.get("nav_change_1y_pct") is not None else "n/a"
            ),
            "3Y Chg":          (
                f"{s['nav_change_3y_pct']*100:+.1f}%"
                if s.get("nav_change_3y_pct") is not None else "n/a"
            ),
            "Peak NAV/sh":     f"${s.get('nav_peak_per_share') or 0:.2f}",
            "Peak Date":       s.get("nav_peak_date", ""),
            "Drawdown":        (
                f"{s['nav_drawdown_from_peak_pct']*100:+.1f}%"
                if s.get("nav_drawdown_from_peak_pct") is not None else "n/a"
            ),
            "Comm. Grade":     profile.get("communication_grade", "—"),
            "Quarters":        s.get("periods_available", 0),
        })

    summary_df = pd.DataFrame(rows)
    # Sort by 3Y change ascending (worst performers first)
    def _sort_key(v):
        try:
            return float(v.replace("%", "").replace("+", ""))
        except Exception:
            return 0.0
    summary_df["_sort"] = summary_df["3Y Chg"].map(_sort_key)
    summary_df = summary_df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    st.dataframe(summary_df.set_index("Ticker"), use_container_width=True)

    # ── NAV trajectory chart (indexed) ───────────────────────────────────
    st.subheader("NAV/Share Trajectories — Indexed to Common Date")

    all_tickers = [t for t in summaries if "error" not in summaries[t]]
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        chart_tickers = st.multiselect(
            "Select funds to chart",
            all_tickers,
            default=[t for t in ["TCPC", "PSEC", "FSK", "TPVG", "ARCC", "MAIN", "CCLFX"] if t in all_tickers],
        )
    with col_sel2:
        index_mode = st.radio(
            "Y-axis",
            ["Indexed to 100 (relative)", "Absolute NAV/share ($)"],
            horizontal=True,
        )

    if chart_tickers:
        if "Indexed" in index_mode:
            idx_df = nav_indexed_to_100(chart_tickers)
            if not idx_df.empty:
                fig_traj = go.Figure()
                for t in chart_tickers:
                    if t in idx_df.columns:
                        col_data = idx_df[t].dropna()
                        fig_traj.add_trace(go.Scatter(
                            x=idx_df.loc[col_data.index, "period"] if "period" in idx_df.columns else col_data.index,
                            y=col_data.values,
                            mode="lines", name=t,
                        ))
                fig_traj.add_hline(y=100, line_dash="dash", line_color="gray")
                fig_traj.update_layout(
                    title="NAV/share indexed to 100 at earliest common period",
                    xaxis_title="Period", yaxis_title="Indexed NAV/share",
                    height=480,
                )
                st.plotly_chart(fig_traj, use_container_width=True)
        else:
            fig_abs = go.Figure()
            for t in chart_tickers:
                df_h = _load_ticker_history(t)
                if df_h.empty or "nav_per_share" not in df_h.columns:
                    continue
                sub = df_h[["period", "nav_per_share"]].dropna().sort_values("period")
                fig_abs.add_trace(go.Scatter(
                    x=sub["period"], y=sub["nav_per_share"],
                    mode="lines", name=t,
                ))
            fig_abs.update_layout(
                title="NAV/share — absolute ($)",
                xaxis_title="Period", yaxis_title="NAV/share ($)",
                height=480,
            )
            st.plotly_chart(fig_abs, use_container_width=True)

    # ── Leverage trends ───────────────────────────────────────────────────
    st.subheader("Leverage (D/E) Trends")
    lev_tickers = st.multiselect(
        "Select funds for leverage chart",
        all_tickers,
        default=[t for t in ["TCPC", "PNNT", "SCM", "FSK", "ARCC", "MAIN"] if t in all_tickers],
        key="lev_chart",
    )
    if lev_tickers:
        fig_lev = go.Figure()
        for t in lev_tickers:
            df_h = _load_ticker_history(t)
            if df_h.empty or "leverage_de" not in df_h.columns:
                continue
            sub = df_h[["period", "leverage_de"]].dropna().sort_values("period")
            fig_lev.add_trace(go.Scatter(
                x=sub["period"], y=sub["leverage_de"],
                mode="lines", name=t,
            ))
        fig_lev.add_hline(y=1.5, line_dash="dash", line_color="orange",
                          annotation_text="1.5x (high leverage threshold)")
        fig_lev.add_hline(y=2.0, line_dash="dash", line_color="red",
                          annotation_text="2.0x (1940 Act limit)")
        fig_lev.update_layout(
            title="Leverage (D/E) by Fund Over Time",
            xaxis_title="Period", yaxis_title="Debt/Equity (×)",
            height=400,
        )
        st.plotly_chart(fig_lev, use_container_width=True)

    # ── Management profiles ───────────────────────────────────────────────
    st.divider()
    st.subheader("Management Team Profiles")

    if not profiles:
        st.info("Management profiles file not found at data/bdc_management_profiles.json")
        return

    _comm_grade_colors = {
        "A": "#22C55E", "B+": "#84CC16", "B": "#A3E635", "B-": "#FACC15",
        "C+": "#FB923C", "C": "#F97316", "D": "#DC2626",
    }

    # Communication grade league table
    grade_data = [
        {"Ticker": t, "Grade": p.get("communication_grade", "?"), "Name": p.get("name", t)}
        for t, p in profiles.items()
    ]
    grade_order = {"A": 0, "B+": 1, "B": 2, "B-": 3, "C+": 4, "C": 5, "D": 6}
    grade_data.sort(key=lambda x: grade_order.get(x["Grade"], 99))
    grade_df = pd.DataFrame(grade_data)
    st.write("**Communication Quality Rankings** (A = best; D = worst)")
    col_g1, col_g2 = st.columns([1, 2])
    with col_g1:
        st.dataframe(grade_df.set_index("Ticker"), use_container_width=True, hide_index=False)

    # Detailed profile for selected fund
    st.subheader("Detailed Profile")
    profiled_tickers = list(profiles.keys())
    selected_profile_ticker = st.selectbox(
        "Select fund for detailed profile", profiled_tickers
    )
    p = profiles.get(selected_profile_ticker, {})
    if p:
        grade = p.get("communication_grade", "?")
        grade_color = _comm_grade_colors.get(grade, "#6B7280")
        st.markdown(f"### {p.get('name', selected_profile_ticker)}")
        st.markdown(
            f"**Communication Grade:** "
            f"<span style='color:{grade_color}; font-weight:bold; font-size:1.2em'>{grade}</span>",
            unsafe_allow_html=True,
        )

        # Key personnel
        personnel = p.get("key_personnel", {})
        if personnel:
            with st.expander("Management Team", expanded=True):
                for role, person in personnel.items():
                    if role != "advisor_ownership" and role != "advisor_compensation" and role != "conflict_note":
                        st.markdown(f"**{role.replace('_', ' ').title()}:** {person}")
                if "advisor_ownership" in personnel:
                    st.info(personnel["advisor_ownership"])
                if "conflict_note" in personnel:
                    st.warning(personnel["conflict_note"])

        # Communication notes
        comm_notes = p.get("communication_notes", "")
        if comm_notes:
            with st.expander("Communication Quality Assessment"):
                st.write(comm_notes)

        # Underwriting profile
        uw = p.get("underwriting_profile", {})
        if uw:
            with st.expander("Underwriting Profile & Track Record"):
                for k, v in uw.items():
                    label = k.replace("_", " ").title()
                    if isinstance(v, list):
                        st.markdown(f"**{label}:**")
                        for item in v:
                            st.markdown(f"- {item}")
                    else:
                        st.markdown(f"**{label}:** {v}")

        # NAV history chart for this fund
        nav_hist = p.get("nav_history_per_share")
        if nav_hist and isinstance(nav_hist, dict):
            with st.expander("Historical NAV/Share (from profile data)"):
                nav_df = pd.DataFrame(
                    [(k, v) for k, v in nav_hist.items() if v is not None],
                    columns=["Period", "NAV/Share"],
                ).sort_values("Period")
                fig_nav = px.line(
                    nav_df, x="Period", y="NAV/Share",
                    title=f"{selected_profile_ticker} NAV/share history",
                    markers=True,
                )
                fig_nav.update_layout(height=300)
                st.plotly_chart(fig_nav, use_container_width=True)

        # Distribution history
        dist_hist = p.get("distribution_history", [])
        if dist_hist:
            with st.expander("Distribution History"):
                for event in dist_hist:
                    icon = "✂️" if any(word in event.get("event","").lower()
                                       for word in ["cut", "reduc", "lower"]) else "•"
                    st.markdown(f"**{event.get('date','?')}:** {event.get('event','')}")

        # Key incidents
        incidents = p.get("key_incidents", [])
        if incidents:
            with st.expander("Key Incidents & Events"):
                for inc in incidents:
                    st.markdown(f"**{inc.get('date','?')}:** {inc.get('event','')}")
                    st.divider()

        # Related party analysis (PSEC-specific)
        rpa = p.get("related_party_analysis")
        if rpa:
            with st.expander("Related-Party Analysis", expanded=True):
                for k, v in rpa.items():
                    st.markdown(f"**{k.replace('_',' ').title()}:** {v}")

        # Analyst assessment
        assessment = p.get("analyst_assessment", "")
        if assessment:
            st.subheader("Analyst Assessment")
            st.warning(assessment)

    st.caption(
        "All profile data sourced from: SEC EDGAR (10-K, 10-Q, DEF 14A, 8-K), "
        "company earnings transcripts (public), and financial press. "
        "This is analytical research for informational purposes, not investment advice."
    )


# ---------------------------------------------------------------------------
# Portfolio & Borrowers tab
# ---------------------------------------------------------------------------

_PORTFOLIO_CACHE = Path(__file__).parent / "data" / "portfolio_cache"
_BORROWER_DB_PATH = Path(__file__).parent / "data" / "borrower_db.json"
_PROCESSED_DIR = Path(__file__).parent / "data" / "processed"
_MONTHLY_WATCHLIST_PATH = _PROCESSED_DIR / "monthly_watchlist.csv"
_PARSER_HEALTH_PATH = _PROCESSED_DIR / "parser_health.csv"


@st.cache_data(ttl=1800)
def _load_borrower_db() -> dict:
    if not _BORROWER_DB_PATH.exists():
        return {}
    try:
        return json.loads(_BORROWER_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


@st.cache_data(ttl=1800)
def _load_portfolio_cache_summary() -> list[dict]:
    """Summarise what's in the portfolio cache."""
    return summarize_portfolio_cache(_PORTFOLIO_CACHE)


@st.cache_data(ttl=1800)
def _load_monthly_watchlist() -> list[dict]:
    return load_csv_records(_MONTHLY_WATCHLIST_PATH)


@st.cache_data(ttl=1800)
def _load_parser_health() -> list[dict]:
    return load_csv_records(_PARSER_HEALTH_PATH)


@st.cache_data(ttl=1800)
def _compute_maturity_wall() -> tuple[list[dict], list[dict]]:
    """Compute maturity wall data from portfolio cache files.

    Returns:
        (wall_rows, past_due_rows) where each is a list of dicts.
        wall_rows: {quarter, fund, fv_mm} for stacked bar chart
        past_due_rows: {fund, issuer, maturity, fv_mm} past-due positions
    """
    return compute_maturity_wall(_PORTFOLIO_CACHE)


def render_portfolio() -> None:
    st.title("Portfolio Companies & Borrowers")
    st.write(
        "Cross-fund Schedule of Investments analysis. Data is parsed from SEC 10-K / 10-Q "
        "filing HTML — the Schedule of Investments section. Run "
        "`python portfolio_collector.py --all --max-filings 2` to populate the cache, "
        "then `python portfolio_collector.py --build-db` to rebuild the borrower database."
    )

    from portfolio_collector import (
        PortfolioCollector, build_borrower_db, analyze_borrower_db, PORTFOLIO_CACHE
    )

    # ── Cache status ──────────────────────────────────────────────────────
    cache_summary = _load_portfolio_cache_summary()
    if not cache_summary:
        st.warning(
            "No portfolio data cached yet. Run: "
            "`python portfolio_collector.py --all --max-filings 2` to collect filing data."
        )
        with st.expander("Quick collect for individual fund"):
            col1, col2 = st.columns([2, 1])
            with col1:
                ticker_input = st.text_input("Ticker to collect", value="PNNT",
                                             key="portfolio_collect_ticker")
            with col2:
                n_f = st.number_input("# filings", min_value=1, max_value=5, value=2,
                                      key="portfolio_n_filings")
            if st.button("Collect now", type="primary", key="portfolio_collect_btn"):
                with st.spinner(f"Fetching {ticker_input} SOI from EDGAR..."):
                    try:
                        c = PortfolioCollector()
                        c.collect_fund(ticker_input.upper(), n_filings=int(n_f))
                        build_borrower_db()
                        st.success("Done — reload page to see data.")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error: {e}")
        return

    # ── Coverage summary ──────────────────────────────────────────────────
    st.subheader("Filing Coverage")
    cache_df = pd.DataFrame(cache_summary)
    st.dataframe(
        cache_df[["ticker", "period", "positions", "non_accruals",
                  "pik_positions", "total_fv_mm"]].rename(columns={
            "ticker": "Fund", "period": "Period", "positions": "Positions",
            "non_accruals": "Non-Accruals", "pik_positions": "PIK",
            "total_fv_mm": "Total FV ($M)",
        }).set_index("Fund"),
        use_container_width=True,
    )

    col_refresh, col_info = st.columns([1, 3])
    with col_refresh:
        if st.button("Rebuild borrower DB", key="rebuild_db_btn"):
            with st.spinner("Rebuilding..."):
                build_borrower_db()
                st.cache_data.clear()
                st.success("Done.")

    # ── Borrower database ─────────────────────────────────────────────────
    db = _load_borrower_db()
    if not db:
        st.info("No borrower database found. Click 'Rebuild borrower DB' above.")
        return

    meta = db.get("meta", {})
    borrowers = db.get("borrowers", {})
    families = db.get("families", {})
    family_review = db.get("family_review", {})

    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Unique borrowers", meta.get("unique_borrowers", 0))
    col2.metric("Unique families", meta.get("unique_families", 0))
    col3.metric("Total positions", meta.get("total_positions", 0))
    col4.metric("Funds covered", len(meta.get("funds_included", [])))
    col5.metric("Funds", ", ".join(meta.get("funds_included", [])))

    st.divider()
    st.subheader("Operating Views")
    st.write(
        "Production-style operating artifacts generated by the refresh flow. "
        "Use these views for the current PM action list and filing-parser quality control."
    )

    watchlist_rows = _load_monthly_watchlist()
    parser_health_rows = _load_parser_health()

    op_col1, op_col2, op_col3 = st.columns(3)
    op_col1.metric("Monthly watchlist rows", len(watchlist_rows))
    op_col2.metric("Parser health rows", len(parser_health_rows))
    op_col3.metric(
        "Manual review filings",
        sum(1 for row in parser_health_rows if row.get("Status") == "needs_manual_review"),
    )

    op_tab1, op_tab2 = st.tabs(["Monthly Watchlist", "Parser Health"])

    with op_tab1:
        if watchlist_rows:
            bucket_options = ["All"] + sorted(
                {row.get("Bucket", "") for row in watchlist_rows if row.get("Bucket", "")},
                key=lambda value: {
                    "Overweight core": 0,
                    "Overweight selectively": 1,
                    "Hold / neutral": 2,
                    "Underweight / caution": 3,
                    "Avoid / trim first": 4,
                }.get(value, 99),
            )
            bucket_filter = st.selectbox(
                "Filter by PM bucket",
                bucket_options,
                key="monthly_watchlist_bucket",
            )
            watchlist_df = pd.DataFrame(
                build_monthly_watchlist_rows(watchlist_rows, bucket=bucket_filter)
            )
            st.dataframe(watchlist_df, use_container_width=True, height=420)
            st.caption(f"Source: `{_MONTHLY_WATCHLIST_PATH.relative_to(Path(__file__).parent)}`")
        else:
            st.info("No monthly watchlist found yet. Run `python refresh.py --score-only`.")

    with op_tab2:
        if parser_health_rows:
            status_filter = st.selectbox(
                "Filter by parser status",
                ["All", "needs_manual_review", "used_fallback", "parsed_cleanly"],
                key="parser_health_status",
            )
            parser_df = pd.DataFrame(
                build_parser_health_rows(parser_health_rows, status=status_filter)
            )
            st.dataframe(parser_df, use_container_width=True, height=420)
            st.caption(f"Source: `{_PARSER_HEALTH_PATH.relative_to(Path(__file__).parent)}`")
        else:
            st.info("No parser health report found yet. Run `python refresh.py --score-only` or `python refresh.py`.")

    if families:
        st.divider()
        st.subheader("Borrower Families (Related-Entity Rollup)")
        st.write(
            "This view rolls related borrower entities into family-level surveillance buckets. "
            "It is intended for transmission mapping, refinancing clusters, and sponsor-platform monitoring."
        )

        family_min_funds = st.slider(
            "Minimum funds holding the family",
            1,
            6,
            2,
            key="family_min_funds",
        )
        family_rows = build_family_summary_rows(families, min_funds=family_min_funds)
        if family_rows:
            family_df = pd.DataFrame(family_rows).set_index("Family")

            def _style_family_flag(val):
                return "background-color: #fee2e2; font-weight: bold" if val and "YES" in str(val) else ""

            st.dataframe(
                family_df.style.applymap(_style_family_flag, subset=["Non-Accrual"]),
                use_container_width=True,
                height=360,
            )
        else:
            st.info(f"No borrower families held by {family_min_funds}+ funds.")

        fam_c1, fam_c2, fam_c3 = st.columns(3)
        fam_c1.metric("Family watchlist rows", len(families))
        fam_c2.metric(
            "Alias overrides",
            meta.get("family_alias_count", 0),
            help="Curated borrower-family overrides loaded during DB build.",
        )
        fam_c3.metric("Family watchlist", Path(meta.get("family_watchlist_path", "")).name or "n/a")

        st.markdown("**Family Stress Tiers**")
        _FAMILY_TIER_COLORS = {"RED": "#fee2e2", "ORANGE": "#ffedd5", "YELLOW": "#fef9c3", "GREEN": ""}

        def _family_tier_color(val):
            color = _FAMILY_TIER_COLORS.get(str(val), "")
            return f"background-color: {color}; font-weight: bold" if color else ""

        family_stress_min = st.slider(
            "Minimum family stress score to show",
            0,
            10,
            3,
            key="family_stress_min_score",
        )
        family_stress_rows = build_family_stress_rows(families, min_score=family_stress_min)
        if family_stress_rows:
            family_stress_df = pd.DataFrame(family_stress_rows).set_index("Family")
            st.dataframe(
                family_stress_df.style.applymap(_family_tier_color, subset=["Tier"]),
                use_container_width=True,
                height=min(420, max(200, len(family_stress_rows) * 36)),
            )
        else:
            st.info(f"No borrower families with stress score ≥ {family_stress_min}.")

        family_non_acc = build_family_non_accrual_rows(families)
        if family_non_acc:
            st.markdown("**Family Non-Accrual Positions**")
            st.dataframe(pd.DataFrame(family_non_acc).set_index("Family"), use_container_width=True)

        family_pik = build_family_pik_rows(families)
        if family_pik:
            st.markdown("**Family PIK Positions**")
            st.dataframe(pd.DataFrame(family_pik).set_index("Family"), use_container_width=True)

        family_losses = build_family_unrealized_loss_rows(families)
        if family_losses:
            st.markdown("**Largest Family Unrealized Losses**")
            st.dataframe(pd.DataFrame(family_losses).set_index("Family"), use_container_width=True)

        st.markdown("**Family Search**")
        family_search_q = st.text_input(
            "Search by family or borrower name",
            key="family_search",
            placeholder="e.g. 'pluralsight', 'integrity', 'streamland'...",
        )
        if family_search_q and len(family_search_q) >= 2:
            q = family_search_q.lower()
            family_matches = {
                key: rec
                for key, rec in families.items()
                if q in key
                or q in rec.get("family_name", "").lower()
                or any(q in name.lower() for name in rec.get("borrower_names", []))
            }
            if family_matches:
                st.write(f"{len(family_matches)} family match(es):")
                for key, rec in sorted(
                    family_matches.items(),
                    key=lambda item: (-item[1].get("fund_count", 0), -item[1].get("borrower_count", 0)),
                )[:20]:
                    with st.expander(
                        f"{rec['family_name']} — {rec.get('borrower_count', 0)} borrower(s), {rec.get('fund_count', 0)} fund(s)"
                    ):
                        st.json(
                            {
                                "family_key": rec.get("family_key"),
                                "borrower_names": rec.get("borrower_names", []),
                                "funds": rec.get("funds", []),
                                "managers": rec.get("managers", []),
                                "total_fv_mm": rec.get("total_fv_mm"),
                                "total_cost_mm": rec.get("total_cost_mm"),
                                "unrealized_pct": rec.get("unrealized_pct"),
                                "is_non_accrual_any": rec.get("is_non_accrual_any"),
                                "non_accrual_funds": rec.get("non_accrual_funds", []),
                                "is_pik_any": rec.get("is_pik_any"),
                                "pik_funds": rec.get("pik_funds", []),
                                "current_by_fund": rec.get("current_by_fund", {}),
                            }
                        )
            else:
                st.info(f"No borrower families matching '{family_search_q}'.")

        st.markdown("**Family Override Review**")
        st.write(
            "These review tables help maintain `data/borrower_family_aliases.json`. "
            "Merge candidates are related borrowers in different families; split candidates are low-cohesion families."
        )
        rev_c1, rev_c2 = st.columns(2)
        rev_c1.metric("Merge candidates", meta.get("family_merge_candidate_count", 0))
        rev_c2.metric("Split candidates", meta.get("family_split_candidate_count", 0))

        merge_similarity = st.slider(
            "Minimum merge-candidate similarity",
            0.3,
            1.0,
            0.6,
            0.05,
            key="family_merge_similarity",
        )
        require_context = st.checkbox(
            "Require shared fund or manager context",
            value=True,
            key="family_merge_require_context",
        )
        merge_rows = build_family_merge_candidate_rows(
            family_review,
            min_similarity=merge_similarity,
            require_shared_context=require_context,
        )
        if merge_rows:
            st.dataframe(pd.DataFrame(merge_rows), use_container_width=True, height=300)
        else:
            st.info("No merge candidates match the current review filters.")

        include_override_splits = st.checkbox(
            "Include override-backed families in split review",
            value=False,
            key="family_split_include_overrides",
        )
        split_rows = build_family_split_candidate_rows(
            family_review,
            include_override_families=include_override_splits,
        )
        if split_rows:
            st.dataframe(pd.DataFrame(split_rows), use_container_width=True, height=260)
        else:
            st.info("No split candidates match the current review filters.")

    # ── Multi-lender issuers ──────────────────────────────────────────────
    st.subheader("Multi-Fund Issuers (Systemic Risk)")
    st.write("Borrowers held by 2+ BDC lenders simultaneously. Deterioration in these "
             "credits will simultaneously impair multiple funds.")

    min_funds_filter = st.slider("Minimum funds holding the issuer", 1, 5, 2,
                                 key="portfolio_min_funds")

    multi = [
        {
            "Issuer": rec["canonical_name"],
            "Funds": rec["fund_count"],
            "Fund List": ", ".join(rec["funds"]),
            "Total FV ($M)": round(rec["total_fv_mm"], 1) if rec["total_fv_mm"] else None,
            "Total Cost ($M)": round(rec["total_cost_mm"], 1) if rec["total_cost_mm"] else None,
            "Unrealized G/L": f"{rec['unrealized_pct']*100:+.1f}%" if rec.get("unrealized_pct") is not None else "—",
            "Non-Accrual": "YES — " + "+".join(rec["non_accrual_funds"]) if rec["is_non_accrual_any"] else "",
            "PIK": "YES — " + "+".join(rec["pik_funds"]) if rec["is_pik_any"] else "",
            "Industry": ", ".join(rec["industries"][:2]),
        }
        for rec in borrowers.values()
        if rec["fund_count"] >= min_funds_filter
    ]
    multi.sort(key=lambda x: (-x["Funds"], -(x["Total FV ($M)"] or 0)))

    if multi:
        multi_df = pd.DataFrame(multi).set_index("Issuer")

        def _style_na(val):
            return "background-color: #fee2e2; font-weight: bold" if val and "YES" in str(val) else ""

        st.dataframe(
            multi_df.style.applymap(_style_na, subset=["Non-Accrual"]),
            use_container_width=True,
            height=400,
        )

        # Fund overlap heatmap
        if len(meta.get("funds_included", [])) >= 2:
            st.subheader("Cross-Fund Borrower Overlap")
            funds_list = meta["funds_included"]
            overlap = pd.DataFrame(0, index=funds_list, columns=funds_list)
            for rec in borrowers.values():
                for f1 in rec["funds"]:
                    for f2 in rec["funds"]:
                        if f1 in overlap.index and f2 in overlap.columns:
                            overlap.loc[f1, f2] += 1
            fig_heat = px.imshow(
                overlap, text_auto=True, aspect="auto",
                color_continuous_scale="Blues",
                title="Shared borrower count between fund pairs",
                labels={"color": "Shared borrowers"},
            )
            st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info(f"No issuers held by {min_funds_filter}+ funds in current data.")

    # ── Concentration heatmap ─────────────────────────────────────────────
    st.divider()
    st.subheader("Borrower × Fund Concentration Heatmap")
    st.write(
        "Each cell shows the FV held by that fund in that borrower. "
        "Red shading = non-accrual at that fund. Asterisk (*) = PIK. "
        "Sorted by number of funds holding the position, then by total FV."
    )

    import numpy as np

    heatmap_top_n = st.slider("Borrowers to display", 10, 60, 30, key="heatmap_top_n")
    heatmap_min_funds = st.slider("Minimum funds holding borrower", 2, 6, 2, key="heatmap_min_funds")

    # Build per-borrower records with latest-period FV per fund
    heatmap_recs = build_borrower_heatmap_records(borrowers, min_funds=heatmap_min_funds)
    top_recs = heatmap_recs[:heatmap_top_n]

    if not top_recs:
        st.info("No borrowers match the current filters.")
    else:
        # Key risks callout
        na_multi = [r for r in top_recs if r["is_na_any"] and r["fund_count"] >= 2]
        if na_multi:
            worst = sorted(na_multi, key=lambda r: (-r["fund_count"], -r["total_fv"]))[:4]
            lines = [f"**{r['name']}** — NA at {', '.join(sorted(r['na_funds']))}  (${r['total_fv']:.0f}M across {r['fund_count']} funds)"
                     for r in worst]
            st.warning(
                "⚠️ **Non-accrual positions in multiple funds:**\n\n" + "\n\n".join(lines)
            )

        # Matrix dimensions
        all_funds_h = sorted({f for r in top_recs for f in r["latest"]})
        n_rows, n_cols = len(top_recs), len(all_funds_h)
        fund_idx = {f: j for j, f in enumerate(all_funds_h)}

        fv_mat   = np.zeros((n_rows, n_cols))
        na_mat   = np.zeros((n_rows, n_cols))
        text_mat = [[""] * n_cols for _ in range(n_rows)]
        hover_mat = [[""] * n_cols for _ in range(n_rows)]

        for i, rec in enumerate(top_recs):
            for fund, app in rec["latest"].items():
                j = fund_idx.get(fund)
                if j is None:
                    continue
                fv = (app.get("fv_mm") or app.get("cost_mm") or 0)
                # Use a tiny non-zero sentinel so "held but no FV" still colours the cell
                fv_mat[i, j] = fv if fv > 0 else 0.01
                if fund in rec["na_funds"]:
                    na_mat[i, j] = 1

                cell = f"${fv:.1f}M" if fv > 0 else "✓"
                if fund in rec["pik_funds"]:
                    cell += "*"
                text_mat[i][j] = cell

                tags = []
                if fund in rec["na_funds"]:
                    tags.append("NON-ACCRUAL")
                if fund in rec["pik_funds"]:
                    tags.append("PIK")
                tag_str = "  [" + " / ".join(tags) + "]" if tags else ""
                hover_mat[i][j] = f"{rec['name']}<br>{fund}: ${fv:.1f}M{tag_str}"

        row_labels = [
            (r["name"][:38] + "…" if len(r["name"]) > 38 else r["name"])
            + f"  ({r['fund_count']})"
            for r in top_recs
        ]

        fig_conc = go.Figure()

        # Base heatmap: FV intensity
        fig_conc.add_trace(go.Heatmap(
            z=fv_mat,
            x=all_funds_h,
            y=row_labels,
            text=text_mat,
            hovertext=hover_mat,
            hoverinfo="text",
            texttemplate="%{text}",
            textfont={"size": 9},
            colorscale=[[0, "#f8fafc"], [0.001, "#bfdbfe"], [0.3, "#3b82f6"], [1, "#1e3a8a"]],
            showscale=True,
            colorbar=dict(title="FV ($M)", thickness=12, len=0.6),
            zmin=0,
        ))

        # NA overlay: red tint
        if na_mat.any():
            fig_conc.add_trace(go.Heatmap(
                z=na_mat,
                x=all_funds_h,
                y=row_labels,
                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(220,38,38,0.35)"]],
                showscale=False,
                hoverinfo="skip",
                zmin=0, zmax=1,
            ))

        fig_conc.update_layout(
            height=max(420, n_rows * 21 + 130),
            margin=dict(l=10, r=10, t=50, b=10),
            title=dict(
                text="Borrower × Fund Exposure  |  Colour = FV ($M)  |  * = PIK  |  Red = Non-Accrual",
                font=dict(size=13),
            ),
            xaxis=dict(side="top", tickfont=dict(size=11)),
            yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        )
        st.plotly_chart(fig_conc, use_container_width=True)

        # Summary stats below the chart
        c1, c2, c3 = st.columns(3)
        top_fv = max(top_recs, key=lambda r: r["total_fv"])
        most_funds = top_recs[0]  # already sorted by fund_count desc
        c1.metric("Most widely held", most_funds["name"][:28], f"{most_funds['fund_count']} funds")
        c2.metric("Largest aggregate FV", top_fv["name"][:28], f"${top_fv['total_fv']:.0f}M")
        c3.metric("NA borrowers in 2+ funds", str(len(na_multi)))

    # ── Borrower stress tiers ─────────────────────────────────────────────
    st.divider()
    st.subheader("Borrower Stress Tiers")
    st.write(
        "Each borrower is scored 0-10 on: unrealized loss depth (0-4), "
        "non-accrual status (0-3), PIK income (0-1), and multi-fund contagion (0-2). "
        "RED = score ≥ 5, ORANGE = 3-4, YELLOW = 1-2."
    )

    _TIER_COLORS = {"RED": "#fee2e2", "ORANGE": "#ffedd5", "YELLOW": "#fef9c3", "GREEN": ""}

    stress_min_score = st.slider("Minimum stress score to show", 0, 10, 3,
                                 key="stress_min_score")
    stressed_borrowers = build_borrower_stress_rows(borrowers, min_score=stress_min_score)

    if stressed_borrowers:
        stress_df = pd.DataFrame(stressed_borrowers).set_index("Issuer")

        def _tier_color(val):
            color = _TIER_COLORS.get(str(val), "")
            return f"background-color: {color}; font-weight: bold" if color else ""

        st.dataframe(
            stress_df.style.applymap(_tier_color, subset=["Tier"]),
            use_container_width=True,
            height=min(500, max(200, len(stressed_borrowers) * 36)),
        )
    else:
        st.info(f"No borrowers with stress score ≥ {stress_min_score}.")

    # ── Non-accrual issuers ───────────────────────────────────────────────
    st.divider()
    st.subheader("Non-Accrual Positions")
    non_acc = build_non_accrual_rows(borrowers)

    if non_acc:
        na_df = pd.DataFrame(non_acc).set_index("Issuer")
        st.dataframe(na_df, use_container_width=True)
    else:
        st.info("No non-accrual positions detected in current data. "
                "Non-accrual detection relies on footnote markers — some filings may not "
                "be fully parsed.")

    # ── PIK concentration ─────────────────────────────────────────────────
    st.divider()
    st.subheader("PIK Borrowers")
    pik_list = build_pik_rows(borrowers)
    if pik_list:
        pik_df = pd.DataFrame(pik_list).set_index("Issuer")
        st.dataframe(pik_df, use_container_width=True)
    else:
        st.info("No PIK positions detected in current data.")

    # ── Unrealized loss ranking ───────────────────────────────────────────
    st.divider()
    st.subheader("Largest Unrealized Losses")
    losses = build_unrealized_loss_rows(borrowers)

    if losses:
        loss_df = pd.DataFrame(losses).set_index("Issuer")
        st.dataframe(loss_df, use_container_width=True)
    else:
        st.info("No significant unrealized losses detected in current data.")

    # ── Borrower search ───────────────────────────────────────────────────
    st.divider()
    st.subheader("Borrower Search")
    search_q = st.text_input("Search by issuer name (partial match)", key="borrower_search",
                              placeholder="e.g. 'software', 'healthcare', company name...")
    if search_q and len(search_q) >= 2:
        q = search_q.lower()
        matches = {k: r for k, r in borrowers.items()
                   if q in k or q in r["canonical_name"].lower()}
        if matches:
            st.write(f"{len(matches)} match(es):")
            for key, rec in sorted(matches.items(),
                                   key=lambda x: -x[1]["fund_count"])[:20]:
                with st.expander(f"{rec['canonical_name']} — {rec['fund_count']} fund(s)"):
                    st.json({
                        "funds": rec["funds"],
                        "total_fv_mm": rec["total_fv_mm"],
                        "total_cost_mm": rec["total_cost_mm"],
                        "unrealized_pct": rec.get("unrealized_pct"),
                        "is_non_accrual_any": rec["is_non_accrual_any"],
                        "non_accrual_funds": rec["non_accrual_funds"],
                        "is_pik_any": rec["is_pik_any"],
                        "pik_funds": rec["pik_funds"],
                        "industries": rec["industries"],
                        "appearances": rec["appearances"],
                    })
        else:
            st.info(f"No borrowers matching '{search_q}'")

    # ── Maturity wall ─────────────────────────────────────────────────────
    st.divider()
    st.subheader("Maturity Wall")
    st.write(
        "FV of positions maturing by quarter (funds with maturity data parsed). "
        "Past-due positions are loans where the stated maturity has already passed — "
        "these are likely in extension, restructuring, or default."
    )

    wall_rows, past_due_rows = _compute_maturity_wall()

    if past_due_rows:
        total_pd = sum(r["FV ($M)"] for r in past_due_rows)
        st.error(
            f"**{len(past_due_rows)} past-due positions** detected across "
            f"{len({r['Fund'] for r in past_due_rows})} fund(s) — "
            f"**${total_pd:,.0f}M total FV**. These positions have passed stated maturity "
            "and may be in technical default, restructuring, or extension."
        )
        pd_df = pd.DataFrame(past_due_rows).drop(columns=["mat_date"]).set_index("Fund")
        st.dataframe(pd_df, use_container_width=True)

    if wall_rows:
        wall_df = pd.DataFrame(wall_rows)
        # Aggregate by quarter + fund
        wall_agg = (
            wall_df.groupby(["Quarter", "Fund"])["FV ($M)"]
            .sum()
            .reset_index()
        )
        # Filter to 2024-2030
        wall_agg = wall_agg[
            wall_agg["Quarter"].between("2024-Q1", "2031-Q4")
        ].copy()
        wall_agg = wall_agg.sort_values("Quarter")

        fig_wall = px.bar(
            wall_agg,
            x="Quarter",
            y="FV ($M)",
            color="Fund",
            title="Maturity Wall — FV ($M) by Quarter",
            labels={"FV ($M)": "Fair Value ($M)"},
            height=420,
        )
        fig_wall.update_layout(xaxis_tickangle=-45, bargap=0.15)
        st.plotly_chart(fig_wall, use_container_width=True)
        st.caption(
            "Note: Only funds where maturity date columns were successfully parsed are shown. "
            "BXSL, FSK, HTGC, MAIN, OBDC and others may have maturity data not captured in current parsing."
        )
    else:
        st.info("No maturity data available. Maturity columns may not be parsed for current funds.")

    # ── Sector concentration ──────────────────────────────────────────────
    st.divider()
    st.subheader("Sector Concentration")
    sector_data: dict[str, float] = {}
    for rec in borrowers.values():
        fv = rec["total_fv_mm"] or 0
        for ind in rec["industries"][:1]:
            if ind:
                sector_data[ind] = sector_data.get(ind, 0) + fv
    if sector_data:
        sec_df = pd.DataFrame([
            {"Sector": k, "Total FV ($M)": round(v, 1)}
            for k, v in sorted(sector_data.items(), key=lambda x: -x[1])
        ])
        fig_sec = px.bar(
            sec_df.head(20), x="Total FV ($M)", y="Sector",
            orientation="h", title="Sector FV concentration across all cached funds",
            height=500,
        )
        fig_sec.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_sec, use_container_width=True)

    st.caption(
        "Portfolio data parsed from SEC EDGAR 10-K/10-Q filing HTML. "
        "Non-accrual and PIK detection depends on footnote conventions — verify against source filings. "
        "FV figures are as-of the filing date of each cached document."
    )


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render() -> None:
    # ── Top-level page navigation ────────────────────────────────────────
    outer_tab1, outer_tab2, outer_tab3, outer_tab4, outer_tab5, outer_tab6, outer_tab7, outer_tab8 = st.tabs([
        "Fund Scenario", "Market Overview", "Red Flag Screener",
        "Historical & Mgmt", "EDGAR Filings", "Portfolio & Borrowers",
        "Macro & Scenarios", "Trade Signals",
    ])

    with outer_tab2:
        render_market_overview()

    with outer_tab3:
        render_screener()

    with outer_tab4:
        render_historical()

    with outer_tab5:
        render_edgar_filings()

    with outer_tab6:
        render_portfolio()

    with outer_tab7:
        render_macro_scenarios()

    with outer_tab8:
        render_trade_signals()

    with outer_tab1:
        _render_fund_scenario()


def _render_fund_scenario() -> None:
    """Original single-fund scenario builder (formerly the body of render())."""
    st.sidebar.header("Fund & Scenario")

    fund_name    = st.sidebar.selectbox("Fund", list(FUND_PROFILES.keys()), index=0)
    profile      = FUND_PROFILES[fund_name]
    ticker       = fund_name.split(" — ")[0]
    is_cclf      = "CCLF" in fund_name
    is_listed_bdc = fund_name in ("HTGC — Hercules Capital", "OBDC — Blue Owl Capital Corp.")

    preset_name         = st.sidebar.selectbox("Primary preset", list(PRESETS.keys()), index=0)
    merged: Dict[str, object] = {**profile, **PRESETS[preset_name]}

    compare_enabled     = st.sidebar.checkbox("Enable comparison scenario", value=True)
    compare_preset_name = st.sidebar.selectbox(
        "Comparison preset", list(PRESETS.keys()), index=1,
        disabled=not compare_enabled,
    )

    # ── Dashboard header ─────────────────────────────────────────────────
    st.title(f"{fund_name} — Liquidity Scenario Dashboard")
    st.write(
        "Interactive scenario engine for exploring liquidity, leverage, and cash-flow "
        "sensitivity under different investor-flow and credit assumptions. "
        "Balance-sheet defaults are approximate starting points from recent public filings; "
        "adjust them in Advanced assumptions. Negative cash indicates liquidity needs beyond "
        "currently modelled facility capacity."
    )

    if is_listed_bdc:
        st.caption(
            "Note: for exchange-listed BDCs the redemption rate models share-repurchase "
            "activity.  Typical listed-BDC repurchase programmes run 1–2 % of NAV per quarter."
        )

    if is_cclf:
        st.info(
            "**Tide turning:** Bloomberg / Robert A. Stanger & Co. data through March 23, 2026 "
            "shows CCLFX quarterly redemptions reached approximately **8 % of NAV** in Q1 2026, "
            "while new subscriptions slowed to ~5.5 % — the first period of sustained net "
            "outflows since inception.  This follows several years of 10–13 % quarterly inflows "
            "that masked distribution-coverage pressure.  Use the **Tide Turning (Current)** "
            "preset to model forward cash flows under these observed rates."
        )

    # ── Core exposed assumptions ─────────────────────────────────────────
    st.sidebar.subheader("Core assumptions")
    quarters = st.sidebar.select_slider(
        "Forecast horizon (quarters)", options=[4, 6, 8, 12, 16],
        value=int(merged["quarters"]), key=f"{ticker}_quarters",
    )
    subscription_rate = st.sidebar.slider(
        "Subscription rate (% of NAV per quarter)",
        0.0, 20.0, float(merged.get("subscription_rate", 0.0)) * 100, 0.25,
        key=f"{ticker}_sub",
    ) / 100
    redemption_rate = st.sidebar.slider(
        "Redemption / repurchase rate (% of NAV per quarter)",
        0.0, 20.0, float(merged.get("redemption_rate", 0.05)) * 100, 0.25,
        key=f"{ticker}_redemption",
    ) / 100
    annual_default_rate = st.sidebar.slider(
        "Annual default rate (%)",
        0.0, 15.0, float(merged["annual_default_rate"]) * 100, 0.25,
        key=f"{ticker}_default",
    ) / 100
    loss_given_default = st.sidebar.slider(
        "Loss given default (%)",
        0.0, 80.0, float(merged["loss_given_default"]) * 100, 1.0,
        key=f"{ticker}_lgd",
    ) / 100
    unfunded_draw_rate = st.sidebar.slider(
        "Unfunded draw rate (% of remaining per quarter)",
        0.0, 30.0, float(merged["unfunded_draw_rate"]) * 100, 1.0,
        key=f"{ticker}_unfunded_draw",
    ) / 100
    portfolio_yield = st.sidebar.slider(
        "Portfolio yield on gross assets (annual %)",
        4.0, 20.0, float(merged["portfolio_yield"]) * 100, 0.25,
        key=f"{ticker}_yield",
    ) / 100
    distribution_rate = st.sidebar.slider(
        "Distribution rate (annual %)",
        0.0, 15.0, float(merged["distribution_rate"]) * 100, 0.25,
        key=f"{ticker}_dist",
    ) / 100

    # ── Advanced assumptions ──────────────────────────────────────────────
    with st.sidebar.expander("Advanced assumptions"):
        nav_start = st.number_input(
            "Starting NAV ($bn)", min_value=0.1,
            value=float(merged["nav_start"]) / 1e9, step=0.5,
            key=f"{ticker}_nav",
        )
        starting_cash = st.number_input(
            "Starting cash ($bn)", min_value=0.0,
            value=float(merged["starting_cash"]) / 1e9, step=0.05,
            key=f"{ticker}_cash",
        )
        senior_notes = st.number_input(
            "Senior notes / bonds ($bn)", min_value=0.0,
            value=float(merged["senior_notes"]) / 1e9, step=0.1,
            key=f"{ticker}_notes",
        )
        facility_out = st.number_input(
            "Facility drawn ($bn)", min_value=0.0,
            value=float(merged["senior_credit_outstanding"]) / 1e9, step=0.1,
            key=f"{ticker}_fac_out",
        )
        facility_limit = st.number_input(
            "Facility limit ($bn)", min_value=0.0,
            value=float(merged["senior_credit_limit"]) / 1e9, step=0.1,
            key=f"{ticker}_fac_lim",
        )
        scheduled_repayment_rate = st.slider(
            "Scheduled repayment rate (% of NAV per quarter)",
            0.0, 10.0, float(merged["scheduled_repayment_rate"]) * 100, 0.25,
            key=f"{ticker}_repay",
        ) / 100
        unfunded_commitments = st.number_input(
            "Unfunded commitments ($bn)", min_value=0.0,
            value=float(merged["unfunded_commitments"]) / 1e9, step=0.1,
            key=f"{ticker}_unfunded",
        )
        borrowing_cost_rate = st.slider(
            "Borrowing cost rate (annual %)",
            0.0, 15.0, float(merged.get("borrowing_cost_rate", 0.054)) * 100, 0.1,
            key=f"{ticker}_borrow",
        ) / 100
        management_fee_rate = st.slider(
            "Management fee rate (annual %)",
            0.0, 3.0, float(merged.get("management_fee_rate", 0.010)) * 100, 0.05,
            key=f"{ticker}_mgmt_fee",
        ) / 100
        pik_income_fraction = st.slider(
            "PIK income fraction (%)",
            0.0, 30.0, float(merged.get("pik_income_fraction", 0.03)) * 100, 0.5,
            key=f"{ticker}_pik",
        ) / 100
        min_cash_buffer = st.number_input(
            "Minimum cash buffer ($bn)", min_value=0.0,
            value=float(merged["min_cash_buffer"]) / 1e9, step=0.05,
            key=f"{ticker}_min_cash",
        )
        max_leverage = st.slider(
            "Max leverage (x)", 0.5, 4.0, float(merged["max_leverage"]), 0.05,
            key=f"{ticker}_lev",
        )

    # ── Build configs ─────────────────────────────────────────────────────
    primary_cfg = ScenarioConfig(
        name=preset_name,
        nav_start=nav_start * 1e9,
        senior_notes=senior_notes * 1e9,
        senior_credit_outstanding=facility_out * 1e9,
        senior_credit_limit=facility_limit * 1e9,
        distribution_rate=distribution_rate,
        redemption_rate=redemption_rate,
        subscription_rate=subscription_rate,
        portfolio_yield=portfolio_yield,
        scheduled_repayment_rate=scheduled_repayment_rate,
        annual_default_rate=annual_default_rate,
        loss_given_default=loss_given_default,
        unfunded_commitments=unfunded_commitments * 1e9,
        unfunded_draw_rate=unfunded_draw_rate,
        quarters=int(quarters),
        min_cash_buffer=min_cash_buffer * 1e9,
        starting_cash=starting_cash * 1e9,
        max_leverage=max_leverage,
        borrowing_cost_rate=borrowing_cost_rate,
        management_fee_rate=management_fee_rate,
        other_expense_rate=float(merged.get("other_expense_rate", 0.002)),
        pik_income_fraction=pik_income_fraction,
    )
    primary_cfg.validate()

    baseline_cfg = replace(primary_cfg, name="Base reference", **PRESETS["Base"])
    baseline_cfg.validate()

    primary_df, primary_summary = scenario_outputs(primary_cfg)
    baseline_df, baseline_summary = scenario_outputs(baseline_cfg)
    breakeven_dist_rate = find_breakeven_distribution_rate(primary_cfg)

    compare_cfg = compare_df = compare_summary = None
    if compare_enabled:
        compare_cfg = replace(primary_cfg, name=compare_preset_name,
                              **PRESETS[compare_preset_name])
        compare_cfg.validate()
        compare_df, compare_summary = scenario_outputs(compare_cfg)

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "Scenario Builder", "Liquidity Dashboard", "Narrative & Memo", "Sensitivity",
    ])

    with tab1:
        st.subheader("Active assumptions")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Primary scenario**")
            st.dataframe(assumptions_table(primary_cfg), use_container_width=True,
                         hide_index=True)
        with c2:
            if compare_cfg is not None:
                st.write("**Comparison scenario**")
                st.dataframe(assumptions_table(compare_cfg), use_container_width=True,
                             hide_index=True)
            else:
                st.info("Enable the comparison toggle in the sidebar to view a second scenario.")

    with tab2:
        st.subheader("Primary scenario KPIs")
        baseline_smry = baseline_summary if preset_name != "Base" else None
        metric_cards(primary_summary, baseline_smry)

        if breakeven_dist_rate < primary_cfg.distribution_rate:
            gap_bps = (primary_cfg.distribution_rate - breakeven_dist_rate) * 10_000
            st.warning(
                f"**Distribution sustainability:** Cash NII fully supports a "
                f"**{breakeven_dist_rate * 100:.2f}%** annual distribution rate over this "
                f"horizon — **{gap_bps:.0f} bps below** the current "
                f"**{primary_cfg.distribution_rate * 100:.2f}%** policy rate. "
                f"The gap is funded by portfolio repayments, subscriptions, or facility draws."
            )
        else:
            st.success(
                f"**Distribution sustainability:** Cash NII fully covers the current "
                f"{primary_cfg.distribution_rate * 100:.2f}% distribution rate under this scenario."
            )

        st.info(narrative(primary_summary, primary_cfg, primary_df))
        st.caption(
            "Negative cash = liquidity needs beyond currently modelled facility capacity, "
            "not merely an accounting dip.  NII coverage <1× means distributions are "
            "partially funded from repayments, subscriptions, or facility draws."
        )

        if compare_cfg is not None and compare_df is not None and compare_summary is not None:
            st.subheader(f"Comparison: {compare_preset_name}")
            metric_cards(compare_summary, baseline_summary)
            st.warning(narrative(compare_summary, compare_cfg, compare_df))

        scenarios_for_charts: List[Tuple[str, pd.DataFrame]] = [("Base", baseline_df)]
        if preset_name != "Base":
            scenarios_for_charts.append((preset_name, primary_df))
        if compare_df is not None and compare_cfg is not None:
            scenarios_for_charts.append((compare_preset_name, compare_df))

        col_l, col_r = st.columns(2)
        with col_l:
            st.plotly_chart(
                line_chart(scenarios_for_charts,
                           ["Cash_Bn", "Facility_Out_Bn", "Headroom_Bn"],
                           "Cash, facility usage, and headroom", "$bn"),
                use_container_width=True,
            )
        with col_r:
            st.plotly_chart(
                line_chart(scenarios_for_charts,
                           ["NAV_Bn", "Leverage_x"],
                           "NAV and leverage trajectory", "Level"),
                use_container_width=True,
            )

        col_l2, col_r2 = st.columns(2)
        with col_l2:
            st.plotly_chart(
                line_chart(scenarios_for_charts,
                           ["Subscriptions_Bn", "Redemptions_Bn"],
                           "Investor flows: subscriptions vs. redemptions", "$bn"),
                use_container_width=True,
            )
        with col_r2:
            st.plotly_chart(
                line_chart(scenarios_for_charts,
                           ["NII_Bn", "NII_Cash_Bn", "Distributions_Bn"],
                           "NII (accrual and cash) vs. distributions", "$bn"),
                use_container_width=True,
            )

        st.plotly_chart(waterfall_chart(primary_df), use_container_width=True)
        st.info(biggest_driver_callout(primary_df))

        st.subheader("Detailed primary scenario output")
        st.dataframe(primary_df, use_container_width=True)
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download primary scenario CSV",
                data=rows_to_csv(primary_df),
                file_name=f"{ticker.lower()}_{preset_name.lower().replace(' ', '_')}.csv",
                mime="text/csv",
            )
        with dl2:
            if compare_df is not None and compare_cfg is not None:
                st.download_button(
                    "Download comparison scenario CSV",
                    data=rows_to_csv(compare_df),
                    file_name=f"{ticker.lower()}_{compare_preset_name.lower().replace(' ', '_')}.csv",
                    mime="text/csv",
                )

    with tab3:
        st.subheader("Memo-style readout")
        st.markdown(f"**Primary scenario — {primary_cfg.name}**")
        st.write(narrative(primary_summary, primary_cfg, primary_df))
        st.markdown(
            f"- Starting cash: {primary_cfg.starting_cash / 1e9:.2f}bn\n"
            f"- Facility headroom at start: "
            f"{(primary_cfg.senior_credit_limit - primary_cfg.senior_credit_outstanding) / 1e9:.2f}bn\n"
            f"- First shortfall quarter: {quarter_label(primary_summary['first_liquidity_shortfall_quarter'])}\n"
            f"- First covenant breach quarter: {quarter_label(primary_summary['first_covenant_breach_quarter'])}\n"
            f"- Ending NAV: {primary_summary['ending_nav_bn']:.2f}bn\n"
            f"- Cumulative cash NII: {primary_summary['cumulative_nii_cash_bn']:.2f}bn\n"
            f"- Cumulative distributions: {primary_summary['cumulative_distributions_bn']:.2f}bn\n"
            f"- NII distribution coverage: {float(primary_summary['nii_distribution_coverage']):.2f}×\n"
            f"- Break-even distribution rate: **{breakeven_dist_rate * 100:.2f}%** "
            f"(current policy: {primary_cfg.distribution_rate * 100:.2f}%; "
            f"gap: {(primary_cfg.distribution_rate - breakeven_dist_rate) * 10_000:.0f} bps)"
        )

        if compare_cfg is not None and compare_summary is not None and compare_df is not None:
            st.markdown(f"**Comparison — {compare_cfg.name}**")
            st.write(narrative(compare_summary, compare_cfg, compare_df))

        with st.expander("All assumptions used in this run"):
            st.json({
                "primary":            asdict(primary_cfg),
                "base_reference":     asdict(baseline_cfg),
                "comparison":         asdict(compare_cfg) if compare_cfg is not None else None,
            })

        with st.expander("Methodology and caveats"):
            st.markdown(
                """
                **Model architecture**

                Each quarter: compute gross investment income on total portfolio (NAV + debt),
                deduct interest expense and management fees to derive net investment income (NII),
                apply distributions, redemptions, and subscriptions as explicit cash flows,
                manage the revolving credit facility, then write down NAV for credit losses.

                **Key assumptions and limitations**

                - *portfolio_yield* applies to gross assets (NAV + debt), calibrated to CCLFX
                  FY2025: total investment income $2,992M / gross assets ~$34B ≈ 8.8%.
                  This includes distributions received from private investment vehicles.
                - *PIK income* accretes to NAV but is excluded from cash NII; stressed scenarios
                  should assume higher PIK fractions as borrowers defer cash payments.
                - *Subscriptions / redemptions* are modelled as explicit quarterly flows.
                  Setting subscription_rate = 0 creates a run-off / wind-down stress test.
                - *Asset liquidity* is not explicitly modelled; the fund is assumed to be able
                  to honour redemptions at NAV without secondary-market haircuts.
                - *Reinvestment* is assumed: repayments and subscription proceeds are redeployed
                  at the same portfolio yield within the quarter.
                - *Distribution rate* is assumed constant; real boards may cut in stress.
                - *Interest rate sensitivity* is not linked to SOFR; yield and cost are static
                  scenario parameters.
                - This dashboard is a scenario engine, not a precise forecast.
                """
            )

    with tab4:
        st.subheader("Redemption rate / default rate sensitivity heatmap")
        st.caption(
            "Scores show the quarter in which liquidity first becomes constrained. "
            "Scores equal to (quarters + 1) indicate no shortfall within the horizon. "
            "Higher scores = more resilient."
        )
        sensitivity_df = build_sensitivity_grid(primary_cfg)
        heatmap = sensitivity_df.pivot(
            index="Default rate", columns="Redemption rate", values="Shortfall score"
        )
        fig = px.imshow(
            heatmap,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="RdYlGn",
            origin="lower",
            labels={"color": "Shortfall score"},
            title="Shortfall quarter score by redemption rate and default rate",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            sensitivity_df[["Redemption rate", "Default rate", "First shortfall"]],
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("Investor flow sensitivity: subscription rate × redemption rate")
        st.caption(
            "All other assumptions held at primary scenario values. "
            "Left heatmap: shortfall score (higher = more resilient; max = quarters + 1 = no shortfall). "
            "Right heatmap: NII distribution coverage ratio (cash NII ÷ distributions; "
            "<1.0× means distributions partially funded from repayments/subscriptions/facility)."
        )

        flow_df = build_flow_sensitivity_grid(primary_cfg)

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            shortfall_pivot = flow_df.pivot(
                index="Subscription rate", columns="Redemption rate", values="Shortfall score"
            )
            fig_shortfall = px.imshow(
                shortfall_pivot,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="RdYlGn",
                origin="lower",
                labels={"color": "Shortfall score"},
                title="Shortfall score (subscription × redemption)",
            )
            st.plotly_chart(fig_shortfall, use_container_width=True)

        with col_h2:
            coverage_pivot = flow_df.pivot(
                index="Subscription rate", columns="Redemption rate", values="NII coverage"
            )
            fig_coverage = px.imshow(
                coverage_pivot,
                text_auto=".2f",
                aspect="auto",
                color_continuous_scale="RdYlGn",
                origin="lower",
                zmin=0.5,
                zmax=1.5,
                labels={"color": "NII coverage (×)"},
                title="NII distribution coverage (subscription × redemption)",
            )
            fig_coverage.add_shape(
                type="line",
                x0=-0.5, x1=len(shortfall_pivot.columns) - 0.5,
                y0=-0.5, y1=len(shortfall_pivot.index) - 0.5,
                line=dict(color="black", width=1, dash="dot"),
            )
            st.plotly_chart(fig_coverage, use_container_width=True)

        st.dataframe(
            flow_df[["Subscription rate", "Redemption rate", "NII coverage"]],
            use_container_width=True, hide_index=True,
        )


if __name__ == "__main__":
    render()
