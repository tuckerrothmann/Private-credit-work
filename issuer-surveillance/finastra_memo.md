# Finastra — issuer memo

## One-line thesis
Finastra is a **completed private-credit workout and refinancing case study**: the $5.3 billion private-credit unitranche originated in September 2023 went on non-accrual at OBDC by Q4 2024, was successfully refinanced via a $4.195 billion syndicated loan in August 2025, and is now held in a different form (syndicated market, revolving facility) — making it the most instructive completed-cycle example in this universe of what large-scale private-credit stress followed by a successful market exit looks like.

## What the company does
Finastra is a large financial-software vendor serving banks and other financial institutions across core banking, payments, lending, treasury, and capital-markets workflows. Formed from the 2017 merger of Misys and D+H Financial Technology, and backed by Vista Equity Partners since 2012. The credit screens defensively:
- mission-critical customer workflows embedded in daily banking operations
- recurring software and maintenance revenue
- high switching costs (core banking changes take years to execute)
- global scale across more than 8,000 financial institutions
- Vista Equity Partners backing

The category risk is that banking-software capex is highly correlated with bank profitability and IT budget cycles — and that cloud-native competitors (Thought Machine, Mambu, Temenos cloud) are slowly displacing legacy installed-base software.

## Why it matters
- **the largest-ever U.S. private-credit deal** at origination ($5.3 billion unitranche, September 2023)
- **non-accrual at OBDC confirmed as of December 31, 2024** — before the refinancing
- **successfully refinanced in August 2025** via a $4.195 billion cross-border syndicated loan — the most significant completed private-credit takeout in this universe
- demonstrates both the stress potential of software private-credit (non-accrual within 15 months of origination) and the market conditions under which private-credit can be exited into syndicated markets
- confirms that the 2025 syndicated market was able to absorb a re-leveraged fintech credit, which has implications for other 2028–2029 maturities in this universe

## The complete deal lifecycle

### Phase 1: Origination (September 2023)
- Finastra completes a **$5.3 billion** private-credit refinancing — at the time the largest private-credit deal in the U.S.
- Structure: **$4.82 billion senior secured unitranche term loan** + **$500 million senior secured multicurrency revolving credit facility**
- Spread: SOFR+725 bps on the unitranche
- Lenders: more than twenty, led by OHA (Oak Hill Advisors) committing $800M+; ARCC, OCSL, OBDC, GBDC, OTF among confirmed participants
- Purpose: took out maturing syndicated first- and second-lien debt and deleveraged the company
- Source: Kirkland & Ellis (borrower counsel), OHA press release

### Phase 2: Non-accrual emergence (Q4 2024)
- OBDC placed its ~$93.5M share of the Finastra unitranche **on non-accrual** as of December 31, 2024
- Evidence: OBDC's Q3 and Q4 2025 SOI tables include a prior-year (December 31, 2024) comparison column that shows the non-accrual designation on the TLB row
- The prior-year TLB entry (cost $93.5M, FV $94.3M, non-accrual=true, empty rate/par/pct_nav) was captured by the portfolio parser as a current-period entry — see parser artifact note below
- Other confirmed lenders (ARCC, OCSL) did not flag non-accrual on their own positions as of 2024 filings

### Phase 3: Attempted refinancing and failure (March–April 2025)
- Morgan Stanley pitches Finastra's lenders on a syndicated refinancing to take out the private-credit unitranche
- **April 2025:** The initial syndicated refinancing attempt **fails** — insufficient investor demand at the required pricing
- Source: Bloomberg ("Wall Street's Stab at Refinancing Finastra's Private Debt Fails," April 2, 2025)

### Phase 4: Successful refinancing (July–August 2025)
- **July 17, 2025:** Morgan Stanley revives the Finastra refinancing plan
- Source: Bloomberg ("Morgan Stanley Revives $4 Billion Finastra Debt Refinancing Plan," July 17, 2025)
- **August 2025:** Finastra completes a **$4.195 billion-equivalent cross-border leveraged loan** — upsized from the initial plan, with spreads tightened mid-execution due to strong investor demand
  - First-lien TLB: S+400 bps (vs. SOFR+725 on the original private-credit unitranche)
  - Second-lien TLB: S+700 bps
  - Proceeds used to repay the 2023 private-credit unitranche in full
  - Source: PitchBook ("Finastra lines up $3.6B syndicated loan to refinance landmark private credit deal"; "Amid investor demand, Finastra lands upsized cross-border leveraged loan, trims credit spread")

