## Implementation Plan: XAU Plan Tracker Stats

### Phase 1 — Model, Store, Service

- [ ] Add stats models in `backend/src/models/xau_plan_tracker_statistics.py`
- [ ] Add `list_results` to `backend/src/xau_price_plan_tracker/report_store.py`
- [ ] Add `backend/src/xau_plan_tracker_statistics/service.py` for aggregation and filtering

### Phase 2 — API

- [ ] Extend `backend/src/api/routes/xau_plan_tracker.py` with:
  - `POST /research/xau/plan-tracker/stats`
  - `GET /research/xau/plan-tracker/stats/{run_id}`

### Phase 3 — CLI

- [ ] Add `backend/scripts/run_xau_plan_tracker_stats.py`
- [ ] Add `run_id`, time filter, side/status filter options

### Phase 4 — Validation

- [ ] Add unit tests:
  - service aggregation/filtering
  - API endpoint payloads
  - CLI help + output path
- [ ] Run Ruff + targeted tests.
