# Tasks: XAU Daily Research Workbench

**Input**: Design documents from `specs/022-xau-daily-research-workbench/`
**Prerequisites**: `plan.md`, `spec.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

## Phase 1: Setup

- [X] T001 Create Feature 022 specification in `specs/022-xau-daily-research-workbench/spec.md`
- [X] T002 Create Feature 022 implementation plan in `specs/022-xau-daily-research-workbench/plan.md`
- [X] T003 [P] Create Feature 022 data model in `specs/022-xau-daily-research-workbench/data-model.md`
- [X] T004 [P] Create Feature 022 API contract in `specs/022-xau-daily-research-workbench/contracts/api.md`
- [X] T005 [P] Create Feature 022 quickstart in `specs/022-xau-daily-research-workbench/quickstart.md`
- [X] T006 Create Feature 022 requirements checklist in `specs/022-xau-daily-research-workbench/checklists/requirements.md`
- [X] T007 Create Feature 022 tasks in `specs/022-xau-daily-research-workbench/tasks.md`

## Phase 2: Foundational Models And Store

- [X] T008 Add workbench request/result/API models in `backend/src/models/xau_daily_workbench.py`
- [X] T009 Add workbench report store in `backend/src/xau_daily_workbench/report_store.py`
- [X] T010 Add package exports in `backend/src/xau_daily_workbench/__init__.py`

## Phase 3: User Story 1 - Run One Daily Workbench

- [X] T011 [P] [US1] Add full fixture workbench run test in `backend/tests/unit/test_xau_daily_workbench_service.py`
- [X] T012 [US1] Implement `run_xau_daily_research_workbench(...)` in `backend/src/xau_daily_workbench/service.py`
- [X] T013 [US1] Implement local bundle source and latest-existing source in `backend/src/xau_daily_workbench/service.py`
- [X] T014 [US1] Persist workbench run artifacts under `data/reports/xau_daily_workbench/`
- [X] T015 [US1] Persist candidate sidecars beside the structural map

## Phase 4: User Story 2 - Preserve Missing Context

- [X] T016 [P] [US2] Add missing CME source test
- [X] T017 [P] [US2] Add missing basis blocked/no-trade test
- [X] T018 [P] [US2] Add missing session open blocked/no-trade test
- [X] T019 [P] [US2] Add candidate sidecar roundtrip test
- [X] T020 [US2] Return blocked results with explicit `missing_inputs`

## Phase 5: User Story 3 - API

- [X] T021 [P] [US3] Add API run/latest/map/candidate contract tests
- [X] T022 [US3] Add `backend/src/api/routes/xau_daily_workbench.py`
- [X] T023 [US3] Register the workbench router in `backend/src/main.py`

## Phase 6: Polish & Validation

- [X] T024 Run workbench service/API tests
- [X] T025 Run structural-map bundle adapter and candidate classifier regression tests
- [X] T026 Run backend import check
- [X] T027 Run ruff on touched Python files
- [X] T028 Confirm no live trading, paper trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell live signal, alert, PnL, or execution was added

## Dependencies & Execution Order

- Setup blocks all work.
- Models and store block service.
- Service blocks API.
- Tests run before final status/commit.

## Implementation Strategy

1. Add strict workbench models.
2. Add focused tests around fixture and missing-context workflows.
3. Implement service orchestration around existing Feature 020A and Feature 021.
4. Add local API endpoints.
5. Run validation and keep frontend deferred.
