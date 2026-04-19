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


def build_borrower_heatmap_records(borrowers: dict, min_funds: int) -> list[dict]:
    """Prepare borrower rows for the concentration heatmap."""
    heatmap_records: list[dict] = []

    for borrower in borrowers.values():
        if borrower.get("fund_count", 0) < min_funds:
            continue

        latest_by_fund: dict[str, dict] = {}
        for appearance in borrower.get("appearances", []):
            fund = appearance.get("fund")
            if not fund:
                continue
            if fund not in latest_by_fund or appearance.get("period", "") > latest_by_fund[fund].get("period", ""):
                latest_by_fund[fund] = appearance

        total_fv = sum((entry.get("fv_mm") or entry.get("cost_mm") or 0) for entry in latest_by_fund.values())
        heatmap_records.append(
            {
                "name": borrower["canonical_name"],
                "fund_count": borrower["fund_count"],
                "total_fv": total_fv,
                "latest": latest_by_fund,
                "na_funds": set(borrower.get("non_accrual_funds", [])),
                "pik_funds": set(borrower.get("pik_funds", [])),
                "is_na_any": borrower.get("is_non_accrual_any", False),
            }
        )

    heatmap_records.sort(key=lambda row: (-row["fund_count"], -row["total_fv"], row["name"]))
    return heatmap_records


def build_family_heatmap_records(families: dict, min_funds: int) -> list[dict]:
    """Prepare borrower-family rows for the concentration heatmap."""
    heatmap_records: list[dict] = []

    for family in families.values():
        if family.get("fund_count", 0) < min_funds:
            continue

        latest_by_fund: dict[str, dict] = {}
        for fund, summary in family.get("current_by_fund", {}).items():
            latest_by_fund[fund] = summary

        total_fv = sum((entry.get("fv_mm") or entry.get("cost_mm") or 0) for entry in latest_by_fund.values())
        heatmap_records.append(
            {
                "name": family["family_name"],
                "fund_count": family["fund_count"],
                "total_fv": total_fv,
                "latest": latest_by_fund,
                "na_funds": set(family.get("non_accrual_funds", [])),
                "pik_funds": set(family.get("pik_funds", [])),
                "is_na_any": family.get("is_non_accrual_any", False),
                "member_count": family.get("borrower_count", 0),
            }
        )

    heatmap_records.sort(key=lambda row: (-row["fund_count"], -row["total_fv"], row["name"]))
    return heatmap_records


def build_family_summary_rows(families: dict, min_funds: int) -> list[dict]:
    """Build family-level systemic-risk rows."""
    rows = [
        {
            "Family": family["family_name"],
            "Borrowers": family.get("borrower_count", 0),
            "Funds": family.get("fund_count", 0),
            "Fund List": ", ".join(family.get("funds", [])),
            "Managers": ", ".join(family.get("managers", [])),
            "Total FV ($M)": round(family["total_fv_mm"], 1) if family.get("total_fv_mm") else None,
            "Total Cost ($M)": round(family["total_cost_mm"], 1) if family.get("total_cost_mm") else None,
            "Unrealized G/L": f"{family['unrealized_pct'] * 100:+.1f}%"
            if family.get("unrealized_pct") is not None else "—",
            "Non-Accrual": "YES — " + "+".join(family.get("non_accrual_funds", []))
            if family.get("is_non_accrual_any") else "",
            "PIK": "YES — " + "+".join(family.get("pik_funds", [])) if family.get("is_pik_any") else "",
            "Industry": ", ".join(family.get("industries", [])[:2]),
        }
        for family in families.values()
        if family.get("fund_count", 0) >= min_funds
    ]
    rows.sort(key=lambda row: (-row["Funds"], -(row["Total FV ($M)"] or 0), row["Family"]))
    return rows


def build_borrower_stress_rows(borrowers: dict, min_score: int) -> list[dict]:
    """Build borrower stress-tier table rows."""
    rows = [
        {
            "Issuer": borrower["canonical_name"],
            "Score": borrower.get("stress_score", 0),
            "Tier": borrower.get("stress_tier", "GREEN"),
            "Unrealized G/L": f"{borrower['unrealized_pct'] * 100:+.1f}%"
            if borrower.get("unrealized_pct") is not None else "—",
            "Funds": ", ".join(borrower.get("funds", [])),
            "Fund Count": borrower.get("fund_count", 0),
            "FV ($M)": round(borrower["total_fv_mm"], 1) if borrower.get("total_fv_mm") else None,
            "Non-Accrual": "YES" if borrower.get("is_non_accrual_any") else "",
            "PIK": "Yes" if borrower.get("is_pik_any") else "",
            "Industry": ", ".join(borrower.get("industries", [])[:1]),
        }
        for borrower in borrowers.values()
        if borrower.get("stress_score", 0) >= min_score
    ]
    rows.sort(key=lambda row: (-row["Score"], -(row["FV ($M)"] or 0), row["Issuer"]))
    return rows


