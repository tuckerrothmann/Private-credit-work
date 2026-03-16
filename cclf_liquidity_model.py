#!/usr/bin/env python3
"""CCLF Liquidity Scenario Model.

Projects 8 quarters of Cliffwater Corporate Lending Fund (CCLF) liquidity under
configurable tender, loss, distribution, and unfunded-commitment assumptions.

Dependencies: Python standard library only.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from math import inf
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent


@dataclass
class ScenarioConfig:
    name: str
    nav_start: float = 31.5e9
    senior_notes: float = 5.65e9
    senior_credit_outstanding: float = 1.19e9
    senior_credit_limit: float = 2.5e9
    distribution_rate: float = 0.1075
    tender_rate: float = 0.05
    portfolio_yield: float = 0.12
    scheduled_repayment_rate: float = 0.03
    annual_default_rate: float = 0.02
    loss_given_default: float = 0.4
    unfunded_commitments: float = 4.0e9
    unfunded_draw_rate: float = 0.10
    quarters: int = 8
    min_cash_buffer: float = 0.0
    starting_cash: float = 0.5e9
    max_leverage: float = 2.0


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
    return {
        "min_cash_bn": min(r["Cash_Bn"] for r in rows),
        "max_facility_utilization_bn": max(r["Facility_Out_Bn"] for r in rows),
        "min_headroom_bn": min(r["Headroom_Bn"] for r in rows),
        "first_liquidity_shortfall_quarter": next((r["Quarter"] for r in rows if r["Liquidity_Shortfall"]), "none"),
        "first_covenant_breach_quarter": next((r["Quarter"] for r in rows if r["Covenant_Breach"]), "none"),
    }


def save_csv(path: Path, rows: List[Dict[str, float | bool | int]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: List[Dict[str, float | bool | int]]) -> None:
    headers = list(rows[0].keys())
    col_widths = {}
    for header in headers:
        lengths = []
        for row in rows:
            value = row[header]
            lengths.append(len(f"{value:,.2f}") if isinstance(value, float) else len(str(value)))
        col_widths[header] = max([len(header)] + lengths)

    header_line = " ".join(f"{header:>{col_widths[header]}}" for header in headers)
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        formatted = []
        for header in headers:
            value = row[header]
            if isinstance(value, float):
                formatted.append(f"{value:>{col_widths[header]},.2f}")
            else:
                formatted.append(f"{str(value):>{col_widths[header]}}")
        print(" ".join(formatted))


def default_scenarios() -> List[ScenarioConfig]:
    return [
        ScenarioConfig(
            name="Baseline",
            tender_rate=0.05,
            annual_default_rate=0.02,
            loss_given_default=0.4,
            unfunded_draw_rate=0.08,
        ),
        ScenarioConfig(
            name="Stressed",
            tender_rate=0.10,
            annual_default_rate=0.06,
            loss_given_default=0.5,
            unfunded_draw_rate=0.15,
            portfolio_yield=0.11,
        ),
    ]


def run_default_scenarios() -> None:
    summary_rows: List[Dict[str, float | str]] = []

    for cfg in default_scenarios():
        rows = run_scenario(cfg)
        save_csv(ROOT / f"{cfg.name.lower()}_projection.csv", rows)
        print(f"\n=== {cfg.name} Scenario ===")
        print_table(rows)
        summary = summarize(rows)
        summary_rows.append({"scenario": cfg.name} | summary)
        print("Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")

    save_csv(ROOT / "scenario_summary.csv", summary_rows)
    print("\nScenario summaries saved to scenario_summary.csv")


if __name__ == "__main__":
    run_default_scenarios()
