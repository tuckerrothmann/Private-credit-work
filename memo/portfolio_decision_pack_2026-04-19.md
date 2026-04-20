# Portfolio Decision Pack

As of 2026-04-19.

Built from the current local screening stack, refresh digest, trade-signal matrix, borrower-family watchlists, and issuer-surveillance memos.

## Bottom line

The repo is now strong enough to support cleaner position-level decisions. The highest-conviction portfolio posture is:

- stay defensive on the structurally weakest listed BDCs: `TPVG`, `PFLT`, `TCPC`, `PNNT`
- keep a tighter leash on the orange bucket: `FSK`, `SCM`, `BCSF`, `GSBD`
- treat the deep-discount green/yellow names as selective valuation opportunities, not automatic buys: `OTF`, `MSDL`, `CGBD`, `MFIC`
- keep quality anchors explicit for relative sizing: `ARCC`, `BXSL`, `MAIN`, `TSLX`, `HTGC`
- push borrower surveillance harder on the cross-lender software names where transmission risk is real: `Pluralsight`, `Kaseya`, `Zendesk`, `iCIMS`, `Flexera`

## Position Calls

| Ticker | Current read | PM action | Why now | What changes the view |
|---|---|---|---|---|
| `TPVG` | Highest-risk name in the pack | Trim / avoid | Score `16`, non-accruals `7.6%` FV, NAV `-22.0%` YoY, P/NAV `0.68x`; this looks like real credit stress, not just a valuation air pocket | Non-accruals stabilize materially and NAV erosion stops for two reporting periods |
| `PFLT` | Weakest risk/reward among the "income" names | Trim / avoid | Score `15`, NII coverage `0.59x`, D/E `1.61x`, asset coverage `162%`; coverage collapse plus leverage drift is the core problem | Coverage returns above `0.90x` without levering harder |
| `TCPC` | Deep value trap risk remains high | Avoid | Score `14`, D/E `1.73x`, asset coverage `158%`, NA `4.0%`; valuation is cheap, but leverage and credit quality are doing the real talking | Leverage and non-accruals both improve at the same time |
| `PNNT` | Sister-fund version of the same problem | Avoid / small only if forced | Score `13`, NII coverage `0.67x`, D/E `1.83x`, asset coverage `155%`; still too levered for the operating weakness | Coverage and leverage inflect in the right direction together |
| `FSK` | Cheap but not clean | Underweight / monitor | Score `10`, P/NAV `0.88x`, NA `4.2%`, NII coverage `0.86x`; discount is understandable | NII coverage recovers and non-accruals stop rising |
| `SCM` | Small-cap balance-sheet strain story | Underweight / monitor | Score `10`, NII coverage `0.81x`, D/E `1.81x`, asset coverage `155%`; too little margin for error | Coverage improves or leverage backs down materially |
| `BCSF` | Coverage-driven orange name, not a washout | Hold with caution | Score `8` in current matrix, NII coverage `0.54x`; less obvious credit blow-up than the red bucket, but coverage deterioration is too sharp to ignore | Coverage recovers above `0.85x` or payout resets cleanly |
| `GSBD` | Manageable but deteriorating | Hold with caution | Score `8`, NII coverage `0.83x`, NAV `-5.7%` YoY; not a crisis, but not good enough for a "safe discount" case | Better earnings coverage and a steadier NAV trend |
| `OTF` | Best cheap name to re-underwrite positively | Selective add | Score `4`, P/NAV roughly `0.70x` in the matrix, NA `0.6%`, D/E `0.78x`; cheapness is much easier to tolerate with low leverage and cleaner credit stats | If coverage keeps slipping below `1.0x` without offsetting NAV resilience |
| `MSDL` | Cheap, but not yet fully proven after the dividend cut | Hold / starter only | Score `3`, matrix says strong buy at discount, but NII coverage is only `0.70x`; valuation is interesting, but post-cut stabilization matters | Two periods of cleaner coverage and dividend reset follow-through |
| `CGBD` | Acceptable discount hold, not a conviction add | Hold | Score `4`, P/NAV `0.92x`, NII coverage `0.99x`; decent but not compelling enough to crowd out better names | More earnings cushion or a wider discount with unchanged credit |
| `MFIC` | Balance-sheet-heavy discount name | Hold / monitor | Score `5`, D/E `1.53x`, asset coverage `165%`, NAV `-3.3%` YoY; not broken, but still balance-sheet constrained | Clearer proof that leverage and NAV can stabilize simultaneously |
| `ARCC` | Benchmark-quality core holding | Overweight core | Score `1`, P/NAV `1.05x`, NA `0.6%`, coverage `1.15x`; still one of the cleanest large-scale compounding platforms | Only if credit metrics weaken enough to justify paying less than benchmark quality |
| `BXSL` | Large-scale quality anchor | Overweight core | Score `2`, P/NAV `1.04x`, NA `0.9%`, coverage `1.12x`; still a high-quality upper-middle-market expression | If non-accruals or leverage start to drift without earnings offset |
| `MAIN` | Best-in-class franchise, expensive for a reason | Overweight but valuation-aware | Score `0`, coverage `1.44x`, NAV `+6.0%` YoY, P/NAV `1.70x`; quality is excellent, but the premium limits new-money aggressiveness | Add more aggressively only on a meaningful premium compression |
| `TSLX` | Cleanest public-credit quality name in the group | Overweight core | Score `1`, coverage `1.28x`, NA `0.1%`; this remains one of the easiest "sleep at night" names in the universe | Only if coverage or credit quality start to crack visibly |
| `HTGC` | Good business, different risk profile | Overweight selectively | Score `2`, P/NAV `1.52x`, NA `0.5%`, but PIK `12%`; strong franchise, but venture/life-science exposure is not interchangeable with first-lien lenders | If venture marks or PIK mix worsen while premium stays high |

