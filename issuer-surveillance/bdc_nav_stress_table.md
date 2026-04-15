# BDC NAV Stress Table — Surveillance Universe Impact

*Quantifies stressed credit exposure as a % of NAV for key BDCs, then estimates incremental NAV compression under two mark scenarios. NAV figures from EDGAR XBRL Q4 2025. Stressed credit positions from filed Q4 2025 schedules of investments.*

---

## BDC NAV baseline (Q4 2025, from EDGAR XBRL)

| BDC | NAV ($B) | Leverage (D/E) | Portfolio FV ($B) | Unrealized loss % | Key characteristic |
|-----|---------|---------------|-----------------|-----------------|-------------------|
| **ARCC** | **$14.32B** | 1.12x | $29.48B | 0.80% | Largest BDC; broadest software exposure; $869M equity write-downs Q4 |
| **OBDC** | **$7.40B** | 1.26x | $16.47B | 0.32% | Blue Owl; Cornerstone + Zendesk; unrealized losses modest relative to peers |
| **BXSL** | **$6.25B** | 1.29x | $14.21B | −1.26%* | Blackstone; Medallia largest position; portfolio slightly below cost |
| **FSK** | **$5.85B** | 1.31x | $13.01B | −5.33% | FS KKR; highest unrealized depreciation in peer group; PIK 12%; Moody's Ba1 |
| **GBDC** | n/a (FY June YE) | 1.25x | n/a | n/a | Golub; BioIVT equity + Zendesk + Kaseya |
| **CGBD** | n/a | 1.31x | n/a | n/a | Carlyle; Kaseya, Avalara, Coupa; NO Cornerstone OnDemand |

*BXSL's portfolio FV below cost reflects the Medallia unrealized loss as the dominant driver.

---

## Stressed credit exposure by BDC (Q4 2025 filed positions)

### ARCC — $14.32B NAV

| Credit | Position | Cost ($M) | Q4 FV ($M) | Current mark | Stress scenario FV | Incremental loss |
|--------|---------|----------|-----------|-------------|------------------|-----------------|
| Cornerstone 2L | Second-lien TL | 137.5 | 125.1 | 91.0¢ | 80.0¢ | −$15.2M |
| Cornerstone preferred | Series A preferred | 179.2 | 152.3 | 85.0¢ | 65.0¢ | −$35.8M |
| Cornerstone 1L + revolver | First-lien | 23.4 | 22.6 | 96.6¢ | 90.0¢ | −$1.5M |
| Zendesk 1L | First-lien TL | 36.2 | ~36.2 | ~100¢ | 90.0¢ | −$3.6M |
| Zendesk preferred | Series A preferred (Zoro) | ~20 | 13.4 | ~67¢ | 0 | −$13.4M |
| Zywave 2L | Second-lien TL | 71.6 | 71.3 | 99.6¢ | 85.0¢ | −$10.5M |
| Zywave 1L | First-lien TL | ~16.6 | ~16.6 | ~100¢ | 92.0¢ | −$1.3M |
| BakeMark 1L | First-lien | 16.1 | 14.0 | 87.0¢ | 75.0¢ | −$1.9M |
| BakeMark 2L | Second-lien | 29.5 | 26.0 | 88.1¢ | 75.0¢ | −$3.8M |
| **ARCC subtotal** | | **~530** | **~477** | | | **~−$87M** |
| **As % of ARCC NAV** | | | | | | **−0.6%** |

*Stress scenario: Cornerstone 2L → 80¢ (consistent with BSL 1L at 78–83¢); Cornerstone preferred → 65¢; Zendesk preferred → zero; Zywave 2L → 85¢ (Caa2 market level); BakeMark to 75¢ (1L approaching distressed).*

### BXSL — $6.25B NAV

| Credit | Position | Cost ($M) | Q4 FV ($M) | Current mark | Stress scenario FV | Incremental loss |
|--------|---------|----------|-----------|-------------|------------------|-----------------|
| Medallia | First-lien (2 tranches) | 393.4 | 307.9 | 78.3¢ | 60.0¢ | −$71.7M |
| Zendesk | First-lien | 1.82 | 1.84 | 101.0¢ | 90.0¢ | −$0.2M |
| **BXSL subtotal** | | **~395** | **~310** | | | **~−$72M** |
| **As % of BXSL NAV** | | | | | | **−1.2%** |

*Stress scenario: Medallia → 60¢ (post-restructuring recovery range for distressed debt-for-equity) — this is the key variable. If Medallia stays at 78¢, impact is zero incremental. If it goes non-accrual and marks at 50¢, impact is ~$112M / 1.8% of BXSL NAV.*

### FSK — $5.85B NAV

| Credit | Position | Cost ($M) | Q4 FV ($M) | Current mark | Stress scenario FV | Incremental loss |
|--------|---------|----------|-----------|-------------|------------------|-----------------|
| Medallia (cash tranches) | First-lien cash-pay | ~$267M | ~$267M | ~99.4¢ | 70.0¢ | −$79M |
| Medallia (PIK tranche) | First-lien PIK | ~$233M | ~$185M | ~79¢ | 55.0¢ | −$56M |
| Zendesk | First-lien (6 tranches) | 158.8 | 159.7 | 100.6¢ | 90.0¢ | −$15.9M |
| **FSK subtotal** | | **~659** | **~612** | | | **~−$151M** |
| **As % of FSK NAV** | | | | | | **−2.6%** |

