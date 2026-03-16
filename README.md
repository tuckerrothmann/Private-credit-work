# Private Credit Liquidity Analysis

This repo houses tooling and workpapers for a forensic review of the Cliffwater Corporate Lending Fund (CCLF) liquidity profile. Current contents:

- `cclf_liquidity_model.py` – scenario engine that links tender obligations, credit losses, unfunded draws, and facility headroom over an 8-quarter horizon. Runs baseline + stressed cases out of the box.
- `baseline_projection.csv`, `stressed_projection.csv`, `scenario_summary.csv` – default outputs from the model.

Coming soon: a structured borrowing-source digest (credit facility + note tranches), asset-side maturity ladder summaries, and any additional sensitivity sweeps.

## Running the model

```bash
python3 cclf_liquidity_model.py
```

The script uses Python stdlib only; edit `run_default_scenarios()` or instantiate `ScenarioConfig` objects for custom cases.