def build_family_stress_rows(families: dict, min_score: int) -> list[dict]:
    """Build family stress-tier table rows."""
    rows = [
        {
            "Family": family["family_name"],
            "Score": family.get("stress_score", 0),
            "Tier": family.get("stress_tier", "GREEN"),
            "Borrowers": family.get("borrower_count", 0),
            "Funds": ", ".join(family.get("funds", [])),
            "Fund Count": family.get("fund_count", 0),
            "FV ($M)": round(family["total_fv_mm"], 1) if family.get("total_fv_mm") else None,
            "Unrealized G/L": f"{family['unrealized_pct'] * 100:+.1f}%"
            if family.get("unrealized_pct") is not None else "—",
            "Non-Accrual": "YES" if family.get("is_non_accrual_any") else "",
            "PIK": "Yes" if family.get("is_pik_any") else "",
            "Industry": ", ".join(family.get("industries", [])[:1]),
        }
        for family in families.values()
        if family.get("stress_score", 0) >= min_score
    ]
    rows.sort(key=lambda row: (-row["Score"], -(row["FV ($M)"] or 0), row["Family"]))
    return rows


def build_non_accrual_rows(borrowers: dict) -> list[dict]:
    """Build non-accrual borrower table rows."""
    rows = [
        {
            "Issuer": borrower["canonical_name"],
            "Non-Accrual At": ", ".join(borrower.get("non_accrual_funds", [])),
            "Fund Count": borrower.get("fund_count", 0),
            "Total FV ($M)": round(borrower["total_fv_mm"], 1) if borrower.get("total_fv_mm") else None,
            "Unrealized G/L": f"{borrower['unrealized_pct'] * 100:+.1f}%"
            if borrower.get("unrealized_pct") is not None else "—",
            "PIK": "Yes" if borrower.get("is_pik_any") else "",
            "Industry": ", ".join(borrower.get("industries", [])[:2]),
        }
        for borrower in borrowers.values()
        if borrower.get("is_non_accrual_any")
    ]
    rows.sort(key=lambda row: (-row["Fund Count"], -(row["Total FV ($M)"] or 0), row["Issuer"]))
    return rows


def build_family_non_accrual_rows(families: dict) -> list[dict]:
    """Build non-accrual family table rows."""
    rows = [
        {
            "Family": family["family_name"],
            "Non-Accrual At": ", ".join(family.get("non_accrual_funds", [])),
            "Borrowers": family.get("borrower_count", 0),
            "Fund Count": family.get("fund_count", 0),
            "Total FV ($M)": round(family["total_fv_mm"], 1) if family.get("total_fv_mm") else None,
            "Unrealized G/L": f"{family['unrealized_pct'] * 100:+.1f}%"
            if family.get("unrealized_pct") is not None else "—",
            "PIK": "Yes" if family.get("is_pik_any") else "",
            "Industry": ", ".join(family.get("industries", [])[:2]),
        }
        for family in families.values()
        if family.get("is_non_accrual_any")
    ]
    rows.sort(key=lambda row: (-row["Fund Count"], -(row["Total FV ($M)"] or 0), row["Family"]))
    return rows


def build_pik_rows(borrowers: dict) -> list[dict]:
    """Build PIK borrower table rows."""
    rows = [
        {
            "Issuer": borrower["canonical_name"],
            "PIK At": ", ".join(borrower.get("pik_funds", [])),
            "Multi-Fund PIK": borrower.get("fund_count", 0) >= 2,
            "Total FV ($M)": round(borrower["total_fv_mm"], 1) if borrower.get("total_fv_mm") else None,
            "Industry": ", ".join(borrower.get("industries", [])[:2]),
        }
        for borrower in borrowers.values()
        if borrower.get("is_pik_any")
    ]
    rows.sort(key=lambda row: (-int(row["Multi-Fund PIK"]), -(row["Total FV ($M)"] or 0), row["Issuer"]))
    return rows


