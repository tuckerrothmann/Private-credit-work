# Private Credit Workbench

A local-first analytical platform for monitoring Business Development Companies (BDCs) and private credit interval funds. Built for an investor who needs to track credit quality, distribution sustainability, and valuation across a 27-fund universe — without paying for Bloomberg or FactSet.

---

## What it does

| Capability | Module | Description |
|---|---|---|
| **Risk screening** | `red_flag_screener.py` | 10-dimension composite risk score (0–18) per fund; RED / ORANGE / YELLOW / GREEN tiers |
| **Trade signals** | `trade_signals.py` | 4×4 signal matrix (risk × valuation) → STRONG_BUY / BUY / HOLD / MONITOR / CAUTION / REDUCE / AVOID |
| **Live prices** | `price_feed.py` | yfinance-backed P/NAV discount tracker; 4-hour cache |
| **Distribution model** | `distribution_model.py` | 8-quarter NII coverage projection, SOFR rate sensitivity, peer percentile rankings |
| **Portfolio collector** | `portfolio_collector.py` | Parses EDGAR 10-K/10-Q SOI tables; extracts non-accrual, PIK, and fair-value data for each fund; builds cross-fund borrower database |
| **MD&A extractor** | `filing_text_extractor.py` | Scrapes Item 7 prose; parses NA count, NA %FV, named companies |
| **EDGAR history** | `portfolio_collector.py --build-db` | 8-quarter rolling XBRL trend series (NII coverage, NAV, leverage) stored as Parquet per ticker |
| **Dashboard** | `dashboard.py` | 8-tab Streamlit app covering all of the above |

---

## Quick start

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows
pip install -r requirements.txt

streamlit run dashboard.py        # launch the dashboard
```

---

## Dashboard tabs

| # | Tab | Key content |
|---|---|---|
| 1 | **Fund Scenario** | Single-fund 8-quarter NII/distribution scenario builder with preset stress scenarios |
| 2 | **Market Overview** | Cross-fund comparison: NII coverage, PIK %, NAV trajectory, leverage |
| 3 | **Red Flag Screener** | Scored risk table, flag frequency heatmap, asset coverage, live NA rates |
| 4 | **Historical & Mgmt** | 8-quarter trend charts per ticker (NII coverage, NAV change, leverage); management profile cards |
| 5 | **EDGAR Filings** | Live filing lookup, XBRL metric extraction, filing index browser |
| 6 | **Portfolio & Borrowers** | SOI-derived portfolio stats, cross-fund borrower exposure, maturity wall |
| 7 | **Macro & Scenarios** | Live P/NAV waterfall, 8Q sustainability projection with SOFR slider, rate sensitivity, peer radar |
| 8 | **Trade Signals** | Risk × valuation scatter, signal summary counts, per-fund rationale |

---

## CLI tools

### Red flag screener

```bash
python red_flag_screener.py                     # full universe, all tiers
python red_flag_screener.py --tier RED ORANGE   # elevated risk only
python red_flag_screener.py --live-na           # enrich with live SOI non-accrual rates
python red_flag_screener.py --csv results.csv
```

**Risk tiers:** GREEN (0–4) · YELLOW (5–7) · ORANGE (8–11) · RED (12+)

### Trade signals

```bash
python trade_signals.py              # signal table (all 27 funds)
python trade_signals.py --matrix     # pivot grid showing tickers in each quadrant
python trade_signals.py --csv out.csv
```

### Live price feed

```bash
python price_feed.py                          # refresh all listed BDCs
python price_feed.py --refresh                # force cache bypass
python price_feed.py --tickers ARCC MAIN HTGC
```

### Distribution sustainability model

```bash
python distribution_model.py                  # 8Q outlook for full universe
python distribution_model.py --ticker PFLT    # single fund
python distribution_model.py --sofr-shock 100 # +100 bps scenario
```

### Portfolio collector

```bash
python portfolio_collector.py --ticker FSK           # parse two most-recent SOI filings
python portfolio_collector.py --tickers ARCC MAIN    # multiple tickers
python portfolio_collector.py --all                  # full universe (slow)
python portfolio_collector.py --build-db             # rebuild cross-fund borrower DB
python portfolio_collector.py --borrower "Thrasio"   # look up a borrower across all funds
```

### MD&A text extractor

```bash
python filing_text_extractor.py TPVG         # extract NA commentary from most-recent 10-K
python filing_text_extractor.py --all        # run for full universe
python filing_text_extractor.py PFLT --raw   # dump full Item 7 text
```

---

## Scoring dimensions

The red flag screener scores 10 dimensions; each adds 0–3 points:

| Dimension | Key thresholds |
|---|---|
| **NII coverage** | <0.70x (3 pts), <0.85x (2 pts), <1.00x (1 pt) |
| **NAV erosion** | >7% YoY (3 pts), >5% (2 pts), >3% (1 pt) |
| **Non-accruals** | >12% FV (3 pts), >6% (2 pts), >3% (1 pt) |
| **PIK creep** | >25% of income (2 pts), >15% (1 pt) |
| **Leverage** | D/E >1.50x (2 pts), >1.20x (1 pt) |
| **Leverage headroom** | Asset coverage <1.75x (2 pts), <2.00x (1 pt) |
| **Distribution** | Cut history (1 pt), uncovered distribution (1 pt) |
| **P/NAV discount** | >30% (2 pts), >15% (1 pt) |
| **Coverage trend** | Collapse (2 pts), deteriorating (1 pt) |
| **Fund-specific** | Interval fund flows, related-party concerns, etc. |

---

## Trade signal matrix

```
               Deep Disc    Discount    Fair Value    Premium
               (<0.80x)    (0.80-0.95x) (0.95-1.05x)  (>1.05x)
