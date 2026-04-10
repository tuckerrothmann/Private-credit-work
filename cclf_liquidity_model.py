"""
CCLFX Liquidity Scenario Model
================================
Quarterly cash-flow and NAV scenario engine for Cliffwater Corporate Lending Fund
(CCLFX) and comparable interval-fund / BDC vehicles.

Model architecture
------------------
Each quarter the engine applies the following mechanics, in order:

  1. Income:  gross investment income on total portfolio (NAV + debt), split between
              cash income and PIK (non-cash accrual).
  2. Costs:   interest expense on all borrowings; management fee and other expenses
              charged on NAV.
  3. NII:     net investment income on accrual basis (NAV impact, includes PIK) and
              on a cash basis (cash impact, excludes PIK).
  4. Flows:   distributions paid to investors; redemption / tender outflows; new
              subscription inflows; scheduled portfolio repayments; unfunded-
              commitment draws by borrowers.
  5. Facility: revolving credit is drawn if cash falls below min_cash_buffer;
              excess cash repays the facility.
  6. Losses:  credit losses reduce NAV (accounting write-down, no cash effect).
  7. NAV:     updated for all accrual-basis items above.

Key calibration (CCLFX Annual Report, year ended March 31, 2025)
-----------------------------------------------------------------
  nav_start               $28.1 billion
  starting_cash            $0.297 billion  (balance sheet)
  senior_notes             $5.65 billion
  senior_credit_outstanding $1.19 billion
  portfolio_yield           8.8 %  total investment income $2,992M / gross assets ~$34B
  borrowing_cost_rate       5.4 %  total interest expense  ~$726M / avg debt  ~$6.8B
  management_fee_rate       0.8 %  management fees $226M / NAV $28.1B
  other_expense_rate        0.2 %  admin, legal, custody (approx.)
  distribution_rate        10.75% (per shareholder letter)

Material improvements over prior version
-----------------------------------------
  * Interest expense and management fees are modelled explicitly.  Omitting them
    overstated quarterly cash generation by roughly $250–300 million on a fund of
    this size.
  * portfolio_yield is applied to gross assets (NAV + total debt), not just NAV.
    This matches how total investment income is reported and avoids systematically
    overstating income as leverage falls.
  * PIK income is tracked separately: it accretes NAV via the NII line but is
    excluded from the cash NII figure that drives the bank account.
  * subscription_rate and redemption_rate are modelled as distinct parameters.
    Setting subscription_rate = 0 produces a run-off / wind-down stress scenario;
    matching it to redemption_rate approximates a steady-state fund.
  * All annual-rate-to-quarterly conversions use consistent geometric compounding.
    Management fees and other expenses use simple linear accrual (/ 4) because
    they are daily-accruing, not compound, in practice.
  * summarize() now correctly detects the first covenant-breach quarter.
  * The redundant min() in the unfunded-draw calculation has been removed.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Rate conversion helpers
# ---------------------------------------------------------------------------

def quarterly_rate(annual_rate: float) -> float:
    """Convert an annual compound rate to its geometric quarterly equivalent.

    Example: 8.8% annual → (1.088 ** 0.25) − 1 ≈ 2.136% per quarter.
    Used for portfolio_yield, borrowing_cost_rate, annual_default_rate, and
    distribution_rate — all of which represent compound economic returns.
    """
    return (1.0 + annual_rate) ** 0.25 - 1.0


def quarterly_fee_rate(annual_rate: float) -> float:
    """Convert an annual fee rate to a quarterly rate by simple division.

    Management and other expense fees accrue on a daily basis (not compound), so
    simple /4 is the correct quarterly approximation.
    """
    return annual_rate / 4.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _validate_bounded_rate(name: str, value: float, lo: float = 0.0, hi: float = 1.0) -> None:
    if not lo <= value <= hi:
        raise ValueError(f"{name}={value!r} is outside the valid range [{lo}, {hi}]")


@dataclass
class ScenarioConfig:
    """Full parameter set for one liquidity scenario run.

    All rates stored as annualised decimals (e.g. 0.10 = 10 %).
    *Exception*: redemption_rate and subscription_rate are expressed as quarterly
    fractions (consistent with the formal quarterly repurchase programme).

    Fields labelled with '# quarterly' are used directly without conversion.
    All others are converted to quarterly equivalents inside run_scenario().
    """

    name: str = "Baseline"

    # ── Balance-sheet starting points ───────────────────────────────────────
    nav_start: float = 28.1e9
    """Starting net asset value ($).  Calibrated to CCLFX FY2025 annual report."""

    senior_notes: float = 5.65e9
    """Outstanding term notes / bonds ($)."""

    senior_credit_outstanding: float = 1.19e9
    """Revolving credit facility drawn at inception ($)."""

    senior_credit_limit: float = 2.5e9
    """Total revolving credit facility capacity ($)."""

    unfunded_commitments: float = 4.0e9
    """Undrawn loan commitments the fund is obligated to fund on borrower request ($)."""

    starting_cash: float = 0.297e9
    """Cash and cash equivalents at period start ($).  Calibrated to FY2025 balance sheet."""

    min_cash_buffer: float = 0.0
    """Minimum desired cash level; revolving facility is drawn if cash falls below this ($)."""

    max_leverage: float = 2.0
    """Debt-to-equity ceiling for covenant-breach detection.
    The 1940 Act requires ≥ 150 % asset coverage (≈ 2.0 × debt-to-equity) for
    registered closed-end funds.  Current CCLFX leverage is ~0.24 ×, far below this."""

    # ── Income and cost rates (annual decimals) ──────────────────────────────
    portfolio_yield: float = 0.088
    """Total investment income as a fraction of gross assets (NAV + total debt) per year.
    Calibrated to CCLFX FY2025: $2,992 M income / ~$34 B gross assets ≈ 8.8 %.
    Note: this includes distributions received from private investment vehicles held
    in the portfolio (~$847 M in FY2025), which are genuine cash receipts."""

    borrowing_cost_rate: float = 0.054
    """Blended annual cost of senior notes + revolving credit facility.
    Calibrated to FY2025: ~$726 M total interest / ~$6.84 B average debt ≈ 5.4 %.
    Applied to the total debt balance each quarter using geometric quarterly conversion."""

    management_fee_rate: float = 0.008
    """Annual management fee as a fraction of NAV.  FY2025: $226 M / $28.1 B ≈ 0.8 %.
    Accrues linearly; converted to quarterly by simple division."""

    other_expense_rate: float = 0.002
    """Other annual operating expenses (admin, legal, custody, transfer agent) as a
    fraction of NAV.  Estimated at ~0.2 % from FY2025 disclosures.
    Accrues linearly; converted to quarterly by simple division."""

    pik_income_fraction: float = 0.03
    """Fraction of gross investment income that is PIK (payment-in-kind, non-cash).
    PIK accretes to loan principal and therefore increases NAV, but does not generate
    cash.  CCLFX FY2025: $70 M PIK / ~$2,992 M total income ≈ 2.3 %; 3 % used as a
    modest forward-looking allowance.  Stressed scenarios should assume higher PIK."""

    # ── Portfolio dynamics ───────────────────────────────────────────────────
    scheduled_repayment_rate: float = 0.03
    """Fraction of NAV returned as principal each quarter from maturing / amortising loans.
    Expressed as a quarterly rate (used directly, not converted).
    Repayments are a balance-sheet rearrangement (loan → cash); no NAV impact at par."""

    annual_default_rate: float = 0.02
    """Annual portfolio default rate (fraction of NAV).  2 % ≈ normal credit environment;
    GFC / COVID analogs range from 6 –10 %+.  Converted to quarterly geometric rate."""

    loss_given_default: float = 0.35
    """Expected loss on a defaulted position.  35 % is consistent with senior secured
    middle-market lending experience.  Stressed scenarios: 45 – 55 %."""

    # ── Investor flow rates ─────────────────────────────────────────────────
    distribution_rate: float = 0.1075
    """Annual distribution yield paid to investors (fraction of NAV per year).
    CCLFX FY2025 average: 10.75 %.  Converted to quarterly geometric rate."""

    redemption_rate: float = 0.05
    """Quarterly investor redemption / tender rate (fraction of NAV — quarterly, used directly).
    CCLFX offers a formal quarterly repurchase programme of up to 5 % of NAV.
    Bloomberg data (Q1 2026): redemptions reached ~8 % of NAV in a single quarter."""

    subscription_rate: float = 0.0
    """Quarterly new-investor subscription inflow (fraction of NAV — quarterly, used directly).
    Set to 0 for a pure run-off / wind-down stress test.
    Historical peak (2024): ~10 –13 % per quarter.  Q1 2026 Bloomberg: ~5.5 %."""

    unfunded_draw_rate: float = 0.10
    """Fraction of remaining unfunded commitments drawn per quarter by borrowers.
    Expressed as a quarterly rate (used directly).  Stressed scenarios: 15 – 20 %."""

    # ── Simulation control ──────────────────────────────────────────────────
    quarters: int = 8
    """Number of quarters to project."""

    # ── Backward-compatibility property ────────────────────────────────────
    @property
    def tender_rate(self) -> float:
        """Alias for redemption_rate (legacy parameter name)."""
        return self.redemption_rate

    # ── Construction helpers ────────────────────────────────────────────────
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioConfig":
        """Construct from a dict, ignoring unknown keys.

        Supports the legacy ``tender_rate`` key, mapping it to ``redemption_rate``.
        """
        payload: dict[str, Any] = dict(data)
        # Remap legacy key
        if "tender_rate" in payload:
            if "redemption_rate" not in payload:
                payload["redemption_rate"] = payload.pop("tender_rate")
            else:
                payload.pop("tender_rate")
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in known})

    def validate(self) -> "ScenarioConfig":
        """Raise ValueError for any out-of-range parameter.  Returns self for chaining."""
        _validate_bounded_rate("portfolio_yield", self.portfolio_yield, 0.0, 0.5)
        _validate_bounded_rate("borrowing_cost_rate", self.borrowing_cost_rate, 0.0, 0.5)
        _validate_bounded_rate("management_fee_rate", self.management_fee_rate, 0.0, 0.2)
        _validate_bounded_rate("other_expense_rate", self.other_expense_rate, 0.0, 0.1)
        _validate_bounded_rate("pik_income_fraction", self.pik_income_fraction, 0.0, 1.0)
        _validate_bounded_rate("scheduled_repayment_rate", self.scheduled_repayment_rate, 0.0, 1.0)
        _validate_bounded_rate("annual_default_rate", self.annual_default_rate, 0.0, 1.0)
        _validate_bounded_rate("loss_given_default", self.loss_given_default, 0.0, 1.0)
        _validate_bounded_rate("distribution_rate", self.distribution_rate, 0.0, 1.0)
        _validate_bounded_rate("redemption_rate", self.redemption_rate, 0.0, 1.0)
        _validate_bounded_rate("subscription_rate", self.subscription_rate, 0.0, 1.0)
        _validate_bounded_rate("unfunded_draw_rate", self.unfunded_draw_rate, 0.0, 1.0)
        if self.nav_start <= 0:
            raise ValueError(f"nav_start must be positive; got {self.nav_start}")
        if self.senior_credit_outstanding > self.senior_credit_limit:
            raise ValueError(
                f"senior_credit_outstanding ({self.senior_credit_outstanding:,.0f}) "
                f"exceeds senior_credit_limit ({self.senior_credit_limit:,.0f})"
            )
        if self.quarters < 1:
            raise ValueError(f"quarters must be ≥ 1; got {self.quarters}")
        return self


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def run_scenario(cfg: ScenarioConfig) -> list[dict[str, Any]]:
    """Run a quarterly liquidity simulation and return a list of per-quarter row dicts.

    All monetary output columns carry the ``_Bn`` suffix and are in billion dollars.
    Leverage is reported as a pure ratio with the ``_x`` suffix.

    Simulation mechanics within each quarter
    -----------------------------------------
    1.  Gross income on total portfolio (NAV + debt), split cash / PIK.
    2.  Interest expense on total debt (geometric quarterly rate).
    3.  Management fee + other expenses on NAV (simple quarterly rate).
    4.  Net investment income: accrual basis (includes PIK) for NAV;
        cash basis (excludes PIK) for bank account.
    5.  Distributions paid to investors (cash out, NAV down).
    6.  Redemptions / tenders (cash out, NAV down).
    7.  New subscriptions (cash in, NAV up).
    8.  Scheduled portfolio repayments (cash in; NAV unchanged — balance-sheet swap).
    9.  Unfunded commitment draws by borrowers (cash out; NAV unchanged at par).
    10. Revolving facility: draw if cash < min_cash_buffer; repay if excess cash.
    11. Credit losses (NAV down; no cash effect — accounting write-down).
    12. NAV updated; end-of-quarter diagnostics computed.

    Reinvestment assumption
    -----------------------
    Scheduled repayments and subscription inflows are assumed to be redeployed into
    new loans at the same portfolio_yield within the quarter.  This is captured
    implicitly: gross_portfolio = nav + total_debt uses the beginning-of-quarter
    NAV (which includes the prior quarter's repayments and subscriptions already).
    Explicitly modelling uninvested cash drag would require tracking the split
    between income-earning assets and idle cash — out of scope for this model.
    """
    cfg.validate()

    # ── Pre-loop rate conversions ─────────────────────────────────────────
    # Compound (geometric) quarterly rates for economic returns
    q_yield       = quarterly_rate(cfg.portfolio_yield)
    q_borrow      = quarterly_rate(cfg.borrowing_cost_rate)
    q_default     = quarterly_rate(cfg.annual_default_rate)
    q_dist        = quarterly_rate(cfg.distribution_rate)
    # Linear (simple) quarterly rates for fees
    q_mgmt        = quarterly_fee_rate(cfg.management_fee_rate)
    q_other       = quarterly_fee_rate(cfg.other_expense_rate)
    # Quarterly rates used directly (already expressed per quarter)
    q_redemption  = cfg.redemption_rate
    q_subscription = cfg.subscription_rate
    q_repayment   = cfg.scheduled_repayment_rate
    q_draw        = cfg.unfunded_draw_rate

    # ── Mutable state ─────────────────────────────────────────────────────
    nav               = cfg.nav_start
    cash              = cfg.starting_cash
    facility          = cfg.senior_credit_outstanding
    unfunded_remaining = cfg.unfunded_commitments

    rows: list[dict[str, Any]] = []

    for quarter in range(1, cfg.quarters + 1):
        cash_bop = cash  # beginning-of-period cash (for net_cash_change)

        # ── 1. Income and costs ───────────────────────────────────────────
        total_debt    = facility + cfg.senior_notes
        gross_assets  = nav + total_debt          # total deployed portfolio (approx)

        gross_income  = gross_assets * q_yield    # total investment income
        pik_income    = gross_income * cfg.pik_income_fraction
        cash_income   = gross_income - pik_income # only cash income reaches the bank

        interest_expense = total_debt * q_borrow
        fees             = nav * (q_mgmt + q_other)  # management fee + other on NAV
        total_costs      = interest_expense + fees

        # NII: accrual basis (PIK included) flows to NAV; cash basis flows to bank
        nii_accrual = gross_income - total_costs
        nii_cash    = cash_income  - total_costs

        # ── 2. Investor flows and portfolio events ────────────────────────
        distributions        = nav * q_dist
        redemptions          = nav * q_redemption
        subscriptions        = nav * q_subscription
        scheduled_repayments = nav * q_repayment

        # Unfunded commitment draw — borrowers request capital
        unfunded_draw      = unfunded_remaining * q_draw
        unfunded_remaining = max(0.0, unfunded_remaining - unfunded_draw)

        # ── 3. Net cash change (pre-facility) ────────────────────────────
        # Inflows:  cash NII, repayments of maturing loans, new subscriptions
        # Outflows: distributions, redemptions, unfunded draws
        # Note: credit losses are *not* a cash event (write-down only)
        net_operating_cash = (nii_cash
                              + scheduled_repayments
                              + subscriptions
                              - distributions
                              - redemptions
                              - unfunded_draw)
        cash += net_operating_cash

        # ── 4. Revolving facility management ─────────────────────────────
        facility_draw  = 0.0
        facility_repay = 0.0
        headroom_bop   = cfg.senior_credit_limit - facility

        if cash < cfg.min_cash_buffer and headroom_bop > 1e-9:
            needed       = cfg.min_cash_buffer - cash
            facility_draw = min(needed, headroom_bop)
            facility     += facility_draw
            cash         += facility_draw

        elif cash > cfg.min_cash_buffer and facility > 1e-9:
            excess         = cash - cfg.min_cash_buffer
            facility_repay = min(excess, facility)
            facility      -= facility_repay
            cash          -= facility_repay

        # ── 5. Credit losses (NAV write-down, no cash effect) ────────────
        credit_losses = nav * q_default * cfg.loss_given_default

        # ── 6. NAV update ────────────────────────────────────────────────
        # + nii_accrual   gross income (incl. PIK) minus expenses
        # + subscriptions new shares issued at NAV (cash in, NAV up equally)
        # - distributions income/capital returned to investors
        # - redemptions   shares repurchased at NAV
        # - credit_losses accounting write-down of impaired loans
        # Note: scheduled_repayments and unfunded_draws are balance-sheet
        #       rearrangements at par → no NAV effect.
        nav = nav + nii_accrual + subscriptions - distributions - redemptions - credit_losses
        nav = max(0.0, nav)

        # ── 7. End-of-quarter diagnostics ────────────────────────────────
        total_debt_eop  = facility + cfg.senior_notes
        headroom_eop    = cfg.senior_credit_limit - facility
        leverage        = total_debt_eop / nav if nav > 0.0 else math.inf
        net_cash_change = cash - cash_bop

        liquidity_shortfall = cash < cfg.min_cash_buffer - 1e-9
        covenant_breach     = (not math.isinf(leverage)) and (leverage > cfg.max_leverage)

        rows.append({
            "Quarter":                  quarter,
            "NAV_Bn":                   nav / 1e9,
            "Cash_Bn":                  cash / 1e9,
            "Gross_Income_Bn":          gross_income / 1e9,
            "PIK_Income_Bn":            pik_income / 1e9,
            "Interest_Expense_Bn":      interest_expense / 1e9,
            "Fees_Bn":                  fees / 1e9,
            "NII_Bn":                   nii_accrual / 1e9,
            "NII_Cash_Bn":              nii_cash / 1e9,
            "Distributions_Bn":         distributions / 1e9,
            "Subscriptions_Bn":         subscriptions / 1e9,
            "Redemptions_Bn":           redemptions / 1e9,
            "Net_Flows_Bn":             (subscriptions - redemptions) / 1e9,
            "Credit_Losses_Bn":         credit_losses / 1e9,
            "Scheduled_Repayments_Bn":  scheduled_repayments / 1e9,
            "Unfunded_Draw_Bn":         unfunded_draw / 1e9,
            "Facility_Out_Bn":          facility / 1e9,
            "Facility_Draw_Bn":         facility_draw / 1e9,
            "Facility_Repay_Bn":        facility_repay / 1e9,
            "Headroom_Bn":              headroom_eop / 1e9,
            "Total_Debt_Bn":            total_debt_eop / 1e9,
            "Net_Cash_Change_Bn":       net_cash_change / 1e9,
            "Leverage_x":               leverage,
            "Liquidity_Shortfall":      liquidity_shortfall,
            "Covenant_Breach":          covenant_breach,
        })

    return rows


# ---------------------------------------------------------------------------
# Summary and I/O
# ---------------------------------------------------------------------------

def summarize(rows: list[dict[str, Any]]) -> dict[str, float | str]:
    """Compute a concise summary dict from a list of per-quarter row dicts.

    Safe to call with rows produced either directly by run_scenario() or via
    ``pd.DataFrame(run_scenario(cfg)).to_dict(orient='records')``; bool columns
    are coerced with bool() to handle numpy.bool_ instances.
    """
    if not rows:
        raise ValueError("Cannot summarize an empty row set.")

    finite_leverages = [
        r["Leverage_x"] for r in rows if not math.isinf(float(r["Leverage_x"]))
    ]

    total_nii_cash      = sum(r["NII_Cash_Bn"] for r in rows)
    total_distributions = sum(r["Distributions_Bn"] for r in rows)
    nii_coverage = (
        total_nii_cash / total_distributions if total_distributions > 0 else math.inf
    )

    return {
        "min_cash_bn":                    min(r["Cash_Bn"] for r in rows),
        "ending_cash_bn":                 rows[-1]["Cash_Bn"],
        "ending_nav_bn":                  rows[-1]["NAV_Bn"],
        "max_facility_utilization_bn":    max(r["Facility_Out_Bn"] for r in rows),
        "min_headroom_bn":                min(r["Headroom_Bn"] for r in rows),
        "peak_leverage_x":                max(finite_leverages) if finite_leverages else math.inf,
        "first_liquidity_shortfall_quarter": next(
            (r["Quarter"] for r in rows if bool(r["Liquidity_Shortfall"])), "none"
        ),
        "first_covenant_breach_quarter": next(
            (r["Quarter"] for r in rows if bool(r["Covenant_Breach"])), "none"
        ),
        "cumulative_nii_cash_bn":         round(total_nii_cash, 4),
        "cumulative_distributions_bn":    round(total_distributions, 4),
        "cumulative_credit_losses_bn":    round(sum(r["Credit_Losses_Bn"] for r in rows), 4),
        "cumulative_net_flows_bn":        round(sum(r["Net_Flows_Bn"] for r in rows), 4),
        "nii_distribution_coverage":      round(nii_coverage, 4),
    }


def find_breakeven_distribution_rate(
    cfg: ScenarioConfig,
    precision: float = 1e-4,
) -> float:
    """Find the annual distribution rate at which cumulative cash NII exactly covers
    cumulative distributions over the scenario horizon.

    Uses bisection on [0, cfg.distribution_rate].  The result is the highest
    distribution rate the fund can sustain purely from investment income — no
    dependence on subscription inflows, portfolio repayments, or facility draws.

    Returns
    -------
    float
        Annual distribution rate (decimal) where NII coverage = 1.0.
        If coverage is already ≥ 1.0 at the current rate, returns cfg.distribution_rate.
        If even a near-zero distribution rate can't be covered (extreme stress),
        returns 0.0.
    """
    from dataclasses import replace as _replace

    def _coverage(rate: float) -> float:
        rows = run_scenario(_replace(cfg, distribution_rate=max(rate, 1e-6)))
        s = summarize(rows)
        dist = s["cumulative_distributions_bn"]
        return s["cumulative_nii_cash_bn"] / dist if dist > 0 else math.inf

    # Already covered at current rate — no gap to close
    if _coverage(cfg.distribution_rate) >= 1.0:
        return cfg.distribution_rate

    lo, hi = 1e-4, cfg.distribution_rate

    # Verify lo gives coverage > 1.0 (extremely stressed scenarios may not)
    if _coverage(lo) < 1.0:
        return 0.0

    for _ in range(60):
        if hi - lo < precision:
            break
        mid = (lo + hi) / 2.0
        if _coverage(mid) > 1.0:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2.0


def save_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write scenario output rows to a CSV file."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def load_scenarios(path: Path) -> list[ScenarioConfig]:
    """Load scenarios from a JSON file.

    Supports both a bare list ``[{...}, ...]`` and the wrapped form
    ``{"scenarios": [{...}, ...], "metadata": {...}}``.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = data["scenarios"] if isinstance(data, dict) else data
    return [ScenarioConfig.from_dict(item) for item in items]


def run_scenarios(
    scenarios: list[ScenarioConfig],
    output_dir: Path = Path("."),
    print_tables: bool = True,
) -> None:
    """Run all scenarios, print tables, and write output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_rows    = [run_scenario(cfg) for cfg in scenarios]
    summaries   = [summarize(rows) for rows in all_rows]

    if print_tables:
        for cfg, rows, summary in zip(scenarios, all_rows, summaries):
            print(f"\n{'=' * 70}")
            print(f"Scenario: {cfg.name}")
            print(f"{'=' * 70}")
            header = (f"{'Q':>3}  {'NAV':>8}  {'Cash':>9}  {'NII':>8}  "
                      f"{'Dist':>8}  {'Subs':>7}  {'Redm':>7}  "
                      f"{'Losses':>8}  {'Lev':>6}")
            print(header)
            print("-" * len(header))
            for r in rows:
                print(
                    f"{r['Quarter']:>3}  "
                    f"{r['NAV_Bn']:>8.2f}  "
                    f"{r['Cash_Bn']:>9.3f}  "
                    f"{r['NII_Bn']:>8.3f}  "
                    f"{r['Distributions_Bn']:>8.3f}  "
                    f"{r['Subscriptions_Bn']:>7.3f}  "
                    f"{r['Redemptions_Bn']:>7.3f}  "
                    f"{r['Credit_Losses_Bn']:>8.3f}  "
                    f"{r['Leverage_x']:>6.3f}"
                    + ("  [SHORTFALL]" if r["Liquidity_Shortfall"] else "")
                    + ("  [COVENANT]" if r["Covenant_Breach"] else "")
                )
            print(f"\nSummary: {summary}")

    # Per-scenario CSVs
    for cfg, rows in zip(scenarios, all_rows):
        slug = cfg.name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        save_csv(rows, output_dir / f"{slug}_projection.csv")

    # Cross-scenario summary CSV
    summary_rows = [{"scenario": cfg.name, **s} for cfg, s in zip(scenarios, summaries)]
    with (output_dir / "scenario_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)

    # Effective scenario configs (for audit trail)
    effective = [asdict(cfg) for cfg in scenarios]
    (output_dir / "effective_scenarios.json").write_text(
        json.dumps(effective, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if print_tables:
        print(f"\nWrote {len(scenarios)} scenario(s) to {output_dir}/")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run CCLFX liquidity scenarios.")
    parser.add_argument(
        "--scenarios",
        default="scenarios/default_scenarios.json",
        help="Path to scenarios JSON (default: scenarios/default_scenarios.json)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write output CSV files (default: current directory)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress table output; write files only.",
    )
    args = parser.parse_args()

    path = Path(args.scenarios)
    if not path.exists():
        parser.error(f"Scenarios file not found: {path}")

    scenarios = load_scenarios(path)
    run_scenarios(scenarios, output_dir=Path(args.output_dir), print_tables=not args.quiet)


if __name__ == "__main__":
    main()
