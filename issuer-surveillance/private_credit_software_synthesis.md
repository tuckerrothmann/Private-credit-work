# Software Private Credit — PM-Level Synthesis

*A unified view across the issuer universe, lender landscape, and transmission risk to BDC unsecured bonds*

---

## The central argument

Software private credit is not a monolithic risk. It is a **dispersion story** — and the divergence between the best and worst credits in the private-credit software universe is widening in ways that are not yet uniformly visible in published marks, accrual statuses, or BDC portfolio commentary.

The practical implication for BDC unsecured bond investors is this: **the risk is not that software is uniformly bad**. The risk is that the average mark across a BDC's software book may be the average of some very healthy names and some seriously impaired ones — and that the impaired ones may not yet be recognizably impaired in the published schedules.

This memo synthesizes the full issuer universe into a coherent PM-level framework.

---

## The five issuer categories

### Category 1: Active restructuring — capital-structure decisions being made now

**Medallia** has escalated from mark surveillance to active restructuring. The April 2, 2026 Bloomberg report confirmed that **lenders led by Blackstone refused to extend the PIK lifeline**, forcing full cash-pay interest that adds ~$100M per year against ~$200M in EBITDA — coverage of approximately **0.67x**. Total debt has grown to ~$3B via PIK accrual. BXSL now marks the position at **77.75¢** (Q4 2025 earnings). FSK's Q4 2025 earnings separately disclosed the impaired PIK tranche at ~$185M FV / $233M cost = ~79¢. On March 24, 2026, Moody's **downgraded FSK to Ba1** (speculative grade), citing its 14.7% PIK income share (vs. 6.3% peer median) and naming Medallia specifically. Restructuring options being discussed: debt-for-equity swap or fresh equity injection by Thoma Bravo.

**Key signal:** This is no longer a forward risk — it is a live forced restructuring event. Non-accrual designation at BXSL or FSK in Q1 2026 filings is the next measurable trigger.

**Cornerstone OnDemand** is the second Category 1 name — confirmed by Q4 2025 10-K filings across ARCC and OBDC. *(Correction April 2026: earlier versions incorrectly attributed CGBD first-lien marks at 77–82¢ and a PNNT first-lien at par to Cornerstone OnDemand. Those positions are Cornerstone Building Brands and Cornerstone Advisors of Arizona respectively — different companies with similar names.)* Clearlake Capital's 2021 ~$5.2B take-private of this talent management software platform shows impairment in the second-lien and preferred equity layers: ARCC marks second-lien at **91¢** and preferred at **85¢**; OBDC marks second-lien at **94¢** and preferred at **89¢**. The $2.1B first-lien is a **broadly syndicated TLB** (CUSIP 86803YAB92) held by CLOs and loan funds — invisible in BDC filings — trading at approximately **78–83¢** in the secondary leveraged loan market. The October 2026 revolver ($300M) is the near-term forcing event. Total confirmed BDC exposure: ~$583M cost / ~$531M FV (ARCC + OBDC only).

**Key signal:** The BSL market pricing the $2.1B first-lien at 78–83¢ is real-time, arm's-length pricing that leads BDC quarterly marks. ARCC also holds appreciating common equity ($13.6M → $19.9M), indicating the operating company has positive enterprise value — the distress is structural (over-leverage) not operational. See dedicated memo: `cornerstone_ondemand_memo.md`.

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
1. **Medallia** — active restructuring; April 2026 PIK refusal forcing event; BXSL 77.75¢; Moody's FSK downgrade Ba1; 0.67x coverage; debt-for-equity or Thoma Bravo equity injection imminent
2. **Cornerstone OnDemand** — $2.1B BSL first-lien TLB at ~78–83¢ in secondary market; ARCC/OBDC second-lien 91–94¢; preferred 85–89¢; Oct 2026 revolver wall; primary driver: 2021 LBO leverage + rate shock + AI pressure on talent management software
3. **Zendesk** — ARCC preferred equity −52% Q3→Q4 2025; first-lien clean at 99–103¢ across FSK, OBDC, GBDC, BXSL, TCPC; **pure private credit — NO BSL TLB**; $4.6B senior debt held by 5-lender private club (BCRED dominant at ~$1B+, non-traded, completely opaque); BDC-visible ~$409M = only 9% of total first-lien; ~1x interest coverage (~$430M cash interest vs. ~$400–500M EBITDA); Nov 2028 first-lien maturity; see `zendesk_memo.md`
4. **Zywave** *(new)* — Caa2/CCC+; ARCC preferred written to zero Q4 2025; $450M BSL first-lien (Nov 2027 maturity); ARCC 2L at anomalous 99.6¢ — most likely compression candidate Q1/Q2 2026; sole BDC holder; Clearlake + Aurora Capital sponsors; see `zywave_memo.md`
5. **Finastra** — completed cycle / historical anchor; all lenders at par; scale demands ongoing monitoring
6. **Kaseya** — first-lien resolved via BSL refi at S+325; residual risk in holding-company PIK preferred ($34.1M accreting) and new $925M second-lien
7. **Pluralsight** — completed workout; ARCC FV written to zero; GSBD marks declining
8. **RealPage** — no confirmed BDC holding; legal risk template unique and applicable more broadly