Low  (0-4)   STRONG BUY     BUY          HOLD          HOLD
Mod  (5-7)      BUY        MONITOR      MONITOR        REDUCE
Elev (8-11)   CAUTION      CAUTION       AVOID         AVOID
High (12+)     AVOID        AVOID        AVOID         AVOID
```

---

## Universe (27 funds)

**Listed BDCs (22):** ARCC, BCSF, BXSL, CGBD, CSWC, FSK, GAIN, GBDC, GLAD, GSBD, HTGC, MAIN, OBDC, OCSL, OTF, PFLT, PNNT, PSEC, SCM, SLRC, TCPC, TPVG, TSLX

**Interval / non-traded (5):** BCRED, BREIT, CCLFX, PIMCO-FCI (and TSLX as listed BDC)

All funds have static metrics in `data/bdc_universe.json`. Listed BDCs additionally have:
- Live market prices (yfinance, 4-hour TTL cache)
- 2-quarter SOI portfolio snapshots in `data/portfolio_cache/`
- XBRL 8-quarter trend history in `data/edgar_cache/history/`

---

## Data sources

| Source | What it provides |
|---|---|
| EDGAR XBRL API | NAV, leverage, NII, coverage ratios — 8-quarter history |
| EDGAR filing HTML | SOI tables (non-accrual, PIK, fair value per position) |
| EDGAR filing HTML | Item 7 MD&A prose (non-accrual % narrative) |
| yfinance | Daily close prices for listed BDCs |
| `data/bdc_universe.json` | Static fund metadata; manually updated from filings |

---

## Repo layout

```
├── dashboard.py               Streamlit app (8 tabs)
├── red_flag_screener.py       Risk scoring engine + CLI
├── trade_signals.py           Signal matrix + CLI
├── price_feed.py              Live P/NAV pricing
├── distribution_model.py      NII sustainability + rate sensitivity
├── portfolio_collector.py     SOI parser + borrower DB builder
├── filing_text_extractor.py   MD&A Item 7 text extractor
├── requirements.txt
│
├── data/
│   ├── bdc_universe.json              27-fund static metrics
│   ├── borrower_db.json               Cross-fund borrower exposure DB
│   ├── price_cache.json               Live price cache (gitignored)
│   ├── bdc_management_profiles.json   Manager bios and track records
│   ├── edgar_cache/
│   │   ├── history/                   Per-ticker 8Q Parquet trend files
│   │   ├── facts/                     EDGAR XBRL facts (per CIK)
│   │   └── submissions/               EDGAR submissions (per CIK)
│   ├── portfolio_cache/               Per-fund SOI JSON snapshots
│   ├── text_cache/                    MD&A extraction results (gitignored)
│   ├── raw/                           Source PDFs
│   └── processed/                     Model outputs, CSVs, memos
│
├── scenarios/
│   └── default_scenarios.json         CCLF liquidity scenario presets
├── memo/
│   └── cclf_liquidity_memo.md
└── issuer-surveillance/               Sponsor-backed issuer tracking
```

---

## Key known limitations

- Non-accrual rates for FSK, SCM, TCPC, PFLT use MD&A text extraction (SOI footnote format is non-standard); rates are directionally correct but may lag a quarter.
- OCSL fiscal year ends September 30; latest data is Q4 FY2025 (Sep 2025).
- Interval fund scores (CCLFX, BCRED, BREIT, PIMCO-FCI) rely entirely on static metrics; no live pricing.
- NII coverage trend model uses 8-quarter XBRL history; funds added recently (BCSF, GSBD, OCSL, OTF, TSLX) have fewer history points.
- Price/NAV discounts reflect most recent yfinance close; during market hours intraday moves are not captured until next cache refresh.
