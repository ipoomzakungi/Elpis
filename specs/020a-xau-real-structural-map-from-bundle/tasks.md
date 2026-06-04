# Tasks: XAU Real Structural Map From Bundle

**Input**: Design documents from `specs/020a-xau-real-structural-map-from-bundle/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup

- [X] T001 Create Feature 020A specification in `specs/020a-xau-real-structural-map-from-bundle/spec.md`
- [X] T002 Create Feature 020A implementation plan in `specs/020a-xau-real-structural-map-from-bundle/plan.md`
- [X] T003 [P] Create Feature 020A research notes in `specs/020a-xau-real-structural-map-from-bundle/research.md`
- [X] T004 [P] Create Feature 020A data model in `specs/020a-xau-real-structural-map-from-bundle/data-model.md`
- [X] T005 [P] Create Feature 020A adapter contract in `specs/020a-xau-real-structural-map-from-bundle/contracts/api.md`
- [X] T006 [P] Create Feature 020A quickstart in `specs/020a-xau-real-structural-map-from-bundle/quickstart.md`
- [X] T007 Create Feature 020A requirements checklist in `specs/020a-xau-real-structural-map-from-bundle/checklists/requirements.md`
- [X] T008 Create Feature 020A tasks in `specs/020a-xau-real-structural-map-from-bundle/tasks.md`

---

## Phase 2: Foundational Adapter

- [X] T009 Add bundle adapter module in `backend/src/xau_daily_structural_map/bundle_adapter.py`
- [X] T010 Implement JSON report loading for direct and composed report payloads in `backend/src/xau_daily_structural_map/bundle_adapter.py`
- [X] T011 Implement expected-range snapshot extraction and range-label-only unavailable handling in `backend/src/xau_daily_structural_map/bundle_adapter.py`
- [X] T012 Implement manual/computed/unavailable basis resolution in `backend/src/xau_daily_structural_map/bundle_adapter.py`
- [X] T013 Implement parquet wall loading and embedded wall fallback in `backend/src/xau_daily_structural_map/bundle_adapter.py`
- [X] T014 Implement persistence through Feature 019 store in `backend/src/xau_daily_structural_map/bundle_adapter.py`

---

## Phase 3: User Story 1 - Generate One Local Bundle Map

- [X] T015 [P] [US1] Add full-context adapter test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`
- [X] T016 [US1] Verify full-context persisted map round-trips in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`

---

## Phase 4: User Story 2 - Preserve Missing Context

- [X] T017 [P] [US2] Add missing-basis adapter test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`
- [X] T018 [P] [US2] Add missing-expected-range adapter test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`
- [X] T019 [P] [US2] Add range-label-only adapter test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`
- [X] T020 [P] [US2] Add null OI-change and volume preservation test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`

---

## Phase 5: User Story 3 - Wall Fallbacks

- [X] T021 [P] [US3] Add missing-parquet embedded-wall fallback test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`
- [X] T022 [P] [US3] Add no-wall persistence test in `backend/tests/unit/test_xau_daily_structural_map_bundle_adapter.py`

---

## Phase 6: Polish & Validation

- [X] T023 Run store tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map_store.py -q`
- [X] T024 Run Feature 018 tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map.py -q`
- [X] T025 Run Feature 017 tests from backend: `python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q`
- [X] T026 Run adapter tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map_bundle_adapter.py -q`
- [X] T027 Run backend import check from backend: `python -c "from src.main import app; print('backend import ok')"`
- [X] T028 Run ruff on touched Python files
- [X] T029 Confirm no live trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML model training, buy/sell output, alerts, PnL, or backtest was added

---

## Dependencies & Execution Order

- Phase 1 setup has no dependencies.
- Phase 2 adapter blocks all user-story tests.
- Phase 3 is the MVP.
- Phase 4 and Phase 5 can validate independently after the adapter exists.
- Phase 6 validation depends on implemented phases.

## Implementation Strategy

1. Add the adapter module with pure local file loading.
2. Add temp bundle fixtures and focused tests.
3. Run focused and regression validation.
4. Stop before forward outcomes, classifiers, signals, alerts, PnL, or backtests.