*Updated April 2026: Medallia #1 (active restructuring). Cornerstone #2 corrected — CGBD/PNNT were misidentified; actual signal is BSL secondary market pricing at 78–83¢. Zywave added as #4 (new surveillance name, Caa2, Nov 2027 maturity wall, ARCC 99.6¢ 2L anomaly). Rankings reflect combined BSL structural insight and issuer-level research completed this session.*

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
| 2 | ✅ Built | Cross-issuer mark-drift table | See cross_issuer_mark_drift.md; Q3→Q4 2025 data plus Cornerstone added |
| 3 | ✅ Confirmed | Kaseya 2025 refinancing | March 2025; $3.175B FL at S+325 + $925M SL at S+500; clean BSL exit; private credit repaid |
| 4 | ✅ Completed | OBDC non-accrual attribution | National Dentex ($83M loss), Feradyne, Walker Edison are the main names; no software credits in non-accrual pool |
| 5 | ✅ Completed | Medallia deep-dive | April 2026 forcing event confirmed (Bloomberg); BXSL 77.75¢; Moody's FSK downgrade; debt ~$3B, coverage 0.67x; see medallia_memo.md |
| 6 | ✅ Completed | ARCC capital-stack scan | 168 multi-layer issuers; ~$869M Q3→Q4 equity write-downs; Cornerstone identified as #2 surveillance name; see arcc_capital_stack_scan.md |
| 7 | ✅ Completed | BSL poaching memo | $34.1B 2025 takeouts; adverse selection dynamic; FSK Moody's downgrade causal mechanism; see bsl_poaching_memo.md |
| 8 | ✅ Completed | Mystery company identity research | High Street = HSIP (Abry Partners); Cardinal/Packers = Zywave (Clearlake+Aurora); Cobalt = BioIVT (Linden Capital, LEI confirmed); Balrog = BakeMark (Clearlake, OBDC DBA confirmed) |
| 9 | ✅ Completed | Cornerstone BSL capital structure | $2.1B TLB (CUSIP 86803YAB92) in CLOs at 78–83¢; CGBD/PNNT misidentification corrected; only ARCC+OBDC confirmed holders |
| 10 | ✅ Completed | Zywave surveillance memo | Caa2/CCC+; $450M BSL 1L Nov 2027; ARCC sole BDC holder; 99.6¢ 2L anomaly documented; see zywave_memo.md |
| 11 | ✅ Completed | Q1 2026 filing watch | Per-issuer thresholds for Medallia, Cornerstone, Zendesk, Zywave, FSK, ARCC; May 2026 calendar; see q1_2026_filing_watch.md |
| 12 | ✅ Completed | Screener validation | Screener correctly identifies BDC-level risk (FSK ORANGE, TPVG/PFLT/TCPC RED); does not capture issuer concentration — by design; see sofr_ai_attribution.md |
| 13 | ✅ Completed | BDC NAV stress table | Per-BDC stressed credit exposure as % of NAV; aggregate compression scenarios; see bdc_nav_stress_table.md |
| 14 | Active | Track Medallia restructuring event | Q1 2026 BDC filings (May 2026): non-accrual designation expected; debt-for-equity or Thoma Bravo equity injection |
| 15 | Active | Track Cornerstone OnDemand | Does BSL TLB drop below 78¢? Does Oct 2026 revolver get extended? OBDC 2L — below 90¢ in Q1? |
| 16 | Active | Track Zywave 2L compression | ARCC 2L should compress from 99.6¢ toward 85–90¢ as Nov 2027 maturity approaches without visible refi progress |
| 17 | ✅ Completed | Zendesk capital structure research | Confirmed NO BSL TLB — pure private credit club; $4.6B senior at SOFR+500; BCRED dominant (~$1B+, non-traded); BDC-visible = 9%; ~1x interest coverage; see `zendesk_memo.md` |
| 18 | Active | Track ARCC Zendesk preferred | 52% Q4 markdown is the key forward signal; Q1 2026 print confirms trajectory; preferred → zero would signal first-lien compression incoming |
| 19 | ✅ Completed | BakeMark surveillance memo | "Balrog" identity confirmed; 1L at 87¢, 2L at 88¢ (ARCC) vs. 81¢ (OBDC) — 700bps divergence; preferred written off; pure SOFR rate shock (no AI exposure); Clearlake concentration; see `bakemark_memo.md` |
| 20 | ✅ Completed | BDC bond positioning document | FSK fairly priced at T+280–320bps; BXSL modestly rich vs. Medallia tail risk; ARCC neutral; OBDC neutral; FSK/ARCC pair trade thesis for Q1 2026 earnings season; see `bdc_bond_positioning.md` |

---

## What this project is not claiming

This project is not predicting defaults. It is not claiming that any of these companies will fail to pay interest next quarter. It is building an early-warning framework based on the observation that:

- private-credit marks are disclosed quarterly with a lag
- when marks move, they tend to move in the same direction they've been moving
- a 21-point mark dispersion on a $762M public BDC position is not a rounding error
- a non-accrual on a $5.3B private-credit loan is not an administrative footnote

The project's value is in being right about the direction earlier than consensus — and this memo is the record of that thesis, the evidence behind it, and the specific data points that would confirm or refute it.
