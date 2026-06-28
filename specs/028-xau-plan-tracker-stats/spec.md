## Feature Specification: XAU Plan Tracker Stats

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`  
**Created**: 2026-06-09  
**Status**: Draft  
**Input**: Aggregate Feature 026 plan-tracker outcomes for statistical reporting.

### Goal

Create a research-only aggregation API and CLI for existing plan-tracker runs so users can
query outcome summary statistics without re-running simulations.

### User Stories

- As a researcher, I want aggregate counts and run summaries across sessions.
- As a researcher, I want a one-run summary for a selected run_id.
- As an operator, I need outputs that are still explicitly non-signaling.

### Requirements

- Add result models for request/query, dte aggregate, run summary, and final stats output.
- Add `list_results` in plan-tracker report store for enumeration.
- Implement `XauPlanTrackerStatisticsService`:
  - `run(request)`
  - `run_for_run(run_id, request)`
- Add API endpoints:
  - `POST /api/v1/research/xau/plan-tracker/stats`
  - `GET  /api/v1/research/xau/plan-tracker/stats/{run_id}`
- Add script:
  - `backend/scripts/run_xau_plan_tracker_stats.py`
- Preserve research-only guardrails:
  - `signal_allowed=false`
  - `research_only=true`
- Keep all responses deterministic and offline (no trading/execution side effects).

### Acceptance Criteria

- Focused pytest set for stats service/API/CLI passes.
- Responses include filtering behavior for planning times, side, status, unavailable inclusion, and run count limits.
- No live order IDs, execution data, broker fields, or capital assumptions added.
