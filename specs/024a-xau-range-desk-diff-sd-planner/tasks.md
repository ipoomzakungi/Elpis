# Tasks: XAU Range Desk / Diff-SD Planner

**Input**: Design documents from `specs/024a-xau-range-desk-diff-sd-planner/`
**Prerequisites**: `plan.md`, `spec.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required for the planner and API route.

## Phase 1: Setup

- [X] T001 Create Feature 024A specification in `specs/024a-xau-range-desk-diff-sd-planner/spec.md`
- [X] T002 Create Feature 024A implementation plan in `specs/024a-xau-range-desk-diff-sd-planner/plan.md`
- [X] T003 [P] Create Feature 024A data model in `specs/024a-xau-range-desk-diff-sd-planner/data-model.md`
- [X] T004 [P] Create Feature 024A API contract in `specs/024a-xau-range-desk-diff-sd-planner/contracts/api.md`
- [X] T005 [P] Create Feature 024A quickstart in `specs/024a-xau-range-desk-diff-sd-planner/quickstart.md`
- [X] T006 Create Feature 024A requirements checklist in `specs/024a-xau-range-desk-diff-sd-planner/checklists/requirements.md`

## Phase 2: Foundational Models And Planner

- [X] T007 Add Range Desk Pydantic models in `backend/src/models/xau_range_desk.py`
- [X] T008 Add Range Desk package exports in `backend/src/xau_range_desk/__init__.py`
- [X] T009 Add pure Range Desk planner in `backend/src/xau_range_desk/planner.py`

## Phase 3: User Story 1 - Map Futures Levels To Traded Levels

- [X] T010 [P] [US1] Add diff mapping planner test in `backend/tests/unit/test_xau_range_desk_planner.py`
- [X] T011 [US1] Implement diff and mapped-level calculation in `backend/src/xau_range_desk/planner.py`

## Phase 4: User Story 2 - Build Planning Zones And Targets

- [X] T012 [P] [US2] Add SD zone and target-plan test in `backend/tests/unit/test_xau_range_desk_planner.py`
- [X] T013 [US2] Implement no-trade, stretch-zone, mapped wall, and target-plan output in `backend/src/xau_range_desk/planner.py`

## Phase 5: User Story 3 - Preserve Missing Context

- [X] T014 [P] [US3] Add missing context test in `backend/tests/unit/test_xau_range_desk_planner.py`
- [X] T015 [US3] Preserve missing SD and wall context in `backend/src/xau_range_desk/planner.py`

## Phase 6: API And Validation

- [X] T016 Add Range Desk API route in `backend/src/api/routes/xau_range_desk.py`
- [X] T017 Register Range Desk router in `backend/src/main.py`
- [X] T018 Add API route test in `backend/tests/unit/test_xau_range_desk_api.py`
- [X] T019 Update `docs/project_status.md`
- [X] T020 Run focused Feature 024A tests and adjacent Feature 021/022/023 regressions
- [X] T021 Run backend import check and ruff on touched Python files
- [X] T022 Start backend and verify `/health`, `/docs`, and `/api/v1/research/xau/range-desk/plan`
- [X] T023 Confirm no live trading, paper trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell live signal, alert, PnL, or execution was added
