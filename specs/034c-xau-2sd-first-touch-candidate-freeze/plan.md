# Implementation Plan: XAU 2SD First-Touch Candidate Freeze

## Phase 1 - Coverage Audit

- Inspect raw Vol2Vol rows before normalization.
- Classify every completed session with exact DTE, parser, timing, and mapping reasons.
- Fix only demonstrated parser defects and rerun affected studies.

## Phase 2 - Candidate Freeze

- Add a hashed `FT2_RAW_V1` manifest.
- Keep small-target and rejection challengers separate and non-promotable.
- Preserve fixed daily plan and literal first-touch semantics.

## Phase 3 - Daily Sample Workflow

- Extend daily collection with explicit CDP preflight.
- Persist immutable plans, events, alerts, acknowledgements, outcomes, and summaries.
- Add reference and broker-translated provisional alert states.

## Phase 4 - Reporting

- Add sample, side, cost, uncertainty, drawdown, holdout, and promotion reports.
- Add a schema-only external raw-study importer without fabricating observations.

## Phase 5 - Validation

- Run focused tests and Feature 034B regressions.
- Execute the full retained-session audit and candidate report.
- Generate the current plan or fail closed with exact reasons.
- Commit and push only code, tests, config, specs, and documentation.
