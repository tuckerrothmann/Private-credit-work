#!/usr/bin/env python3
"""CCLF liquidity scenario model.

Projects Cliffwater Corporate Lending Fund (CCLF) liquidity under configurable
assumptions for tenders, distributions, defaults, and unfunded commitments.

Highlights:
- standard-library only model runtime
- config-driven scenarios from JSON
- CSV output for each scenario plus a summary file
- reusable functions for downstream tooling/tests
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, fields
from math import inf
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "scenarios" / "default_scenarios.json"


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

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "ScenarioConfig":
        field_names = {f.name for f in fields(cls)}
        unknown = sorted(set(payload) - field_names)
        if unknown:
            raise ValueError(f"Unknown scenario field(s): {', '.join(unknown)}")
        cfg = cls(**payload)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Scenario name cannot be empty")
        if self.quarters <= 0:
            raise ValueError("quarters must be > 0")
        if self.nav_start <= 0:
            raise ValueError("nav_start must be > 0")
        if self.senior_credit_limit < 0 or self.senior_credit_outstanding < 0:
            raise ValueError("credit amounts must be >= 0")
        if self.senior_credit_outstanding > self.senior_credit_limit:
            raise ValueError("senior_credit_outstanding cannot exceed senior_credit_limit")
        bounded_rates = {
            "distribution_rate": self.distribution_rate,
            "tender_rate": self.tender_rate,
            "scheduled_repayment_rate": self.scheduled_repayment_rate,
            "annual_default_rate": self.annual_default_rate,
            "loss_given_default": self.loss_given_default,
            "unfunded_draw_rate": self.unfunded_draw_rate,
        }
        for label, value in bounded_rates.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{label} must be between 0 and 1")
        if self.portfolio_yield < 0:
            raise ValueError("portfolio_yield must be >= 0")
        if self.starting_cash < 0 or self.min_cash_buffer < 0 or self.unfunded_commitments < 0:
            raise ValueError("cash and commitment values must be >= 0")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be > 0")


def quarterly_rate(annual_rate: float) -> float:
    return 1 - (1 - annual_rate) ** 0.25


def sanitize_name(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "scenario"


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

    for quarter in range(1, cfg.quarters + 1):
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
                "Quarter": quarter,
                "NAV_Bn": nav / 1e9,
                "Cash_Bn": cash / 1e9,
                "Facility_Out_Bn": facility / 1e9,
                "Facility_Draw_Bn": facility_draw / 1e9,
                "Facility_Repay_Bn": facility_repay / 1e9,
                "Headroom_Bn": (facility_limit - facility) / 1e9,
                "Tender_Outflow_Bn": tender / 1e9,
                "Distributions_Bn": distributions / 1e9,
                "Credit_Losses_Bn": credit_losses / 1e9,
                "Scheduled_Repayments_Bn": scheduled_repayments / 1e9,
                "NII_Bn": nii / 1e9,
                "Net_Cash_Change_Bn": net_cash / 1e9,
                "Unfunded_Draw_Bn": unfunded_draw / 1e9,
                "Total_Debt_Bn": total_debt / 1e9,
                "Liquidity_Shortfall": liquidity_shortfall,
                "Covenant_Breach": covenant_breach,
                "Leverage_x": leverage,
            }
        )

    return rows


def summarize(rows: List[Dict[str, float | bool | int]]) -> Dict[str, float | str]:
    if not rows:
        raise ValueError("Cannot summarize empty row set")
    return {
        "min_cash_bn": min(r["Cash_Bn"] for r in rows),
        "ending_cash_bn": rows[-1]["Cash_Bn"],
        "ending_nav_bn": rows[-1]["NAV_Bn"],
        "max_facility_utilization_bn": max(r["Facility_Out_Bn"] for r in rows),
        "min_headroom_bn": min(r["Headroom_Bn"] for r in rows),
        "peak_leverage_x": max(r["Leverage_x"] for r in rows),
        "first_liquidity_shortfall_quarter": next((r["Quarter"] for r in rows if r["Liquidity_Shortfall"]), "none"),
        "first_covenant_breach_quarter": next((r["Quarter"] for r in rows if r["Covenant_Breach"]), "none"),
    }


def save_csv(path: Path, rows: List[Dict[str, float | bool | int]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: List[Dict[str, float | bool | int]]) -> None:
    headers = list(rows[0].keys())
    col_widths = {}
    for header in headers:
        lengths = [len(f"{row[header]:,.2f}") if isinstance(row[header], float) else len(str(row[header])) for row in rows]
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


def load_scenarios(path: Path) -> List[ScenarioConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "scenarios" in payload:
        payload = payload["scenarios"]
    if not isinstance(payload, list):
        raise ValueError("Scenario config must be a list or {'scenarios': [...]} object")
    return [ScenarioConfig.from_dict(item) for item in payload]


def save_effective_config(path: Path, scenarios: Sequence[ScenarioConfig]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"scenarios": [asdict(cfg) for cfg in scenarios]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_scenarios(scenarios: Iterable[ScenarioConfig], output_dir: Path, print_tables: bool = True) -> List[Dict[str, float | str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: List[Dict[str, float | str]] = []

    for cfg in scenarios:
        rows = run_scenario(cfg)
        save_csv(output_dir / f"{sanitize_name(cfg.name)}_projection.csv", rows)
        summary = summarize(rows)
        summary_rows.append({"scenario": cfg.name} | summary)
        if print_tables:
            print(f"\n=== {cfg.name} Scenario ===")
            print_table(rows)
            print("Summary:")
            for key, value in summary.items():
                print(f"  {key}: {value}")

    save_csv(output_dir / "scenario_summary.csv", summary_rows)
    save_effective_config(output_dir / "effective_scenarios.json", list(scenarios))
    if print_tables:
        print(f"\nScenario summaries saved to {output_dir / 'scenario_summary.csv'}")
    return summary_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Scenario JSON config path (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT,
        help="Directory for scenario CSV outputs (default: repo root)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Write outputs without printing scenario tables",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    scenarios = load_scenarios(args.config)
    run_scenarios(scenarios, output_dir=args.output_dir, print_tables=not args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
