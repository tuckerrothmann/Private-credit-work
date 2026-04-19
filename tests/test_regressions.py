from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from dashboard_helpers import (
    build_borrower_heatmap_records,
    build_borrower_stress_rows,
    build_family_heatmap_records,
    build_family_merge_candidate_rows,
    build_family_non_accrual_rows,
    build_family_pik_rows,
    build_family_split_candidate_rows,
    build_family_stress_rows,
    build_family_summary_rows,
    build_family_unrealized_loss_rows,
    build_non_accrual_rows,
    build_pik_rows,
    build_unrealized_loss_rows,
    compute_maturity_wall,
    summarize_portfolio_cache,
)
from portfolio_collector import (
    _borrower_key,
    _borrower_family_key,
    _clean_issuer_name,
    _review_token_signature,
    build_borrower_db,
    compute_live_na_rates,
    latest_portfolio_cache_files,
    parse_soi_html,
    write_family_review_candidates,
)
import refresh
from trade_signals import load_all_signals, load_signal_funds


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_borrowers() -> dict:
    return {
        "alpha": {
            "canonical_name": "Alpha Software",
            "fund_count": 2,
            "funds": ["ARCC", "PFLT"],
            "appearances": [
                {"fund": "ARCC", "period": "2025-09-30", "fv_mm": 10.0},
                {"fund": "ARCC", "period": "2025-12-31", "fv_mm": 14.0},
                {"fund": "PFLT", "period": "2025-12-31", "cost_mm": 8.0},
            ],
            "non_accrual_funds": ["PFLT"],
            "pik_funds": ["ARCC"],
            "is_non_accrual_any": True,
            "is_pik_any": True,
            "stress_score": 6,
            "stress_tier": "RED",
            "unrealized_pct": -0.22,
            "total_fv_mm": 22.0,
            "total_cost_mm": 30.0,
            "industries": ["Software", "Application"],
        },
        "beta": {
            "canonical_name": "Beta Healthcare",
            "fund_count": 1,
            "funds": ["GSBD"],
            "appearances": [
                {"fund": "GSBD", "period": "2025-12-31", "fv_mm": 5.0},
            ],
            "non_accrual_funds": [],
            "pik_funds": ["GSBD"],
            "is_non_accrual_any": False,
            "is_pik_any": True,
            "stress_score": 2,
            "stress_tier": "YELLOW",
            "unrealized_pct": -0.04,
            "total_fv_mm": 5.0,
            "total_cost_mm": 5.4,
            "industries": ["Healthcare"],
        },
    }


def _sample_families() -> dict:
    return {
        "alpha": {
            "family_key": "alpha",
            "family_name": "Alpha Family",
            "borrower_count": 2,
            "borrower_names": ["Alpha OpCo", "Alpha Holdco"],
            "fund_count": 2,
            "funds": ["ARCC", "PFLT"],
            "manager_count": 2,
            "managers": ["Ares", "PennantPark"],
            "non_accrual_funds": ["PFLT"],
            "pik_funds": ["ARCC"],
            "is_non_accrual_any": True,
            "is_pik_any": True,
            "stress_score": 6,
            "stress_tier": "RED",
            "unrealized_pct": -0.22,
            "total_fv_mm": 22.0,
            "total_cost_mm": 30.0,
            "industries": ["Software", "Application"],
            "current_by_fund": {
                "ARCC": {"fund": "ARCC", "period": "2025-12-31", "fv_mm": 14.0, "cost_mm": 18.0},
                "PFLT": {"fund": "PFLT", "period": "2025-12-31", "fv_mm": 8.0, "cost_mm": 12.0},
            },
        },
        "beta": {
            "family_key": "beta",
            "family_name": "Beta Family",
            "borrower_count": 1,
            "borrower_names": ["Beta Healthcare"],
            "fund_count": 1,
            "funds": ["GSBD"],
            "manager_count": 1,
            "managers": ["GSAM"],
            "non_accrual_funds": [],
            "pik_funds": ["GSBD"],
            "is_non_accrual_any": False,
            "is_pik_any": True,
            "stress_score": 2,
            "stress_tier": "YELLOW",
            "unrealized_pct": -0.04,
            "total_fv_mm": 5.0,
            "total_cost_mm": 5.4,
            "industries": ["Healthcare"],
            "current_by_fund": {
                "GSBD": {"fund": "GSBD", "period": "2025-12-31", "fv_mm": 5.0, "cost_mm": 5.4},
            },
        },
    }


