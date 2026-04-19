# Private Credit Workbench

A local-first research and monitoring platform for listed BDCs, interval funds, and issuer-level private-credit surveillance.

The repo is built around a 35-fund universe plus an issuer-surveillance workflow focused on borrower stress, mark drift, refinancing risk, and BDC bond transmission.

## What it does

| Capability | Module / Folder | Description |
|---|---|---|
| Risk screening | `red_flag_screener.py` | Composite fund risk scoring with tiering and explainable flags |
| Trade signals | `trade_signals.py` | Risk x valuation matrix using the same enriched data path as the screener |
| Live prices | `price_feed.py` | yfinance-backed P/NAV discounts for listed BDCs |
| Distribution model | `distribution_model.py` | Coverage outlook, rate sensitivity, and peer comparisons |
| Portfolio collector | `portfolio_collector.py` | SOI parsing, borrower DB construction, and live non-accrual rate extraction |
| MD&A extractor | `filing_text_extractor.py` | Item 7 / MD&A extraction and narrative non-accrual parsing |
| Liquidity model | `cclf_liquidity_model.py` | CCLF interval-fund liquidity and stress-testing engine |
| Dashboard | `dashboard.py` | Streamlit UI across scenarios, screening, EDGAR, borrowers, and trade signals |
| Issuer surveillance | `issuer-surveillance/` | Memos, positioning notes, watchlists, and lender / BDC exposure mapping |

## Quick start

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .[dev]

pytest -q
streamlit run dashboard.py
```

## Operator workflow

For the common refresh / scoring / testing loop, use the PowerShell workbench:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/workbench.ps1 -Task daily
powershell -ExecutionPolicy Bypass -File scripts/workbench.ps1 -Task full
powershell -ExecutionPolicy Bypass -File scripts/workbench.ps1 -Task test
```

Notes:
- The script respects an already-activated virtualenv before it falls back to `.\.venv\Scripts\python.exe`.
- `-DryRun` avoids file-writing refresh steps where possible; for example `-Task daily -DryRun` runs a score-only dry run and prints the screener without rewriting the CSV.
- `-Task full -DryRun` skips borrower DB rebuild because that command has no dry-run mode today.

## CI

GitHub Actions now runs a small smoke suite on pushes to `main`, pull requests, and manual dispatch:

- `python -m pytest -q`
- `python refresh.py --score-only --dry-run`
- `python red_flag_screener.py --live-na`

## Core CLI entry points

```bash
python red_flag_screener.py --live-na
python trade_signals.py --matrix
python distribution_model.py
python portfolio_collector.py --build-db
python filing_text_extractor.py --all
python refresh.py --score-only
python cclf_liquidity_model.py --scenarios scenarios/default_scenarios.json
```

## Universe

- Listed BDCs (27): `ARCC, BCSF, BXSL, CGBD, CSWC, FSK, GAIN, GBDC, GLAD, GSBD, HTGC, MAIN, MFIC, MSDL, NMFC, OBDC, OCCI, OCSL, OTF, PFLT, PNNT, PSEC, SCM, SLRC, TCPC, TPVG, TSLX`
- Interval / non-traded vehicles (8): `ASIF, BCRED, BREIT, CCLFX, GCRED, HLEND, PIMCO-FCI, SSLP`

Universe metadata lives in `data/bdc_universe.json`.

## High-value folders

- `data/processed/`: generated outputs, digests, and summaries
- `memo/`: fund-level investment memos, including the CCLF liquidity work
- `issuer-surveillance/`: borrower and sector surveillance artifacts
- `scenarios/`: liquidity-model scenario configs
- `tests/`: regression coverage

## Issuer surveillance starting points

If you are jumping into the borrower side first, start here:

1. `issuer-surveillance/private_credit_software_synthesis.md`
2. `issuer-surveillance/bdc_bond_positioning.md`
3. `issuer-surveillance/NEXT_ACTIONS.md`

## Data notes

- Listed BDC pricing is cached locally and refreshed from yfinance.
- Live non-accrual overrides come from the latest cached SOI files, with MD&A fallback for known parser edge cases.
- Trend enrichment comes from cached EDGAR XBRL history.
- Interval / non-traded vehicles rely more heavily on static disclosures than listed names.

## Current limitations

- Some non-accrual values still rely on MD&A narrative extraction where SOI formatting is non-standard.
- Interval / non-traded names have materially thinner disclosure than listed BDCs.
- Trend history depth varies by ticker and filing cadence.
- Generated cache files and borrower DB outputs should be treated as rebuildable artifacts, not hand-edited source data.
