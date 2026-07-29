# Feature Specification: XAU FT2 Trading-Date And Execution Integrity

**Feature Branch**: `codex/034d-xau-ft2-trading-date-integrity`
**Created**: 2026-07-29
**Status**: Active

## Goal

Correct the Vol2Vol source-session to Bangkok trading-date join, invalidate
stale XAU references, model executable bid/ask fills, and distinguish actual
manual fills from reference entries.

## Frozen Candidate Boundary

Feature 034D must not change `FT2_RAW_V1`:

- candidate ID or hash;
- T0 DTE target/tolerance;
- literal 2SD first-touch trigger;
- TP25/SL25;
- one-event counting;
- OI/rejection policy;
- promotion gates.

## Mapping Integrity

- Preserve source session date as source metadata.
- Derive Bangkok trading date from the actual activation timestamp.
- Select the latest fully closed XAUUSD bar at or before activation.
- Require source gap no greater than 120 seconds.
- Exclude stale plans from every denominator and statistic.
- Preserve old reports and identify superseded evidence.

## Execution Integrity

- Treat retained Dukascopy OHLC as bid-side unless metadata proves otherwise.
- Long limit entry requires synthetic ask to reach the boundary.
- Short limit entry requires bid to reach the boundary.
- Long exits use bid; short exits use synthetic ask.
- Report fills separately from reference touches at every frozen spread.
- Cost subtraction cannot create an executable fill.

## Manual Fill Integrity

- Reference alerts do not create assumed manual outcomes.
- Acknowledgement can record observation-only or an actual broker fill.
- Actual fill price and timestamp remain separate from reference entry.
- Manual outcomes are measured only from acknowledged actual fills.

## Guardrails

- No order submission, sizing, recovery, averaging, or martingale.
- `research_only=true`
- `signal_allowed=false`
- `order_submission_allowed=false`

## Acceptance

- Five known stale joins are reproduced and audited.
- July 5 is remapped using July 6 Bangkok bars when available.
- Corrected plans, events, outcomes, fill sensitivity, comparison, and integrity
  artifacts are generated without overwriting 034C.
- Focused tests and all 034-034C regressions pass.