def _sample_family_review() -> dict:
    return {
        "merge_candidates": [
            {
                "Borrower A": "Alpha OpCo",
                "Borrower B": "Alpha Holdco",
                "Family A": "alpha op",
                "Family B": "alpha hold",
                "Similarity": 0.8,
                "Shared Fund Count": 1,
                "Shared Manager Count": 1,
                "Combined FV ($M)": 30.0,
            },
            {
                "Borrower A": "Beta One",
                "Borrower B": "Beta Two",
                "Family A": "beta one",
                "Family B": "beta two",
                "Similarity": 0.55,
                "Shared Fund Count": 0,
                "Shared Manager Count": 0,
                "Combined FV ($M)": 12.0,
            },
        ],
        "split_candidates": [
            {
                "Family": "Gamma Family",
                "Override Applied": False,
                "Max Pair Similarity": 0.1,
                "Shared Fund Pairs": 0,
                "Total FV ($M)": 20.0,
            },
            {
                "Family": "Delta Family",
                "Override Applied": True,
                "Max Pair Similarity": 0.2,
                "Shared Fund Pairs": 0,
                "Total FV ($M)": 25.0,
            },
        ],
    }


def _sample_soi_html() -> str:
    return """
<html>
  <body>
    <h2>Consolidated Schedule of Investments</h2>
    <table>
      <tr>
        <th>Portfolio Company</th>
        <th>Investment Type</th>
        <th>Interest Rate</th>
        <th>Maturity Date</th>
        <th>Principal</th>
        <th>Cost</th>
        <th>Fair Value</th>
        <th>% of Net Assets</th>
      </tr>
      <tr>
        <td>Acme Holdings, LLC</td>
        <td>First Lien</td>
        <td>SOFR + 5.50%</td>
        <td>12/31/2028</td>
        <td>$10,000</td>
        <td>$9,800</td>
        <td>$9,900</td>
        <td>1.0%</td>
      </tr>
      <tr>
        <td>Bravo Software, Inc.</td>
        <td>Second Lien</td>
        <td>SOFR + 6.50%</td>
        <td>06/30/2029</td>
        <td>$8,000</td>
        <td>$7,500</td>
        <td>$7,600</td>
        <td>0.8%</td>
      </tr>
    </table>
  </body>
</html>
""".strip()


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


def test_parse_soi_html_retries_full_html_when_chunk_misses_heading() -> None:
    full_html = _sample_soi_html()
    large_html = full_html.replace("</body>", ("x" * 3_100_000) + "</body>")

    with patch("portfolio_collector._extract_soi_chunk", return_value="<html><body><p>No schedule here</p></body></html>"):
        investments = parse_soi_html(large_html, "TEST", "2025-12-31", "10-K")

    assert len(investments) == 2
    assert investments[0].issuer == "Acme Holdings, LLC"


def test_parse_soi_html_retries_full_html_when_chunk_has_no_rows() -> None:
    full_html = _sample_soi_html()
    large_html = full_html.replace("</body>", ("x" * 3_100_000) + "</body>")
    chunk_html = """
<html>
  <body>
    <h2>Consolidated Schedule of Investments</h2>
    <table>
      <tr><th>Assets</th><th>December 31, 2025</th></tr>
      <tr><td>Investments at fair value</td><td>$100,000</td></tr>
    </table>
  </body>
</html>
""".strip()

    with patch("portfolio_collector._extract_soi_chunk", return_value=chunk_html):
        investments = parse_soi_html(large_html, "TEST", "2025-12-31", "10-K")

    assert len(investments) == 2
    assert investments[0].issuer == "Acme Holdings, LLC"


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


