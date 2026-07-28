# Feature Specification: XAU Tiered First-Touch Manual Signal

**Feature Branch**: `codex/034b-xau-tiered-first-touch-manual-signal`
**Created**: 2026-07-28
**Status**: Active

## Goal

Extend frozen Feature 034 with a narrow T0/DTE-0.80 tiered experiment and
deterministic non-executable manual alerts.

## Scope

- Canonical T0 DTE-0.80 fixed plan only.
- Literal 1SD, interpolated 1.5SD, literal 2SD, and literal 3SD.
- Lower-long candidates; upper-short remains observed.
- Predefined TP12.5/SL12.5 and TP25/SL25 profiles.
- OI-confluence zone and two frozen rejection definitions.
- Rejection-confirmed entry on the next executable closed-bar open.
- Optional synchronized broker quote translation.
- Immutable JSONL plans, signals, acknowledgements, outcomes, and summaries.
- Latest-signal and acknowledgement API endpoints.

## Guardrails

- No broker orders, position size, leverage, recovery, martingale, averaging,
  or automated execution.
- Only one active manual candidate.
- Tiers touched while active are recorded as missed, not stacked.
- `research_only=true`
- `signal_allowed=false`
- `order_submission_allowed=false`
- Feature 034's frozen registry and replication outputs remain unchanged.

## Acceptance

- Historical matrix and executable OI/rejection rerun are produced.
- 1SD TP12.5/SL12.5 remains disabled unless its own gates pass.
- 1.5SD is explicitly labeled an Elpis interpolation.
- Current plan is generated or fails closed with reasons.
- Focused tests, API tests, Ruff, import, and CLI help pass.
