# Tasks: XAU Daily Structural Map

**Input**: Design documents from `specs/018-xau-daily-structural-map/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup

- [X] T001 Create Feature 018 specification in `specs/018-xau-daily-structural-map/spec.md`
- [X] T002 Create Feature 018 implementation plan in `specs/018-xau-daily-structural-map/plan.md`
- [X] T003 [P] Create Feature 018 research notes in `specs/018-xau-daily-structural-map/research.md`
- [X] T004 [P] Create Feature 018 data model in `specs/018-xau-daily-structural-map/data-model.md`
- [X] T005 [P] Create Feature 018 payload contract in `specs/018-xau-daily-structural-map/contracts/api.md`
- [X] T006 [P] Create Feature 018 quickstart in `specs/018-xau-daily-structural-map/quickstart.md`
- [X] T007 Create Feature 018 requirements checklist in `specs/018-xau-daily-structural-map/checklists/requirements.md`
- [X] T008 Create Feature 018 tasks in `specs/018-xau-daily-structural-map/tasks.md`

---

## Phase 2: Foundational Schemas

- [X] T009 [P] Add structural map readiness and wall mapping enums in `backend/src/models/xau.py`
- [X] T010 [P] Add `XauDailyStructuralMapRange` and `XauDailyStructuralMapBasis` schemas in `backend/src/models/xau.py`
- [X] T011 [P] Add `XauDailyStructuralMapWall` schema in `backend/src/models/xau.py`
- [X] T012 Add `XauDailyStructuralMap` schema and validators in `backend/src/models/xau.py`

---

## Phase 3: User Story 1 - Build One Daily Research Map

- [X] T013 [P] [US1] Add full-context map test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T014 [P] [US1] Add Feature 017 integration test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T015 [US1] Add structural map builder in `backend/src/xau_quikstrike_fusion/daily_structural_map.py`
- [X] T016 [US1] Ensure complete maps keep `signal_allowed = false` in `backend/src/xau_quikstrike_fusion/daily_structural_map.py`

---

## Phase 4: User Story 2 - Preserve Partial Context

- [X] T017 [P] [US2] Add missing-basis test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T018 [P] [US2] Add missing-expected-range test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T019 [P] [US2] Add missing-session-open test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T020 [P] [US2] Add blank Matrix cell null-preservation test in `backend/tests/unit/test_xau_daily_structural_map.py`
- [X] T021 [US2] Implement missing-context readiness and no-signal reasons in `backend/src/xau_quikstrike_fusion/daily_structural_map.py`

---

## Phase 5: Polish & Validation

- [X] T022 Run map tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map.py -q`
- [X] T023 Run Feature 017 tests from backend: `python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q`
- [X] T024 Run inventory tests from repo root: `python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q`
- [X] T025 Run backend import check from backend: `python -c "from src.main import app; print('backend import ok')"`
- [X] T026 Run ruff on touched Python files
- [X] T027 Confirm no live trading, broker integration, private keys, endpoint replay, paid vendor ingestion, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML model training, or buy/sell output was added

---

## Dependencies & Execution Order

- Phase 1 setup has no dependencies.
- Phase 2 schemas block builder and tests.
- Phase 3 complete-map behavior is the MVP.
- Phase 4 partial-context behavior can validate independently after schemas exist.
- Phase 5 validation depends on implemented phases.

## Implementation Strategy

1. Add schemas.
2. Add builder.
3. Add tests.
4. Run focused validation.
5. Stop before strategy signals, candidate classifiers, alerts, or backtests.