def test_build_borrower_heatmap_records_uses_latest_appearances_and_sorting() -> None:
    records = build_borrower_heatmap_records(_sample_borrowers(), min_funds=1)

    assert [record["name"] for record in records] == ["Alpha Software", "Beta Healthcare"]
    assert records[0]["total_fv"] == 22.0
    assert records[0]["latest"]["ARCC"]["period"] == "2025-12-31"
    assert records[0]["na_funds"] == {"PFLT"}
    assert records[0]["pik_funds"] == {"ARCC"}


def test_build_borrower_table_rows_apply_filters_and_ordering() -> None:
    borrowers = _sample_borrowers()

    stress_rows = build_borrower_stress_rows(borrowers, min_score=3)
    non_accrual_rows = build_non_accrual_rows(borrowers)
    pik_rows = build_pik_rows(borrowers)
    loss_rows = build_unrealized_loss_rows(borrowers)

    assert [row["Issuer"] for row in stress_rows] == ["Alpha Software"]
    assert stress_rows[0]["Tier"] == "RED"
    assert stress_rows[0]["Unrealized G/L"] == "-22.0%"

    assert [row["Issuer"] for row in non_accrual_rows] == ["Alpha Software"]
    assert non_accrual_rows[0]["Non-Accrual At"] == "PFLT"

    assert [row["Issuer"] for row in pik_rows] == ["Alpha Software", "Beta Healthcare"]
    assert pik_rows[0]["Multi-Fund PIK"] is True
    assert pik_rows[1]["Multi-Fund PIK"] is False

    assert [row["Issuer"] for row in loss_rows] == ["Alpha Software"]
    assert loss_rows[0]["Cost ($M)"] == 30.0


def test_build_family_helpers_apply_filters_and_ordering() -> None:
    families = _sample_families()

    summary_rows = build_family_summary_rows(families, min_funds=1)
    heatmap_records = build_family_heatmap_records(families, min_funds=1)
    stress_rows = build_family_stress_rows(families, min_score=3)
    non_accrual_rows = build_family_non_accrual_rows(families)
    pik_rows = build_family_pik_rows(families)
    loss_rows = build_family_unrealized_loss_rows(families)

    assert [row["Family"] for row in summary_rows] == ["Alpha Family", "Beta Family"]
    assert summary_rows[0]["Borrowers"] == 2

    assert [record["name"] for record in heatmap_records] == ["Alpha Family", "Beta Family"]
    assert heatmap_records[0]["latest"]["ARCC"]["period"] == "2025-12-31"
    assert heatmap_records[0]["na_funds"] == {"PFLT"}

    assert [row["Family"] for row in stress_rows] == ["Alpha Family"]
    assert stress_rows[0]["Tier"] == "RED"

    assert [row["Family"] for row in non_accrual_rows] == ["Alpha Family"]
    assert non_accrual_rows[0]["Non-Accrual At"] == "PFLT"

    assert [row["Family"] for row in pik_rows] == ["Alpha Family", "Beta Family"]
    assert pik_rows[0]["Multi-Fund PIK"] is True
    assert pik_rows[1]["Multi-Fund PIK"] is False

    assert [row["Family"] for row in loss_rows] == ["Alpha Family"]
    assert loss_rows[0]["Cost ($M)"] == 30.0


def test_build_family_review_rows_filter_candidates() -> None:
    review = _sample_family_review()

    merge_rows = build_family_merge_candidate_rows(review, min_similarity=0.6, require_shared_context=True)
    split_rows = build_family_split_candidate_rows(review, include_override_families=False)

    assert [row["Borrower A"] for row in merge_rows] == ["Alpha OpCo"]
    assert [row["Family"] for row in split_rows] == ["Gamma Family"]


