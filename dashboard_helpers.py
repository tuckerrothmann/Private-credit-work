from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from portfolio_collector import latest_portfolio_cache_files


def summarize_portfolio_cache(cache_dir: Path) -> list[dict]:
    """Summarize parsed portfolio cache files."""
    files = sorted(cache_dir.glob("*.json"))
    files = [f for f in files if not f.name.startswith("_")]
    summary: list[dict] = []

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        ticker = path.stem.split("_")[0]
        period = "_".join(path.stem.split("_")[1:])
        na_count = sum(1 for position in data if position.get("is_non_accrual"))
        pik_count = sum(1 for position in data if position.get("is_pik"))
        total_fv = sum(position.get("fv_mm") or 0 for position in data)
        summary.append(
            {
                "file": path.name,
                "ticker": ticker,
                "period": period,
                "positions": len(data),
                "non_accruals": na_count,
                "pik_positions": pik_count,
                "total_fv_mm": round(total_fv, 1),
            }
        )

    return summary


def _parse_maturity_date(maturity: str) -> date | None:
    parts = maturity.split("/")
    try:
        if len(parts) == 3:
            month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            month, day, year = int(parts[0]), 15, int(parts[1])
        else:
            return None
        if year < 2019 or year > 2035:
            return None
        return date(year, month, day)
    except Exception:
        return None


def compute_maturity_wall(cache_dir: Path, today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Build maturity-wall and past-due rows from the latest filing per fund."""
    as_of = today or date.today()
    files = sorted(latest_portfolio_cache_files(cache_dir).values(), key=lambda path: path.name)

    wall_rows: list[dict] = []
    past_due_rows: list[dict] = []

    for path in files:
        ticker = path.stem.split("_")[0]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        seen_positions: set[tuple] = set()
        for position in data:
            maturity = position.get("maturity", "") or ""
            fv = position.get("fv_mm")
            issuer = position.get("issuer", "")
            if not maturity or not fv or fv <= 0 or not issuer:
                continue

            maturity_date = _parse_maturity_date(maturity)
            if maturity_date is None:
                continue

            key = (issuer[:30], maturity, round(fv, 1))
            if key in seen_positions:
                continue
            seen_positions.add(key)

            quarter_label = f"{maturity_date.year}-Q{(maturity_date.month - 1) // 3 + 1}"
            if maturity_date < as_of:
                past_due_rows.append(
                    {
                        "Fund": ticker,
                        "Issuer": issuer[:60],
                        "Maturity": maturity,
                        "FV ($M)": round(fv, 1),
                        "mat_date": maturity_date,
                    }
                )
            else:
                wall_rows.append(
                    {
                        "Quarter": quarter_label,
                        "Fund": ticker,
                        "FV ($M)": round(fv, 1),
                    }
                )

    past_due_rows.sort(key=lambda row: row["mat_date"])
    return wall_rows, past_due_rows
