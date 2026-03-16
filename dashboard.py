#!/usr/bin/env python3
"""Streamlit dashboard for CCLF liquidity scenarios."""
from __future__ import annotations

from dataclasses import replace
from io import StringIO
from typing import Dict

import pandas as pd
import streamlit as st

from cclf_liquidity_model import ScenarioConfig, run_scenario, summarize

st.set_page_config(page_title="CCLF Liquidity Dashboard", layout="wide")

PRESETS: Dict[str, Dict[str, float]] = {
    "Base": {},
    "Mild stress": {
        "tender_rate": 0.075,
        "annual_default_rate": 0.04,
        "loss_given_default": 0.45,
        "unfunded_draw_rate": 0.12,
        "portfolio_yield": 0.115,
    },
    "Severe stress": {
        "tender_rate": 0.12,
        "annual_default_rate": 0.08,
        "loss_given_default": 0.55,
        "unfunded_draw_rate": 0.18,
        "portfolio_yield": 0.105,
    },
    "Distribution cut": {
        "distribution_rate": 0.06,
        "tender_rate": 0.08,
        "annual_default_rate": 0.04,
        "loss_given_default": 0.45,
    },
    "Funding squeeze": {
        "tender_rate": 0.09,
        "unfunded_draw_rate": 0.20,
        "scheduled_repayment_rate": 0.02,
        "starting_cash": 0.25e9,
    },
}


def bn(value: float) -> str:
    return f"{value:,.2f}bn"


def quarter_label(value: int | str) -> str:
    return str(value) if isinstance(value, str) else f"Q{value}"


