# Implementation Plan: XAU Tiered First-Touch Manual Signal

## Phase 1 - Freeze Policy

- Add hashed 034B tier, barrier, OI-zone, rejection, broker, and promotion rules.

## Phase 2 - Historical Matrix

- Build T0 strict-DTE plans.
- Interpolate 1.5SD without modifying Feature 034.
- Evaluate tier/barrier profiles and side-specific sensitivity.
- Run lower-2SD OI-zone rejection with next-bar entry.

## Phase 3 - Manual Alert Workflow

- Add current plan and manual-alert state classification.
- Add broker quote translation and fail-closed freshness/spread gates.
- Add immutable JSONL journals and acknowledgement behavior.
- Add API and CLI surfaces.

## Phase 4 - Validation

- Run tests and retained-data matrix.
- Generate current-day plan.
- Commit and push only code, tests, config, specs, and docs.