### Phase 5: Current state (Q3–Q4 2025 and beyond)
- The $4.82 billion private-credit unitranche has been **fully repaid** through the syndicated refinancing
- OBDC's remaining Finastra exposure is solely the **revolving credit facility** (~$27.9M FV as of Q4 2025), which was not part of the TLB refinancing
- All confirmed BDC holders in Q3–Q4 2025 show only revolving or small residual positions, all accruing normally

## Confirmed public BDC portfolio evidence — current period (Q3–Q4 2025)

| Fund | Filing period | Position type | Cost ($M) | Fair value ($M) | Mark (¢/$) | Rate | Non-accrual? | Source |
|------|--------------|--------------|-----------|-----------------|------------|------|--------------|--------|
| ARCC | Q4 2025 (10-K) | First lien senior secured loan | 51.4 | 52.6 | **102.3** | Floating ~10.97% | No | Filed 10-K |
| ARCC | Q3 2025 (10-Q) | First lien senior secured loan | 51.9 | ~52.6 | ~101 | Floating ~11.29% | No | Filed 10-Q |
| OCSL | Q4 2025 (10-K) | First lien senior secured | 11.7 | 11.5 | **98.3** | Fixed 7.25% | No | Filed 10-K |
| OBDC | Q4 2025 (10-K) | First lien revolving loan | 27.5 | 27.9 | ~101 | Floating S+ | No | Filed 10-K |
| OBDC | Q3 2025 (10-Q) | First lien revolving loan | 27.7 | 28.1 | ~101 | Floating S+ | No | Filed 10-Q |
| GBDC | Q4 2025 (10-K) | One stop (multiple tranches) | ~3.0 | ~2.9 | ~98.8 | Floating S+ | No | Filed 10-K |
| OTF | Portfolio page | First lien senior secured loan | — | — | — | — | No | Portfolio disclosure |

**Note:** ARCC's Q3 2025 position ($51.9M cost) with no FV in the parser output likely reflects an XBRL parsing gap — the Q4 10-K confirms FV of $52.6M. The ARCC position may be exposure to the revolving facility or a residual first-lien instrument, not the unitranche TLB (which was repaid in August 2025).

**On the ARCC and OCSL positions post-refinancing:** ARCC and OCSL both continue to show Finastra first-lien exposure in Q4 2025 despite the unitranche repayment. Two explanations are possible: (a) they hold participation in or exposure to the new syndicated facility, or (b) their positions were structured as first-lien-only in a different credit agreement that was not fully repaid by the August 2025 deal. This warrants clarification in the next filing cycle.

## The mark dispersion: rate structure, not credit divergence

Among the current-period holders:
- **ARCC at 102.3 cents** holds a floating-rate loan at ~11%
- **OCSL at 98.3 cents** holds a fixed-rate loan at 7.25%

A 7.25% fixed-rate loan in a 10–11% rate environment trades at a discount to par because the holder earns below the market clearing rate. This is interest rate duration, not credit deterioration. When corrected for rate type, both lenders are marking the same credit quality at approximately par.

## What the lifecycle teaches

The Finastra case study provides four lessons applicable to the broader private-credit software universe:

1. **Private-credit non-accrual does not automatically mean permanent loss.** OBDC had the Finastra TLB on non-accrual in Q4 2024, yet the unitranche was repaid at par (or near par) in August 2025. Non-accrual is an accounting designation reflecting uncertainty about interest collection — it does not mean the principal is lost.

2. **Syndicated market access is the key refinancing variable.** The April 2025 failure followed by an August 2025 success shows how quickly market appetite can change. The 325bp tightening from SOFR+725 (private-credit rate) to S+400 (syndicated rate) also shows that private-credit lenders priced in a meaningful illiquidity and complexity premium that the syndicated market ultimately did not need.

