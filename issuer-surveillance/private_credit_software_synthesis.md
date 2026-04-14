# Software Private Credit — PM-Level Synthesis

*A unified view across the issuer universe, lender landscape, and transmission risk to BDC unsecured bonds*

---

## The central argument

Software private credit is not a monolithic risk. It is a **dispersion story** — and the divergence between the best and worst credits in the private-credit software universe is widening in ways that are not yet uniformly visible in published marks, accrual statuses, or BDC portfolio commentary.

The practical implication for BDC unsecured bond investors is this: **the risk is not that software is uniformly bad**. The risk is that the average mark across a BDC's software book may be the average of some very healthy names and some seriously impaired ones — and that the impaired ones may not yet be recognizably impaired in the published schedules.

This memo synthesizes the full issuer universe into a coherent PM-level framework.

---

## The five issuer categories

### Category 1: Live stress — marks and accruals already showing strain
**Medallia** is the clearest current live stress case. BXSL has marked the first-lien loan at **78.3 cents** (Q4 2025 10-K), while FSK marks a comparable position at **99 cents** — a 21-point dispersion that cannot be explained by tranche seniority alone. FSK has also activated a **4.0% PIK tranche** on its holding. The Blackstone mark has drifted from approximately 94 cents (late 2024) to 78 cents (Q4 2025), a trajectory that typically signals operating underperformance, franchise deterioration, or both.

**Key signal:** When two sophisticated institutions mark the same first-lien loan 21 points apart, one of them is more right than the other. BXSL's 78-cent mark represents a $85M unrealized loss against cost. Until that gap closes — either through recovery at FSK's mark or through FSK marking down to BXSL's level — the dispersion is itself the signal.

### Category 2: Completed cycle — private-credit stress, failed takeout, successful refinancing
**Finastra** is the most instructive completed case study in this universe. The $5.3 billion private-credit unitranche (SOFR+725, originated September 2023) went on non-accrual at OBDC by December 31, 2024 — within 15 months of origination. A syndicated takeout attempt in April 2025 failed. In August 2025, a revised $4.195 billion cross-border syndicated loan (S+400 / S+700) fully refinanced the private-credit debt, repaying all unitranche lenders. By Q3 2025, OBDC's remaining Finastra exposure was only the revolving credit facility (~$27.9M).

**What this teaches:** (1) Private-credit non-accrual does not automatically mean permanent loss — the unitranche was repaid at or near par through the syndicated exit. (2) The original SOFR+725 private-credit spread included ~325bps of illiquidity premium over the syndicated clearing rate (S+400) — confirming that private-credit lenders are compensated for complexity and opacity. (3) April 2025 syndicated market demand was insufficient; August 2025 demand was sufficient — a four-month window shifted market appetite materially.

**Parser artifact disclosure:** The portfolio parser initially flagged a $93.5M OBDC entry as non-accrual in Q3 and Q4 2025 current-period data. Investigation confirmed this was prior-year (December 31, 2024) comparison-column data extracted from the iXBRL SOI tables — the non-accrual was real for that prior period but was resolved by the August 2025 refinancing. Diagnostics: FV above cost (100.9¢ — inconsistent with genuine non-accrual), empty rate/par/pct_nav fields, and identical cost/FV across Q3 and Q4 quarter-ends (prior-year comparison data is static).

**Current state:** All confirmed BDC holders carry Finastra positions at or near par and accruing. The active monitoring priority has shifted from credit stress to understanding the structure of post-refinancing residual positions (ARCC, OCSL) and tracking operating performance under the new syndicated capital structure.

### Category 3: Capital-structure complexity — first-lien resolved, equity layer still accruing
**Kaseya** executed a clean BSL refinancing in March 2025: $3.175B first-lien at S+325 (225bps tighter than the original 2022 S+550), plus a new $925M second-lien at S+500. Private-credit lenders were repaid in full. The first-lien stress thesis is substantially resolved. What remains: ARCC holds a **14.35% PIK preferred equity stake** in the holding company (Knockout Intermediate Holdings I, cost now $34.1M from $31.8M at PIK accretion), which was not part of the debt refinancing. The equity layer continues to accrue without cash payment behind the new $4.1B BSL stack.

**Key signal:** Clean first-lien refinancing at tight BSL spreads confirms the market's comfort with corporate-level first-lien risk. The residual concern is the non-cash-pay holding-company equity layer — a structural complexity that belongs in the same category as the Zendesk equity impairment observed below.

