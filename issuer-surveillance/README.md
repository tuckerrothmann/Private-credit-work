# Issuer Surveillance

This folder extends the Cliffwater / private-credit workbench into **issuer-level surveillance** for a BDC unsecured bond investor lens.

## Objective
Identify underlying issuers that could create trouble for BDC / private-credit lenders **before** the deterioration is fully reflected in marks, non-accruals, or market perception.

## Core question
For each issuer memo:
- why was this company financeable?
- what could go wrong from here?
- why might lender pain be **under-reflected in current marks**?
- how could that pain transmit into BDC unsecured bond risk?

## Current contents
- `issuer_risk_radar.csv` — ranked first-pass issuer danger list
- `expanded_watchlist.csv` — broader 25-40 name cross-sector screen
- `issuer_lender_bdc_matrix.csv` — first-pass issuer / lender / BDC matrix
- `memo_queue.md` — recommended memo order
- `medallia_memo.md` — first live stress memo
- `finastra_memo.md`
- `kaseya_memo.md`
- `realpage_memo.md`
- `zendesk_memo.md`
- `coupa_memo.md`
- `anaplan_memo.md`
- `avalara_memo.md`
- `pluralsight_memo.md`

## Interpretation
These are **investor working memos**, not rating-agency writeups. The point is to surface:
- hidden mark risk
- recovery fragility
- lender / BDC transmission channels
- what to monitor next

## Best next build-outs
1. add a lender-exposure matrix across ARCC / BXSL / BCRED / HTGC / OBDC / OTF / GSBD / GBDC
2. attach source links and dated updates to each issuer memo
3. track quarter-over-quarter mark / pricing changes where public evidence appears
