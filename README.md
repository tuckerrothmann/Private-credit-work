# Private Credit Liquidity Analysis

A focused working repo for reviewing the Cliffwater Corporate Lending Fund (CCLF) liquidity profile, source disclosures, and simple downside scenarios.

## What is in the repo

- `cclf_liquidity_model.py` - 8-quarter scenario model for tender pressure, distributions, credit losses, unfunded draws, and borrowing headroom
- `baseline_projection.csv` - baseline model output
- `stressed_projection.csv` - stressed model output
- `scenario_summary.csv` - compact scenario-level summary table
- `scripts/extract_cclf_pdf.py` - converts the raw report PDFs into plaintext sidecar files
- `tools/extract_cliffwater.py` - extracts disclosure blocks around key liquidity / leverage anchors into JSONL
- `data/raw/` - original Cliffwater report PDFs and plaintext extracts
- `data/processed/` - extracted snippets and processed text artifacts

## Quick start

### 1) Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependency for the PDF tools

```bash
pip install -r requirements.txt
```

### 3) Run the liquidity model

```bash
python cclf_liquidity_model.py
```

This refreshes:
- `baseline_projection.csv`
- `stressed_projection.csv`
- `scenario_summary.csv`

### 4) Rebuild report text extracts

```bash
python scripts/extract_cclf_pdf.py
```

### 5) Extract disclosure blocks for review

```bash
python tools/extract_cliffwater.py
```

Default output:
- `data/processed/cliffwater_blocks.jsonl`

## Notes

- The liquidity model uses only the Python standard library.
- The PDF extraction tools require `pdfminer.six`.
- `cliffwater_blocks.jsonl` is newline-delimited JSON, which makes it easy to inspect or load into pandas later.

## Suggested next improvements

- parameterize scenario assumptions from a YAML/JSON config
- add a maturity ladder / financing stack input table
- create a small notebook or dashboard for scenario comparison
- parse specific facility and note disclosures into structured fields instead of text blocks