## Practical Positioning

If we had to turn this into portfolio buckets right now:

- `Overweight core`: `ARCC`, `BXSL`, `TSLX`, `MAIN`
- `Overweight selectively`: `HTGC`, `OTF`
- `Hold / neutral`: `MSDL`, `CGBD`, `MFIC`
- `Underweight / caution`: `FSK`, `SCM`, `BCSF`, `GSBD`
- `Avoid / trim first`: `TPVG`, `PFLT`, `TCPC`, `PNNT`

## Borrower Transmission Watchlist

These are the highest-value cross-lender borrower families to keep close because they touch multiple relevant BDCs at once.

| Family | Why it matters | Current read | Immediate use |
|---|---|---|---|
| `Pluralsight` | `7` funds, `6` managers, `RED`, surveillance score `27`, non-accrual exposure already spread across multiple funds | Best live transmission case in the borrower DB | Use as the lead "stress can travel" case in fund reviews, especially for `GSBD`, `OBDC`, `OCSL`, `OTF`, `TCPC` |
| `Kaseya` | `9` funds, `8` managers, surveillance score `15` | Not yet a clean stress case, but massive overlap makes it systemically important inside the tracked universe | Keep as a top refinance-and-mark-risk watch item |
| `Zendesk` | `7` funds, `6` managers, surveillance score `12` | Broad ownership and meaningful FV footprint | Tie into the existing `zendesk_memo.md` and use for cross-fund underwriting comparisons |
| `iCIMS` | `7` funds, `7` managers, surveillance score `13` | Cleaner than the red bucket, but the overlap is too wide to ignore | Good candidate for a "quiet transmission" case study |
| `Flexera` | `7` funds, `6` managers, surveillance score `11` | Another broad software overlap name with meaningful total FV | Use to compare underwriting quality across "good" managers, not just distressed names |

## What To Do In The Next 30 Days

### Portfolio-manager track

1. Re-underwrite `PFLT`, `TPVG`, `TCPC`, and `PNNT` one by one with explicit "sell / trim / hold" conclusions and falsification triggers.
2. Do a valuation-quality split on `OTF`, `MSDL`, `CGBD`, and `MFIC` so we separate true opportunity from cheap leverage.
3. Build one cross-fund transmission note around `Pluralsight` and one around `Kaseya`.
4. Keep `ARCC`, `BXSL`, `MAIN`, `TSLX`, and `HTGC` as the default comparison set for relative sizing decisions.

### Dev / platform track

1. Add a parser-health artifact to the refresh flow so every run tells us which filings parsed cleanly, which used fallback, and which still need manual review.
2. Add a second SOI fallback path via `FilingSummary.xml` / report pages for filings where full-document HTML still underperforms.
3. Add a generated "decision pack inputs" export so the screener, trade matrix, refresh digest, and borrower watchlist can feed a memo like this with less manual stitching.
4. Keep extracting dashboard shaping logic into helpers, especially around the watchlist and decision-summary views.

## Current Working Thesis

The repo has moved beyond generic screening. The edge now is in combining:

- fund-level balance-sheet and coverage stress
- valuation discipline
- borrower overlap and family rollups
- issuer-specific mark and refinance surveillance

That combination should let us be more aggressive where discounts are clean and much less forgiving where "cheap" is just delayed recognition of weaker credit.
