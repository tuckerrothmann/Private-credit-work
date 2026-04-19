from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from dashboard_helpers import compute_maturity_wall, summarize_portfolio_cache
from portfolio_collector import compute_live_na_rates, latest_portfolio_cache_files
import refresh
from trade_signals import load_all_signals, load_signal_funds


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_latest_portfolio_cache_files_prefers_newest_period(tmp_path: Path) -> None:
    _write_json(tmp_path / "ARCC_2025-09-30.json", [])
    _write_json(tmp_path / "ARCC_2025-12-31.json", [])
    _write_json(tmp_path / "_sub_0000017313.json", {})

    latest = latest_portfolio_cache_files(tmp_path)

    assert latest["ARCC"].name == "ARCC_2025-12-31.json"


def test_compute_live_na_rates_uses_newest_cached_filing(tmp_path: Path) -> None:
    old_positions = [
        {"fv_mm": 40.0, "is_non_accrual": True},
        {"fv_mm": 40.0, "is_non_accrual": False},
    ]
    new_positions = [
        {"fv_mm": 80.0, "is_non_accrual": False},
    ]
    _write_json(tmp_path / "PFLT_2025-09-30.json", old_positions)
    _write_json(tmp_path / "PFLT_2025-12-31.json", new_positions)

    rates = compute_live_na_rates(tmp_path)

    assert rates["PFLT"] == 0.0


def test_load_signal_funds_uses_full_enrichment_pipeline() -> None:
    base = [{"ticker": "ABC"}]
    with_na = [{"ticker": "ABC", "_na_source": "live"}]
    with_prices = [{"ticker": "ABC", "_price_source": "live"}]

    with patch("red_flag_screener.load_universe_with_trends", return_value=base) as load_trends, \
         patch("red_flag_screener.enrich_funds_with_live_na", return_value=with_na) as enrich_na, \
         patch("price_feed.enrich_funds_with_prices", return_value=with_prices) as enrich_prices:
        result = load_signal_funds()

    assert result == with_prices
    load_trends.assert_called_once_with("data/bdc_universe.json", history_dir=None)
    enrich_na.assert_called_once_with(base, cache_dir=None)
    enrich_prices.assert_called_once_with(with_na)


def test_load_all_signals_delegates_to_canonical_fund_loader() -> None:
    funds = [{"ticker": "ABC"}]
    signals = [{"ticker": "ABC", "signal": "BUY"}]

    with patch("trade_signals.load_signal_funds", return_value=funds) as load_funds, \
         patch("trade_signals.compute_signals", return_value=signals) as compute:
        result = load_all_signals()

    assert result == signals
    load_funds.assert_called_once_with()
    compute.assert_called_once_with(funds)


def test_get_latest_10kq_period_skips_cache_writes_in_dry_run(tmp_path: Path) -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["10-Q"],
                "reportDate": ["2025-12-31"],
            }
        }
    }

    with patch.object(refresh, "EDGAR_CACHE", tmp_path), \
         patch.object(refresh, "_fetch_json", return_value=payload):
        period = refresh._get_latest_10kq_period("17313", allow_cache_write=False)

    assert period == "2025-12-31"
    assert not (tmp_path / "submissions" / "CIK0000017313.json").exists()


def test_summarize_portfolio_cache_handles_counts_and_totals(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "ARCC_2025-12-31.json",
        [
            {"fv_mm": 10.0, "is_non_accrual": True, "is_pik": False},
            {"fv_mm": 15.5, "is_non_accrual": False, "is_pik": True},
        ],
    )
    _write_json(tmp_path / "_sub_0000017313.json", {"ignored": True})

    summary = summarize_portfolio_cache(tmp_path)

    assert summary == [
        {
            "file": "ARCC_2025-12-31.json",
            "ticker": "ARCC",
            "period": "2025-12-31",
            "positions": 2,
            "non_accruals": 1,
            "pik_positions": 1,
            "total_fv_mm": 25.5,
        }
    ]


def test_compute_maturity_wall_uses_latest_files_and_deduplicates_positions(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "ARCC_2025-09-30.json",
        [{"issuer": "Old Co", "maturity": "3/31/2025", "fv_mm": 99.0}],
    )
    _write_json(
        tmp_path / "ARCC_2025-12-31.json",
        [
            {"issuer": "Alpha Holdings", "maturity": "3/31/2026", "fv_mm": 25.0},
            {"issuer": "Alpha Holdings", "maturity": "3/31/2026", "fv_mm": 25.0},
            {"issuer": "Beta LLC", "maturity": "1/2025", "fv_mm": 11.0},
        ],
    )

    wall_rows, past_due_rows = compute_maturity_wall(tmp_path, today=date(2026, 1, 15))

    assert wall_rows == [{"Quarter": "2026-Q1", "Fund": "ARCC", "FV ($M)": 25.0}]
    assert len(past_due_rows) == 1
    assert past_due_rows[0]["Fund"] == "ARCC"
    assert past_due_rows[0]["Issuer"] == "Beta LLC"
    assert past_due_rows[0]["FV ($M)"] == 11.0
