# Issuer / Lender / BDC Exposure Matrix

*Last updated: April 2026. Filing-sourced data from borrower_db.json cross-fund index.*

## How to read this matrix

| Cell label | Meaning |
|-----------|---------|
| **Confirmed (filed)** | Issuer appears in this BDC's filed Schedule of Investments (10-K or 10-Q) |
| **Confirmed (portfolio page)** | Issuer appears on the fund's public portfolio disclosure page |
| **Confirmed (law firm / announcement)** | Lender platform publicly identified in financing announcement |
| **Likely / ecosystem** | Platform's public ecosystem strongly suggests exposure; not yet in a filed schedule |
| **No evidence** | No confirmed or strongly plausible evidence found in this project's sources |

**Sourcing standard:** "Confirmed (filed)" entries are backed by borrower_db.json data drawn from public BDC 10-K and 10-Q filings. Other confirmation types are backed by law-firm pages, portfolio disclosure pages, or credible public reporting cited in source_log.md.

---

## Primary surveillance matrix — 9 issuers × 11 BDC / credit vehicles

| Issuer | ARCC | BXSL | BCRED | FSK | OBDC | OTF | GSBD | GBDC | CGBD | OCSL | HTGC |
|--------|------|------|-------|-----|------|-----|------|------|------|------|------|
| **Medallia** | No evidence | **Confirmed (filed)** 78.3¢ | **Confirmed (portfolio page)** | **Confirmed (filed)** ~99¢ PIK | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence |
| **Finastra** | **Confirmed (filed)** 102¢ | No evidence | No evidence | No evidence | **Confirmed (filed)** revolving ~101¢ | **Confirmed (portfolio page)** | No evidence | **Confirmed (filed)** ~98.8¢ | No evidence | **Confirmed (filed)** 98¢ fixed | No evidence |
| **Kaseya** | **Confirmed (filed)** PIK preferred equity | No evidence | No evidence | No evidence | **Confirmed (filed)** 100¢ pref | No evidence | **Confirmed (filed)** 101¢ | **Confirmed (filed)** 101¢ | **Confirmed (filed)** 102¢ | **Confirmed (filed)** 100¢ | No evidence |
| **Zendesk** | **Confirmed (filed)** 1st lien + **PIK pref −52%** | **Confirmed (filed)** 101¢ | **Confirmed (portfolio page)** | **Confirmed (filed)** ~101¢ | **Confirmed (filed)** ~101¢ | **Confirmed (portfolio page)** | No evidence | **Confirmed (filed)** ~100¢ | No evidence | No evidence | No evidence |
| **RealPage** | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence |
| **Anaplan** | **Confirmed (filed)** 100¢ | **Confirmed (filed)** 101¢ | No evidence | No evidence | No evidence | **Confirmed (portfolio page)** | No evidence | No evidence | No evidence | No evidence | No evidence |
| **Avalara** | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | No evidence | **Confirmed (filed)** 102¢ | **Confirmed (filed)** 101¢ | No evidence |
| **Coupa** | No evidence | **Confirmed (filed)** 102¢ | No evidence | No evidence | No evidence | **Confirmed (portfolio page)** | No evidence | **Confirmed (ann't)** | No evidence | No evidence | No evidence |
| **Pluralsight** | **Confirmed (filed)** PIK debt 1.50% | No evidence | No evidence | No evidence | No evidence | No evidence | **Confirmed (filed)** debt + equity | No evidence | No evidence | No evidence | No evidence |

---

## Detailed notes by issuer

### Medallia
- **BXSL (Blackstone Secured Lending):** Q4 2025 10-K. Two tranches. Cost $393.4M, FV $307.9M. **78.3 cents on dollar.** No non-accrual. Maturity October 29, 2028.
- **FSK (FS KKR Capital Corp):** Q3–Q4 2025 10-Q/10-K. Multiple tranches. Cash tranche at ~99.4 cents. PIK tranche (4.0% PIK, SOFR+250bps) at ~98.4 cents. No non-accrual. Maturity October 29, 2028.
- **BCRED (Blackstone Private Credit):** Portfolio page (Jan 2026). Listed as "Medallia/F1 (Medallia, Inc.)" first-lien senior secured. Mark and size not publicly disclosed.
- **Mark dispersion:** 21 percentage points between BXSL (78¢) and FSK (~99¢) as of the same period-end. The Blackstone mark has drifted from approximately 94 (late 2024) to 78 (Q4 2025) per public reporting.

### Finastra
- **Deal lifecycle:** $5.3B private-credit unitranche (SOFR+725) originated September 2023; went on non-accrual at OBDC by Q4 2024; April 2025 syndicated refinancing attempt failed; **August 2025: fully refinanced via $4.195B cross-border syndicated TLB (S+400 / S+700)** — private-credit unitranche repaid in full.
- **ARCC (Ares Capital Corporation):** Q4 2025 10-K. First-lien senior secured loan: cost $51.4M, FV $52.6M. **102.3 cents.** No non-accrual. Rate 10.97% (floating). Post-refinancing instrument; nature (new syndicated / revolving / residual) to be confirmed.
- **OCSL (Oaktree Specialty Lending):** FY2025 10-K. First-lien: cost $11.7M, FV $11.5M. **98.3 cents.** No non-accrual. Maturity September 13, 2029. Fixed rate 7.25%.
- **OBDC (Blue Owl Capital Corporation):** Q4 2025 10-K. First-lien revolving loan: cost $27.5M, FV $27.9M, accruing normally. The TLB was on non-accrual at OBDC as of December 31, 2024 and was repaid in August 2025 via the syndicated refinancing. OBDC's remaining exposure is the revolving facility only.
- **GBDC (Golub Capital BDC):** Q4 2025. "One stop" positions at ~98.8 cents; small (~$2.9M FV); no non-accrual.
- **OTF (Blue Owl Technology Finance):** Portfolio holdings page. Listed as Finastra USA first-lien senior secured loan.
- **Mark dispersion note:** The 4-point gap between ARCC (102¢) and OCSL (98¢) reflects rate structure, not credit quality. ARCC floating ~11% vs. OCSL fixed 7.25% — below-market fixed rate discounts appropriately in a high-rate environment.
- **Parser artifact note:** The portfolio parser showed a $93.5M OBDC entry with is_non_accrual=true. This is **prior-year (December 31, 2024) comparison-column data** — the Q3 and Q4 2025 10-Q/10-K SOI tables include prior-year comparison columns, and the parser extracted both. The non-accrual on the TLB was real as of December 31, 2024 but was resolved by the August 2025 refinancing. Diagnostics: identical cost/FV across Q3 and Q4, FV above cost (100.9¢), empty rate/par/pct_nav.

### Kaseya
- **Refinancing completed March 2025:** $3.175B first-lien at **S+325** (7yr, OID 99.5) + $925M second-lien at **S+500** (8yr, OID 99.5) + $535M revolving facility. Lead arranger: Morgan Stanley. Original 2022 private-credit syndicate (S+550) repaid in full. Pricing 225bps tighter on first-lien confirms market comfort.
- **CGBD (TCG BDC / Carlyle Secured Lending):** Q3–Q4 2025 10-Q/10-K. First-lien: cost $36.3M, FV $36.8M. **101.5 cents.** New BSL paper (post-Mar 2025 refi). Maturity June 23, 2029.
- **GSBD (Goldman Sachs BDC):** Q4 2025 10-K. First-lien: cost $19.1M, FV $19.4M. **101.1 cents.** New BSL paper.
- **OBDC (Blue Owl Capital Corporation):** Q4 2025. Perpetual preferred stock (S+): cost $17.4M, FV $17.3M. **99.7 cents.** No non-accrual.
- **OCSL (Oaktree Specialty Lending):** Q4 2025. First-lien: cost $34.3M, FV $34.2M. **99.5 cents.**
- **SLRC (SLR Investment Corp):** Q3–Q4 2025. First-lien: cost $33.8M, FV $33.6M. **99.2 cents.** PIK.
- **TCPC (BlackRock TCP Capital):** Q4 2025. First-lien: cost $9.3M, FV $9.5M. **102.8 cents.**
- **ARCC (Ares Capital Corporation):** Q3 2025: cost $31.8M, rate **14.62% PIK**. Q4 2025: cost grew to $34.1M, rate **14.35% PIK**. **Holding-company preferred stock** in Knockout Intermediate Holdings I — not refinanced; remains outstanding. Cost basis grew $2.3M Q3→Q4 from PIK accretion.
- **GBDC (Golub Capital BDC):** Original 2022 lender confirmed via Paul, Weiss announcement. Q3/Q4 2025 shows ~$4M equity/warrant position at ~1600¢ mark — consistent with a small equity co-invest, not a first-lien term loan.
- **Structural note:** The 2025 refinancing added a new $925M second-lien tranche (S+500) not present in the 2022 structure. ARCC's holding-company PIK preferred ($34.1M accreting) remains outstanding behind the full $4.1B debt stack.

### Zendesk
- **ARCC (Ares Capital Corporation) — key mark signal:** ARCC holds a full capital stack in Zoro TopCo (the Zendesk holding company): (1) first-lien term loan (~$36.2M cost, 8.69% floating); (2) **Series A preferred stock (13.50% PIK)**: Q3 FV $27.9M → Q4 FV **$13.4M (−52% Q3→Q4)**; (3) Class A common equity: Q3 FV $2.5M → Q4 FV **−$2.0M (written to zero)**. The 52% preferred equity markdown is the first concrete filing-sourced evidence of capital-structure impairment at Zendesk.
- **BXSL (Blackstone Secured Lending):** Q4 2025 10-K. First-lien term loan: cost $1.82M, FV $1.84M. **101.0 cents.** Maturity November 22, 2028.
- **FSK (FS KKR Capital Corp):** Q4 2025 (10-K). Six tranches totaling approximately $158.8M cost / $159.7M FV. ~100.6¢ avg. No non-accrual. Q4 size doubled vs. Q3 ($79.1M) from new originations.
- **GBDC (Golub Capital BDC):** Q4 2025. First-lien "one stop": ~$28.3M cost / $28.2M FV. **~99.6 cents.**
- **OBDC (Blue Owl Capital Corporation):** Q4 2025. First-lien: ~$177.9M cost / $180.3M FV. **~101.3 cents.** Slight position growth Q3→Q4.
- **TCPC (BlackRock TCP Capital):** Q4 2025. First-lien: ~$5.6M cost / $5.8M FV. **~103.6 cents.**
- **BCRED (Blackstone Private Credit):** Portfolio page (Jan 2026). Listed as Zendesk, Inc. first-lien senior secured.
- **OTF (Blue Owl Technology Finance):** Portfolio holdings page. Listed as Zendesk, Inc. first-lien senior secured loan.
- **Capital-structure pattern:** Equity layers (ARCC preferred −52%, common near zero) are absorbing losses while first-lien lenders (FSK, GBDC, OBDC, BXSL, TCPC) remain at 99–103¢. This is the exact pattern seen at Pluralsight before first-lien marks moved.

### RealPage
- **No confirmed BDC portfolio holdings** found in borrower_db.json across the 27-BDC surveillance universe.
- **Lender confirmation:** Latham advises on $4.0B financing package (first-lien term loan, revolver, second-lien). Syndicate members not publicly named.
- **Status:** Legal and regulatory watch case rather than direct BDC mark-surveillance case.

### Anaplan
- **ARCC (Ares Capital Corporation):** Q3–Q4 2025. First-lien senior secured: cost $5.8M, FV $5.8M. **100.0 cents.** Fixed rate (8.70% Q3, 8.32% Q4). Maturity June 2029.
- **BXSL (Blackstone Secured Lending):** Q4 2025 10-K. Three first-lien tranches. Total cost $44.9M, FV $45.3M. **100.6–101.4 cents.** SOFR+. Maturity June 21, 2029.
- **OTF (Blue Owl Technology Finance):** Portfolio holdings page. Listed as Anaplan first-lien senior secured loan.
- **Lender confirmation:** Latham advises direct lenders on financing supporting Thoma Bravo's acquisition of Anaplan.

### Avalara
- **CGBD (TCG BDC / Carlyle Secured Lending):** Q3–Q4 2025. First-lien: cost $23.4M, FV $23.9M. **101.9 cents.** SOFR-based. Maturity October 19, 2028. Plus revolver (unfunded, CGBD 10-K).
- **OCSL (Oaktree Specialty Lending):** FY2025 10-K. First-lien: cost $49.8M, FV $50.5M. **101.4 cents.** Fixed rate 6.25%. Maturity October 19, 2028. Plus second position (unfunded revolver, small negative FV).

### Coupa
- **BXSL (Blackstone Secured Lending):** Q4 2025 10-K. Two first-lien tranches. Total cost $3.57M, FV $3.64M. **101.7–102.2 cents.** SOFR+. Maturity February 27, 2030.
- **OTF (Blue Owl Technology Finance):** Portfolio holdings page. Listed as Coupa Holdings first-lien senior secured loan.
- **GBDC (Golub Capital BDC):** Confirmed as original 2023 lender per public reporting. Filing-level confirmation in GBDC schedules not yet verified.

### Pluralsight
- **ARCC (Ares Capital Corporation):** Q3 2025 10-Q. First-lien senior secured: FV $21.6M. Rate **8.70% + 1.50% PIK** (post-restructuring PIK feature). Maturity August 2029.
- **GSBD (Goldman Sachs BDC):** Q3 2025 10-Q. Multiple positions: first-lien debt at 11.70% ($15.7M FV), first-lien debt at 8.70% ($9.7M FV and $4.9M FV), plus **common stock** (approximately $13.2M FV — large cost basis impaired via restructuring). Maturity August 22, 2029.
- **Lender/new-owner group:** Goodwin summary identifies Blue Owl, Ares, Golub, Oaktree, Benefit Street, Goldman Sachs, and BlackRock as part of the debt-for-equity exchange group.
- **KBRA designation:** Called Pluralsight a "bellwether" for private-credit BDC exposure in 2024 restructuring commentary.

---

## Mark summary — confirmed filing-sourced data

| Issuer | Best-supported mark | Filing date | Fund | Status |
|--------|--------------------|-----------|----|--------|
| Medallia | **78.3¢** | Q4 2025 10-K | BXSL | Current; diverges from FSK at 99¢ |
| Medallia | **~99¢ (PIK active)** | Q4 2025 10-K | FSK | 21-point gap vs. BXSL |
| Finastra | **102¢** | Q4 2025 10-K | ARCC | Floating rate; accruing; no stress signal |
| Finastra | **98¢ (fixed 7.25%)** | Q4 2025 10-K | OCSL | Fixed below-market rate; discount reflects rate duration, not credit concern |
| Kaseya | **102¢** | Q4 2025 10-K | CGBD | Clean first-lien |
| Kaseya | **PIK preferred** (14.62%) | Q4 2025 10-K | ARCC | Holdco preferred, no cash pay |
| Zendesk | **101¢** | Q4 2025 10-K | BXSL | Clean; forward AI risk |
| Anaplan | **101¢** | Q4 2025 10-K | BXSL | Clean control case |
| Avalara | **102¢** | Q4 2025 10-K | CGBD | Clean control case |
| Coupa | **102¢** | Q4 2025 10-K | BXSL | Clean forward risk |
| Pluralsight | **PIK debt + equity** | Q3 2025 10-Q | ARCC/GSBD | Post-restructuring positions |

---

## Risk tier summary

| Issuer | Risk tier | Primary signal | BDC visibility |
|--------|-----------|---------------|----------------|
| Medallia | **Tier 1 — Live stress** | 78¢ mark at BXSL; 21-pt dispersion; PIK at FSK | BXSL, FSK, BCRED |
| Finastra | **Tier 3 — Completed cycle / historical anchor** | Unitranche repaid Aug 2025 via $4.2B syndicated refi; TLB was non-accrual at OBDC in Q4 2024 | ARCC, OCSL, OBDC (revolver), GBDC, OTF |
| Pluralsight | **Tier 1 — Historical workout** | PIK debt + equity post-restructuring | ARCC, GSBD |
| Kaseya | **Tier 2 — Hidden structure** | PIK preferred in holdco; refi catalyst | CGBD, GSBD, ARCC |
| Zendesk | **Tier 2 — Forward risk** | Broadest BDC visibility; AI category | BXSL, FSK, BCRED, OTF |
| RealPage | **Tier 2 — Legal/regulatory** | No BDC confirmation; legal overhang | (No BDC filing confirmation) |
| Coupa | **Tier 3 — Control / watch** | Clean marks; AI risk latent | BXSL, OTF |
| Anaplan | **Tier 3 — Control / watch** | Clean marks; 2029 refi to watch | ARCC, BXSL, OTF |
| Avalara | **Tier 3 — Control / defensible** | Strongest recovery thesis; clean marks | CGBD, OCSL |

---

## What this matrix enables

1. **BDC-level concentration check** — BXSL appears in Medallia, Zendesk, Anaplan, and Coupa; understanding BXSL's total software exposure helps size the mark-down risk in one vehicle
2. **Cross-lender divergence tracking** — BXSL vs. FSK on Medallia is the live 21-point dispersion to watch; ARCC (102¢, floating) vs. OCSL (98¢, fixed 7.25%) on Finastra reflects rate structure rather than credit divergence
3. **ARCC exposure audit** — ARCC appears in Anaplan (clean), Kaseya (PIK preferred), Pluralsight (PIK debt), and Finastra (accruing) — a mixed picture that warrants monitoring in ARCC's own published disclosures
4. **Refinancing wall** — October 2028 (Avalara), November 2028 (Zendesk), June–August 2029 (Anaplan, Kaseya, Finastra, Pluralsight) is a concentrated maturity window for this universe

---

## Sourcing notes and confidence levels

**Highest confidence (filing-sourced via borrower_db.json):**
Medallia at BXSL and FSK; Finastra at OBDC, ARCC, and OCSL; Kaseya at CGBD and GSBD; Zendesk at BXSL and FSK; Anaplan at ARCC and BXSL; Avalara at CGBD and OCSL; Coupa at BXSL; Pluralsight at ARCC and GSBD; Kaseya PIK preferred at ARCC.

**Good confidence (portfolio page or law firm announcement):**
Medallia at BCRED; Finastra and Zendesk at OTF; Zendesk at BCRED; Anaplan, Coupa at OTF; ARCC Zendesk from research-backed public portfolio commentary.

**Screening confidence (transaction-level announcement only; filing not yet confirmed):**
Kaseya and Coupa at GBDC (Golub identified as lender in 2022/2023 announcements).

**No evidence:**
RealPage across the entire 27-BDC universe in the borrower_db.json index.
