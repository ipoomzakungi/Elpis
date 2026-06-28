# Feature Specification: XAU Plan Tracker Dashboard

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`
**Created**: 2026-06-09
**Status**: Draft
**Input**: User requested a frontend dashboard for Feature 026 outputs.

## User Scenarios & Testing

### User Story 1 - View Latest Plan Tracker Run (Priority: P1)

As an XAU researcher, I want to open `/xau-plan-tracker` and see the latest Feature 026
run so I can inspect snapshots and simulated orders without calling scripts manually.

### User Story 2 - Inspect Snapshot Plan Levels (Priority: P1)

As a researcher, I want to inspect 10:10 and 18:10 planning snapshots with future/spots,
Diff, DTE, native SD, and mapped long/short plan levels.

### User Story 3 - Inspect Simulated Order Outcomes (Priority: P1)

As a researcher, I want to see order status, trigger/exit, PnL points, drawdown points,
near-miss diagnostics, and recovery outcomes for each tracked order.

### User Story 4 - Debug Data Provenance (Priority: P2)

As a research operator, I need to see missing inputs, limitations, and no-signal reasons
so I can explain exactly why a plan did not trigger or was blocked.

## Requirements

- **FR-001**: Dashboard must load latest run from `GET /api/v1/research/xau/plan-tracker/latest`.
- **FR-002**: Dashboard must load matching snapshots from `GET /api/v1/research/xau/plan-tracker/runs/{run_id}/snapshots`.
- **FR-003**: Dashboard must load matching orders from `GET /api/v1/research/xau/plan-tracker/runs/{run_id}/orders`.
- **FR-004**: Dashboard must support loading a specific run_id for replay/review.
- **FR-005**: Dashboard must display `signal_allowed=false` and `research_only=true`.
- **FR-006**: Dashboard must show long/short entry/target/stop/recovery levels, status, current PnL points, and drawdown.
- **FR-007**: Dashboard must show near-miss diagnostics (`near_miss`, distance, threshold, closest price/time).
- **FR-008**: Dashboard must handle empty/missing artifacts as non-fatal with clear notices.
- **FR-009**: Dashboard must keep all outputs in research context and avoid signaling actions.
- **FR-010**: `No plan tracker run exists` and API failures must surface clean status messages instead of crash.

## Key UI Entities

- **Run summary cards**: run_id, session_date, readiness, counts, signal/research flags.
- **Snapshot cards**: planning time, basis mapping values, SDs, plan levels.
- **Order table**: one row per long/short plan with status and diagnostics.
- **Source quality panel**: missing inputs, limitations, no-signal reasons.
- **Artifact list**: local output paths for run metadata and markdown history.

## Success Criteria

- **SC-001**: Opening `/xau-plan-tracker` shows latest completed run summary if available.
- **SC-002**: Snapshot cards show readable long and short mapped plan details.
- **SC-003**: Near-miss rows appear when `near_miss=true`.
- **SC-004**: Recovery-triggered or recovery-target rows are marked and visible.
- **SC-005**: Empty state appears if no run exists, with guidance to run backend script.

## Assumptions

- Feature 026 remains the source of plan tracking data.
- Backend API returns deterministic run, snapshot, and order payloads.
- This feature is for review and inspection only; no execution controls are added.
