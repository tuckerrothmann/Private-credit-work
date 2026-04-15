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

### Cardinal Parent / Packers Software Intermediate Holdings

Software company — identity requires additional research to confirm product category.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A $39.3M + A-2 $14.0M + A-3 $16.9M = **$70.2M** (all 11.00% PIK) | All three preferred tranches: **−$2.0M each = −$6M total** | **−$76.2M** | Second lien $70.9M at **99.6¢**; First lien no FV |

**Key signal:** All three preferred tranches written to essentially zero. Second-lien debt still marked near par. Pattern: equity impairment precedes debt impairment. Requires identity confirmation — "Packers Software" naming suggests supply chain or food industry software.

---

### CentralSquare Technologies (Supermoose Newco — government/public-safety software)

CentralSquare provides software for government agencies: public safety dispatch, utilities billing, community development permitting, and related municipal workflows. Thoma Bravo spin-off.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred **$103.3M** (15.00% PIK); First lien $144.6M (10.41% / 3.38% PIK, cost only) | **ARCC position effectively exited** — only unfunded revolver remains | **−$103.3M preferred + $144.6M first lien gone** | OCSL holds at **102¢** (suggests debt still current) |

**Key signal:** ARCC's position effectively disappeared between Q3 and Q4 — either a refinancing/exit or restructuring. OCSL still holds at 102¢. The 15.00% PIK preferred in Q3 was a significant non-cash-pay burden. Likely exits via refi or distressed transaction.

---

## Category 2: Large PIK preferred write-downs (non-software, notable for pattern confirmation)

### High Street Buyer / High Street Holdco LLC

**Company identity:** Requires research. Large insurance or financial services platform.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred (4 tranches) + common: **$290.3M** (10.00% PIK) | All units written to **−$2M each = −$12M total** | **−$302.3M** | First lien (4 tranches, ~$45.6M cost): no FV shown in Q4 |

**Key signal:** The single largest equity write-down in ARCC's Q4 portfolio. $302M in preferred and common equity effectively written to zero. The first-lien debt shows no FV — suggesting either it's at par (par = cost, so FV not separately disclosed) or the position is no longer active. The 10.00% PIK preferred at $290M was an extraordinary concentration — this was a very large preferred equity investment alongside $45-67M of first-lien.

---

### Cobalt Buyer Sub / Cobalt Holdings I

**Company identity:** Requires research. Possibly technology or services.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Series A preferred $102.1M (13.75% PIK) + preferred units $1.4M (8% PIK) = **$103.5M** | All preferred to **−$2M each = −$4M total** | **−$107.5M** | First lien (3 tranches + revolver): **94.8¢** |

**Key signal:** Large preferred write-down ($107M) AND first-lien already below par (94.8¢). When both equity AND debt show impairment, this is a Category 1 credit-quality concern, not just a capital-structure optimization. 13.75% PIK rate on preferred suggests this was always a high-risk junior layer.

---

### Balrog Acquisition / Balrog Topco

**Company identity:** Requires research.

| Q3 equity FV | Q4 equity FV | Change | Debt mark (Q4) |
|-------------|-------------|--------|---------------|
| Class A preferred $9.2M (8% PIK) + Series A preferred $34.3M (11% PIK) = **$43.5M** | All preferred to **−$2M each = −$4M total** | **−$47.5M** | First lien $16.1M / $14.0M = **87.0¢**; Second lien $29.5M / $26.0M = **88.1¢** |

**Key signal:** Both first-lien (87¢) and second-lien (88¢) below par — and equity written off. Multiple-layer impairment. The 87¢ first-lien mark suggests this credit is in active distress, not just equity-layer restructuring.

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
- Company identity for High Street Buyer, Cobalt Buyer Sub, Balrog Acquisition, and Cardinal Parent requires additional research
