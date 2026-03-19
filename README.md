# Private Credit Workbench

Focused working repo for two linked tracks:
1. **CCLF / Cliffwater liquidity analysis**
2. **issuer-level surveillance for BDC unsecured bond investing**

It is best treated as an analyst workbench, not a finished production system.

## What is here

This repo currently does five things:

1. **Structures key source disclosures** from CCLF shareholder reports.
2. **Runs a stylized 8-quarter liquidity model** with configurable tender, repayment, default, and unfunded-draw assumptions.
3. **Presents the output in memo and dashboard form** for fast iteration.
4. **Maintains an issuer-surveillance research set** for sponsor-backed / private-credit-financed issuers.
5. **Connects issuer work to BDC unsecured bond risk** through ranked watchlists, memo queues, and lender/BDC mapping.

Current model defaults are now anchored to the latest disclosed **September 30, 2025** facility / commitment snapshot unless a scenario overrides them.

## Repo layout

- `cclf_liquidity_model.py` - config-driven liquidity scenario model
- `dashboard.py` - Streamlit dashboard for interactive scenario analysis
- `scenarios/default_scenarios.json` - default scenario assumptions
- `baseline_projection.csv` - latest baseline model output
- `stressed_projection.csv` - latest stressed model output
- `scenario_summary.csv` - compact summary table across saved scenarios
- `effective_scenarios.json` - exact scenario payload used for the last model run
- `memo/cclf_liquidity_memo.md` - draft narrative memo / investment framing
- `issuer-surveillance/` - issuer project cockpit, watchlists, source logs, radar tables, matrix work, `NEXT_ACTIONS.md`, and live issuer memos
- `data/raw/` - original report PDFs and plaintext sidecars
- `data/processed/source_summary.md` - source-backed disclosure summary
- `data/processed/repurchase_history.csv` - structured filed repurchase-history table
- `data/processed/financing_snapshot.csv` - structured facility / unfunded-commitment snapshot table
- `data/processed/cliffwater_blocks.jsonl` - extracted disclosure blocks for downstream review
- `data/processed/cclf_senior_securities_section.txt` - extracted senior-securities text section
- `scripts/extract_cclf_pdf.py` - converts raw report PDFs into plaintext sidecar files
- `tools/extract_cliffwater.py` - extracts anchor-based disclosure blocks into JSONL
- `tests/` - regression / smoke tests for the scenario model

## Quick start

If you're working on the issuer-surveillance track rather than the liquidity model, start with:
- `issuer-surveillance/README.md`
- `issuer-surveillance/PROJECT_COCKPIT.md`
- `issuer-surveillance/issuer_risk_radar.csv`
- `issuer-surveillance/NEXT_ACTIONS.md`


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
python3 cclf_liquidity_model.py
```

This uses `scenarios/default_scenarios.json` and refreshes:
- `baseline_projection.csv`
- `stressed_projection.csv`
- `scenario_summary.csv`
- `effective_scenarios.json`

### Run with a custom config or alternate output folder

```bash
python3 cclf_liquidity_model.py --config scenarios/default_scenarios.json --output-dir outputs
```

### Quiet mode

```bash
python3 cclf_liquidity_model.py --quiet
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
- sensitivity heatmap for tender / default stress
- assumptions transparency panel

## Rebuild PDF-derived artifacts

### Plaintext sidecars

```bash
python3 scripts/extract_cclf_pdf.py
```

### Anchor-based disclosure extraction

```bash
python3 tools/extract_cliffwater.py
```

Default output:
- `data/processed/cliffwater_blocks.jsonl`

Example with a narrower search window:

```bash
python3 tools/extract_cliffwater.py --pattern 'CCLFX-Annual-Report.pdf' --window 1200
```

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Current analytical framing

A few source-backed points matter most right now:

- CCLF is an **interval fund**, so liquidity is periodic rather than daily.
- The fund must offer at least **5% quarterly repurchases**, with the board able to set offers between **5% and 25%**.
- The fund may repurchase an additional **2%** if an offer is oversubscribed; otherwise tenders are prorated.
- Facility capacity expanded materially in 2025, but **actual borrowings also rose sharply**.
- **Unfunded commitments are large**, which makes the interaction between tenders, leverage, and commitment funding the key stress question.

See `data/processed/source_summary.md` for the sourced disclosure summary, `data/processed/repurchase_history.csv` for the structured tender history, `data/processed/financing_snapshot.csv` for the facility snapshot table, and `memo/cclf_liquidity_memo.md` for the narrative view.

## Notes and caveats

- The liquidity model itself uses only the Python standard library.
- The extraction tools and dashboard require third-party packages listed in `requirements.txt`.
- `cliffwater_blocks.jsonl` is newline-delimited JSON for easy inspection or downstream loading.
- Historical tender-pressure commentary should distinguish between **filed repurchase percentages visible in source reports** and **Tucker-supplied datapoints about requested participation / fulfillment** that are not yet independently anchored inside the repo.

## Recommended next upgrades

- tighten the model with more explicit facility-tranche and maturity-ladder inputs
- add source-backed asset-side liquidity proxies such as repayments, realizations, or sales
- add CI to run tests automatically on push
- package a cleaner investor-facing exhibit pack from dashboard outputs
