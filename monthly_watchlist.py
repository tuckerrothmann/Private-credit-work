from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

WATCHLIST_CONFIG_PATH = Path("data/monthly_watchlist_config.json")
BORROWER_DB_PATH = Path("data/borrower_db.json")
MONTHLY_WATCHLIST_CSV = Path("data/processed/monthly_watchlist.csv")
MONTHLY_WATCHLIST_MD = Path("data/processed/monthly_watchlist.md")

_BUCKET_ORDER = {
    "Overweight core": 0,
    "Overweight selectively": 1,
    "Hold / neutral": 2,
    "Underweight / caution": 3,
    "Avoid / trim first": 4,
}


def load_watchlist_config(path: Path = WATCHLIST_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"tickers": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _display_tier(score: int) -> str:
    if score >= 12:
        return "RED"
    if score >= 8:
        return "ORANGE"
    if score >= 5:
        return "YELLOW"
    return "GREEN"


def _fmt_ratio(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}x"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def _fmt_num(value: Any) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def _transmission_details(family_keys: list[str], borrower_db: dict[str, Any]) -> tuple[str, str]:
    families = borrower_db.get("families", {})
    names: list[str] = []
    snapshots: list[str] = []
    for family_key in family_keys:
        rec = families.get(family_key)
        if not rec:
            names.append(family_key)
            continue
        family_name = rec.get("family_name", family_key)
        names.append(family_name)
        snapshots.append(
            f"{family_name} ({rec.get('stress_tier', 'GREEN')}, "
            f"{rec.get('fund_count', 0)} funds, ${rec.get('total_fv_mm', 0.0):.1f}M FV)"
        )
    return ", ".join(names), "; ".join(snapshots)


def build_monthly_watchlist_rows(
    funds: list[dict[str, Any]],
    signals: list[Any],
    borrower_db: dict[str, Any],
    config: dict[str, Any],
    as_of: str = "",
) -> list[dict[str, Any]]:
    fund_by_ticker = {fund.get("ticker", "").upper(): fund for fund in funds}
    signal_by_ticker = {signal.ticker.upper(): signal for signal in signals}
    rows: list[dict[str, Any]] = []

    for ticker, override in (config.get("tickers") or {}).items():
        fund = fund_by_ticker.get(ticker, {})
        signal = signal_by_ticker.get(ticker)
        score = int(signal.risk_score) if signal else 0
        family_keys = override.get("borrower_family_keys", [])
        family_names, family_snapshot = _transmission_details(family_keys, borrower_db)

        rows.append(
            {
                "Bucket": override.get("bucket", ""),
                "Ticker": ticker,
                "Name": fund.get("name", ticker),
                "PM Action": override.get("pm_action", ""),
                "Signal": signal.signal_label if signal else "",
                "Risk Score": score,
                "Risk Tier": _display_tier(score),
                "P/NAV": _fmt_ratio(fund.get("price_to_nav")),
                "NII Coverage": _fmt_ratio(fund.get("nii_coverage")),
                "Non-Accrual (FV)": _fmt_pct(fund.get("nonaccrual_pct_fair_value")),
                "NAV Chg YoY": _fmt_pct(fund.get("nav_change_yoy_pct")),
                "Leverage D/E": _fmt_num(fund.get("leverage_de")),
                "Borrower Transmission": family_names,
                "Transmission Snapshot": family_snapshot,
                "Why Now": override.get("why_now", ""),
                "What Changes View": override.get("what_changes_view", ""),
                "As Of": as_of or fund.get("as_of", ""),
            }
        )

    rows.sort(
        key=lambda row: (
            _BUCKET_ORDER.get(row["Bucket"], 99),
            -int(row["Risk Score"] or 0),
            row["Ticker"],
        )
    )
    return rows


def write_monthly_watchlist(
    rows: list[dict[str, Any]],
    csv_path: Path = MONTHLY_WATCHLIST_CSV,
    md_path: Path = MONTHLY_WATCHLIST_MD,
    as_of: str = "",
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = list(rows[0].keys()) if rows else [
            "Bucket", "Ticker", "Name", "PM Action", "Signal", "Risk Score",
            "Risk Tier", "P/NAV", "NII Coverage", "Non-Accrual (FV)", "NAV Chg YoY",
            "Leverage D/E", "Borrower Transmission", "Transmission Snapshot",
            "Why Now", "What Changes View", "As Of",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# Monthly Watchlist", ""]
    if as_of:
        lines.extend([f"As of {as_of}.", ""])
    bucket_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        bucket_groups.setdefault(row["Bucket"], []).append(row)
    for bucket in sorted(bucket_groups, key=lambda value: _BUCKET_ORDER.get(value, 99)):
        lines.extend([f"## {bucket}", "", "| Ticker | Action | Signal | P/NAV | NII Cov. | Transmission | What Changes View |", "|---|---|---|---|---|---|---|"])
        for row in bucket_groups[bucket]:
            lines.append(
                f"| `{row['Ticker']}` | {row['PM Action']} | {row['Signal']} | {row['P/NAV'] or 'n/a'} | "
                f"{row['NII Coverage'] or 'n/a'} | {row['Borrower Transmission'] or '-'} | {row['What Changes View']} |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def refresh_monthly_watchlist(
    config_path: Path = WATCHLIST_CONFIG_PATH,
    borrower_db_path: Path = BORROWER_DB_PATH,
    csv_path: Path = MONTHLY_WATCHLIST_CSV,
    md_path: Path = MONTHLY_WATCHLIST_MD,
    as_of: str = "",
) -> list[dict[str, Any]]:
    from red_flag_screener import load_scoring_funds
    from trade_signals import load_all_signals

    config = load_watchlist_config(config_path)
    borrower_db = {}
    if borrower_db_path.exists():
        borrower_db = json.loads(borrower_db_path.read_text(encoding="utf-8"))

    funds = load_scoring_funds()
    signals = load_all_signals()
    rows = build_monthly_watchlist_rows(funds, signals, borrower_db, config, as_of=as_of)
    write_monthly_watchlist(rows, csv_path=csv_path, md_path=md_path, as_of=as_of)
    return rows
