# ARCC Capital Stack Scan — Equity-Layer Impairment Patterns

*Analysis of ARCC Q3→Q4 2025 portfolio filings for names where equity fair value declined while debt marks remain near par — the "Zendesk pattern" applied across the full ARCC book.*

---

## Methodology

ARCC regularly holds multi-layer positions in the same holding company: first-lien debt, second-lien debt, preferred equity (PIK), and common equity — all disclosed in the filed Schedule of Investments. Comparing Q3 2025 (10-Q) vs. Q4 2025 (10-K) across the full ARCC portfolio identifies names where equity FV declined while first-lien or second-lien marks remain at or near par.

**Filter applied:** Equity-layer FV declined by more than $1M Q3→Q4; metadata-empty (subtotal) rows excluded; invest_type categorized as debt vs. equity/preferred.

A total of **168 ARCC issuers** held both debt and equity/preferred layers in Q4 2025.

---

## Why this matters

The Zendesk finding (Series A preferred marked down 52% while first-lien is clean) is not unique to Zendesk. It is the expected signature of a capital structure where:
1. The operating company is not generating enough value to support the full stack
2. The junior equity layers absorb the initial write-down
3. The debt layers follow, typically one to two quarters later

Scanning ARCC's full book for this pattern identifies early-warning signals before they appear in the first-lien marks that other lenders and analysts typically track.

---

## Category 1: Confirmed software credits with equity impairment

### Cornerstone OnDemand (Sunshine Software Holdings / Clearlake Capital)

The most advanced case. See dedicated memo: `cornerstone_ondemand_memo.md`.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| $8.4M revolver only (Q3 ARCC) | Preferred $152.3M (85.0¢); Second lien $125.1M (91.0¢) | New large origination in Q4 at discounts | First lien ~91–100¢; Second lien 91¢ |

**Key signal:** Both debt (second-lien 91¢) and equity (preferred 85¢) marked below par. CGBD marks first-lien at 77–82¢. Multi-BDC confirmation.

---

### Cardinal Parent / Packers Software Intermediate Holdings → **Zywave, Inc.**

**Identity confirmed:** Zywave, Inc. — insurance agency management and commercial lines technology SaaS. "Packers Software Intermediate Holdings" is a Wisconsin-themed LBO code name (Zywave is headquartered in Milwaukee, WI); it has no connection to food industry or supply chain software. Sponsors: Clearlake Capital Group + Aurora Capital Partners.

**Business:** Zywave provides compliance, distribution, and analytics software to independent P&C insurance agencies and commercial lines brokers. Key products: BrokerageBuilder (CRM), Zywave Delivery Systems (DocuLink), and RiskMeter (commercial lines market intelligence). Annual recurring revenue ~$200–250M estimated. Primary customers: independent insurance agents, MGAs, and carrier distribution networks.

**Ownership history:** Aurora Capital Partners took Zywave private in 2019. Clearlake Capital acquired a significant co-sponsorship stake in 2021 alongside a leveraged recap. The "Cardinal Parent / Packers Software" entity structure reflects a 2021 LBO recapitalization layered on top of Aurora's original structure.

**Credit profile:** Moody's rated Caa2 (affirmed July 2025, following a revolver extension that Moody's deemed a distressed exchange relative to original terms). S&P rated CCC+. Maturity wall: first-lien November 2027, second-lien November 2028. Combined estimated BDC debt exposure: ~$70–100M.

**Q4 2025 ARCC marks — Zywave / Cardinal Parent:**

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A $39.3M + A-2 $14.0M + A-3 $16.9M = **$70.2M** (all 11.00% PIK) | All three preferred tranches: **−$2.0M each = −$6M total** | **−$76.2M** | Second lien $70.9M at **99.6¢**; First lien no FV |

**Key signal:** All three preferred tranches (three separate PIK instruments totaling $70.2M cost) written to essentially zero. Second-lien debt still marked near par at 99.6¢ — consistent with the "equity impairs first, debt follows" pattern. The second-lien mark is anomalously high given the Moody's Caa2 rating and 2027 maturity wall. **Surveillance note:** The 2027 first-lien maturity is ~18 months away from Q4 2025; refinancing risk is elevated at current leverage. Expect second-lien marks to compress toward 80–90¢ range if no refinancing progress by Q2 2026.

---

### CentralSquare Technologies (Supermoose Newco — government/public-safety software)

CentralSquare provides software for government agencies: public safety dispatch, utilities billing, community development permitting, and related municipal workflows. Thoma Bravo spin-off.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred **$103.3M** (15.00% PIK); First lien $144.6M (10.41% / 3.38% PIK, cost only) | **ARCC position effectively exited** — only unfunded revolver remains | **−$103.3M preferred + $144.6M first lien gone** | OCSL holds at **102¢** (suggests debt still current) |

