# API Contract: XAU Plan Tracker Dashboard Data Load

Feature 027 is a frontend composition on top of existing Feature 026 API endpoints.

## Required Endpoints

### GET /api/v1/research/xau/plan-tracker/latest

Fetches latest available run metadata.

### GET /api/v1/research/xau/plan-tracker/runs/{run_id}

Fetches one run summary by id.

### GET /api/v1/research/xau/plan-tracker/runs/{run_id}/orders

Fetches tracked research orders for a run.

### GET /api/v1/research/xau/plan-tracker/runs/{run_id}/snapshots

Fetches plan snapshots for a run.

## Frontend Behavior

- On page load: call `latest` then load `run`, `orders`, `snapshots` for that run id.
- On user action: call `{run_id}` endpoints directly and replace table contents.
- On any 404/HTTP error: show explicit user-facing empty/error message.

## Guardrails

- Dashboard does not introduce new backend contracts.
- No signal generation / execution endpoints are added.