def rows_to_csv(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def build_config(name: str, overrides: Dict[str, float]) -> ScenarioConfig:
    return ScenarioConfig.from_dict({"name": name, **overrides})


def narrative(summary: Dict[str, float | str], cfg: ScenarioConfig) -> str:
    if summary["first_liquidity_shortfall_quarter"] != "none":
        return (
            f"This setup appears liquidity-constrained quickly: cash falls below the target buffer by "
            f"{quarter_label(summary['first_liquidity_shortfall_quarter'])}, while minimum headroom compresses to "
            f"{summary['min_headroom_bn']:.2f}bn. Tender pressure ({cfg.tender_rate:.1%} per quarter) and unfunded draws "
            f"({cfg.unfunded_draw_rate:.1%} of remaining commitments per quarter) are the main stress drivers."
        )
    if summary["first_covenant_breach_quarter"] != "none":
        return (
            f"Liquidity holds, but leverage becomes the binding constraint by "
            f"{quarter_label(summary['first_covenant_breach_quarter'])}. Peak leverage reaches {summary['peak_leverage_x']:.2f}x, "
            f"so financing flexibility is the key risk rather than immediate cash depletion."
        )
    return (
        f"Under this scenario, the fund remains above its liquidity floor through the modeled horizon. Ending NAV is "
        f"{summary['ending_nav_bn']:.2f}bn and minimum facility headroom remains {summary['min_headroom_bn']:.2f}bn. "
        f"This looks manageable on a stylized basis, though results remain highly sensitive to tender, repayment, and loss assumptions."
    )


def metric_row(title: str, summary: Dict[str, float | str]) -> None:
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Min cash", bn(float(summary["min_cash_bn"])))
    c2.metric("Ending NAV", bn(float(summary["ending_nav_bn"])))
    c3.metric("Max facility", bn(float(summary["max_facility_utilization_bn"])))
    c4.metric("Min headroom", bn(float(summary["min_headroom_bn"])))
    c5.metric("Peak leverage", f"{float(summary['peak_leverage_x']):.2f}x")
    c6.metric("First shortfall", quarter_label(summary["first_liquidity_shortfall_quarter"]))
    st.caption(title)


def render() -> None:
    st.title("CCLF Liquidity Scenario Dashboard")
    st.write(
        "Interactive scenario tool for exploring Cliffwater Corporate Lending Fund liquidity, leverage, and cash-flow sensitivity. "
        "This is a portfolio-level analytical model, not a loan-by-loan forecast."
    )

    st.sidebar.header("Scenario controls")
    preset_name = st.sidebar.selectbox("Primary preset", list(PRESETS.keys()), index=0)
    compare_enabled = st.sidebar.checkbox("Compare against second scenario", value=True)
    compare_preset_name = st.sidebar.selectbox("Comparison preset", list(PRESETS.keys()), index=2, disabled=not compare_enabled)

    base_cfg = build_config("Primary", PRESETS[preset_name])

    st.sidebar.subheader("Core assumptions")
    nav_start = st.sidebar.number_input("Starting NAV ($bn)", min_value=1.0, value=base_cfg.nav_start / 1e9, step=0.5)
    starting_cash = st.sidebar.number_input("Starting cash ($bn)", min_value=0.0, value=base_cfg.starting_cash / 1e9, step=0.1)
    senior_notes = st.sidebar.number_input("Senior notes ($bn)", min_value=0.0, value=base_cfg.senior_notes / 1e9, step=0.1)
    facility_out = st.sidebar.number_input("Facility drawn ($bn)", min_value=0.0, value=base_cfg.senior_credit_outstanding / 1e9, step=0.1)
    facility_limit = st.sidebar.number_input("Facility limit ($bn)", min_value=0.0, value=base_cfg.senior_credit_limit / 1e9, step=0.1)
    unfunded_commitments = st.sidebar.number_input("Unfunded commitments ($bn)", min_value=0.0, value=base_cfg.unfunded_commitments / 1e9, step=0.1)
    quarters = st.sidebar.slider("Projection horizon (quarters)", min_value=4, max_value=16, value=base_cfg.quarters)

    st.sidebar.subheader("Behavioral / stress assumptions")
    portfolio_yield = st.sidebar.slider("Portfolio yield (annual %)", min_value=0.0, max_value=20.0, value=base_cfg.portfolio_yield * 100, step=0.25) / 100
    distribution_rate = st.sidebar.slider("Distribution rate (annual %)", min_value=0.0, max_value=20.0, value=base_cfg.distribution_rate * 100, step=0.25) / 100
    tender_rate = st.sidebar.slider("Tender rate (quarterly % of NAV)", min_value=0.0, max_value=20.0, value=base_cfg.tender_rate * 100, step=0.25) / 100
    scheduled_repayment_rate = st.sidebar.slider("Scheduled repayment rate (quarterly % of NAV)", min_value=0.0, max_value=10.0, value=base_cfg.scheduled_repayment_rate * 100, step=0.25) / 100
    annual_default_rate = st.sidebar.slider("Annual default rate (%)", min_value=0.0, max_value=20.0, value=base_cfg.annual_default_rate * 100, step=0.25) / 100
    loss_given_default = st.sidebar.slider("Loss given default (%)", min_value=0.0, max_value=100.0, value=base_cfg.loss_given_default * 100, step=1.0) / 100
    unfunded_draw_rate = st.sidebar.slider("Unfunded draw rate (quarterly % of remaining)", min_value=0.0, max_value=50.0, value=base_cfg.unfunded_draw_rate * 100, step=1.0) / 100
    min_cash_buffer = st.sidebar.number_input("Minimum cash buffer ($bn)", min_value=0.0, value=base_cfg.min_cash_buffer / 1e9, step=0.1)
    max_leverage = st.sidebar.slider("Max leverage (x)", min_value=0.5, max_value=4.0, value=base_cfg.max_leverage, step=0.05)

    primary_cfg = ScenarioConfig(
        name=preset_name,
        nav_start=nav_start * 1e9,
        senior_notes=senior_notes * 1e9,
        senior_credit_outstanding=facility_out * 1e9,
        senior_credit_limit=facility_limit * 1e9,
        distribution_rate=distribution_rate,
        tender_rate=tender_rate,
        portfolio_yield=portfolio_yield,
        scheduled_repayment_rate=scheduled_repayment_rate,
        annual_default_rate=annual_default_rate,
        loss_given_default=loss_given_default,
        unfunded_commitments=unfunded_commitments * 1e9,
        unfunded_draw_rate=unfunded_draw_rate,
        quarters=quarters,
        min_cash_buffer=min_cash_buffer * 1e9,
        starting_cash=starting_cash * 1e9,
        max_leverage=max_leverage,
    )
    primary_cfg.validate()

    primary_df = pd.DataFrame(run_scenario(primary_cfg))
    primary_summary = summarize(primary_df.to_dict(orient="records"))

    compare_df = None
    compare_summary = None
    compare_cfg = None
    if compare_enabled:
        compare_cfg = replace(primary_cfg, name=compare_preset_name, **PRESETS[compare_preset_name])
        compare_cfg.validate()
        compare_df = pd.DataFrame(run_scenario(compare_cfg))
        compare_summary = summarize(compare_df.to_dict(orient="records"))

    st.subheader("Scenario summary")
    metric_row(f"Primary scenario: {primary_cfg.name}", primary_summary)
    st.info(narrative(primary_summary, primary_cfg))

    if compare_enabled and compare_df is not None and compare_summary is not None and compare_cfg is not None:
        metric_row(f"Comparison scenario: {compare_cfg.name}", compare_summary)
        st.warning(narrative(compare_summary, compare_cfg))

    st.subheader("Liquidity and leverage paths")
    left, right = st.columns(2)
    with left:
        liquidity_chart = primary_df[["Quarter", "Cash_Bn", "Headroom_Bn", "Facility_Out_Bn"]].set_index("Quarter")
        if compare_df is not None:
            liquidity_chart = liquidity_chart.rename(columns={
                "Cash_Bn": f"Cash - {primary_cfg.name}",
                "Headroom_Bn": f"Headroom - {primary_cfg.name}",
                "Facility_Out_Bn": f"Facility - {primary_cfg.name}",
            })
            comp_liq = compare_df[["Quarter", "Cash_Bn", "Headroom_Bn", "Facility_Out_Bn"]].set_index("Quarter").rename(columns={
                "Cash_Bn": f"Cash - {compare_cfg.name}",
                "Headroom_Bn": f"Headroom - {compare_cfg.name}",
                "Facility_Out_Bn": f"Facility - {compare_cfg.name}",
            })
            liquidity_chart = liquidity_chart.join(comp_liq, how="outer")
        st.line_chart(liquidity_chart)
    with right:
        leverage_chart = primary_df[["Quarter", "NAV_Bn", "Leverage_x"]].set_index("Quarter").rename(columns={
            "NAV_Bn": f"NAV - {primary_cfg.name}",
            "Leverage_x": f"Leverage - {primary_cfg.name}",
        })
        if compare_df is not None:
            comp_lev = compare_df[["Quarter", "NAV_Bn", "Leverage_x"]].set_index("Quarter").rename(columns={
                "NAV_Bn": f"NAV - {compare_cfg.name}",
                "Leverage_x": f"Leverage - {compare_cfg.name}",
            })
            leverage_chart = leverage_chart.join(comp_lev, how="outer")
        st.line_chart(leverage_chart)

    st.subheader("Cash-flow drivers")
    drivers = primary_df[[
        "Quarter",
        "NII_Bn",
        "Scheduled_Repayments_Bn",
        "Distributions_Bn",
        "Tender_Outflow_Bn",
        "Credit_Losses_Bn",
        "Unfunded_Draw_Bn",
        "Net_Cash_Change_Bn",
    ]].set_index("Quarter")
    st.bar_chart(drivers)

    st.subheader("Detailed scenario table")
    st.dataframe(primary_df, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="Download primary scenario CSV",
            data=rows_to_csv(primary_df),
            file_name=f"{primary_cfg.name.lower().replace(' ', '_')}_scenario.csv",
            mime="text/csv",
        )
    with c2:
        if compare_df is not None and compare_cfg is not None:
            st.download_button(
                label="Download comparison scenario CSV",
                data=rows_to_csv(compare_df),
                file_name=f"{compare_cfg.name.lower().replace(' ', '_')}_scenario.csv",
                mime="text/csv",
            )

    with st.expander("Methodology and caveats"):
        st.markdown(
            """
            - This dashboard is a scenario engine, not a precise forecast.
            - Asset liquidity is approximated at a portfolio level using repayment and draw assumptions.
            - Tender activity, repayment pace, default severity, and distribution policy are the dominant sensitivities.
            - Financing terms and asset-cash-flow behavior should be tightened further as more source disclosures are structured.
            """
        )


if __name__ == "__main__":
    render()