def build_family_pik_rows(families: dict) -> list[dict]:
    """Build family-level PIK rows."""
    rows = [
        {
            "Family": family["family_name"],
            "PIK At": ", ".join(family.get("pik_funds", [])),
            "Borrowers": family.get("borrower_count", 0),
            "Multi-Fund PIK": family.get("fund_count", 0) >= 2,
            "Total FV ($M)": round(family["total_fv_mm"], 1) if family.get("total_fv_mm") else None,
            "Industry": ", ".join(family.get("industries", [])[:2]),
        }
        for family in families.values()
        if family.get("is_pik_any")
    ]
    rows.sort(key=lambda row: (-int(row["Multi-Fund PIK"]), -(row["Total FV ($M)"] or 0), row["Family"]))
    return rows


def build_unrealized_loss_rows(
    borrowers: dict,
    min_unrealized_pct: float = -0.05,
    min_total_cost_mm: float = 1.0,
    limit: int = 30,
) -> list[dict]:
    """Build borrower unrealized-loss ranking rows."""
    rows = [
        {
            "Issuer": borrower["canonical_name"],
            "Funds": ", ".join(borrower.get("funds", [])),
            "Cost ($M)": round(borrower["total_cost_mm"], 1) if borrower.get("total_cost_mm") else None,
            "FV ($M)": round(borrower["total_fv_mm"], 1) if borrower.get("total_fv_mm") else None,
            "Unrealized G/L": f"{borrower['unrealized_pct'] * 100:+.1f}%",
            "Non-Accrual": "Yes" if borrower.get("is_non_accrual_any") else "",
            "Industry": ", ".join(borrower.get("industries", [])[:2]),
        }
        for borrower in borrowers.values()
        if borrower.get("unrealized_pct") is not None
        and borrower["unrealized_pct"] < min_unrealized_pct
        and (borrower.get("total_cost_mm") or 0) > min_total_cost_mm
    ]
    rows.sort(key=lambda row: float(row["Unrealized G/L"].replace("%", "").replace("+", "")))
    return rows[:limit]


def build_family_unrealized_loss_rows(
    families: dict,
    min_unrealized_pct: float = -0.05,
    min_total_cost_mm: float = 1.0,
    limit: int = 30,
) -> list[dict]:
    """Build family unrealized-loss ranking rows."""
    rows = [
        {
            "Family": family["family_name"],
            "Borrowers": ", ".join(family.get("borrower_names", [])[:4]),
            "Funds": ", ".join(family.get("funds", [])),
            "Cost ($M)": round(family["total_cost_mm"], 1) if family.get("total_cost_mm") else None,
            "FV ($M)": round(family["total_fv_mm"], 1) if family.get("total_fv_mm") else None,
            "Unrealized G/L": f"{family['unrealized_pct'] * 100:+.1f}%",
            "Non-Accrual": "Yes" if family.get("is_non_accrual_any") else "",
            "Industry": ", ".join(family.get("industries", [])[:2]),
        }
        for family in families.values()
        if family.get("unrealized_pct") is not None
        and family["unrealized_pct"] < min_unrealized_pct
        and (family.get("total_cost_mm") or 0) > min_total_cost_mm
    ]
    rows.sort(key=lambda row: float(row["Unrealized G/L"].replace("%", "").replace("+", "")))
    return rows[:limit]


def build_family_merge_candidate_rows(
    review: dict,
    min_similarity: float = 0.5,
    require_shared_context: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Filter/sort family merge candidates for dashboard display."""
    rows = [
        row
        for row in review.get("merge_candidates", [])
        if (row.get("Similarity") or 0) >= min_similarity
        and (
            not require_shared_context
            or (row.get("Shared Fund Count", 0) > 0 or row.get("Shared Manager Count", 0) > 0)
        )
    ]
    rows.sort(
        key=lambda row: (
            -(row.get("Similarity") or 0),
            -(row.get("Shared Fund Count") or 0),
            -(row.get("Shared Manager Count") or 0),
            -(row.get("Combined FV ($M)") or 0),
            row.get("Borrower A", ""),
        )
    )
    return rows[:limit]


def build_family_split_candidate_rows(
    review: dict,
    include_override_families: bool = True,
    limit: int = 50,
) -> list[dict]:
    """Filter/sort family split candidates for dashboard display."""
    rows = [
        row
        for row in review.get("split_candidates", [])
        if include_override_families or not row.get("Override Applied", False)
    ]
    rows.sort(
        key=lambda row: (
            row.get("Override Applied", False),
            row.get("Max Pair Similarity") or 0,
            row.get("Shared Fund Pairs") or 0,
            -(row.get("Total FV ($M)") or 0),
            row.get("Family", ""),
        )
    )
    return rows[:limit]
