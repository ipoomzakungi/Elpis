# Tasks: XAU Daily Structural Map Persistence And Sample Run

**Input**: Design documents from `specs/019-xau-daily-structural-map-persistence-and-sample-run/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup

- [X] T001 Create Feature 019 specification in `specs/019-xau-daily-structural-map-persistence-and-sample-run/spec.md`
- [X] T002 Create Feature 019 implementation plan in `specs/019-xau-daily-structural-map-persistence-and-sample-run/plan.md`
- [X] T003 [P] Create Feature 019 research notes in `specs/019-xau-daily-structural-map-persistence-and-sample-run/research.md`
- [X] T004 [P] Create Feature 019 data model in `specs/019-xau-daily-structural-map-persistence-and-sample-run/data-model.md`
- [X] T005 [P] Create Feature 019 artifact contract in `specs/019-xau-daily-structural-map-persistence-and-sample-run/contracts/api.md`
- [X] T006 [P] Create Feature 019 quickstart in `specs/019-xau-daily-structural-map-persistence-and-sample-run/quickstart.md`
- [X] T007 Create Feature 019 requirements checklist in `specs/019-xau-daily-structural-map-persistence-and-sample-run/checklists/requirements.md`
- [X] T008 Create Feature 019 tasks in `specs/019-xau-daily-structural-map-persistence-and-sample-run/tasks.md`

---

## Phase 2: Foundational Models

- [X] T009 [P] Add structural-map artifact and metadata models in `backend/src/models/xau_daily_structural_map.py`
- [X] T010 [P] Add structural-map package initialization in `backend/src/xau_daily_structural_map/__init__.py`

---

## Phase 3: User Story 1 - Persist One Structural Map

- [X] T011 [P] [US1] Add full-context persistence and round-trip tests in `backend/tests/unit/test_xau_daily_structural_map_store.py`
- [X] T012 [US1] Add path-safe structural-map report store in `backend/src/xau_daily_structural_map/report_store.py`
- [X] T013 [US1] Add metadata, map JSON, map Markdown, and walls JSON persistence in `backend/src/xau_daily_structural_map/report_store.py`

---

## Phase 4: User Story 2 - Preserve Partial Maps

- [X] T014 [P] [US2] Add missing-basis persistence test in `backend/tests/unit/test_xau_daily_structural_map_store.py`
- [X] T015 [P] [US2] Add missing-expected-range persistence test in `backend/tests/unit/test_xau_daily_structural_map_store.py`
- [X] T016 [P] [US2] Add missing-session-open persistence test in `backend/tests/unit/test_xau_daily_structural_map_store.py`
- [X] T017 [P] [US2] Add null OI-change and volume preservation test in `backend/tests/unit/test_xau_daily_structural_map_store.py`

---

## Phase 5: User Story 3 - Generate A Local Sample Run

- [X] T018 [P] [US3] Add sample-run helper test in `backend/tests/unit/test_xau_daily_structural_map_store.py`
- [X] T019 [US3] Add `generate_xau_daily_structural_map_report` in `backend/src/xau_daily_structural_map/sample_run.py`

---

## Phase 6: Polish & Validation

- [X] T020 Run store tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map_store.py -q`
- [X] T021 Run Feature 018 tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map.py -q`
- [X] T022 Run Feature 017 tests from backend: `python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q`
- [X] T023 Run inventory tests from repo root: `python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q`
- [X] T024 Run backend import check from backend: `python -c "from src.main import app; print('backend import ok')"`
- [X] T025 Run ruff on touched Python files
- [X] T026 Confirm no live trading, broker integration, private keys, endpoint replay, paid vendor ingestion, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML model training, buy/sell output, alerts, PnL, or backtest was added

---

## Dependencies & Execution Order

- Phase 1 setup has no dependencies.
- Phase 2 models block store and sample-run result schemas.
- Phase 3 persistence is the MVP.
- Phase 4 partial-map tests validate persistence does not fabricate missing context.
- Phase 5 sample-run helper depends on store and Feature 018 builder.
- Phase 6 validation depends on implemented phases.

## Implementation Strategy

1. Add persistence models.
2. Add path-safe store.
3. Add sample-run helper.
4. Add focused tests.
5. Run validation.
6. Stop before outcomes, signal classifiers, alerts, or backtests.