**Key signal:** ARCC's position effectively disappeared between Q3 and Q4 — either a refinancing/exit or restructuring. OCSL still holds at 102¢. The 15.00% PIK preferred in Q3 was a significant non-cash-pay burden. Likely exits via refi or distressed transaction.

---

## Category 2: Large PIK preferred write-downs (non-software, notable for pattern confirmation)

### High Street Buyer / High Street Holdco LLC → **High Street Insurance Partners (HSIP) / Highstreet Insurance Partners**

**Identity confirmed:** High Street Insurance Partners (currently rebranded Highstreet Insurance Partners) — full-service independent insurance brokerage and benefits platform. HQ: Traverse City, Michigan. Founded 2018 by Scott Wick. SEC EDGAR CIK: 0002021228 (Form D filings corroborate four-tranche 10.00% PIK preferred structure).

**Business:** Buy-and-build independent insurance agency platform (P&C, employee benefits, financial/retirement, personal lines). As of year-end 2025: ~3,000 employees, ~350 offices, 36 states, 189+ acquisitions completed since inception. Revenue exceeded $700M in 2025 (from ~$100M at 2021 Abry acquisition). One of the top 25 U.S. insurance brokers by revenue; ranked #4–6 most active acquirer in independent agency M&A league tables.

**PE Sponsor:** Abry Partners (Boston) — acquired from founding sponsor Huron Capital Partners in April 2021. Abry owns ~22%; remainder held by management, agency partners, and Huron Capital rollover.

**Ares / ARCC role:** Critically, Ares Capital served as **administrative agent, lead arranger, and bookrunner on the senior secured credit facility AND invested preferred AND common equity** at the 2021 Abry acquisition — confirmed by Ares Management Q2/Q3 2021 Direct Lending Commitments bulletins. This explains the unusual multi-layer concentration ($290M+ preferred alongside first-lien debt). Ares was also lead arranger on the August 2025 $550M DDTL refinancing.

**Write-down interpretation:** The operating company HSIP appears operationally healthy — active acquisitions continued through March 2026, no public disclosure of default or restructuring. The $302M write-down likely reflects either: (1) HoldCo preferred impaired by the August 2025 DDTL recapitalization that shifted value to first-lien lenders, leaving holdco preferred structurally below waterfall recovery, or (2) an EBITDA/LTV mark-to-model determination that enterprise value no longer supports preferred layer recovery. This is a **capital structure distress** not an operating company default.

**Q4 2025 ARCC marks — High Street:**

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred (4 tranches) + common: **$290.3M** (10.00% PIK) | All units written to **−$2M each = −$12M total** | **−$302.3M** | First lien (4 tranches, ~$45.6M cost): no FV shown in Q4 |

**Key signal:** The single largest equity write-down in ARCC's Q4 portfolio. $302M in preferred and common equity effectively written to zero. First-lien debt shows no FV in Q4 — possibly at or near par (no separate FV disclosed when FV ≈ cost) or restructured in the August 2025 DDTL. The 10.00% PIK preferred at $290M was an extraordinary concentration in a single insurance distribution platform.

**Open items:** (1) Confirm fate of first-lien tranches ($45–67M cost) post-August 2025 DDTL. (2) Screen other BDC schedules of investments for "High Street Buyer" to identify co-lenders. (3) Monitor ARCC Q1 2026 10-Q (expected May 2026) for any first-lien mark changes.

---

### Cobalt Buyer Sub / Cobalt Holdings I → **Pharmaceuticals (sector confirmed; operating company name unresolved)**

**Identity:** Sector confirmed as pharmaceuticals via Golub Capital BDC (GBDC) industry classification. The operating company name is not publicly resolvable from available SEC filing cross-references. "Cobalt" naming is consistent with the pharmaceutical sector (blue cobalt imagery is common in pharma branding). Sponsor identity unknown from public sources.

**Cross-issuer divergence — critical analytical signal:** GBDC holds the **original LBO co-invest common equity** (cost ~$11K → Q4 2025 FV ~$19.1M), which is appreciating — indicating genuine enterprise value growth at the operating company level. ARCC holds a **later-vintage rescue preferred** (13.75% PIK Series A, cost ~$104.6M → Q4 2025 FV ~−$2.0M), which has been written off entirely. This is NOT contradictory:
- GBDC's original equity (essentially costless, acquired at LBO close) represents residual enterprise value above all debt
- ARCC's rescue preferred (issued years after the LBO, at high PIK rate) was a junior capital infusion that sat below GBDC's equity in the recovery waterfall — or was issued at the holdco level where structural subordination trapped it
- The 13.75% PIK rate signals this was always a high-risk junior capital infusion, priced as distress financing from inception

**Q4 2025 ARCC marks — Cobalt:**

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred $102.1M (13.75% PIK) + preferred units $1.4M (8% PIK) = **$103.5M** | All preferred to **−$2M each = −$4M total** | **−$107.5M** | First lien (3 tranches + revolver): **94.8¢** |