*Stress scenario: Medallia cash tranche → 70¢ (non-accrual recognition compresses all tranches); PIK tranche → 55¢ (deeper loss on structurally subordinated PIK).*

**FSK is the most sensitive BDC**: 5.33% existing unrealized depreciation + $5.85B NAV + Moody's Ba1 downgrade means any additional mark compression on Medallia flows directly into NAV and leverage ratio headroom. An additional −$151M loss on stressed credits would be −2.6% of NAV — on top of the −5.33% already embedded.

### OBDC — $7.40B NAV

| Credit | Position | Cost ($M) | Q4 FV ($M) | Current mark | Stress scenario FV | Incremental loss |
|--------|---------|----------|-----------|-------------|------------------|-----------------|
| Cornerstone 2L | Second-lien TL | 153.9 | 144.4 | 93.8¢ | 80.0¢ | −$21.2M |
| Cornerstone preferred | Series A preferred | 75.2 | 66.9 | 89.0¢ | 65.0¢ | −$18.0M |
| Zendesk | First-lien | 177.9 | 180.3 | 101.3¢ | 90.0¢ | −$17.8M |
| BakeMark 2L | Second-lien | ~$30M | ~$24M | ~81¢ | 70.0¢ | −$3.3M |
| **OBDC subtotal** | | **~437** | **~416** | | | **~−$60M** |
| **As % of OBDC NAV** | | | | | | **−0.8%** |

---

## Aggregate stress summary

| BDC | NAV ($B) | Incremental stress loss | As % NAV | D/E (current) | D/E (post-stress) |
|-----|---------|----------------------|---------|-------------|-----------------|
| ARCC | $14.32B | ~$87M | **−0.6%** | 1.12x | ~1.13x |
| BXSL | $6.25B | ~$72M (Medallia to 60¢) | **−1.2%** | 1.29x | ~1.30x |
| FSK | $5.85B | ~$151M | **−2.6%** | 1.31x | ~1.35x |
| OBDC | $7.40B | ~$60M | **−0.8%** | 1.26x | ~1.27x |

**Key finding: At the BDC vehicle level, the stressed-scenario losses are manageable for ARCC, BXSL, and OBDC** — none breach the 2.0x 1940 Act leverage ceiling even under stress. FSK is the most constrained: −2.6% incremental NAV compression on top of existing −5.33% unrealized losses, combined with D/E already at 1.31x.

---

## What this means for BDC unsecured bonds

The 1940 Act requires BDCs to maintain asset coverage ≥ 150% of borrowings (i.e., D/E ≤ 2.0x asset-weighted) before issuing new debt. No BDC in this analysis is close to that ceiling under these stress scenarios. The **practical constraint is not regulatory**, it is **funding cost and market confidence**:

1. **FSK**: Post-Moody's Ba1 downgrade, FSK's unsecured bond spreads have likely widened 50–100bps. An additional −$151M NAV compression further increases perceived risk. FSK's dividend coverage at 0.86x NII is already the weakest in the peer group.

2. **BXSL**: Medallia at 77.75¢ is already embedded. The question is whether it goes to 60¢ (non-accrual after restructuring) or recovers via Thoma Bravo equity injection. At 60¢, the incremental loss is ~$72M / ~1.2% of NAV — modest but the *trajectory signal* (from 94¢ → 78¢ → 60¢) would accelerate spread widening on BXSL unsecured bonds.

3. **ARCC**: Diversification is the key buffer. The $87M incremental stress on a $14.32B NAV is ~0.6% — ARCC has the most room. But ARCC is also uniquely exposed to Clearlake concentration: BakeMark + Zywave + Cornerstone all simultaneously.

---

## Screener validation note

The BDC screener (red_flag_screener.py) correctly reflects BDC-level risk:
- **FSK: ORANGE (score 10)** — 12% PIK income, 0.86x NII coverage, NAV −3% YoY correctly flagged
- **ARCC: GREEN (score 1)** — correct; ARCC's aggregate metrics are healthy despite concentration in stressed names; the screener doesn't capture issuer-level concentration risk (by design — that's what the surveillance memos do)
- **BXSL: GREEN (score 2)** — correct; Medallia is a large position but BXSL's aggregate NII coverage (1.12x), leverage (1.29x), and NAV trend (+1%) remain healthy

The screener and the issuer surveillance memos serve complementary functions:
- **Screener**: BDC vehicle health — NII coverage, leverage, PIK share, NAV trajectory, non-accrual rate
- **Surveillance memos**: Issuer-level concentration risk — where specific marks are going and why

Neither replaces the other. A BDC can be GREEN on the screener while holding a time-bomb position (BXSL + Medallia). A BDC can be ORANGE on the screener for unrelated reasons (FSK's PIK share was elevated even before Medallia became acute).

---

*Sources: EDGAR XBRL Q4 2025 (universe_metrics.json); filed Q4 2025 BDC Schedules of Investments (borrower_db.json, portfolio_cache/). Stress scenarios are illustrative; actual outcomes depend on restructuring terms, sponsor behavior, and market conditions.*

*Last updated: April 2026*