def test_build_borrower_db_enriches_manager_history_and_watchlist(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps(
            {
                "funds": [
                    {"ticker": "ARCC", "manager": "Ares", "type": "listed_bdc", "name": "Ares Capital"},
                    {"ticker": "PFLT", "manager": "PennantPark", "type": "listed_bdc", "name": "PennantPark"},
                ]
            }
        ),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "ARCC_2025-09-30.json",
        [
            {
                "issuer": "Example Borrower LLC",
                "fund_ticker": "ARCC",
                "period": "2025-09-30",
                "filing_type": "10-Q",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "8.50 %",
                "maturity": "12/2028",
                "cost_mm": 10.0,
                "fv_mm": 9.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 425,
            }
        ],
    )
    _write_json(
        cache_dir / "ARCC_2025-12-31.json",
        [
            {
                "issuer": "Example Borrower LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "9.25 %",
                "maturity": "06/2027",
                "cost_mm": 12.0,
                "fv_mm": 11.0,
                "is_pik": True,
                "is_non_accrual": False,
                "spread_bps": 475,
            },
            {
                "issuer": "Example Borrower LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "9.25 %",
                "maturity": "06/2027",
                "cost_mm": 3.0,
                "fv_mm": 2.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 475,
            },
        ],
    )
    _write_json(
        cache_dir / "PFLT_2025-12-31.json",
        [
            {
                "issuer": "Example Borrower LLC",
                "fund_ticker": "PFLT",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "Unitranche",
                "rate_str": "10.00 %",
                "maturity": "03/2028",
                "cost_mm": 8.0,
                "fv_mm": 6.0,
                "is_pik": False,
                "is_non_accrual": True,
                "spread_bps": 525,
            }
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
    )

    borrower = db["borrowers"]["example borrower"]
    assert borrower["manager_count"] == 2
    assert borrower["managers"] == ["Ares", "PennantPark"]
    assert borrower["fund_type_breakdown"] == {"listed_bdc": 2}
    assert borrower["nearest_maturity"] == "06/2027"
    assert borrower["current_by_fund"]["ARCC"]["fv_mm"] == 13.0
    assert borrower["current_by_fund"]["ARCC"]["position_count"] == 2
    assert borrower["current_by_fund"]["PFLT"]["is_non_accrual"] is True
    assert borrower["period_count"] == 2
    assert borrower["first_seen_period"] == "2025-09-30"
    assert borrower["last_seen_period"] == "2025-12-31"
    assert borrower["peak_fund_count"] == 2
    assert borrower["surveillance_score"] >= borrower["stress_score"] * 2

    watchlist_text = watchlist_path.read_text(encoding="utf-8")
    assert "Example Borrower LLC" in watchlist_text
    assert "PennantPark" in watchlist_text


def test_clean_issuer_name_strips_unicode_dash_instrument_suffix() -> None:
    issuer, instrument, markers = _clean_issuer_name(
        "Edge Adhesives Holdings, Inc. – Term Debt (S + 5.5 %, 9.6 % Cash, Due 8/2026)"
    )

    assert issuer == "Edge Adhesives Holdings, Inc."
    assert instrument == "Term Debt (S + 5.5 %, 9.6 % Cash, Due 8/2026)"
    assert markers == set()

    issuer, instrument, _ = _clean_issuer_name("Meadowlark Acquirer, LLC- Unfunded Revolver")
    assert issuer == "Meadowlark Acquirer, LLC"
    assert instrument == "Unfunded Revolver"


def test_borrower_key_normalizes_dba_plus_and_related_entity_variants() -> None:
    base = _borrower_key("Pluralsight, Inc.")

    assert _borrower_key("Paradigmatic Holdco LLC (dba Pluralsight)") == base
    assert _borrower_key("Pluralsight, LLC+") == base
    assert _borrower_key("Pluralsight, LLC and Pluralsight Holdings, LLC and Paradigmatic Holdco LLC") == base
    assert _borrower_key("Alpha Buyer, Inc.") == "alpha buyer"


def test_borrower_family_key_rolls_related_entities_without_overmerging() -> None:
    assert _borrower_family_key("Project Granite Buyer, Inc.") == "granite"
    assert _borrower_family_key("Project Granite Holdings, LLC") == "granite"
    assert _borrower_family_key("B T Group Acquisition, Inc.") == "bt group"
    assert _borrower_family_key("ACP Avenu Buyer, LLC") == "acp avenu"
    assert _borrower_family_key("ACP Avenu Midco LLC") == "acp avenu"
    assert _borrower_family_key("North Haven Fairway Buyer, LLC") == "north haven fairway"
    assert _borrower_family_key("North Haven Saints Equity Holdings, LP") == "north haven saints"
    assert _borrower_family_key("U.S. Government Securities") == "us government securities"
    assert _borrower_family_key("U.S. Treasury Bill") == "us treasury bill"


def test_build_borrower_db_filters_negative_noise_and_merges_instrument_suffixes(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps({"funds": [{"ticker": "ARCC", "manager": "Ares", "type": "listed_bdc"}]}),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "ARCC_2025-12-31.json",
        [
            {
                "issuer": "Edge Adhesives Holdings, Inc. – Term Debt (S + 5.5 %, 9.6 % Cash, Due 8/2026)",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Chemicals",
                "invest_type": "First lien",
                "rate_str": "9.60 %",
                "maturity": "08/2026",
                "cost_mm": 5.5,
                "fv_mm": 5.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 550,
            },
            {
                "issuer": "Edge Adhesives Holdings, Inc., Revolver",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Chemicals",
                "invest_type": "Revolver",
                "rate_str": "9.10 %",
                "maturity": "08/2026",
                "cost_mm": 1.2,
                "fv_mm": 1.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 500,
            },
            {
                "issuer": "Fixed 2.7 %",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "",
                "invest_type": "",
                "rate_str": "",
                "maturity": "",
                "cost_mm": -12.0,
                "fv_mm": -12.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": None,
            },
            {
                "issuer": "Hyphen Solutions, LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "Equity",
                "rate_str": "",
                "maturity": "",
                "cost_mm": -0.011,
                "fv_mm": -0.011,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": None,
            },
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
    )

    assert sorted(db["borrowers"]) == ["edge adhesives holdings"]
    borrower = db["borrowers"]["edge adhesives holdings"]
    assert borrower["canonical_name"] == "Edge Adhesives Holdings, Inc."
    assert borrower["total_fv_mm"] == 6.0
    assert borrower["total_cost_mm"] == 6.7
    assert borrower["current_by_fund"]["ARCC"]["position_count"] == 2


def test_build_borrower_db_ignores_scale_error_outlier_without_dropping_borrower(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps({"funds": [{"ticker": "GSBD", "manager": "GSAM", "type": "listed_bdc"}]}),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "GSBD_2025-12-31.json",
        [
            {
                "issuer": "Pluralsight, Inc.",
                "fund_ticker": "GSBD",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "8.75 %",
                "maturity": "08/2029",
                "cost_mm": 15.0,
                "fv_mm": 14.0,
                "is_pik": False,
                "is_non_accrual": True,
                "spread_bps": 450,
            },
            {
                "issuer": "Pluralsight, Inc.",
                "fund_ticker": "GSBD",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "8.75 %",
                "maturity": "08/2029",
                "cost_mm": 4836.698,
                "fv_mm": 13.167,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 450,
            },
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
    )

    borrower = db["borrowers"]["pluralsight"]
    assert borrower["canonical_name"] == "Pluralsight, Inc."
    assert borrower["total_cost_mm"] == 15.0
    assert borrower["total_fv_mm"] == 27.167
    assert borrower["current_by_fund"]["GSBD"]["fv_mm"] == 27.167


def test_build_borrower_db_builds_family_rollups_and_watchlist(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    family_watchlist_path = tmp_path / "borrower_family_watchlist.csv"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps(
            {
                "funds": [
                    {"ticker": "ARCC", "manager": "Ares", "type": "listed_bdc"},
                    {"ticker": "PFLT", "manager": "PennantPark", "type": "listed_bdc"},
                ]
            }
        ),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "ARCC_2025-12-31.json",
        [
            {
                "issuer": "Project Granite Buyer, Inc.",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "9.50 %",
                "maturity": "03/2028",
                "cost_mm": 20.0,
                "fv_mm": 18.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 475,
            },
            {
                "issuer": "Project Granite Holdings, LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "Equity",
                "rate_str": "",
                "maturity": "",
                "cost_mm": 4.0,
                "fv_mm": 2.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": None,
            },
            {
                "issuer": "ACP Avenu Buyer, LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Business Services",
                "invest_type": "First lien",
                "rate_str": "10.00 %",
                "maturity": "06/2029",
                "cost_mm": 12.0,
                "fv_mm": 11.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 500,
            },
        ],
    )
    _write_json(
        cache_dir / "PFLT_2025-12-31.json",
        [
            {
                "issuer": "Project Granite Buyer, Inc.",
                "fund_ticker": "PFLT",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "Unitranche",
                "rate_str": "10.25 %",
                "maturity": "04/2028",
                "cost_mm": 9.0,
                "fv_mm": 7.0,
                "is_pik": True,
                "is_non_accrual": True,
                "spread_bps": 525,
            },
            {
                "issuer": "ACP Avenu Midco LLC",
                "fund_ticker": "PFLT",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Business Services",
                "invest_type": "Second lien",
                "rate_str": "11.00 %",
                "maturity": "07/2029",
                "cost_mm": 8.0,
                "fv_mm": 7.5,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 550,
            },
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
        family_watchlist_path=family_watchlist_path,
    )

    granite_family = db["families"]["granite"]
    assert granite_family["borrower_count"] == 2
    assert granite_family["fund_count"] == 2
    assert granite_family["total_fv_mm"] == 27.0
    assert granite_family["is_non_accrual_any"] is True
    assert granite_family["is_pik_any"] is True
    assert "Project Granite Buyer, Inc." in granite_family["borrower_names"]
    assert "Project Granite Holdings, LLC" in granite_family["borrower_names"]

    avenu_family = db["families"]["acp avenu"]
    assert avenu_family["borrower_count"] == 2
    assert avenu_family["fund_count"] == 2
    assert avenu_family["total_fv_mm"] == 18.5

    family_watchlist_text = family_watchlist_path.read_text(encoding="utf-8")
    assert "Project Granite Buyer, Inc., Project Granite Holdings, LLC" in family_watchlist_text


def test_build_borrower_db_applies_family_alias_overrides(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    family_watchlist_path = tmp_path / "borrower_family_watchlist.csv"
    alias_path = tmp_path / "borrower_family_aliases.json"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps({"funds": [{"ticker": "ARCC", "manager": "Ares", "type": "listed_bdc"}]}),
        encoding="utf-8",
    )
    alias_path.write_text(
        json.dumps(
                {
                    "borrower_key_overrides": {
                        "alpha buyer": {"family_key": "alpha platform", "family_name": "Alpha Platform"},
                        "beta holdings": {"family_key": "alpha platform", "family_name": "Alpha Platform"},
                    }
                }
            ),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "ARCC_2025-12-31.json",
        [
            {
                "issuer": "Alpha Buyer, Inc.",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "9.5 %",
                "maturity": "03/2029",
                "cost_mm": 10.0,
                "fv_mm": 9.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 475,
            },
            {
                "issuer": "Beta Holdings, LLC",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "Equity",
                "rate_str": "",
                "maturity": "",
                "cost_mm": 3.0,
                "fv_mm": 2.5,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": None,
            },
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
        family_watchlist_path=family_watchlist_path,
        family_alias_path=alias_path,
    )

    family = db["families"]["alpha platform"]
    assert family["family_name"] == "Alpha Platform"
    assert family["borrower_count"] == 2
    assert family["total_fv_mm"] == 11.5
    assert db["meta"]["family_alias_count"] == 2
    assert db["meta"]["family_alias_matched_count"] == 2
    assert db["meta"]["family_alias_unmatched_count"] == 0
    assert db["meta"]["family_alias_unmatched_keys"] == []


def test_build_borrower_db_reports_unmatched_family_alias_keys(tmp_path: Path) -> None:
    cache_dir = tmp_path / "portfolio_cache"
    cache_dir.mkdir()
    output_path = tmp_path / "borrower_db.json"
    watchlist_path = tmp_path / "borrower_watchlist.csv"
    family_watchlist_path = tmp_path / "borrower_family_watchlist.csv"
    alias_path = tmp_path / "borrower_family_aliases.json"
    universe_path = tmp_path / "bdc_universe.json"

    universe_path.write_text(
        json.dumps({"funds": [{"ticker": "ARCC", "manager": "Ares", "type": "listed_bdc"}]}),
        encoding="utf-8",
    )
    alias_path.write_text(
        json.dumps(
            {
                "borrower_key_overrides": {
                    "alpha buyer": {"family_key": "alpha platform", "family_name": "Alpha Platform"},
                    "missing borrower": {"family_key": "missing platform", "family_name": "Missing Platform"},
                }
            }
        ),
        encoding="utf-8",
    )

    _write_json(
        cache_dir / "ARCC_2025-12-31.json",
        [
            {
                "issuer": "Alpha Buyer, Inc.",
                "fund_ticker": "ARCC",
                "period": "2025-12-31",
                "filing_type": "10-K",
                "industry": "Software",
                "invest_type": "First lien",
                "rate_str": "9.5 %",
                "maturity": "03/2029",
                "cost_mm": 10.0,
                "fv_mm": 9.0,
                "is_pik": False,
                "is_non_accrual": False,
                "spread_bps": 475,
            },
        ],
    )

    db = build_borrower_db(
        cache_dir=cache_dir,
        output_path=output_path,
        universe_path=universe_path,
        watchlist_path=watchlist_path,
        family_watchlist_path=family_watchlist_path,
        family_alias_path=alias_path,
    )

    assert db["meta"]["family_alias_count"] == 2
    assert db["meta"]["family_alias_matched_count"] == 1
    assert db["meta"]["family_alias_unmatched_count"] == 1
    assert db["meta"]["family_alias_unmatched_keys"] == ["missing borrower"]


def test_write_family_review_candidates_exports_merge_and_split_rows(tmp_path: Path) -> None:
    merge_path = tmp_path / "merge.csv"
    split_path = tmp_path / "split.csv"

    rows = write_family_review_candidates(
        {"family_review": _sample_family_review()},
        merge_output_path=merge_path,
        split_output_path=split_path,
    )

    assert len(rows["merge_candidates"]) == 2
    assert len(rows["split_candidates"]) == 2

    merge_text = merge_path.read_text(encoding="utf-8")
    split_text = split_path.read_text(encoding="utf-8")

    assert "Alpha OpCo" in merge_text
    assert "Gamma Family" in split_text


def test_review_token_signature_drops_generic_industry_words() -> None:
    assert _review_token_signature("X4 Pharmaceuticals, Inc.") == set()
    assert _review_token_signature("Higginbotham Insurance Agency, Inc.") == {"agency", "higginbotham"}