**Key signal:** Large preferred write-down ($107M) AND first-lien already below par (94.8¢). When both equity AND debt show impairment, this is a Category 1 credit-quality concern, not a capital-structure optimization. The GBDC equity appreciation confirms the operating company has positive enterprise value — meaning the Cobalt senior credit facility debt (94.8¢) may recover more than the mark implies. The total write-off is concentrated in ARCC's high-PIK junior capital layer.

**Open item:** Company name remains unresolved. Recommend cross-referencing GBDC's Q4 2025 10-K schedule of investments filtered to pharmaceuticals sector and $11K–$19M equity positions to identify the operating company.

---

### Balrog Acquisition / Balrog Topco → **BakeMark USA, LLC**

**Identity confirmed:** BakeMark USA, LLC — leading North American distributor of bakery ingredients and supplies to commercial bakeries, in-store bakeries, and foodservice operators. Confirmed via OBDC (Blue Owl Capital Corporation) 10-K schedule of investments, which explicitly cross-references the Balrog holding entities with the "BakeMark" DBA. Sponsor: Clearlake Capital Group (acquired in 2021 LBO).

**Business:** BakeMark distributes fats/oils, icings, mixes, fillings, and specialty bakery ingredients to wholesale and retail bakeries across North America. Revenues estimated ~$1.5–2.0B (distribution-model, low margin). At 2021 LBO close: S&P B-, estimated 9x leverage. Subject to commodity input cost inflation (palm oil, shortening, cocoa) and foodservice end-market volatility.

**Multi-BDC exposure — second-lien distress confirmed:**
- OBDC (Blue Owl): Second-lien Tranche A mark declined from **96.7¢ (Q3 2025)** to **81.0¢ (Q4 2025)** — a -15.7¢ single-quarter decline
- ARCC: Second lien ~88¢; First lien ~87¢ — both below par, multi-layer impairment confirmed
- Combined disclosed BDC second-lien exposure: ~$79M par value
- S&P maintained research update in January 2026 noting deteriorating credit metrics

**Q4 2025 ARCC marks — BakeMark / Balrog:**

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Class A preferred $9.2M (8% PIK) + Series A preferred $34.3M (11% PIK) = **$43.5M** | All preferred to **−$2M each = −$4M total** | **−$47.5M** | First lien $16.1M / $14.0M = **87.0¢**; Second lien $29.5M / $26.0M = **88.1¢** |

**Key signal:** Both first-lien (87¢) and second-lien (88¢) below par — and equity written off. Multiple-layer impairment at all levels of the capital structure. The 87¢ first-lien mark and OBDC's 81¢ second-lien mark (sharper decline than ARCC's mark) indicate active credit distress. BakeMark is a **non-software credit** but its multi-layer impairment pattern (Clearlake sponsor, 9x LBO leverage, all equity written off, both lien layers below par) mirrors the software names and confirms ARCC's systematic risk is broader than the software thesis alone. See Clearlake Capital concentration section below.

---

---

## Clearlake Capital concentration risk

Three of the five named write-down credits above are **Clearlake Capital Group** portfolio companies:

| Company | Sector | Clearlake role | ARCC position status |
|---------|--------|---------------|----------------------|
| Cornerstone OnDemand (Sunshine Software) | HCM/workforce SaaS | Controlling sponsor ($5.4B 2021 take-private) | 2L at 91¢, preferred at 85¢ — active surveillance |
| Zywave, Inc. (Cardinal Parent) | Insurance agency SaaS | Co-sponsor (with Aurora Capital) | Preferred written off; 2L at 99.6¢ — maturity wall 2027 |
| BakeMark USA (Balrog Acquisition) | Bakery distribution | Controlling sponsor (2021 LBO) | All equity written off; 1L 87¢, 2L 81–88¢ — active distress |

