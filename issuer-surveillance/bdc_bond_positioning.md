# BDC Unsecured Bond Positioning — Credit Quality vs. Market Pricing

*The "so what" for BDC unsecured bond investors: which BDC bonds look mispriced given the issuer-level credit quality findings in this project.*

---

## Framework

BDC unsecured bonds are rated senior unsecured obligations of the BDC holding company. Their credit quality is a function of:
1. **Asset coverage** (portfolio FV ÷ total debt ≥ 150% per 1940 Act)
2. **NAV trajectory** — is the denominator of that coverage ratio growing or eroding?
3. **NII coverage of the dividend** — can the BDC sustain distributions without NAV drawdown?
4. **Portfolio credit quality** — what is the forward-looking stress on the asset side?
5. **Funding structure** — concentration of maturities, revolver availability, reliance on short-term funding

This project provides an unusual angle on item 4 — through issuer-level surveillance, we can identify portfolio credit stress *before* it fully appears in published marks or accrual changes.

---

## BDC bond universe snapshot (Q1 2026)

| BDC | Rating | Unsecured bond spread (est.) | Leverage (D/E) | NII coverage | Key portfolio risk |
|-----|--------|------------------------------|----------------|--------------|-------------------|
| **ARCC** | BBB (S&P) / Baa3 (Moody's) | ~T+130–160bps | 1.12x | ~1.10x | Cornerstone + Zywave + BakeMark concentration (Clearlake) |
| **OBDC** | BBB– (S&P) | ~T+165–185bps | 1.26x | ~1.05x | Cornerstone 2L/preferred + Zendesk 1L ($178M) |
| **BXSL** | BBB (S&P) | ~T+140–160bps | 1.29x | ~1.12x | Medallia ($308M, 78¢) — single-name concentration |
| **FSK** | **Ba1 (Moody's, Mar 2026)** | **~T+280–320bps** | 1.31x | 0.86x | Medallia ($451M blended) + 12% PIK income |
| **GBDC** | BBB– (S&P) | ~T+160–180bps | 1.25x | ~1.08x | BioIVT + Zendesk + Kaseya; June FYE (data lag) |
| **CGBD** | Not rated / BB (est.) | ~T+250–280bps | 1.31x | ~1.00x | Kaseya, Avalara, Coupa; NO Cornerstone OnDemand |

*Spread estimates are approximations based on recent new issuance and secondary market color; BDC bond spreads are not systematically publicly reported. FSK post-Ba1-downgrade spread estimated from investment-grade-to-HY transition mechanics.*

---

## The core finding: FSK stands apart

### FSK — Ba1 (Moody's), speculative grade

Moody's downgraded FSK to Ba1 on March 24, 2026 — the first BDC in the peer group to cross into speculative territory. The stated reasons:
- **14.7% PIK income share** (peer median: 6.3%) — signals borrowers unable to service cash interest
- **0.86x NII dividend coverage** — FSK is distributing more than it earns in net investment income
- **Medallia named explicitly** — $451M blended exposure ($267M cash + $233M PIK tranches) at ~79¢/99¢ blended; non-accrual trigger approaching
- **NAV decline of −3% YoY** — directional trend is wrong before non-accruals are formally declared

**What this means for FSK bonds:**
- Investment-grade-qualified buyers (insurance companies, bank portfolios) are forced sellers post-Ba1; supply/demand imbalance likely continues
- **Incremental stressed-credit loss under our scenarios: ~$151M / −2.6% of NAV** (per `bdc_nav_stress_table.md`) — this would further compress the D/E buffer
- FSK already at 1.31x leverage; under Medallia non-accrual (55–70¢ stress), D/E moves toward ~1.35x — still well below 2.0x 1940 Act ceiling, but further from being able to issue new debt comfortably
- **Dividend cut risk is the primary bondholder risk**, not default — a dividend reduction would further widen FSK's bonds as income-oriented investors exit

**FSK bond thesis (as of April 2026):** FSK's unsecured bonds at ~T+300bps are pricing substantial credit concern. The question is whether that spread is *enough* given: (a) Medallia forced restructuring is not yet in the marks, (b) NII coverage of 0.86x means dividend risk is real, (c) PIK income concentration will not reverse quickly. At T+300bps, bonds are roughly equivalent to a B-rated corporate — a BDC with $5.85B NAV and 1.31x D/E is not a B credit on asset coverage. But on *income sustainability and management track record*, the Ba1 is defensible. **Net view: FSK bonds are fairly priced at T+280–320bps, not cheap, not significantly rich.** The risk/reward is asymmetric: upside limited by continued PIK concentration and Medallia trajectory; downside if Medallia hits non-accrual and FSK cuts the dividend.

---

## BXSL — the single-name Medallia bet

BXSL is the purest expression of Medallia risk in the BDC bond universe. Medallia represents ~4.9% of BXSL's total portfolio at cost ($395M / ~$8B). The Q4 2025 mark at 77.75¢ is already embedded. The question is what comes next:

**Scenario A — Thoma Bravo equity injection (base case, ~50% prob):**
- Medallia remains accruing; BXSL mark stabilizes at 75–80¢; bonds remain at T+140–160bps
- BXSL's 1.12x NII coverage and investment-grade rating are intact
- **Bond implication: no material change; current spread is appropriate**

**Scenario B — Debt-for-equity restructuring (35% prob):**
- Medallia goes non-accrual; BXSL writes down from 77.75¢ toward 55–65¢
- Incremental loss ~$71–112M / 1.1–1.8% of BXSL NAV
- Leverage moves from 1.29x → ~1.31x; NII coverage dips modestly
- **Bond implication: spread widens to T+200–220bps on trajectory signal alone**
- This is the scenario the market is partially pricing but not fully reflecting

**Scenario C — Medallia continues to deteriorate (15% prob):**
- Multiple lenders place on non-accrual; restructuring fails; BXSL marks toward 40–50¢
- Loss ~$112–160M; could trigger Moody's review
- **Bond implication: spread widens to T+240–260bps; rating downgrade risk**

**BXSL bond thesis:** At T+140–160bps, BXSL bonds are pricing ~20% probability of Scenario B stress (using spread differential vs. ARCC as the risk premium). Our surveillance work suggests that probability is higher — closer to 35%. **BXSL bonds look modestly rich vs. the Medallia tail risk** they embed. The trade: BXSL bonds are not catastrophically mispriced, but offer asymmetric downside if Medallia restructuring is confirmed in Q1 2026 filings.

---

## ARCC — the diversification premium is real, but Clearlake is the hidden concentration

ARCC is the most diversified BDC in the peer group ($14.32B NAV, ~350+ portfolio companies). The screener correctly flags ARCC as GREEN — aggregate metrics are healthy. But the issuer surveillance reveals a hidden concentration:

**Clearlake Capital concentration in ARCC:**
| Company | Position | Q4 2025 mark status |
|---------|---------|---------------------|
| Cornerstone OnDemand | 2L ($137.5M) + preferred ($179.2M) + 1L + common | 2L at 91¢, preferred at 85¢, common appreciating |
| Zywave | 1L ($16.6M) + 2L ($71.6M) + preferred ($73.7M) | 2L at anomalous 99.6¢, preferred written off |
| BakeMark | 1L ($16.1M) + 2L ($29.5M) + preferred (written off) | 1L at 87¢, 2L at 88¢ |
| Wellness Pet | Distressed exchange June 2025 | Impaired |
| Pretium Packaging | Chapter 11, 2025 | Impaired |

**Total Clearlake-related ARCC exposure: ~$525M+ across these names**. If three of ARCC's five largest Clearlake credits are simultaneously impaired, the diversification benefit for this specific sponsor relationship has been substantially consumed.

Under our stress scenarios, ARCC's incremental loss is ~$87M / −0.6% of NAV — manageable. But the *trajectory* risk is that Clearlake's credit quality broadly deteriorates (sponsor overextension), which would hit ARCC disproportionately.

**ARCC bond thesis:** ARCC bonds at T+130–160bps are appropriately priced for the market's view of ARCC as the "blue chip" BDC. The diversification argument is valid at the portfolio level. The risk that is NOT in the spread: Clearlake concentration at the sponsor level — a correlation risk that ARCC's portfolio-level diversification doesn't protect against. **ARCC bonds are fairly valued; we would not underweight vs. the BDC index, but we would not add at current spreads given the Clearlake concentration that is not yet visible in aggregate metrics.**

---

## OBDC — the administrative agent advantage

Blue Owl's OBDC is the administrative agent on both the Cornerstone OnDemand deal and is a significant Zendesk lender. The administrative agent role provides:
- First access to monthly/quarterly borrower compliance certificates
- Control over amendment and waiver negotiations
- Early visibility into covenant stress before marks move

**This is a double-edged sword for bondholders:**
- **Upside:** OBDC is likely to know about Cornerstone and Zendesk stress before other lenders react; they can position accordingly
- **Downside:** As admin agent, OBDC may be more constrained in selling or marking down positions aggressively (reputational and contractual reasons)

OBDC's Zendesk first-lien ($178M at 101.3¢) and Cornerstone 2L ($144M at 93.8¢) are both large relative to its $7.40B NAV. Combined, these two names represent ~$324M / ~4.4% of NAV — the single largest identifiable cluster of stressed-credit concentration in OBDC's portfolio.

Under stress scenarios, OBDC's incremental loss is ~$60M / −0.8% of NAV — modest. But if Cornerstone revolver stress accelerates in Q3/Q4 2026 (Oct 2026 maturity), OBDC as admin agent will be directly involved in any amendment or restructuring.

**OBDC bond thesis:** Bonds at T+165–185bps appear reasonably priced. The admin agent role provides information advantage. The Zendesk + Cornerstone cluster is the key downside case. **Neutral — hold at current spreads; monitor the Oct 2026 Cornerstone revolver maturity as the next potential catalyst.**

---

## Relative value summary

| BDC | Bond spread (est.) | Our view | Direction |
|-----|-------------------|---------|-----------|
| **FSK** | T+280–320bps | Fairly priced; downside if Medallia hits non-accrual + dividend cut | Neutral / slight avoid |
| **BXSL** | T+140–160bps | Modestly rich vs. Medallia tail risk; 35% prob of B scenario not priced | Slight underweight |
| **ARCC** | T+130–160bps | Fairly priced; Clearlake concentration not in spread | Neutral; do not add |
| **OBDC** | T+165–185bps | Reasonably priced; admin agent advantage partially offsets concentration | Neutral |
| **CGBD** | ~T+250–280bps | No major surveillance names (NO Cornerstone OnDemand); spread reflects smaller franchise, not credit stress | Mildly attractive vs. peers if spread is accurate |

---

## The trade we'd watch

**FSK bonds vs. ARCC bonds — the pair trade:**

At current estimated spreads (~T+300 FSK vs. ~T+145 ARCC), the FSK–ARCC spread differential is ~155bps. The historical differential for a BDC investment-grade vs. Ba1 comparison would suggest 200–250bps is more appropriate if FSK's downgrade is sticky and Medallia non-accrual is confirmed.

If Medallia goes formally non-accrual at FSK in Q1 2026 filings (May 2026), the differential should widen toward 200–250bps — primarily through FSK bonds widening to T+350–380bps, not ARCC tightening. **The trade: short FSK bonds / long ARCC bonds into Q1 2026 earnings season (May 2026).**

Risk to the trade: Thoma Bravo injects equity into Medallia before non-accrual designation, FSK marks stabilize, differential compresses back toward 120bps.

---

## Key catalysts (Q2 2026)

| Date | Event | Impact |
|------|-------|--------|
| May 2026 | Q1 2026 BDC 10-Q filings | Medallia accrual status; Zendesk preferred mark; Cornerstone 2L trajectory |
| Oct 2026 | Cornerstone OnDemand revolver maturity | Revolver extension or stress event; OBDC/ARCC as principal holders |
| Nov 2027 | Zywave first-lien maturity | Refinancing test; ARCC 2L should compress well before this date |
| Nov 2028 | Zendesk first-lien maturity | $4.6B refinancing test; requires demonstrating AI revenue growth trajectory |

---

## What this analysis does not do

This document does not provide trading recommendations or investment advice. It applies the issuer-level surveillance findings from this project to the BDC unsecured bond context. The spread estimates are approximations; actual trading levels should be verified against TRACE, Bloomberg, or dealer runs. The probability estimates for Medallia scenarios are qualitative judgments based on public information, not quantitative models.

---

*Sources: EDGAR XBRL Q4 2025 BDC metrics; `bdc_nav_stress_table.md`; `medallia_memo.md`; `zendesk_memo.md`; `cornerstone_ondemand_memo.md`; Moody's FSK downgrade March 24, 2026; Bloomberg April 2, 2026 (Medallia PIK refusal). All spread estimates are approximations.*

*Last updated: April 2026*
