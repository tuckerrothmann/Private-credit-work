from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from portfolio_collector import compute_live_na_rates, latest_portfolio_cache_files
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