**Clearlake's broader distress pattern in the same period:**
- **Pretium Packaging:** Chapter 11 bankruptcy filed 2025. Clearlake-backed rigid packaging company. ARCC and other BDCs held first-lien exposure.
- **Wellness Pet:** Distressed debt exchange completed June 2025 (technically a default under Moody's/S&P definition). Clearlake-backed premium pet food brand.

**Concentration thesis:** Clearlake's portfolio companies — particularly those acquired in 2021 at peak leverage multiples — are experiencing simultaneous credit deterioration. The common thread is: (1) 2021 LBO vintage at 8–11x leverage, (2) higher-than-expected input costs or revenue shortfalls in 2022–2024, (3) PIK preferred structures that allowed deferred payments to mask cash flow strain, and (4) coordinated write-downs in Q4 2025 as the PIK interest compounding reached unsustainable levels or refinancing windows closed.

**For ARCC:** The Clearlake concentration means that three separate "independent" write-downs in the ARCC book are actually exposed to the same PE sponsor's portfolio management decisions and creditor relationships. In a workout or restructuring scenario, Clearlake would be negotiating with ARCC on multiple fronts simultaneously — creating leverage risk in the other direction.

---

## Systematic pattern observations

### 1. The −$2M marker
Many ARCC equity write-downs end at exactly −$2.0M FV. This appears to be ARCC's convention for reporting equity positions that have been written to nominal/zero value — it represents "economic zero" rather than a literal negative $2M. The pattern is consistent: when ARCC writes preferred equity to essentially zero, the FV shows as −$2.0M.

### 2. PIK rate as risk proxy
The write-down severity correlates with the original PIK rate:
- 10% PIK preferred → large write-downs (High Street $302M, likely high-leverage acquisition with deferred equity returns)
- 11–11% PIK → significant write-downs (Cardinal, Balrog)
- 13.75–15% PIK → full write-offs (Cobalt, CentralSquare) — the highest rates signal the most subordinated risk layers

### 3. Debt marks follow equity with a lag
The sequence is consistent across the ARCC portfolio and matches the Pluralsight/Medallia pattern:
1. Equity (common, then preferred) impaired first
2. Second-lien impaired 1–2 quarters later
3. First-lien impaired last (if at all)

Cornerstone is at Step 2 (second-lien at 91–94¢). Balrog and Cobalt are at Step 2+ (both debt layers impaired). High Street may be at Step 3 depending on first-lien status.

### 4. Total scale of Q3→Q4 equity impairment
From the top 30 declines alone:

| Name | Q3 equity FV | Q4 equity FV | Decline |
|------|------------|------------|---------|
| High Street Buyer | $290.3M | −$12.0M | −$302M |
| Miami Beckham United | $174.5M | $0.0M | −$174M |
| Cobalt Buyer | $103.5M | −$4.0M | −$107M |
| CentralSquare Technologies | $103.3M | $0.0M* | −$103M |
| Cardinal Parent / Packers Software | $70.2M | −$6.0M | −$76M |
| Balrog Acquisition | $43.5M | −$4.0M | −$47M |
| Essential Services Holding | $37.2M | −$4.0M | −$41M |
| Zendesk | $30.4M | $11.4M | −$19M |
| **Subtotal (top 8)** | **$853M** | | **−$869M** |

*CentralSquare position effectively exited

The top 8 names alone represent approximately $869M in equity fair value reductions Q3→Q4 2025, from a starting point of ~$853M. This is essentially full write-offs of these equity positions within a single quarter.

---

## Surveillance implications

**For the project thesis:** The pattern confirms that ARCC — the largest and most diversified BDC — is systematically absorbing large equity write-downs on its preferred and common equity co-investments, while first-lien debt remains marked closer to par. This is consistent with the project's prediction that:
- BDC books contain more risk than first-lien-focused analysis suggests
- Equity layers embedded in "diversified" BDC portfolios can absorb hundreds of millions in unrealized losses without triggering non-accrual
- The next step in the impairment cycle is second-lien and eventually first-lien recognition

**Cornerstone OnDemand is the highest-priority new name** because it shows second-lien impairment (91–94¢) already confirmed by multiple lenders, plus CGBD first-lien at 77–82¢ — the clearest advance signal that debt-layer recognition is imminent.

**For BDC unsecured bonds:** ARCC's equity write-downs of $869M+ in a single quarter from the top 8 names represent a meaningful compression of NAV that is real but may not be fully visible in headline non-accrual rates (all positions remain accruing). This is exactly the "hidden mark risk" the project is tracking.

---

## Data notes
- All data from ARCC Q3 2025 (10-Q, September 30, 2025) and Q4 2025 (10-K, December 31, 2025) filed Schedules of Investments
- Metadata-empty rows (no par_str, rate_str, pct_nav_str) excluded from analysis — these are subtotal/aggregate rows
- The −$2.0M FV values are ARCC's convention for writing positions to nominal/zero value
- Company identities confirmed via EDGAR cross-reference, OBDC DBA disclosures, and Moody's/S&P rating commentary:
  - **High Street Buyer** = High Street Insurance Partners / Highstreet Insurance Partners (Abry Partners; insurance brokerage; Traverse City MI; SEC CIK 0002021228)
  - **Cardinal Parent / Packers Software** = Zywave, Inc. (Clearlake Capital + Aurora; insurance SaaS; Milwaukee WI; Moody's Caa2)
  - **Cobalt Buyer Sub** = Pharmaceuticals sector confirmed (GBDC industry tag); operating company name unresolved
  - **Balrog Acquisition** = BakeMark USA, LLC (Clearlake Capital; bakery distribution; confirmed via OBDC DBA disclosure)
- Updated April 2026
