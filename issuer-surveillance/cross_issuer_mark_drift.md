# Cross-Issuer Mark-Drift Table

*Point-in-time BDC portfolio marks for key surveillance issuers, Q3 vs. Q4 2025. Built from portfolio_cache (metadata-empty/subtotal rows excluded). Data reflects the most recent filed 10-Q (Q3 = September 30, 2025) and 10-K (Q4 = December 31, 2025).*

---

## How to read this table

- **Mark (¢/$)** = fair value ÷ cost × 100. Where the BDC reports FV but not cost (equity instruments), mark is shown as n/a.
- **PIK** = position is partially or fully PIK (non-cash-pay).
- **NA** = position is on non-accrual status per the fund's filing.
- A blank Q3 cell means the fund did not hold this issuer in the Q3 filing or had no parseable Q3 cache file for that fund.
- All figures are in $M unless noted.

---

## Medallia — Active restructuring as of April 2026

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| **BXSL** | n/a | — | **307.9** | **78.3¢** (77.75¢ per Q4 earnings) | — | Mark trajectory: 94¢→89¢→87¢→82¢→77.75¢; "capital structure discussions expected" |
| **FSK** | 452.7 | 99.0¢ PIK | 454.2 | 98.9¢ PIK | -0.1¢ | Filed blended mark ~99¢; Q4 earnings separately disclosed PIK tranche at ~$185M FV / $233M cost = **~79¢** (~$29M unrealized Q4 loss) |

