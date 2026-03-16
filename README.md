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
- `data/processed/` - extracted snippets, source summaries, and processed text artifacts
- `memo/` - draft investment memos and narrative outputs
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

## Recommended next upgrades

- move from heuristic text extraction to structured disclosure parsing
- add richer financing-stack and maturity-ladder inputs
- build scenario comparison charts or a lightweight dashboard
- add CI to run tests automatically on push
