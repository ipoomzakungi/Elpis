# Feature Specification: XAU 2SD First-Touch Candidate Freeze

**Feature Branch**: `codex/034c-xau-ft2-raw-candidate-freeze`
**Created**: 2026-07-28
**Status**: Active

## Goal

Audit strict T0/DTE-0.80 coverage, freeze literal 2SD raw first touch as one
provisional research candidate, and accumulate an immutable forward sample.

## Primary Candidate

`FT2_RAW_V1` uses fixed T0 levels, source DTE 0.75-0.85,
distance-reanchored XAUUSD mapping, one aggregated literal-2SD first touch,
touch-reference entry, and TP25/SL25.

OI, IV, volume, and rejection are descriptive context. They do not gate the
primary alert.

## Separate Challengers

- `FT2_SMALL_V1`: TP12.5/SL12.5, shadow only.
- `FT2_REJECTION_V1`: OI/rejection next-bar study, descriptive only.
- 1SD, 1.5SD, and 3SD remain controls owned by Feature 034B.

## Guardrails

- No order submission, position sizing, averaging, recovery, or martingale.
- No parameter optimization or strategy-family expansion.
- One first 2SD touch per session and one active provisional candidate.
- Frozen candidate plans cannot be recalculated or overwritten.
- Corrections append superseding records.
- Feature 034 and 034B source and historical outputs remain unchanged.
- `research_only=true`
- `signal_allowed=false`
- `order_submission_allowed=false`

## Acceptance

- Every retained session receives a precise coverage or exclusion classification.
- The frozen manifest hash validates and changes when rules change.
- Raw first touch can emit a reference alert without OI/rejection.
- Broker translation requires a synchronized quote.
- Append-only plans, alerts, acknowledgements, events, outcomes, and summaries exist.
- Sample and promotion reports distinguish operational progress from validation.
- Standard promotion cannot use the external prior as a bypass.
- Ruff, focused tests, backend import, CLI help, and retained-data audit pass.
