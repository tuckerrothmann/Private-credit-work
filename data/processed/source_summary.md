# CCLF Source Summary

Working summary of key liquidity / financing disclosures pulled from the raw report text files.

## Fund structure and liquidity terms

- CCLF is a **closed-end interval fund**.
- The fund has a fundamental policy to make **quarterly repurchase offers of at least 5%** of outstanding shares.
- The board can set the quarterly repurchase offer amount between **5% and 25%** of outstanding shares.
- If tender requests exceed the offer amount, the fund may repurchase up to an additional **2%** of outstanding shares, but otherwise tenders are prorated.

Source excerpts:
- `data/raw/CCLFX-Annual-Report.txt` lines ~402829-402839
- `data/raw/CCLFX-Annual-Report.txt` lines ~404807-404813
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~440925-440935
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~443083-443089

## Historical repurchase percentages visible in the filed text

The filed repurchase-results tables have now been normalized into:
- `data/processed/repurchase_history.csv`

Structured source-backed observations currently captured:
- **2024-05-15** pricing date — **1.99%** executed, **$389.4mm** repurchased
- **2024-08-14** pricing date — **2.58%** executed, **$558.3mm** repurchased
- **2024-11-13** pricing date — **2.92%** executed, **$695.3mm** repurchased
- **2025-02-19** pricing date — **2.24%** executed, **$595.1mm** repurchased
- **2025-06-09** pricing date — **3.42%** executed, **$1.025bn** repurchased
- **2025-09-08** pricing date — **2.90%** executed, **$917.5mm** repurchased

Those figures suggest that *executed* repurchases have generally run below the standard 5% quarterly offer size, though executed percentages still do **not** answer the separate question of underlying tender demand.

Relevant source locations:
- `data/raw/CCLFX-Annual-Report.txt` lines ~404818-404890
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~443103-443150

## Tender-pressure context not yet independently anchored in repo

Tucker also reported that the most recent tender request was about **14%** of shares, with only about **5-7%** fulfilled. If accurate, that would imply latent investor liquidity demand materially above executed repurchases.

That is analytically important, but it should currently be treated as a **Tucker-provided datapoint**, not a sourced filing fact inside this repo, until the underlying notice, shareholder letter, or transfer-agent / fund disclosure is pulled in and cited directly.

A structured facility snapshot table now lives at:
- `data/processed/financing_snapshot.csv`

## Senior credit facility — March 31, 2025

The annual report describes a senior secured credit facility amended effective December 18, 2024 with:

- total committed size: **$5.45bn**
- term loans: **$1.19bn**
- revolving loan capacity: **$3.1575bn**
- delayed draw term loan capacity: **$1.1025bn**
- accordion / increase request capacity: up to **$6.5bn** total, subject to lender approval
- revolver maturity: **April 6, 2029**
- term loans / DDTL maturity: **April 8, 2030**

Balances outstanding as of March 31, 2025:
- term loan: **$1.19bn**
- revolving loan: **$0**

Other disclosed facility facts for FY ended March 31, 2025:
- average term loan balance: **$842.6mm**
- maximum term loan borrowings: **$1.19bn**
- average revolver balance: **$307.3mm**
- maximum revolver borrowings: **$1.075bn**
- term loan weighted average interest rate: **7.11%**
- revolver weighted average interest rate: **7.13%**
- term loan rate at period-end: **6.45%**
- facility interest expense: **$87.5mm**
- commitment fees: **$5.0mm**
- unused commitment fees: **$1.3mm**

Source:
- `data/raw/CCLFX-Annual-Report.txt` lines ~402842-402881

## Senior credit facility — September 30, 2025

The semi-annual report shows the facility expanded further, amended effective September 12, 2025:

- total committed size: **$6.475bn**
- term loans: **$1.365bn**
- revolving loan capacity: **$3.8325bn**
- delayed draw term loan capacity: **$1.2775bn**
- facility increase request capacity: up to **$9.0bn**, subject to lender approval
- revolver maturity: **April 23, 2030**
- part of term loan stack matures **April 23, 2031**; remaining term loans / DDTL mature **April 8, 2030**

Balances outstanding as of September 30, 2025:
- term loan: **$1.30bn**
- revolving loan: **$1.365bn**
- DDTL: **$547.5mm**
- total facility borrowings: **$3.2125bn**

Other disclosed facility facts for 6M ended September 30, 2025:
- average term loan balance: **$1.316bn**
- average revolver balance: **$779.1mm**
- average DDTL balance: **$276.7mm**
- weighted average rates: roughly **6.17%-6.23%** across tranches
- period-end rates: **6.10%** term / **6.04%** revolver / **6.19%** DDTL
- facility interest expense: **$79.3mm**
- commitment fees: **$3.4mm**
- unused commitment fees: **$1.23mm**

Source:
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~440942-440985

## Unfunded commitments

The raw disclosures show material unfunded commitments:

- as of March 31, 2025:
  - principal amount: **$4.689bn**
  - fair value: **$4.760bn**
- as of September 30, 2025:
  - principal amount: **$6.260bn**
  - fair value: **$6.251bn**

This is an important liquidity call on the portfolio because those commitments can become future funding needs even while the fund is managing repurchase offers and leverage.

Source:
- `data/raw/CCLFX-Annual-Report.txt` lines ~398520-398520
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~435765-435766

## Senior notes

The report text confirms a large multi-series secured note stack issued across 2022-2025, secured alongside the facility by a first-priority security interest on substantially all fund / guarantor assets.

Useful takeaways:
- the note stack is large and layered across many maturities
- the fund uses **interest-rate swaps** to align fixed-rate note liabilities with a predominantly floating-rate asset base
- the March 2025 annual report references additional note issuance priced in March 2025 and issued in July 2025

Source:
- `data/raw/CCLFX-Annual-Report.txt` lines ~402903-403040
- `data/raw/CCLFX-Semi-Annual-Report.txt` lines ~441050-441120

## Analytical implications

The most important high-level points from the source docs are:

1. The fund offers only **limited interval-fund liquidity**, not daily liquidity.
2. Even so, the repurchase program creates a recurring cash-use obligation.
3. Executed repurchases shown in the filings have been below the standard 5% offer amount, but that alone does **not** resolve the question of underlying tender demand.
4. Facility capacity expanded materially between March and September 2025, but **actual utilization also rose sharply**.
5. Unfunded commitments are large enough to matter to any stress analysis.
6. If Tucker's latest tender-demand datapoint is confirmed, then **latent demand could be materially higher than executed repurchases imply**, which would strengthen the case for focusing on tender pressure as a primary stress variable.
7. The financing stack is meaningful and senior to common shareholders, which makes liquidity and asset-coverage discipline central to the thesis.
