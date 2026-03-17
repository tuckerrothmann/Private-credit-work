#!/usr/bin/env python3
"""Streamlit dashboard for CCLF liquidity scenarios."""
from __future__ import annotations

from dataclasses import asdict, replace
from io import StringIO
from typing import Dict, Iterable, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    "Net inflows": {
        "net_subscription_rate": 0.01,
        "tender_rate": 0.04,
        "annual_default_rate": 0.02,
    },
}

SENSITIVITY_TENDERS = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15]
SENSITIVITY_DEFAULTS = [0.01, 0.02, 0.04, 0.06, 0.08, 0.10]


def bn(value: float) -> str:
    return f"{value:,.2f}bn"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def quarter_label(value: int | str) -> str:
    return str(value) if isinstance(value, str) else f"Q{value}"


def rows_to_csv(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def build_config(name: str, overrides: Dict[str, float]) -> ScenarioConfig:
    return ScenarioConfig.from_dict({"name": name, **overrides})


def scenario_outputs(cfg: ScenarioConfig) -> tuple[pd.DataFrame, Dict[str, float | str]]:
    df = pd.DataFrame(run_scenario(cfg))
    summary = summarize(df.to_dict(orient="records"))
    return df, summary


def narrative(summary: Dict[str, float | str], cfg: ScenarioConfig, df: pd.DataFrame) -> str:
    total_tenders = df["Tender_Outflow_Bn"].sum()
    total_distributions = df["Distributions_Bn"].sum()
    total_losses = df["Credit_Losses_Bn"].sum()
    total_unfunded = df["Unfunded_Draw_Bn"].sum()
    total_subscriptions = df["Subscription_Inflow_Bn"].sum()
    dominant = max(
        [
            ("tender activity", total_tenders),
            ("distribution outflows", total_distributions),
            ("credit losses", total_losses),
            ("unfunded commitment draws", total_unfunded),
            ("net subscriptions", total_subscriptions),
        ],
        key=lambda item: abs(item[1]),
    )[0]

    if summary["first_liquidity_shortfall_quarter"] != "none":
        return (
            f"Under the {cfg.name} scenario, liquidity becomes constrained by "
            f"{quarter_label(summary['first_liquidity_shortfall_quarter'])}. Starting cash of {cfg.starting_cash / 1e9:.2f}bn and "
            f"facility headroom of {(cfg.senior_credit_limit - cfg.senior_credit_outstanding) / 1e9:.2f}bn are not sufficient to offset "
            f"combined pressures from tenders, distributions, credit losses, and unfunded draws. Minimum cash reaches "
            f"{summary['min_cash_bn']:.2f}bn and minimum headroom compresses to {summary['min_headroom_bn']:.2f}bn. The dominant stress driver in this run is {dominant}."
        )
    if summary["first_covenant_breach_quarter"] != "none":
        return (
            f"The {cfg.name} scenario avoids an immediate liquidity shortfall, but leverage becomes the key constraint by "
            f"{quarter_label(summary['first_covenant_breach_quarter'])}. Peak leverage reaches {summary['peak_leverage_x']:.2f}x against a "
            f"{cfg.max_leverage:.2f}x ceiling. That suggests financing flexibility, rather than pure cash depletion, is the main risk to monitor."
        )
    return (
        f"The {cfg.name} scenario remains above the modeled liquidity floor throughout the forecast horizon. Ending NAV is "
        f"{summary['ending_nav_bn']:.2f}bn, ending cash is {summary['ending_cash_bn']:.2f}bn, and peak leverage reaches {summary['peak_leverage_x']:.2f}x. "
        f"Results still depend heavily on tender assumptions ({pct(cfg.tender_rate)} quarterly), repayment pace ({pct(cfg.scheduled_repayment_rate)} quarterly), subscription support ({pct(cfg.net_subscription_rate)} quarterly), and default severity ({pct(cfg.loss_given_default)} LGD)."
    )


def biggest_driver_callout(df: pd.DataFrame) -> str:
    totals = {
        "Tender outflows": df["Tender_Outflow_Bn"].sum(),
        "Distributions": df["Distributions_Bn"].sum(),
        "Credit losses": df["Credit_Losses_Bn"].sum(),
        "Unfunded draws": df["Unfunded_Draw_Bn"].sum(),
    }
    label, value = max(totals.items(), key=lambda item: item[1])
    return f"Largest cumulative cash drain over the projection horizon: {label} at {value:.2f}bn."


def metric_cards(summary: Dict[str, float | str], baseline_summary: Dict[str, float | str] | None = None) -> None:
    col1, col2, col3, col4, col5 = st.columns(5)

    def delta(key: str) -> float | None:
        if baseline_summary is None:
            return None
        base = baseline_summary[key]
        cur = summary[key]
        if isinstance(base, str) or isinstance(cur, str):
            return None
        return float(cur) - float(base)

    min_cash_delta = delta("min_cash_bn")
    headroom_delta = delta("min_headroom_bn")
    leverage_delta = delta("peak_leverage_x")

    col1.metric("First shortfall", quarter_label(summary["first_liquidity_shortfall_quarter"]))
    col2.metric("Min cash", bn(float(summary["min_cash_bn"])), None if min_cash_delta is None else f"{min_cash_delta:+.2f}bn vs base")
    col3.metric("Max facility", bn(float(summary["max_facility_utilization_bn"])))
    col4.metric("Min headroom", bn(float(summary["min_headroom_bn"])), None if headroom_delta is None else f"{headroom_delta:+.2f}bn vs base")
    col5.metric("Peak leverage", f"{float(summary['peak_leverage_x']):.2f}x", None if leverage_delta is None else f"{leverage_delta:+.2f}x vs base")


def line_chart(scenarios: List[tuple[str, pd.DataFrame]], value_columns: List[str], title: str, y_title: str) -> go.Figure:
    fig = go.Figure()
    palette = ["#9CA3AF", "#2563EB", "#DC2626", "#059669"]
    for idx, (name, df) in enumerate(scenarios):
        color = palette[idx % len(palette)]
        for column in value_columns:
            fig.add_trace(
                go.Scatter(
                    x=df["Quarter"],
                    y=df[column],
                    mode="lines",
                    name=f"{column.replace('_Bn', '').replace('_x', '')} - {name}",
                    line=dict(color=color, dash="solid" if idx == 0 else "dash" if idx == 1 else "dot"),
                )
            )
    fig.update_layout(title=title, xaxis_title="Quarter", yaxis_title=y_title, legend_title="Series", height=420)
    return fig


def waterfall_chart(df: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    for column, color in [
        ("Tender_Outflow_Bn", "#DC2626"),
        ("Distributions_Bn", "#F59E0B"),
        ("Credit_Losses_Bn", "#7C3AED"),
        ("Unfunded_Draw_Bn", "#2563EB"),
        ("Scheduled_Repayments_Bn", "#059669"),
        ("Subscription_Inflow_Bn", "#14B8A6"),
        ("NII_Bn", "#10B981"),
    ]:
        figure.add_trace(go.Bar(x=df["Quarter"], y=df[column], name=column.replace("_Bn", ""), marker_color=color))
    figure.update_layout(barmode="relative", title="Quarterly cash-flow drivers", xaxis_title="Quarter", yaxis_title="$bn", height=420)
    return figure


def assumptions_table(cfg: ScenarioConfig) -> pd.DataFrame:
    payload = asdict(cfg)
    rows = []
    for key, value in payload.items():
        pretty_key = key.replace("_", " ").title()
        if key in {"nav_start", "senior_notes", "senior_credit_outstanding", "senior_credit_limit", "unfunded_commitments", "starting_cash", "min_cash_buffer"}:
            pretty_value = f"{value / 1e9:.2f}bn"
        elif key.endswith("rate") or key == "loss_given_default":
            pretty_value = pct(value)
        else:
            pretty_value = value
        rows.append({"Assumption": pretty_key, "Value": pretty_value})
    return pd.DataFrame(rows)


def build_sensitivity_grid(cfg: ScenarioConfig) -> pd.DataFrame:
    rows = []
    for tender_rate in SENSITIVITY_TENDERS:
        for default_rate in SENSITIVITY_DEFAULTS:
            test_cfg = replace(cfg, tender_rate=tender_rate, annual_default_rate=default_rate)
            _, summary = scenario_outputs(test_cfg)
            shortfall = summary["first_liquidity_shortfall_quarter"]
            score = cfg.quarters + 1 if shortfall == "none" else int(shortfall)
            rows.append(
                {
                    "Tender rate": f"{tender_rate * 100:.0f}%",
                    "Default rate": f"{default_rate * 100:.0f}%",
                    "Shortfall quarter score": score,
                    "First shortfall": "No shortfall" if shortfall == "none" else f"Q{shortfall}",
                }
            )
    return pd.DataFrame(rows)


def render() -> None:
    st.title("CCLF Liquidity Scenario Dashboard")
    st.write(
        "Interactive scenario tool for exploring Cliffwater Corporate Lending Fund liquidity, leverage, and cash-flow sensitivity. "
        "Negative cash implies liquidity needs beyond currently modeled facility capacity."
    )

    st.sidebar.header("Scenario Builder")
    preset_name = st.sidebar.selectbox("Primary preset", list(PRESETS.keys()), index=0)
    compare_enabled = st.sidebar.checkbox("Enable comparison scenario", value=True)
    compare_preset_name = st.sidebar.selectbox("Comparison preset", list(PRESETS.keys()), index=2, disabled=not compare_enabled)

    base_cfg = build_config(preset_name, PRESETS[preset_name])

    st.sidebar.subheader("Core exposed assumptions")
    quarters = st.sidebar.select_slider("Forecast horizon (quarters)", options=[4, 6, 8, 12, 16], value=base_cfg.quarters)
    tender_rate = st.sidebar.slider("Tender rate (% of NAV per quarter)", 0.0, 20.0, base_cfg.tender_rate * 100, 0.25) / 100
    annual_default_rate = st.sidebar.slider("Annual default rate (%)", 0.0, 15.0, base_cfg.annual_default_rate * 100, 0.25) / 100
    loss_given_default = st.sidebar.slider("Loss given default (%)", 0.0, 80.0, base_cfg.loss_given_default * 100, 1.0) / 100
    unfunded_draw_rate = st.sidebar.slider("Unfunded draw rate (% of remaining per quarter)", 0.0, 30.0, base_cfg.unfunded_draw_rate * 100, 1.0) / 100
    portfolio_yield = st.sidebar.slider("Portfolio yield (annual %)", 8.0, 18.0, base_cfg.portfolio_yield * 100, 0.25) / 100
    distribution_rate = st.sidebar.slider("Distribution rate (annual %)", 0.0, 15.0, base_cfg.distribution_rate * 100, 0.25) / 100
    net_subscription_rate = st.sidebar.slider("Net subscription inflow (% of NAV per quarter)", -2.0, 3.0, base_cfg.net_subscription_rate * 100, 0.25) / 100

    with st.sidebar.expander("Advanced assumptions"):
        nav_start = st.number_input("Starting NAV ($bn)", min_value=1.0, value=base_cfg.nav_start / 1e9, step=0.5)
        starting_cash = st.number_input("Starting cash ($bn)", min_value=0.0, value=base_cfg.starting_cash / 1e9, step=0.1)
        senior_notes = st.number_input("Senior notes ($bn)", min_value=0.0, value=base_cfg.senior_notes / 1e9, step=0.1)
        facility_out = st.number_input("Facility drawn ($bn)", min_value=0.0, value=base_cfg.senior_credit_outstanding / 1e9, step=0.1)
        facility_limit = st.number_input("Facility limit ($bn)", min_value=0.0, value=base_cfg.senior_credit_limit / 1e9, step=0.1)
        scheduled_repayment_rate = st.slider("Scheduled repayment rate (% of NAV per quarter)", 0.0, 10.0, base_cfg.scheduled_repayment_rate * 100, 0.25) / 100
        unfunded_commitments = st.number_input("Unfunded commitments ($bn)", min_value=0.0, value=base_cfg.unfunded_commitments / 1e9, step=0.1)
        min_cash_buffer = st.number_input("Minimum cash buffer ($bn)", min_value=0.0, value=base_cfg.min_cash_buffer / 1e9, step=0.1)
        max_leverage = st.slider("Max leverage (x)", 0.5, 4.0, base_cfg.max_leverage, 0.05)

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
        net_subscription_rate=net_subscription_rate,
        quarters=int(quarters),
        min_cash_buffer=min_cash_buffer * 1e9,
        starting_cash=starting_cash * 1e9,
        max_leverage=max_leverage,
    )
    primary_cfg.validate()

    baseline_cfg = replace(primary_cfg, name="Base reference", **PRESETS["Base"])
    baseline_cfg.validate()

    primary_df, primary_summary = scenario_outputs(primary_cfg)
    baseline_df, baseline_summary = scenario_outputs(baseline_cfg)

    compare_df = None
    compare_summary = None
    compare_cfg = None
    if compare_enabled:
        compare_cfg = replace(primary_cfg, name=compare_preset_name, **PRESETS[compare_preset_name])
        compare_cfg.validate()
        compare_df, compare_summary = scenario_outputs(compare_cfg)

    tab1, tab2, tab3, tab4 = st.tabs(["Scenario Builder", "Liquidity Dashboard", "Narrative Summary", "Sensitivity"])

    with tab1:
        st.subheader("Active assumptions")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Primary scenario**")
            st.dataframe(assumptions_table(primary_cfg), use_container_width=True, hide_index=True)
        with c2:
            if compare_cfg is not None:
                st.write("**Comparison scenario**")
                st.dataframe(assumptions_table(compare_cfg), use_container_width=True, hide_index=True)
            else:
                st.info("Enable the comparison toggle in the sidebar to view a second scenario.")
        st.caption("Advanced assumptions are intentionally tucked away to keep the main experience clean while preserving analyst-level control.")

    with tab2:
        st.subheader("Primary scenario KPIs")
        metric_cards(primary_summary, baseline_summary if primary_cfg.name != "Base" else None)
        st.info(narrative(primary_summary, primary_cfg, primary_df))
        st.caption("Note: negative cash indicates liquidity needs beyond currently modeled facility capacity, not just an accounting dip.")

        if compare_cfg is not None and compare_df is not None and compare_summary is not None:
            st.subheader("Comparison scenario KPIs")
            metric_cards(compare_summary, baseline_summary)
            st.warning(narrative(compare_summary, compare_cfg, compare_df))

        scenarios = [("Base", baseline_df)]
        if primary_cfg.name != "Base":
            scenarios.append((primary_cfg.name, primary_df))
        if compare_cfg is not None and compare_df is not None:
            scenarios.append((compare_cfg.name, compare_df))

        col_left, col_right = st.columns(2)
        with col_left:
            st.plotly_chart(
                line_chart(scenarios, ["Cash_Bn", "Facility_Out_Bn", "Headroom_Bn"], "Cash, facility usage, and headroom", "$bn"),
                use_container_width=True,
            )
        with col_right:
            st.plotly_chart(
                line_chart(scenarios, ["NAV_Bn", "Leverage_x"], "NAV and leverage trajectory", "Level"),
                use_container_width=True,
            )

        st.plotly_chart(waterfall_chart(primary_df), use_container_width=True)
        st.info(biggest_driver_callout(primary_df))

        st.subheader("Detailed primary scenario output")
        st.dataframe(primary_df, use_container_width=True)
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                label="Download primary scenario CSV",
                data=rows_to_csv(primary_df),
                file_name=f"{primary_cfg.name.lower().replace(' ', '_')}_scenario.csv",
                mime="text/csv",
            )
        with dl2:
            if compare_df is not None and compare_cfg is not None:
                st.download_button(
                    label="Download comparison scenario CSV",
                    data=rows_to_csv(compare_df),
                    file_name=f"{compare_cfg.name.lower().replace(' ', '_')}_scenario.csv",
                    mime="text/csv",
                )

    with tab3:
        st.subheader("Memo-style readout")
        st.markdown(f"**Primary scenario — {primary_cfg.name}**")
        st.write(narrative(primary_summary, primary_cfg, primary_df))
        st.markdown(
            f"- Starting cash: {primary_cfg.starting_cash / 1e9:.2f}bn\n"
            f"- Starting facility headroom: {(primary_cfg.senior_credit_limit - primary_cfg.senior_credit_outstanding) / 1e9:.2f}bn\n"
            f"- First shortfall quarter: {quarter_label(primary_summary['first_liquidity_shortfall_quarter'])}\n"
            f"- First covenant breach quarter: {quarter_label(primary_summary['first_covenant_breach_quarter'])}\n"
            f"- Ending NAV: {primary_summary['ending_nav_bn']:.2f}bn"
        )
        if compare_cfg is not None and compare_summary is not None and compare_df is not None:
            st.markdown(f"**Comparison scenario — {compare_cfg.name}**")
            st.write(narrative(compare_summary, compare_cfg, compare_df))

        with st.expander("See all assumptions used in this run"):
            st.json({
                "primary": asdict(primary_cfg),
                "baseline_reference": asdict(baseline_cfg),
                "comparison": asdict(compare_cfg) if compare_cfg is not None else None,
            })

        with st.expander("Methodology and caveats"):
            st.markdown(
                """
                - This dashboard is a scenario engine, not a precise forecast.
                - Asset liquidity is approximated at a portfolio level using repayment and draw assumptions.
                - Tender activity, repayment pace, default severity, and distribution policy are the dominant sensitivities.
                - Financing terms and asset-cash-flow behavior should be tightened further as more source disclosures are structured.
                """
            )

    with tab4:
        st.subheader("Tender/default sensitivity heatmap")
        sensitivity_df = build_sensitivity_grid(primary_cfg)
        heatmap = sensitivity_df.pivot(index="Default rate", columns="Tender rate", values="Shortfall quarter score")
        fig = px.imshow(
            heatmap,
            text_auto=True,
            aspect="auto",
            color_continuous_scale="RdYlGn",
            origin="lower",
            labels={"color": "Shortfall score"},
            title="Higher scores are better; no shortfall is scored beyond the modeled horizon",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(sensitivity_df[["Tender rate", "Default rate", "First shortfall"]], use_container_width=True, hide_index=True)


if __name__ == "__main__":
    render()