3. **The initial private-credit spread (SOFR+725) was generous.** The clearing rate in the syndicated market (S+400) implies the original lenders were receiving ~325bps of excess spread above the competitive clearing level. This is the private-credit illiquidity/origination premium — and it partly explains why private-credit lenders were willing to originate even though the credit would go to non-accrual within 15 months.

4. **Revolving facilities are stickier than term loans.** OBDC, ARCC, and OCSL all retain revolving or residual first-lien exposure post-refinancing. The revolving facility — which provides working capital access — was not part of the syndicated takeout. This is a structural pattern to watch in other credits: when a term loan refinances, revolving commitments often remain with the original lenders.

## Parser artifact note — OBDC $93.5M prior-year entry
The portfolio parser flagged a $93.5M OBDC entry for "Finastra USA, Inc." as non-accrual in both Q3 and Q4 2025. This entry is **prior-year comparison data** (December 31, 2024) extracted from the SOI tables, not a current-period position. OBDC's iXBRL SOI tables include both the current-period column and a prior-year comparison column; the parser extracted rows from both, yielding duplicate entries. The prior-year column rows lack par, rate, and pct_nav values (those cells are blank in the comparison column), and they carry the non-accrual flag that was accurate for December 31, 2024.

Three diagnostics confirmed this:
1. **Identical cost and FV across Q3 2025 and Q4 2025** ($93,496K and $94,335K in both periods) — prior-year comparison data is static across filings
2. **FV above cost (100.9 cents)** — inconsistent with genuine non-accrual, which would imply a discount to reflect credit risk
3. **Empty rate, par, and pct_nav fields** — formatting consistent with a comparison-column row, not a current-period loan entry

The non-accrual on the Finastra TLB was REAL as of December 31, 2024 — but it was a prior-period event that was resolved through the August 2025 refinancing. The parser correctly captured the non-accrual flag from the prior-year data but incorrectly presented it as a current-period position.

## Working judgment
- **Hidden mark risk: 1 / 5** — the unitranche has been repaid; remaining exposure is the revolving facility at near par; no current non-accrual anywhere
- **BDC bond relevance: 3 / 5** — the historical case study is instructive; ARCC and OCSL retain residual exposure that warrants monitoring to understand the post-refinancing instrument structure
- **Recovery fragility: 1 / 5** — the credit proved recoverable; private-credit lenders received repayment at par from syndicated market proceeds

## Dated sources / anchors

| Date | Source | Key fact |
|------|--------|----------|
| 2023-09 | Kirkland & Ellis | $4.82B senior unitranche + $500M revolver; 20+ lenders; SOFR+725 |
| 2023-09 | OHA / PR Newswire | OHA lead arranger; $800M+ commitment |
| Q4 2024 | OBDC 10-K (prior-year comparison data) | $93.5M Finastra TLB on non-accrual as of Dec 31, 2024 |
| 2025-04-02 | Bloomberg | Initial syndicated refinancing attempt fails |
| 2025-07-17 | Bloomberg | Morgan Stanley revives $4B Finastra refinancing |
| 2025-08 | PitchBook | $4.195B cross-border TLB (S+400 / S+700) closes; private-credit unitranche repaid |
| Q3–Q4 2025 | ARCC 10-Q/10-K (filed) | $51.4M FV; 102.3 cents; floating ~11%; no non-accrual |
| Q4 2025 | OCSL 10-K (filed) | $11.5M FV; 98.3 cents; fixed 7.25%; no non-accrual |
| Q4 2025 | OBDC 10-K (filed) | Revolving ~$27.9M FV; floating S+; no non-accrual |
| Q4 2025 | GBDC 10-K (filed) | Small "one stop" positions; ~$2.9M FV; ~98.8 cents; no non-accrual |
| 2025–2026 | Blue Owl Technology Finance portfolio | Finastra USA listed as first-lien senior secured loan |

## Next best additions
- clarify whether ARCC and OCSL post-refinancing positions reflect participation in the new syndicated facility or a separate credit agreement not repaid by the August 2025 deal
- source the specific coupon and terms of the revolving facility that remains outstanding (not part of the August 2025 syndicated refinancing)
- operating metrics post-refinancing: ARR growth, EBITDA, leverage vs. original underwriting
- Vista Equity Partners exit timing and any dividend recap or capital structure changes since 2017 acquisition
