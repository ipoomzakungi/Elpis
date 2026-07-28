# XAU Vol2Vol First-Touch Study

Feature 034 is an isolated, research-only replication of a user-supplied
summary of an external 500-session Vol2Vol study.

## Evidence Boundary

The original PDF was not present in the workspace during implementation. The
external counts, DTE statement, and reversal definition are therefore recorded
as user-supplied priors. They are not presented as independently verified local
evidence.

The external study's eventual $25 reversal label is evaluated separately from
strict TP25-before-SL25 first passage. An eventual reversal after more than 25
adverse points may succeed under the published label and fail under the strict
label.

## Time Anchors

- T0 selects raw source DTE nearest 0.80.
- T1 selects the snapshot nearest the prior applicable COMEX Gold settlement
  at 13:30 America/New_York, with IANA daylight-saving conversion.
- T2 selects the latest exact-session snapshot at or before 07:00 Bangkok.

CME's Gold Futures Daily Settlement Procedure defines the active-month
settlement period as 13:29-13:30 ET:

`https://www.cmegroup.com/content/dam/cmegroup/market-regulation/rule-filings/2023/8/23-170_APPAB.pdf`

CME Gold options are options on Gold futures:

`https://www.cmegroup.com/content/dam/cmegroup/rulebook/COMEX/1a/115.pdf`

## Mapping Boundary

Distance reanchoring transfers futures SD distances to retained XAUUSD bars. It
is explicitly not called an exact-contract basis.

Same-time reference basis requires a closed XAUUSD bar no more than 300 seconds
before the selected snapshot. Exact GC contract basis remains unavailable
without matching contract prices.

## Shadow Boundary

The shadow state machine produces hypothetical point levels and journal state
only. It has no broker adapter, position sizing, averaging, recovery,
martingale, paper-order, or live-order interface.
