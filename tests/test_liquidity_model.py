"""
Comprehensive test suite for cclf_liquidity_model.py.

Tests are grouped by domain:
  - quarterly_rate() and quarterly_fee_rate() helpers
  - Interest expense mechanics
  - Fee drag mechanics
  - PIK income (accrual vs. cash split)
  - Subscription / redemption flows
  - Credit loss mechanics
  - Unfunded commitment draw pool
  - Revolving facility draw and repay
  - Leverage and covenant breach
  - Liquidity shortfall detection
  - summarize() — including covenant breach fix and new metrics
  - ScenarioConfig validation and construction
  - File I/O: run_scenarios(), load_scenarios()
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any
import unittest

from cclf_liquidity_model import (
    ScenarioConfig,
    load_scenarios,
    quarterly_fee_rate,
    quarterly_rate,
    run_scenario,
    run_scenarios,
    summarize,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides: Any) -> ScenarioConfig:
    """Return a minimal, all-zero-rate config so each test can isolate one mechanic.

    nav_start=$10B, starting_cash=$1B, senior_notes=$2B, facility=$0.5B out of $3B,
    all rates zeroed unless explicitly overridden.
    """
    defaults: dict[str, Any] = dict(
        name="Test",
        nav_start=10e9,
        senior_notes=2e9,
        senior_credit_outstanding=0.5e9,
        senior_credit_limit=3.0e9,
        unfunded_commitments=0.0,
        starting_cash=1.0e9,
        min_cash_buffer=0.0,
        max_leverage=5.0,
        quarters=1,
        portfolio_yield=0.0,
        borrowing_cost_rate=0.0,
        management_fee_rate=0.0,
        other_expense_rate=0.0,
        pik_income_fraction=0.0,
        scheduled_repayment_rate=0.0,
        annual_default_rate=0.0,
        loss_given_default=0.4,
        distribution_rate=0.0,
        redemption_rate=0.0,
        subscription_rate=0.0,
        unfunded_draw_rate=0.0,
    )
    defaults.update(overrides)
    return ScenarioConfig(**defaults)


def _run1(**overrides: Any) -> dict[str, Any]:
    """Run for 1 quarter and return the single row dict."""
    return run_scenario(_cfg(**overrides))[0]


# ---------------------------------------------------------------------------
# quarterly_rate() and quarterly_fee_rate()
# ---------------------------------------------------------------------------

class TestQuarterlyRate(unittest.TestCase):
    def test_zero_annual_rate_gives_zero_quarterly(self) -> None:
        self.assertAlmostEqual(quarterly_rate(0.0), 0.0)

    def test_geometric_round_trips_to_annual(self) -> None:
        """(1 + q)^4 should equal (1 + r) for any annual rate r."""
        for r in (0.02, 0.08, 0.12, 0.20):
            q = quarterly_rate(r)
            self.assertAlmostEqual((1 + q) ** 4, 1 + r, places=10,
                                   msg=f"Round-trip failed for r={r}")

    def test_geometric_exceeds_simple_for_positive_rates(self) -> None:
        """Geometric quarterly < annual/4 (geometric discounts future cash-flows)."""
        for r in (0.02, 0.08, 0.15):
            self.assertLess(quarterly_rate(r), r / 4,
                            msg=f"Geometric should be < simple for r={r}")

    def test_quarterly_fee_rate_is_simple_division(self) -> None:
        self.assertAlmostEqual(quarterly_fee_rate(0.08), 0.02)
        self.assertAlmostEqual(quarterly_fee_rate(0.0), 0.0)


# ---------------------------------------------------------------------------
# Interest expense
# ---------------------------------------------------------------------------

class TestInterestExpense(unittest.TestCase):
    def test_interest_expense_column_present_and_positive(self) -> None:
        row = _run1(borrowing_cost_rate=0.054)
        self.assertIn("Interest_Expense_Bn", row)
        self.assertGreater(row["Interest_Expense_Bn"], 0.0)

    def test_interest_expense_reduces_nii_vs_zero_cost(self) -> None:
        row_cost = _run1(portfolio_yield=0.10, borrowing_cost_rate=0.054)
        row_free = _run1(portfolio_yield=0.10, borrowing_cost_rate=0.0)
        self.assertLess(row_cost["NII_Bn"], row_free["NII_Bn"])

    def test_interest_expense_reduces_cash_nii(self) -> None:
        row_cost = _run1(portfolio_yield=0.10, borrowing_cost_rate=0.054)
        row_free = _run1(portfolio_yield=0.10, borrowing_cost_rate=0.0)
        self.assertLess(row_cost["NII_Cash_Bn"], row_free["NII_Cash_Bn"])

    def test_interest_expense_applied_to_total_debt(self) -> None:
        """Interest_Expense ≈ (senior_notes + facility) × quarterly_rate(borrow_cost)."""
        borrow = 0.054
        row = _run1(borrowing_cost_rate=borrow,
                    senior_notes=2e9, senior_credit_outstanding=0.5e9)
        expected = (2e9 + 0.5e9) * quarterly_rate(borrow) / 1e9
        self.assertAlmostEqual(row["Interest_Expense_Bn"], expected, places=6)


# ---------------------------------------------------------------------------
# Fee drag
# ---------------------------------------------------------------------------

class TestFeeDrag(unittest.TestCase):
    def test_fees_column_present_and_positive(self) -> None:
        row = _run1(management_fee_rate=0.008)
        self.assertIn("Fees_Bn", row)
        self.assertGreater(row["Fees_Bn"], 0.0)

    def test_management_fee_reduces_nii(self) -> None:
        row_fee = _run1(portfolio_yield=0.10, management_fee_rate=0.008)
        row_free = _run1(portfolio_yield=0.10, management_fee_rate=0.0)
        self.assertLess(row_fee["NII_Bn"], row_free["NII_Bn"])

    def test_other_expense_reduces_nii(self) -> None:
        row_exp = _run1(portfolio_yield=0.10, other_expense_rate=0.002)
        row_free = _run1(portfolio_yield=0.10, other_expense_rate=0.0)
        self.assertLess(row_exp["NII_Bn"], row_free["NII_Bn"])

    def test_fee_applied_to_nav_not_gross_assets(self) -> None:
        """Fees = nav × (mgmt + other) / 4 (linear quarterly)."""
        mgmt = 0.008
        row = _run1(management_fee_rate=mgmt, nav_start=10e9)
        expected = 10e9 * quarterly_fee_rate(mgmt) / 1e9
        self.assertAlmostEqual(row["Fees_Bn"], expected, places=6)


# ---------------------------------------------------------------------------
# PIK income
# ---------------------------------------------------------------------------

class TestPIKIncome(unittest.TestCase):
    def test_pik_income_column_present_and_positive(self) -> None:
        row = _run1(portfolio_yield=0.10, pik_income_fraction=0.10)
        self.assertIn("PIK_Income_Bn", row)
        self.assertGreater(row["PIK_Income_Bn"], 0.0)

    def test_pik_accretes_nav_same_as_cash_income(self) -> None:
        """NAV is unaffected by whether income is cash or PIK — both accrete equally."""
        row_pik  = _run1(portfolio_yield=0.10, pik_income_fraction=0.50)
        row_cash = _run1(portfolio_yield=0.10, pik_income_fraction=0.00)
        self.assertAlmostEqual(row_pik["NAV_Bn"], row_cash["NAV_Bn"], places=6)

    def test_pik_reduces_cash_relative_to_all_cash(self) -> None:
        """More PIK means less cash received."""
        row_high_pik = _run1(portfolio_yield=0.10, pik_income_fraction=0.50)
        row_no_pik   = _run1(portfolio_yield=0.10, pik_income_fraction=0.00)
        self.assertLess(row_high_pik["Cash_Bn"], row_no_pik["Cash_Bn"])

    def test_pik_zero_means_nii_equals_nii_cash(self) -> None:
        row = _run1(portfolio_yield=0.10, pik_income_fraction=0.0)
        self.assertAlmostEqual(row["NII_Bn"], row["NII_Cash_Bn"], places=10)

    def test_pik_positive_means_nii_exceeds_nii_cash(self) -> None:
        row = _run1(portfolio_yield=0.10, pik_income_fraction=0.20)
        self.assertGreater(row["NII_Bn"], row["NII_Cash_Bn"])


# ---------------------------------------------------------------------------
# Subscriptions and redemptions
# ---------------------------------------------------------------------------

class TestInvestorFlows(unittest.TestCase):
    def _iso_cfg(self, **kw: Any) -> ScenarioConfig:
        """Zero-income config to isolate flow mechanics from income effects."""
        return _cfg(portfolio_yield=0.0, borrowing_cost_rate=0.0,
                    management_fee_rate=0.0, other_expense_rate=0.0,
                    annual_default_rate=0.0, distribution_rate=0.0, **kw)

    def test_subscriptions_increase_nav_and_cash(self) -> None:
        # Zero outstanding facility so excess cash isn't immediately swept to repay it
        row = run_scenario(self._iso_cfg(
            subscription_rate=0.05, senior_credit_outstanding=0.0,
        ))[0]
        self.assertGreater(row["NAV_Bn"], 10.0)  # started at 10B
        self.assertGreater(row["Cash_Bn"], 1.0)  # started at 1B; nothing to repay

    def test_redemptions_decrease_nav_and_cash(self) -> None:
        row = run_scenario(self._iso_cfg(
            redemption_rate=0.05, senior_credit_outstanding=0.0,
        ))[0]
        self.assertLess(row["NAV_Bn"], 10.0)
        self.assertLess(row["Cash_Bn"], 1.0)

    def test_net_zero_flows_are_nav_and_cash_neutral(self) -> None:
        """When subscription_rate == redemption_rate, no net effect on NAV or cash.

        We zero out the facility so that the facility-repayment sweep (which would
        absorb any positive cash balance) doesn't obscure the result.
        """
        row = run_scenario(self._iso_cfg(
            subscription_rate=0.05, redemption_rate=0.05,
            senior_credit_outstanding=0.0,
        ))[0]
        self.assertAlmostEqual(row["NAV_Bn"], 10.0, places=6)
        self.assertAlmostEqual(row["Cash_Bn"], 1.0, places=6)

    def test_net_flows_column_equals_subs_minus_redemptions(self) -> None:
        row = _run1(subscription_rate=0.06, redemption_rate=0.04)
        expected = row["Subscriptions_Bn"] - row["Redemptions_Bn"]
        self.assertAlmostEqual(row["Net_Flows_Bn"], expected, places=10)

    def test_zero_subscription_rate_yields_zero_subscriptions(self) -> None:
        row = _run1(subscription_rate=0.0)
        self.assertEqual(row["Subscriptions_Bn"], 0.0)


# ---------------------------------------------------------------------------
# Credit losses
# ---------------------------------------------------------------------------

class TestCreditLosses(unittest.TestCase):
    def test_credit_losses_reduce_nav(self) -> None:
        row = _run1(annual_default_rate=0.10, loss_given_default=0.5)
        self.assertLess(row["NAV_Bn"], 10.0)

    def test_credit_losses_do_not_directly_change_cash(self) -> None:
        """Losses are write-downs; they reduce NAV but not the cash account."""
        row_loss = _run1(annual_default_rate=0.10, loss_given_default=0.5)
        row_none = _run1(annual_default_rate=0.0)
        # Both should have the same cash (1B starting) — no cash effect from losses
        self.assertAlmostEqual(row_loss["Cash_Bn"], row_none["Cash_Bn"], places=6)

    def test_credit_losses_column_positive_when_defaults_exist(self) -> None:
        row = _run1(annual_default_rate=0.04, loss_given_default=0.4)
        self.assertGreater(row["Credit_Losses_Bn"], 0.0)

    def test_credit_losses_zero_when_no_defaults(self) -> None:
        row = _run1(annual_default_rate=0.0)
        self.assertEqual(row["Credit_Losses_Bn"], 0.0)


# ---------------------------------------------------------------------------
# Unfunded commitments
# ---------------------------------------------------------------------------

class TestUnfundedCommitments(unittest.TestCase):
    def test_unfunded_draw_reduces_remaining_pool(self) -> None:
        cfg = _cfg(unfunded_commitments=1e9, unfunded_draw_rate=0.10, quarters=2)
        rows = run_scenario(cfg)
        # Second-quarter draw must be smaller (pool shrunk)
        self.assertGreater(rows[0]["Unfunded_Draw_Bn"], rows[1]["Unfunded_Draw_Bn"])

    def test_unfunded_draw_depletes_cash(self) -> None:
        """Drawing unfunded commitments is a cash outflow for the fund."""
        row_draw = _run1(unfunded_commitments=2e9, unfunded_draw_rate=0.20)
        row_none = _run1(unfunded_commitments=0.0)
        self.assertLess(row_draw["Cash_Bn"], row_none["Cash_Bn"])

    def test_zero_unfunded_commitments_produces_zero_draw(self) -> None:
        row = _run1(unfunded_commitments=0.0, unfunded_draw_rate=0.25)
        self.assertEqual(row["Unfunded_Draw_Bn"], 0.0)


# ---------------------------------------------------------------------------
# Revolving facility
# ---------------------------------------------------------------------------

class TestFacilityMechanics(unittest.TestCase):
    def test_facility_drawn_when_cash_below_min_buffer(self) -> None:
        # Start with no cash, min_buffer = 2B, plenty of headroom
        row = _run1(starting_cash=0.0, min_cash_buffer=2.0e9,
                    senior_credit_outstanding=0.0, senior_credit_limit=5.0e9,
                    portfolio_yield=0.0)
        self.assertGreater(row["Facility_Draw_Bn"], 0.0)

    def test_facility_repaid_when_excess_cash(self) -> None:
        # Start with lots of cash, facility partially drawn
        row = _run1(starting_cash=5.0e9, senior_credit_outstanding=1.0e9,
                    portfolio_yield=0.0, min_cash_buffer=0.0)
        self.assertGreater(row["Facility_Repay_Bn"], 0.0)

    def test_facility_cannot_exceed_limit(self) -> None:
        row = _run1(starting_cash=0.0, min_cash_buffer=10.0e9,  # large buffer
                    senior_credit_outstanding=0.0, senior_credit_limit=3.0e9,
                    portfolio_yield=0.0)
        self.assertLessEqual(row["Facility_Out_Bn"], 3.0)

    def test_no_facility_draw_when_fully_utilised(self) -> None:
        """No draw available when facility is at limit."""
        row = _run1(starting_cash=0.0, min_cash_buffer=1.0e9,
                    senior_credit_outstanding=3.0e9, senior_credit_limit=3.0e9,
                    portfolio_yield=0.0)
        self.assertEqual(row["Facility_Draw_Bn"], 0.0)
        self.assertTrue(row["Liquidity_Shortfall"])


# ---------------------------------------------------------------------------
# Leverage and covenant breach
# ---------------------------------------------------------------------------

class TestLeverageAndCovenant(unittest.TestCase):
    def test_leverage_equals_total_debt_over_nav(self) -> None:
        row = _run1()
        expected = row["Total_Debt_Bn"] / row["NAV_Bn"]
        self.assertAlmostEqual(row["Leverage_x"], expected, places=8)

    def test_covenant_breach_fires_when_leverage_exceeds_max(self) -> None:
        # Extreme debt relative to nav and a tight covenant
        row = _run1(nav_start=1.0e9, senior_notes=9.0e9, max_leverage=1.0,
                    senior_credit_outstanding=0.0)
        self.assertTrue(row["Covenant_Breach"])

    def test_no_covenant_breach_when_leverage_below_max(self) -> None:
        row = _run1(nav_start=10e9, senior_notes=2e9, max_leverage=5.0,
                    senior_credit_outstanding=0.0)
        self.assertFalse(row["Covenant_Breach"])

    def test_covenant_breach_not_fired_for_inf_leverage(self) -> None:
        """When NAV collapses to zero, leverage is inf — not a numeric breach."""
        cfg = _cfg(nav_start=0.01e9, senior_notes=10e9, max_leverage=1.0,
                   annual_default_rate=1.0, loss_given_default=1.0,
                   portfolio_yield=0.0, distribution_rate=0.0)
        rows = run_scenario(cfg)
        # The covenant_breach should still be well-defined (True or False, not error)
        self.assertIsInstance(rows[-1]["Covenant_Breach"], bool)


# ---------------------------------------------------------------------------
# Liquidity shortfall
# ---------------------------------------------------------------------------

class TestLiquidityShortfall(unittest.TestCase):
    def test_shortfall_when_cash_below_min_buffer_with_full_facility(self) -> None:
        row = _run1(starting_cash=0.0, min_cash_buffer=1.0e9,
                    senior_credit_outstanding=3.0e9, senior_credit_limit=3.0e9,
                    portfolio_yield=0.0)
        self.assertTrue(row["Liquidity_Shortfall"])

    def test_no_shortfall_with_adequate_cash(self) -> None:
        row = _run1(starting_cash=5.0e9, min_cash_buffer=0.0)
        self.assertFalse(row["Liquidity_Shortfall"])


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------

class TestSummarize(unittest.TestCase):
    def _shortfall_at_q2(self) -> list[dict[str, Any]]:
        """Config that maintains Q1 but runs dry in Q2."""
        cfg = _cfg(
            starting_cash=2.0e9,
            min_cash_buffer=0.0,
            portfolio_yield=0.0,
            distribution_rate=0.0,
            redemption_rate=0.50,  # drain 50% of nav each quarter
            senior_credit_outstanding=3.0e9,
            senior_credit_limit=3.0e9,
            quarters=3,
        )
        return run_scenario(cfg)

    def test_summarize_first_shortfall_quarter_detected(self) -> None:
        rows = self._shortfall_at_q2()
        summary = summarize(rows)
        shortfall_q = summary["first_liquidity_shortfall_quarter"]
        self.assertNotEqual(shortfall_q, "none")
        self.assertIsInstance(shortfall_q, int)

    def test_summarize_first_covenant_breach_detected(self) -> None:
        """Key regression: previously summarize() always returned 'none' for covenants."""
        cfg = _cfg(nav_start=1.0e9, senior_notes=9.0e9, max_leverage=1.0,
                   senior_credit_outstanding=0.0, portfolio_yield=0.0,
                   distribution_rate=0.0, quarters=3)
        rows = run_scenario(cfg)
        summary = summarize(rows)
        self.assertNotEqual(summary["first_covenant_breach_quarter"], "none",
                            msg="Covenant breach in every row but summarize() returned 'none'")
        self.assertEqual(summary["first_covenant_breach_quarter"], 1)

    def test_summarize_covenant_breach_from_pandas_dict(self) -> None:
        """summarize() must work on rows round-tripped through pandas (numpy.bool_ columns)."""
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not installed")
        cfg = _cfg(nav_start=1.0e9, senior_notes=9.0e9, max_leverage=1.0,
                   senior_credit_outstanding=0.0, portfolio_yield=0.0)
        df = pd.DataFrame(run_scenario(cfg))
        summary = summarize(df.to_dict(orient="records"))
        self.assertNotEqual(summary["first_covenant_breach_quarter"], "none")

    def test_summarize_no_shortfall_returns_none_string(self) -> None:
        rows = run_scenario(_cfg(starting_cash=10e9))
        summary = summarize(rows)
        self.assertEqual(summary["first_liquidity_shortfall_quarter"], "none")
        self.assertEqual(summary["first_covenant_breach_quarter"], "none")

    def test_summarize_nii_distribution_coverage_present_and_positive(self) -> None:
        rows = run_scenario(_cfg(portfolio_yield=0.10, distribution_rate=0.05))
        summary = summarize(rows)
        self.assertIn("nii_distribution_coverage", summary)
        self.assertGreater(summary["nii_distribution_coverage"], 0.0)

    def test_summarize_coverage_below_one_when_dist_exceeds_nii_cash(self) -> None:
        """Large distribution with small yield should give coverage < 1."""
        rows = run_scenario(_cfg(
            portfolio_yield=0.02,
            distribution_rate=0.15,
            pik_income_fraction=0.0,
            borrowing_cost_rate=0.0,
        ))
        summary = summarize(rows)
        self.assertLess(summary["nii_distribution_coverage"], 1.0)

    def test_summarize_raises_on_empty_rows(self) -> None:
        with self.assertRaises(ValueError):
            summarize([])

    def test_summarize_contains_cumulative_fields(self) -> None:
        rows = run_scenario(_cfg(portfolio_yield=0.08, distribution_rate=0.05, quarters=4))
        summary = summarize(rows)
        for key in ("cumulative_nii_cash_bn", "cumulative_distributions_bn",
                    "cumulative_credit_losses_bn", "cumulative_net_flows_bn"):
            self.assertIn(key, summary)


# ---------------------------------------------------------------------------
# Output column completeness
# ---------------------------------------------------------------------------

class TestOutputColumns(unittest.TestCase):
    EXPECTED_COLUMNS = {
        "Quarter", "NAV_Bn", "Cash_Bn",
        "Gross_Income_Bn", "PIK_Income_Bn", "Interest_Expense_Bn", "Fees_Bn",
        "NII_Bn", "NII_Cash_Bn",
        "Distributions_Bn", "Subscriptions_Bn", "Redemptions_Bn", "Net_Flows_Bn",
        "Credit_Losses_Bn", "Scheduled_Repayments_Bn", "Unfunded_Draw_Bn",
        "Facility_Out_Bn", "Facility_Draw_Bn", "Facility_Repay_Bn",
        "Headroom_Bn", "Total_Debt_Bn", "Net_Cash_Change_Bn",
        "Leverage_x", "Liquidity_Shortfall", "Covenant_Breach",
    }

    def test_all_expected_columns_present(self) -> None:
        rows = run_scenario(_cfg())
        self.assertEqual(set(rows[0].keys()), self.EXPECTED_COLUMNS)

    def test_quarter_count_matches_config(self) -> None:
        for n in (1, 4, 8, 12):
            rows = run_scenario(_cfg(quarters=n))
            self.assertEqual(len(rows), n)
            self.assertEqual(rows[-1]["Quarter"], n)


# ---------------------------------------------------------------------------
# ScenarioConfig validation and construction
# ---------------------------------------------------------------------------

class TestScenarioConfig(unittest.TestCase):
    def test_validate_rejects_portfolio_yield_above_bound(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(portfolio_yield=0.6).validate()

    def test_validate_rejects_negative_redemption_rate(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(redemption_rate=-0.01).validate()

    def test_validate_rejects_pik_fraction_above_one(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(pik_income_fraction=1.5).validate()

    def test_validate_rejects_facility_exceeding_limit(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(senior_credit_outstanding=4e9, senior_credit_limit=3e9).validate()

    def test_validate_rejects_zero_quarters(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(quarters=0).validate()

    def test_validate_rejects_nonpositive_nav(self) -> None:
        with self.assertRaises(ValueError):
            _cfg(nav_start=0.0).validate()

    def test_validate_returns_self_for_chaining(self) -> None:
        cfg = _cfg()
        self.assertIs(cfg.validate(), cfg)

    def test_from_dict_maps_legacy_tender_rate_to_redemption_rate(self) -> None:
        cfg = ScenarioConfig.from_dict({"name": "Legacy", "tender_rate": 0.07})
        self.assertAlmostEqual(cfg.redemption_rate, 0.07)
        # tender_rate is a property, not a dataclass field
        self.assertNotIn("tender_rate", {f.name for f in cfg.__dataclass_fields__.values()})

    def test_from_dict_redemption_rate_takes_priority_over_tender_rate(self) -> None:
        cfg = ScenarioConfig.from_dict({
            "name": "Both", "tender_rate": 0.05, "redemption_rate": 0.08
        })
        self.assertAlmostEqual(cfg.redemption_rate, 0.08)

    def test_from_dict_ignores_unknown_keys(self) -> None:
        cfg = ScenarioConfig.from_dict({
            "name": "Base", "some_future_field": 99.9
        })
        self.assertEqual(cfg.name, "Base")

    def test_tender_rate_property_returns_redemption_rate(self) -> None:
        cfg = _cfg(redemption_rate=0.06)
        self.assertAlmostEqual(cfg.tender_rate, 0.06)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

class TestFileIO(unittest.TestCase):
    def test_run_scenarios_creates_all_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            scenarios = [_cfg(name="Smoke", quarters=2)]
            run_scenarios(scenarios, output_dir=out, print_tables=False)
            self.assertTrue((out / "smoke_projection.csv").exists())
            self.assertTrue((out / "scenario_summary.csv").exists())
            self.assertTrue((out / "effective_scenarios.json").exists())

    def test_run_scenarios_summary_contains_nii_coverage(self) -> None:
        import csv as csv_mod
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            run_scenarios([_cfg(name="Cover", portfolio_yield=0.08,
                               distribution_rate=0.05, quarters=2)],
                          output_dir=out, print_tables=False)
            with (out / "scenario_summary.csv").open(encoding="utf-8") as fh:
                reader = csv_mod.DictReader(fh)
                row = next(reader)
            self.assertIn("nii_distribution_coverage", row)

    def test_load_scenarios_reads_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(
                '{"scenarios": [{"name": "New", "subscription_rate": 0.05, '
                '"borrowing_cost_rate": 0.054, "pik_income_fraction": 0.03}]}',
                encoding="utf-8",
            )
            scenarios = load_scenarios(path)
            self.assertEqual(len(scenarios), 1)
            self.assertAlmostEqual(scenarios[0].subscription_rate, 0.05)
            self.assertAlmostEqual(scenarios[0].borrowing_cost_rate, 0.054)
            self.assertAlmostEqual(scenarios[0].pik_income_fraction, 0.03)

    def test_load_scenarios_supports_legacy_tender_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.json"
            path.write_text(
                '{"scenarios": [{"name": "Old", "tender_rate": 0.05}]}',
                encoding="utf-8",
            )
            scenarios = load_scenarios(path)
            self.assertAlmostEqual(scenarios[0].redemption_rate, 0.05)

    def test_load_scenarios_bare_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bare.json"
            path.write_text('[{"name": "A"}, {"name": "B"}]', encoding="utf-8")
            scenarios = load_scenarios(path)
            self.assertEqual(len(scenarios), 2)


if __name__ == "__main__":
    unittest.main()