### Category 4: AI disruption risk — first concrete equity-layer impairment confirmed
**Zendesk** is the largest-ever direct-lending LBO at the time of close. Current first-lien marks remain clean at 99–103¢ across FSK, GBDC, OBDC, BXSL, and TCPC. But ARCC's Q3→Q4 2025 filings reveal the **first concrete impairment signal**: ARCC holds a full capital stack at Zoro TopCo (the Zendesk holding entity), including Series A preferred stock (13.50% PIK) and common equity. Between Q3 and Q4 2025, the **preferred stock was marked down 52%** (from $27.9M to $13.4M) and common equity was written to -$2.0M. First-lien marks are unchanged.

**Key signal:** The sequence — equity impairment visible, first-lien still clean — mirrors the early trajectory at Pluralsight and Medallia before first-lien recognition. Zendesk has moved from "forward risk" to "active equity monitoring" category. The 52% preferred markdown in a single quarter is not consistent with business-as-usual.

**Coupa** and **Anaplan** remain in the pure forward-risk category — clean marks across all lenders, 2029–2030 refinancing windows are the primary catalysts to watch.

### Category 5: Historical anchor — completed workout with clear lessons
**Pluralsight** is the only name in this universe with a fully completed restructuring. The outcome confirms: recurring revenue did not prevent lender loss, IP-transfer liability management exercises can accelerate the workout, and lenders can become equity holders in reorganized entities at a fraction of their original loan cost. ARCC now holds Pluralsight PIK debt (1.50% PIK), and GSBD holds both restructured debt and common stock equity valued at approximately $13M against what was a very large pre-workout cost basis.

**Key signal:** If Medallia or Finastra follow a similar trajectory, the Pluralsight playbook — LME, IP transfer, debt-for-equity — becomes the template to watch.

---

## Six theses worth holding simultaneously

### Thesis 1: Software private-credit risk is a dispersion story, not a sector call

The problem is not "software bad." It is that software credit may split sharply between:
- mission-critical systems of record with durable switching costs (Avalara, Anaplan)
- categories vulnerable to AI compression, workflow substitution, or customer build-vs-buy shifts (Zendesk, Coupa)
- credits with operating problems overlaid on already-high leverage (Medallia, Finastra)
- special-situation legal or structural complexity (RealPage, Kaseya holdco preferred)

A portfolio manager who averages across "software exposure" is averaging across these very different risk profiles. Sub-category precision matters more than the headline label.

### Thesis 2: Public BDC marks are the best window into otherwise opaque private-credit stress

