# Implementation Plan: XAU Plan Tracker Dashboard

**Branch**: `codex/xau-vol-oi-research-pipeline` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

## Scope

Build a frontend dashboard page at `/xau-plan-tracker` that reads existing
Feature 026 API outputs and renders readable planning snapshots, order outcomes, and
diagnostic information for research review.

## Technical Context

- **Language/Version**: TypeScript / Next.js (app router)
- **Stack already used in app**: React hooks, local API client in `frontend/src/services/api.ts`
- **API surfaces**:
  - `GET /api/v1/research/xau/plan-tracker/latest`
  - `GET /api/v1/research/xau/plan-tracker/runs/{run_id}`
  - `GET /api/v1/research/xau/plan-tracker/runs/{run_id}/orders`
  - `GET /api/v1/research/xau/plan-tracker/runs/{run_id}/snapshots`
- **Design**: Use existing dashboard visual language (`rounded` cards, status tags, compact tables).

## Frontend Tasks

1. Add `/xau-plan-tracker` route page.
2. Load latest run on mount and show a run ID input to fetch specific runs.
3. Render status cards (run id/date/readiness counts).
4. Render 10:10/18:10 snapshot cards with long/short plan details.
5. Render order table with status tags and near-miss flags.
6. Add explicit research-only notice (`signal_allowed=false`, `research_only=true`).
7. Add source-quality section from run-level missing inputs / limitations / no-signal reasons.
8. Add nav link in global header.

## Error handling

- If latest run endpoint returns 404, show empty-state guidance.
- If run/orders/snapshots fetch fails, show error text and keep existing run state unchanged.

## Data Integrity

- No model transforms that mutate payloads.
- Do not calculate or infer trading signals.
- Format numeric values safely with `n/a` for nulls to avoid rendering exceptions.

## Validation

- Build frontend and fix rendering/typing issues.
- Verify route loads local runs created by Feature 026 script.

