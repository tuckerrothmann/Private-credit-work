# Next Steps

Latest decision artifact: `memo/portfolio_decision_pack_2026-04-19.md`
Latest operating artifacts: `data/processed/monthly_watchlist.csv`, `data/processed/parser_health.csv`

## Portfolio manager priorities

1. Re-underwrite the highest-risk listed names after the merged parser and scoring changes: `PFLT`, `TPVG`, `TCPC`, `PNNT`, `FSK`, `SCM`, `BCSF`, `GSBD`.
2. Review the "cheap or trap" bucket with a fresh valuation lens: `OTF`, `MSDL`, `CGBD`, `MFIC`.
3. Keep the quality anchors explicit for relative sizing: `ARCC`, `BXSL`, `MAIN`, `TSLX`, `HTGC`.
4. Advance the issuer-transmission work on the highest-value overlap names: `Kaseya`, `Zendesk`, `Pluralsight`, `Flexera`, `iCIMS`.
5. Turn the CCLF work into a source-backed liquidity packet: tender demand, facility headroom, commitment funding, repayment cadence, and stress timing.

## Senior dev priorities

1. Keep using the canonical trade-signal loader so screener, dashboard, and CLI cannot drift again.
2. Add more small regression tests around cache selection, parser edge cases, and generated-output consistency.
3. Decide whether generated files like `data/borrower_db.json` should stay tracked or be rebuilt on demand.
4. Extend `scripts/workbench.ps1` as the standard local operator workflow for `refresh.py`, screener outputs, and borrower DB rebuilds.
5. Consider extracting more dashboard business logic into pure helpers so it is easier to test without importing Streamlit.
6. Expand the new GitHub Actions smoke suite when additional stable checks emerge (`trade_signals.py --matrix`, targeted parser fixtures, generated-output diffs).