**Key signals (updated April 2026):**
- **April 2, 2026 forcing event (Bloomberg):** Lenders led by Blackstone refused to extend the PIK lifeline, forcing ~$100M incremental annual cash interest. Total debt ~$3B, EBITDA ~$200M → **coverage ~0.67x**. Restructuring options: debt-for-equity swap or Thoma Bravo equity injection.
- **March 24, 2026 (Moody's):** FSK downgraded to Ba1 (speculative grade) — first time FSK has lost investment-grade rating. Moody's cited FSK's **14.7% PIK income share** (vs. 6.3% peer median) and explicitly named Medallia as a marked-down non-non-accrual. Direct consequence of adverse selection (BSL took better credits, FSK holds higher PIK concentration).
- **Filing-based dispersion** (Q4 2025, December 31, 2025): BXSL 78.3¢ vs. FSK ~99¢ blended — still a ~21-point gap in filed data. BXSL's mark as lead lender has higher credibility; FSK's filed 99¢ blended includes large cash-pay tranches near par alongside the below-par PIK tranche.

---

## Kaseya — Capital-structure complexity; first-lien now in BSL market

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| CGBD | 36.8 | 101.5¢ | 36.8 | 101.5¢ | flat | New BSL first-lien (post-Mar 2025 refi) |
| GSBD | 19.4 | 101.1¢ | 19.4 | 101.1¢ | flat | New BSL first-lien |
| OBDC | 16.4 | 101.4¢ | 17.3 | 99.7¢ | -1.7¢ | Perpetual preferred stock (S+), not term loan |
| SLRC | 33.6 | 99.2¢ PIK | 33.6 | 99.2¢ PIK | flat | First-lien, PIK |
| OCSL | n/a | — | 34.2 | 99.5¢ | — | New position in Q4 |
| TCPC | n/a | — | 9.5 | 102.8¢ | — | New position in Q4 |
| **ARCC** | cost 31.8 | PIK | cost 34.1 | PIK | +$2.3M cost | **Holding-company preferred; not refinanced; accreting at 14.35% PIK** |

**Key signal:** The March 2025 BSL refinancing ($3.175B at S+325, 225bps tighter vs. original S+550) removed the first-lien stress thesis. BDCs now holding Kaseya are in the new BSL paper. ARCC's holding-company PIK preferred ($34.1M cost, no FV disclosed) was not part of the refinancing and continues to accrete without cash payment.

---

## Finastra — Completed cycle; all lenders at par

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| ARCC | cost 51.9 (unfunded) | — | 52.6 | 102.3¢ | funded | Revolver funded Q3→Q4; floating ~11% |
| GBDC | 6.8 | 98.6¢ | 2.9 | 98.9¢ | -$3.9M size | Partial repayment or position reduction |
| OBDC | 28.1 | 101.4¢ | 27.9 | 101.6¢ | flat | Revolving facility (TLB repaid Aug 2025) |
| OCSL | 15.5 | 98.9¢ | 13.4 | 100.4¢ | +1.5¢ | Fixed rate 7.25%; slight below-par reflects duration |

**Key signal:** All lenders clean at or near par. Original $5.3B unitranche was repaid via August 2025 $4.195B syndicated refinancing. This is the reference case for how a large private-credit non-accrual can resolve cleanly — no lender loss confirmed.

---

## Zendesk — Forward AI risk; equity layer now showing first impairment

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| FSK | 79.1 | 99.4¢ | 159.7 | 100.6¢ | +$80.6M | New originations in Q4; 6 tranches total |
| GBDC | 31.2 | 101.8¢ | 33.5 | 101.6¢ | +$2.3M | Stable first-lien |
| OBDC | 101.6 | 101.6¢ | 109.3 | 101.3¢ | +$7.7M | Slight position increase; stable mark |
| BXSL | n/a | — | 1.8 | 101.0¢ | — | Small first-lien tranche |
| TCPC | n/a | — | 5.8 | 103.6¢ | — | Small first-lien tranche |
| **ARCC** | **27.9** | **n/a** PIK | **13.4** | **n/a** PIK | **−$14.5M (−52%)** | **Series A preferred stock (Zoro TopCo); 13.50% PIK; ARCC also holds first-lien ~$36M** |

**Key signal:** ARCC's Series A preferred stock (13.50% PIK) at Zoro TopCo was marked down from $27.9M to $13.4M in a single quarter — a **52% write-down of the preferred equity layer**. ARCC's common equity went from $2.5M to -$2.0M. All first-lien lenders (FSK, GBDC, OBDC, BXSL, TCPC) remain at par or slight premium. This is the first concrete evidence that Zendesk's capital structure is absorbing losses in the equity layers while the debt layers remain clean — consistent with the AI-disruption thesis and consistent with the pattern observed at Pluralsight and Medallia before first-lien marks moved.

---

## Pluralsight — Completed workout; debt-for-equity template

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| **ARCC** | 21.6 | n/a PIK | cost 43.6 | n/a PIK NA | — | FV written off; cost basis remains |
| GBDC | 16.2 | 109.5¢ | 16.4 | 109.4¢ NA | flat | Restructured equity marked above par |
| GSBD | 44.7 | 100.4¢ | 29.0 | 99.6¢ NA | -$15.7M | Significant position decline |
| OCSL | 35.3 | 100.0¢ | 61.0 | 92.6¢ NA | +$25.7M size | Large position increase at discount |
| TCPC | n/a | — | 39.0 | 102.0¢ PIK | — | PIK debt tranche |

**Key signal:** Pluralsight is a completed workout with ongoing mark diversity. ARCC has effectively written its Zendesk-style PIK position to zero FV. GSBD's position declined $15.7M Q3→Q4. OCSL significantly increased exposure at 92.6¢. This is the historical case study: equity holders receive near-zero recoveries; lenders who stayed through the restructuring hold complex instruments at various marks.

---

## Anaplan — Clean; no stress signals

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| BXSL | n/a | — | 45.3 | 100.8¢ | — | Clean |
| GBDC | 59.7 | 100.8¢ | 59.6 | 100.8¢ | flat | Clean |
| OBDC | 64.3 | 100.0¢ | 64.2 | 100.0¢ | flat | Clean |

**Signal:** No stress; 2029 maturity window is the next relevant catalyst.

---

## Coupa — Clean; no stress signals

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Change | Notes |
|------|----------------|---------|----------------|---------|--------|-------|
| CGBD | 19.5 | 103.0¢ | 19.5 | 102.9¢ | flat | Stable |
| GBDC | 31.4 | 99.2¢ | 31.3 | 99.3¢ | flat | Stable |
| OBDC | 1.6 | 100.9¢ | 1.5 | 100.8¢ | flat | Stable |
| OCSL | 13.1 | 101.7¢ | 25.7 | 100.0¢ | +$12.6M | New origination in Q4 |
| BXSL | n/a | — | 3.6 | 101.8¢ | — | New |

**Signal:** No stress; clean marks across all lenders.

---

## OBDC non-accrual attribution (Q4 2025)

OBDC reported a 2.7% / 1.3% (cost/FV) non-accrual rate as of December 31, 2025. The breakdown from the Q4 2025 10-K schedule of investments (metadata-filled positions only, FV ≥ $0):

| Borrower | Cost ($M) | FV ($M) | Mark | Notes |
|---------|-----------|---------|------|-------|
| National Dentex Labs LLC (fka Barracuda Dental) | 161.8 | 78.4 | 48.5¢ | 4 tranches; large loss |
| Feradyne Outdoors, LLC | 78.2 | 54.5 | 69.7¢ | Sporting goods |
| Pluralsight, LLC | 48.8 | 44.5 | 91.2¢ | 2 tranches; near-par |
| Walker Edison Furniture Company LLC | 39.5 | 28.5 | 72.2¢ | 3 tranches incl. near-zero |
| EOS Finco S.A.R.L | 22.3 | 9.8 | 44.1¢ | European finco |
| PS Operating Company (fka QC Supply) | 13.4 | 4.2 | 31.1¢ | |
| Ideal Image Development | 2.3 | 12.1 | mixed | Revolver + term |
| Norvax (dba GoHealth) | 2.3 | 1.4 | 60.0¢ | Health insurance tech |
| Plasma Buyer LLC (dba PathGroup) | 1.4 | 1.2 | ~82¢ | 3 tranches |
| **Total** | **~370.0** | **~234.5** | **63.4¢ avg** | |

**Observations:**
- National Dentex is the largest single impairment at 48.5¢ ($83.4M unrealized loss)
- No software names in OBDC's non-accrual pool — this is healthcare, industrials, and consumer
- Pluralsight (48.8¢ → 44.5¢, 91¢ mark) is in the list but at near-par value; reflects restructured instruments
- The non-accrual pool is heavily concentrated: National Dentex + Feradyne + Walker Edison account for 78% of non-accrual FV

---

## Cornerstone OnDemand — Confirmed multi-layer impairment (Q4 2025 new entry)

*Full memo: `cornerstone_ondemand_memo.md`*

| Fund | Q3 2025 FV ($M) | Q3 Mark | Q4 2025 FV ($M) | Q4 Mark | Notes |
|------|----------------|---------|----------------|---------|-------|
| **ARCC** | ~$8.4M (revolver only) | ~100¢ | **Second lien: $125.1M / $137.5M = 91.0¢** | **91.0¢ 2L** | ARCC appears to have originated or funded new second-lien + preferred in Q4 2025 |
| **ARCC** | — | — | **Preferred: $152.3M / $179.2M = 85.0¢** | **85.0¢ pref** | 10.50% PIK; new position in Q4 |
| **OBDC** | — | — | **Second lien: $144.4M / $153.9M = 93.8¢** | **93.8¢ 2L** | Cross-lender confirmation |
| **OBDC** | — | — | **Preferred: $66.9M / $75.2M = 89.0¢** | **89.0¢ pref** | Independent mark |
| **CGBD** | — | — | First lien: $6.2M / $7.5M = **82.0¢** | **82.0¢ 1L** | Most alarming signal |
| **CGBD** | — | — | First lien: $2.2M / $2.9M = **77.2¢** | **77.2¢ 1L** | Same credit, different tranche |
| **PNNT** | — | — | First lien: $5.9M / $5.9M = **100.0¢** | **100.0¢ 1L** | Mark dispersion vs. CGBD |

**Key signal:** Cornerstone is more advanced in the impairment cycle than Zendesk. CGBD marks first-lien at 77–82¢ (identical range to BXSL's Medallia mark) while PNNT holds comparable first-lien at par — mark dispersion in the first-lien layer is confirmed. ARCC and OBDC both mark second-lien at 91–94¢ and preferred at 85–89¢ — cross-lender consistency increases mark credibility. **This is the first surveillance name where first-lien impairment is confirmed by a filed mark below 80¢** (CGBD 77.2¢), ahead of ARCC's Q4 second-lien + preferred origination at discounted prices.

Total confirmed BDC exposure (Q4 2025): ~$585M cost / ~$525M FV (~90¢ blended across ARCC, OBDC, CGBD, PNNT).

---

## Synthesis observations

**Divergence pattern confirms the thesis:**
1. The Zendesk preferred equity (−52%) and Pluralsight (ARCC FV written to zero) confirm that equity layers move before first-lien marks — the transmission sequence is equity → subordinated debt → first-lien
2. Medallia's 21-point first-lien dispersion (BXSL 78¢ vs. FSK 99¢ blended) is the clearest case where first-lien stress has become unambiguous at a major BDC; the April 2, 2026 PIK refusal has escalated this to an active restructuring situation
3. Cornerstone OnDemand adds a second name where first-lien marks have moved below 80¢ (CGBD 77.2¢) alongside second-lien and preferred impairment — advancing the surveillance universe from "equity-only impairment" to "multi-layer confirmed"
4. Kaseya's clean BSL refinancing at S+325 confirms that the market differentiates: MSP IT platforms with clean cash flows can access BSL 225bps tighter, while AI-disrupted categories (Zendesk, Medallia, Cornerstone) remain in private credit absorbing cumulative mark deterioration

**Surveillance ranking update (April 2026):**
1. **Medallia** — active restructuring; April 2026 forcing event confirmed; BXSL 77.75¢; Moody's FSK downgrade
2. **Cornerstone OnDemand** — CGBD first-lien 77–82¢; ARCC second-lien 91¢ + preferred 85¢; multi-BDC confirmed; talent management software under AI/competitive pressure
3. **Zendesk** — ARCC preferred equity −52%; first-lien clean at 99–103¢; next quarterly filing is the tell
4. **Pluralsight** — completed workout; historical template
5. **Finastra** — completed cycle; all at par; monitoring residual positions

**What to watch in Q1 2026 filings (May 2026):**
- **Medallia**: Will BXSL mark decline below 77¢? Will FSK take it to non-accrual? Q1 2026 is the first filing after the April 2026 PIK-refusal forcing event
- **Cornerstone**: Does CGBD first-lien continue declining below 77¢? Does PNNT (at par) converge toward CGBD?
- **Zendesk**: Does ARCC preferred equity decline further from $13.4M, or does it stabilize?
- **FSK overall**: After the Moody's downgrade, does FSK's Q1 2026 filing show broader mark revision across the PIK-heavy portfolio?
