#!/usr/bin/env python3
"""CCLF Liquidity Scenario Model

This script projects 8 quarters of Cliffwater Corporate Lending Fund (CCLF)
liquidity activity under configurable scenarios that link tender program
obligations, credit losses, and borrowing headroom.

Dependencies: Python 3 standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import csv
from math import inf


@dataclass
class ScenarioConfig:
    name: str
    nav_start: float = 31.5e9  # USD
    senior_notes: float = 5.65e9
    senior_credit_outstanding: float = 1.19e9
    senior_credit_limit: float = 2.5e9
    distribution_rate: float = 0.1075  # annual
    tender_rate: float = 0.05  # percent of NAV repurchased per quarter
    portfolio_yield: float = 0.12  # annual gross investment yield
    scheduled_repayment_rate: float = 0.03  # percent of NAV turning to cash per quarter
    annual_default_rate: float = 0.02
    loss_given_default: float = 0.4
    unfunded_commitments: float = 4.0e9
    unfunded_draw_rate: float = 0.1  # percent of remaining unfunded commitments per quarter
    quarters: int = 8
    min_cash_buffer: float = 0.0
    starting_cash: float = 0.5e9
    max_leverage: float = 2.0  # Debt / NAV ceiling


def quarterly_rate(annual_rate: float) -> float:
    return 1 - (1 - annual_rate) ** 0.25


def run_scenario(cfg: ScenarioConfig) -> List[Dict[str, float | bool | int]]:
    rows: List[Dict[str, float | bool | int]] = []
    cash = cfg.starting_cash
    nav = cfg.nav_start
    facility = cfg.senior_credit_outstanding
    facility_limit = cfg.senior_credit_limit
    senior_notes = cfg.senior_notes
    unfunded_remaining = cfg.unfunded_commitments
    q_default_rate = quarterly_rate(cfg.annual_default_rate)
    q_yield = cfg.portfolio_yield / 4
    q_distribution_rate = cfg.distribution_rate / 4

    for q in range(1, cfg.quarters + 1):
        nii = nav * q_yield
        distributions = nav * q_distribution_rate
        tender = nav * cfg.tender_rate
        credit_losses = nav * q_default_rate * cfg.loss_given_default
        scheduled_repayments = nav * cfg.scheduled_repayment_rate
        unfunded_draw = min(unfunded_remaining, unfunded_remaining * cfg.unfunded_draw_rate)
        unfunded_remaining -= unfunded_draw

        cash_sources = nii + scheduled_repayments
        cash_uses = distributions + tender + credit_losses + unfunded_draw
        net_cash = cash_sources - cash_uses

        cash += net_cash

        liquidity_shortfall = False
        facility_draw = 0.0
        facility_repay = 0.0

        if cash < cfg.min_cash_buffer:
            needed = cfg.min_cash_buffer - cash
            available = max(0.0, facility_limit - facility)
            facility_draw = min(needed, available)
            facility += facility_draw
            cash += facility_draw
            if cash < cfg.min_cash_buffer - 1e-6:
                liquidity_shortfall = True

        if cash > cfg.min_cash_buffer and facility > 0:
            excess = cash - cfg.min_cash_buffer
            facility_repay = min(excess, facility)
            facility -= facility_repay
            cash -= facility_repay

        nav = nav + nii - distributions - tender - credit_losses
        total_debt = facility + senior_notes
        leverage = total_debt / nav if nav > 0 else inf
        covenant_breach = leverage > cfg.max_leverage

        rows.append(
            {
                "Quarter": q,
                "NAV_Bn": nav / 1e9,
                "Cash_Bn": cash / 1e9,
                "Facility_Out_Bn": facility / 1e9,
                "Facility_Draw_Bn": facility_draw / 1e9,
                "Facility_Repay_Bn": facility_repay / 1e9,
                "Headroom_Bn": (facility_limit - facility) / 1e9,
                "Tender_Outflow_Bn": tender / 1e9,
                "Distributions_Bn": distributions / 1e9,
                "Credit_Losses_Bn": credit_losses / 1e9,
                "Unfunded_Draw_Bn": unfunded_draw / 1e9,
                "Liquidity_Shortfall": liquidity_shortfall,
                "Covenant_Breach": covenant_breach,
                "Leverage_x": leverage,
            }
        )

    return rows


def summarize(rows: List[Dict[str, float | bool | int]]) -> Dict[str, float | str]:
    min_cash = min(r["Cash_Bn"] for r in rows)
    max_facility = max(r["Facility_Out_Bn"] for r in rows)
    min_headroom = min(r["Headroom_Bn"] for r in rows)
    first_shortfall = next((r["Quarter"] for r in rows if r["Liquidity_Shortfall"]), "none")
    first_breach = next((r["Quarter"] for r in rows if r["Covenant_Breach"]), "none")
    return {
        "min_cash_bn": min_cash,
        "max_facility_utilization_bn": max_facility,
        "min_headroom_bn": min_headroom,
        "first_liquidity_shortfall_quarter": first_shortfall,
        "first_covenant_breach_quarter": first_breach,
    }


def save_csv(path: str, rows: List[Dict[str, float | bool | int]]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: List[Dict[str, float | bool | int]]) -> None:
    headers = list(rows[0].keys())
    col_widths = {}
    for h in headers:
        lengths = []
        for row in rows:
            val = row[h]
            if isinstance(val, float):
                lengths.append(len(f"{val:,.2f}"))
            else:
                lengths.append(len(str(val)))
        col_widths[h] = max([len(h)] + lengths)
    header_line = " ".join(f"{h:>{col_widths[h]}}" for h in headers)
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        formatted = []
        for h in headers:
            val = row[h]
            if isinstance(val, float):
                formatted.append(f"{val:>{col_widths[h]},.2f}")
            else:
                formatted.append(f"{str(val):>{col_widths[h]}}")
        print(" ".join(formatted))


def run_default_scenarios() -> None:
    baseline_cfg = ScenarioConfig(
        name="Baseline",
        tender_rate=0.05,
        annual_default_rate=0.02,
        loss_given_default=0.4,
        unfunded_draw_rate=0.08,
    )

    stressed_cfg = ScenarioConfig(
        name="Stressed",
        tender_rate=0.10,
        annual_default_rate=0.06,
        loss_given_default=0.5,
        unfunded_draw_rate=0.15,
        portfolio_yield=0.11,
    )

    scenarios = [baseline_cfg, stressed_cfg]
    summary_rows: List[Dict[str, float | str]] = []

    for cfg in scenarios:
        rows = run_scenario(cfg)
        save_csv(f"{cfg.name.lower()}_projection.csv", rows)
        print(f"\n=== {cfg.name} Scenario ===")
        print_table(rows)
        summary = summarize(rows)
        summary_rows.append({"scenario": cfg.name} | summary)
        print("Summary:")
        for k, v in summary.items():
            print(f"  {k}: {v}")

    save_csv("scenario_summary.csv", summary_rows)
    print("\nScenario summaries saved to scenario_summary.csv")


if __name__ == "__main__":
    run_default_scenarios()