Because many private loans do not trade and many borrowers do not file public financials, BDC schedules of investments are often the most accessible and reliable recurring signal for:
- changing lender sentiment (BXSL's Medallia mark moving from ~100 to 78 over 18 months)
- valuation gaps across holders (BXSL vs. FSK on Medallia; OBDC non-accrual vs. ARCC accruing on Finastra)
- when a software issuer moves from "watch" to "problem credit" in at least one lender's view

The borrower_db.json cross-fund index in this project makes it possible to track these signals systematically.

### Thesis 3: Recurring-revenue underwriting may have overstated downside protection

The Medallia and Pluralsight pattern suggests that ARR-based underwriting can help lenders get comfortable upfront, but may not protect them later if:
- customer value perception weakens despite stable subscription counts
- growth slows materially below underwriting projections
- interest burden rises faster than operating improvement
- strategic buyers are less aggressive than expected in a distressed sale

A 99-cent mark on a $1.5 billion loan to a software company that is actually performing near Medallia's level is a marking mistake, not a valuation success.

### Thesis 4: Recovery quality in software is about franchise continuity, not collateral

For most of these borrowers, the key recovery question is not lien coverage on hard assets — there are no hard assets. It is whether lenders can preserve:
- customer retention through a workout process
- product roadmap credibility when management is distracted by restructuring
- employee and engineering continuity under financial distress
- channel and implementation partner confidence

This is a different workout logic than in asset-heavy sectors. The Pluralsight case shows that the answer can be: not very well.

### Thesis 5: Legal and structural complexity can impair recovery before operating weakness shows up

Pluralsight's IP-transfer LME and RealPage's antitrust overhang suggest that software recoveries can be impaired by non-operating factors:
- unrestricted subsidiary moves that shift value before lenders can act
- antitrust or litigation clouds that reduce buyer appetite
- multi-entity roll-ups (Kaseya-Datto) with unclear break-up value
- sponsor/lender conflict over liability management sequence

These are asymmetric risks: when they materialize, they move fast; before they materialize, they are invisible in standard mark-to-model analyses.

### Thesis 6: The three-trait filter for highest-value surveillance names

The names most useful for anticipating BDC bond risk combine:
1. **clear sponsor-backed software leverage** — confirmed private-credit financing
2. **public BDC/vehicle visibility** — exposure confirmed in filed schedules of investments
3. **an operating or structural question that marks may not yet fully reflect**

On this basis, the current ranking is:
1. **Medallia** — live mark stress, PIK activity, 21-point dispersion confirmed (BXSL 78.3¢ vs. FSK 98.9¢)
2. **Zendesk** — ARCC preferred equity −52% Q3→Q4 2025 is the first concrete impairment signal; first-lien still clean but equity layer transmitting
3. **Finastra** — completed cycle / historical anchor; all lenders at par; scale demands ongoing monitoring
4. **Kaseya** — first-lien resolved via BSL refi at S+325; residual risk in holding-company PIK preferred ($34.1M accreting) and new $925M second-lien
5. **Pluralsight** — completed workout; ARCC FV written to zero; GSBD marks declining
6. **RealPage** — no confirmed BDC holding; legal risk template unique and applicable more broadly

*Zendesk upgraded to #2 based on Q4 2025 filing data confirming a 52% markdown in ARCC's preferred equity position at Zoro TopCo. Kaseya downgraded to #4 following the March 2025 clean BSL refinancing at S+325 (225bps tighter than 2022).*

---

## The CCLF connection

The CCLF liquidity analysis connects to this issuer work through a different mechanism. CCLF is not a single-issuer problem — it is a structural fund-level risk. But the same private-credit ecosystem that financed Medallia, Finastra, Kaseya, and Zendesk is also represented in CCLF's portfolio.

If software credit marks deteriorate more broadly, CCLF faces three compounding pressures:
1. **asset marks decline** — reducing NAV and potentially triggering closer lender scrutiny on the credit facility
2. **repayment generation slows** — as stressed borrowers extend and avoid prepayment, reducing cash available to fund repurchases
3. **redemption demand increases** — as investors become more aware of credit-quality questions, tender demand rises exactly when the fund is least able to satisfy it

The CCLF liquidity memo covers these dynamics. But the issuer surveillance work is the early-warning system for what drives them.

---

## Practical next analytical priorities

| Priority | Status | Action | Why now |
|----------|--------|--------|---------|
| 1 | ✅ Confirmed | CCLF 14% tender request | Bloomberg March 11, 2026 confirmed; Q1 2026 record; 7% cap; concurrent $1B secondary sale via Evercore |
| 2 | ✅ Built | Cross-issuer mark-drift table | See cross_issuer_mark_drift.md; Q3→Q4 2025 data for all surveillance names |
| 3 | ✅ Confirmed | Kaseya 2025 refinancing | March 2025; $3.175B FL at S+325 + $925M SL at S+500; clean BSL exit; private credit repaid |
| 4 | ✅ Completed | OBDC non-accrual attribution | National Dentex ($83M loss), Feradyne, Walker Edison are the main names; no software credits in non-accrual pool |
| 5 | Active | Track BXSL Medallia mark in next schedule | Confirm whether 78¢ drift is stabilizing or continuing; watch FSK convergence |
| 6 | Active | Track ARCC Zendesk preferred in next filing | 52% Q4 markdown is the key forward signal; next quarterly print will confirm trajectory |
| 7 | Active | Watch FSK Medallia marks vs. BXSL | Convergence or continued divergence is the tell; FSK's PIK mechanism is deferring recognition |

---

## What this project is not claiming

This project is not predicting defaults. It is not claiming that any of these companies will fail to pay interest next quarter. It is building an early-warning framework based on the observation that:

- private-credit marks are disclosed quarterly with a lag
- when marks move, they tend to move in the same direction they've been moving
- a 21-point mark dispersion on a $762M public BDC position is not a rounding error
- a non-accrual on a $5.3B private-credit loan is not an administrative footnote

The project's value is in being right about the direction earlier than consensus — and this memo is the record of that thesis, the evidence behind it, and the specific data points that would confirm or refute it.
