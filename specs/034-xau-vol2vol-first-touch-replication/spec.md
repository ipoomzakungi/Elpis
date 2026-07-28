# Feature Specification: XAU Vol2Vol First-Touch Replication

**Feature Branch**: `codex/034-xau-vol2vol-first-touch-replication`
**Created**: 2026-07-28
**Status**: Active

## Goal

Replicate the supplied external 500-session Vol2Vol SD first-touch study on
retained Elpis data while separating:

- the published eventual $25 reversal label;
- a tradable first-passage TP25/SL25 label;
- fixed daily time anchors;
- futures-to-XAUUSD mapping assumptions.

The external counts are priors, not locally validated probabilities.

## Requirements

- Freeze the study rules in `backend/config/xau_vol2vol_first_touch_study_v1.json`.
- Exclude missing, incomplete, substituted, or date-mismatched Vol2Vol sessions.
- Select one series without cross-series mixing.
- Keep T0 DTE 0.80, T1 CME settlement, and T2 Bangkok 07:00 separate.
- Keep distance-reanchored and same-time-reference-basis mappings separate.
- Build literal 1SD, 2SD, and 3SD first-touch events with aggregated and
  side-specific counting modes.
- Evaluate eventual reversal and strict first-passage labels separately.
- Pre-register barrier and DTE sensitivity without choosing a winner after the run.
- Produce a deterministic research-only shadow plan with no order interface.
- Attach descriptive OI/IV/flow context without making it a mandatory baseline filter.
- Report Wilson intervals, session bootstrap, chronological holdout, costs,
  side results, loss clustering, and promotion gates.

## Guardrails

- `research_only=true`
- `signal_allowed=false`
- `order_submission_allowed=false`
- No broker adapter, order submission, sizing, leverage, recovery, martingale,
  averaging, or automatic LLM decision path.
- Candidate validation v2, C1/C2, protocol v1, and Feature 032 reports are immutable.

## Acceptance Criteria

- Focused tests prove first-touch counting, label differences, timestamp safety,
  mapping separation, series isolation, cost-count invariance, and shadow-only state.
- Ruff, backend import, and CLI help pass.
- A retained-data run writes all required artifacts.
- Generated data and reports remain untracked.
