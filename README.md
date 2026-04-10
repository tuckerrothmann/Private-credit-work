# Private Credit Liquidity Analysis

A focused working repo for reviewing the Cliffwater Corporate Lending Fund (CCLF) liquidity profile, source disclosures, and downside scenarios.

## Repo layout

- `cclf_liquidity_model.py` - config-driven 8-quarter liquidity scenario model
- `scenarios/default_scenarios.json` - default scenario assumptions
- `baseline_projection.csv` - baseline model output
- `stressed_projection.csv` - stressed model output
- `scenario_summary.csv` - compact scenario summary table
- `effective_scenarios.json` - exact scenario payload used for the last model run
- `dashboard.py` - Streamlit dashboard for interactive scenario analysis
- `scripts/extract_cclf_pdf.py` - converts raw report PDFs into plaintext sidecar files
- `tools/extract_cliffwater.py` - extracts anchor-based disclosure blocks into JSONL
- `data/raw/` - original Cliffwater report PDFs and plaintext extracts
- `data/processed/` - extracted snippets and processed text artifacts
- `tests/` - basic regression / smoke tests for the scenario model

## Quick start

### Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```bash
pip install -r requirements.txt
```

## Run the liquidity model

```bash
python cclf_liquidity_model.py
```

This uses `scenarios/default_scenarios.json` and refreshes:
- `baseline_projection.csv`
- `stressed_projection.csv`
- `scenario_summary.csv`
- `effective_scenarios.json`

### Run with a custom config or alternate output folder

```bash
python cclf_liquidity_model.py --config scenarios/default_scenarios.json --output-dir outputs
```

### Quiet mode

```bash
python cclf_liquidity_model.py --quiet
```

## Run the dashboard

```bash
streamlit run dashboard.py
```

The dashboard includes:
- scenario presets
- user-adjustable assumptions
- KPI cards
- liquidity / leverage charts
- cash-flow driver charts
- downloadable scenario CSVs
- plain-English scenario interpretation
- sensitivity heatmap for tender/default stress
- assumptions transparency panel

## Rebuild PDF-derived artifacts

### Plaintext sidecars

```bash
python scripts/extract_cclf_pdf.py
```

### Anchor-based disclosure extraction

```bash
python tools/extract_cliffwater.py
```

Default output:
- `data/processed/cliffwater_blocks.jsonl`

Example with a narrower search window:

```bash
python tools/extract_cliffwater.py --pattern 'CCLFX-Annual-Report.pdf' --window 1200
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- The liquidity model itself uses only the Python standard library.
- The PDF extraction tools require `pdfminer.six`.
- `cliffwater_blocks.jsonl` is newline-delimited JSON for easy inspection or downstream loading.

## BDC Universe & Red Flag Screener

### Run the screener

```bash
# Screen all funds, show RED and ORANGE tier only
python red_flag_screener.py --tier RED ORANGE

# Output full results to CSV
python red_flag_screener.py --csv data/processed/screener_results.csv

# Set minimum score threshold
python red_flag_screener.py --min-score 4
```

**Risk tiers:** GREEN (0–3) · YELLOW (4–6) · ORANGE (7–10) · RED (11+)

### Collect live EDGAR data

```bash
# Look up a CIK
python edgar_collector.py --lookup ARCC

# Show recent 10-K/10-Q filings
python edgar_collector.py --filings PSEC

# Refresh full universe XBRL metrics
python edgar_collector.py

# Refresh specific tickers only
python edgar_collector.py --tickers TPVG FSK PNNT
```

EDGAR data is cached in `data/edgar_cache/` for 24 hours (pass `--force-refresh` to bypass).

### Universe file

`data/bdc_universe.json` contains ~21 funds covering:
- 17 publicly-traded BDCs (filed 10-K/10-Q with EDGAR XBRL)
- 2 large private-credit interval funds (CCLFX, BCRED)
- 1 non-traded REIT reference case (BREIT)

Metrics include NAV, leverage, NII coverage, PIK income %, non-accrual rates,
price/NAV, and quarterly flow data. Balance-sheet fields are refreshed from EDGAR XBRL
automatically; NII coverage, PIK %, and non-accrual rates require manual updates from filings.

## Dashboard tabs

| Tab | Content |
|---|---|
| Fund Scenario | Single-fund 8-quarter liquidity projection with scenario presets |
| Market Overview | Cross-fund comparison charts (NII coverage, PIK %, NAV trajectory) |
| Red Flag Screener | Scored risk table and flag frequency analysis |
| EDGAR Filings | Live filing lookup and XBRL metric extraction per ticker |

## Recommended next upgrades

- automated PDF parsing of 10-Q non-accrual disclosures to keep non-accrual rates current
- full EDGAR XBRL trend analysis (8-quarter rolling NII coverage series)
- add CI to run tests automatically on push
- alert/notification system when a fund crosses a risk-tier threshold
