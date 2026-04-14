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

### Category 2: Scale / refinancing surveillance — largest single private-credit deal with 2029 maturity
**Finastra** is the $5.3 billion private-credit loan that cannot be ignored by size alone. Filing-confirmed exposure across ARCC ($52.6M FV at 102 cents), OCSL ($11.5M FV at 98 cents, fixed rate), OBDC (revolving ~$27.9M FV, accruing), and GBDC (small positions at ~99 cents), plus OTF portfolio-page confirmation. **All confirmed holders are accruing at or near par as of Q4 2025.**

**On the apparent mark dispersion:** The 4-point gap between ARCC (102¢, floating ~11%) and OCSL (98¢, fixed 7.25%) reflects rate structure rather than credit quality. A 7.25% fixed-rate loan in a 10%+ rate environment appropriately trades at a discount to par — this is interest rate duration, not credit deterioration. When controlled for rate type, the lender consensus is clean.

**Parser artifact disclosure:** During this project's investigation, the portfolio parser initially flagged a $93.5M OBDC entry for Finastra as non-accrual. Subsequent forensic analysis identified this as a subtotal row: the entry had (1) FV above cost at 100.9 cents (inconsistent with non-accrual), (2) empty rate and par fields (consistent with a totals row), and (3) identical cost and FV across Q3 and Q4 quarter-ends (impossible for a real loan). The non-accrual flag was misapplied via the parser's issuer-level carry-forward mechanism. No confirmed non-accrual exists at any Finastra lender.

**Key signal:** A $5.3B private-credit loan maturing in September 2029 — part of the same maturity cluster as Kaseya, Anaplan, and Pluralsight — warrants active monitoring even with clean current marks. The refinancing execution quality in 2028–2029 will be a market signal about private-credit appetite for large leveraged fintech names.

### Category 3: Capital-structure complexity — hidden stress signals in structure
**Kaseya** shows clean first-lien marks at CGBD (101.5 cents) and GSBD (101.1 cents), but **ARCC holds a 14.62% PIK preferred equity stake** in the holding company (Knockout Intermediate Holdings I). PIK preferred at 14.62% in a holding company sitting above $3.7B of first-lien debt is not a simple equity kicker — it is a structural signal that the capital stack has multiple layers, the junior layers are accruing without cash payment, and the holding-company leverage picture may be more complex than the first-lien marks alone imply.

**Key signal:** Clean first-lien marks and non-cash PIK preferred equity are compatible outcomes. The first-lien can be healthy today while the equity-layer complexity creates pressure on overall enterprise value and refinancing flexibility.

### Category 4: Forward risk — category disruption not yet in marks
**Zendesk** is the largest-ever direct-lending LBO at the time of close, with filing-confirmed exposure across BXSL, FSK, BCRED, and Blue Owl Technology Finance. Current marks are clean (at or above par). The risk is forward-looking: customer-support software is the category most directly in the path of AI-native workflow automation, and **marks that look right today may not look right as AI adoption accelerates and seat counts compress**.

**Coupa** and **Anaplan** sit in the same forward-risk category — cleaner fundamentals and more defensible category positions than Zendesk, but also facing the question of whether the 2029–2030 refinancing windows will encounter a different market reality than the 2022–2023 close conditions.

**Key signal:** The absence of mark pressure today is not evidence of absence of risk. It is evidence that the category-level disruption thesis has not yet become a credit-level impairment thesis.

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
1. **Medallia** — live mark stress, PIK activity, 21-point dispersion (confirmed filing)
2. **Kaseya** — holdco PIK preferred complexity, large refinancing catalyst (confirmed filing)
3. **Finastra** — largest single private-credit loan; $5.3B at 2029 maturity; all lenders at par but scale demands surveillance (confirmed filing)
4. **Zendesk** — broadest BDC visibility, forward AI risk (confirmed filing)
5. **Pluralsight** — completed workout, confirmed filing in both PIK debt and equity forms (confirmed filing)
6. **RealPage** — no confirmed BDC holding, but legal risk template is unique and applicable more broadly

*Finastra was previously ranked #2 based on a parsing artifact that initially appeared as a $93.5M OBDC non-accrual. Investigation confirmed the entry was a subtotal row with a misapplied non-accrual flag. No confirmed non-accrual exists at any Finastra lender; Finastra has been re-ranked to reflect its actual surveillance priority: scale and refinancing risk rather than current credit stress.*

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

| Priority | Action | Why now |
|----------|--------|---------|
| 1 | Source the CCLF 14% tender request datapoint | Most important unconfirmed data point in the project |
| 2 | Track BXSL Medallia mark in next filed schedule | Confirms whether the 78-cent drift is stabilizing or continuing |
| 3 | Source Finastra 2025 syndicated refinancing outcome | Execution quality is the credit signal — price, size taken out, and what remained with private-credit holders |
| 4 | Track OBDC portfolio for any new non-accrual credits | With the Finastra parsing artifact resolved, OBDC's actual 2.7% / 1.3% (cost/FV) non-accrual pool needs borrower-level attribution |
| 5 | Watch FSK Medalllia marks vs. BXSL | Convergence or continued divergence is the tell |
| 6 | Add Kaseya 2025 refinancing details | Execution quality reveals true market appetite for the credit |
| 7 | Build cross-issuer mark-drift table | Single view showing cost vs. FV trends across all names over time |

---

## What this project is not claiming

This project is not predicting defaults. It is not claiming that any of these companies will fail to pay interest next quarter. It is building an early-warning framework based on the observation that:

- private-credit marks are disclosed quarterly with a lag
- when marks move, they tend to move in the same direction they've been moving
- a 21-point mark dispersion on a $762M public BDC position is not a rounding error
- a non-accrual on a $5.3B private-credit loan is not an administrative footnote

The project's value is in being right about the direction earlier than consensus — and this memo is the record of that thesis, the evidence behind it, and the specific data points that would confirm or refute it.
