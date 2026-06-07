# Tasks: XAU Candidate Forward Outcomes

**Input**: Design documents from `specs/023-xau-candidate-forward-outcomes/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

## Phase 1: Setup

- [X] T001 Create Feature 023 specification in `specs/023-xau-candidate-forward-outcomes/spec.md`
- [X] T002 Create Feature 023 implementation plan in `specs/023-xau-candidate-forward-outcomes/plan.md`
- [X] T003 [P] Create Feature 023 research notes in `specs/023-xau-candidate-forward-outcomes/research.md`
- [X] T004 [P] Create Feature 023 data model in `specs/023-xau-candidate-forward-outcomes/data-model.md`
- [X] T005 [P] Create Feature 023 API contract in `specs/023-xau-candidate-forward-outcomes/contracts/api.md`
- [X] T006 [P] Create Feature 023 quickstart in `specs/023-xau-candidate-forward-outcomes/quickstart.md`
- [X] T007 Create Feature 023 requirements checklist in `specs/023-xau-candidate-forward-outcomes/checklists/requirements.md`
- [X] T008 Create Feature 023 tasks in `specs/023-xau-candidate-forward-outcomes/tasks.md`

## Phase 2: Foundational Models And Price Loading

- [X] T009 Add candidate outcome enums and Pydantic models in `backend/src/models/xau_candidate_outcome.py`
- [X] T010 Add model validators that enforce `signal_allowed=false`, `research_only=true`, count parity, local paths, and no blank ids in `backend/src/models/xau_candidate_outcome.py`
- [X] T011 Add local price-bar models and providers in `backend/src/xau_candidate_outcomes/price_series.py`
- [X] T012 Add package exports in `backend/src/xau_candidate_outcomes/__init__.py`

## Phase 3: User Story 1 - Compute Candidate Outcome Windows

- [X] T013 [P] [US1] Add short target-before-stop test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T014 [P] [US1] Add short stop-before-target test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T015 [P] [US1] Add long target and MFE/MAE test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T016 [P] [US1] Add breakout continuation test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T017 [US1] Implement outcome calculator in `backend/src/xau_candidate_outcomes/calculator.py`

## Phase 4: User Story 2 - Preserve Missing And Partial Price Coverage

- [X] T018 [P] [US2] Add missing price bars test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T019 [P] [US2] Add partial window test in `backend/tests/unit/test_xau_candidate_outcome_calculator.py`
- [X] T020 [P] [US2] Add model guardrail tests in `backend/tests/unit/test_xau_candidate_outcome_models.py`
- [X] T021 [US2] Ensure calculator preserves nulls and limitation notes in `backend/src/xau_candidate_outcomes/calculator.py`

## Phase 5: User Story 3 - Persist And Serve Outcome Runs

- [X] T022 [P] [US3] Add candidate artifact roundtrip test in `backend/tests/unit/test_xau_candidate_outcome_store.py`
- [X] T023 [US3] Add outcome report store in `backend/src/xau_candidate_outcomes/report_store.py`
- [X] T024 [US3] Add outcome orchestration service in `backend/src/xau_candidate_outcomes/service.py`
- [X] T025 [P] [US3] Add API run/latest/read tests in `backend/tests/unit/test_xau_candidate_outcome_api.py`
- [X] T026 [US3] Add API router in `backend/src/api/routes/xau_candidate_outcomes.py`
- [X] T027 [US3] Register the candidate outcome router in `backend/src/main.py`
- [X] T028 [P] [US3] Add CLI tests in `backend/tests/unit/test_run_xau_candidate_forward_outcomes_script.py`
- [X] T029 [US3] Add CLI script in `backend/scripts/run_xau_candidate_forward_outcomes.py`

## Phase 6: Documentation And Validation

- [X] T030 Update `docs/project_status.md`
- [X] T031 Update `docs/course_source/COURSE_DOCTRINE_INDEX.md`
- [X] T032 Run Feature 021 and Feature 022 regression tests
- [X] T033 Run Feature 023 model, calculator, store, API, and CLI tests
- [X] T034 Run backend import check and CLI help
- [X] T035 Run ruff on touched Python files
- [X] T036 Start backend and verify `/health` and `/docs`
- [X] T037 Confirm no live trading, paper trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell live signal, alert, PnL, or execution was added

## Dependencies & Execution Order

- Phase 1 setup has no dependencies.
- Phase 2 models and price loading block calculator, store, API, and CLI.
- Phase 3 is the MVP evidence-calculation slice.
- Phase 4 adds missing/partial coverage guardrails.
- Phase 5 persists and exposes outcome runs.
- Phase 6 validation depends on all implemented phases.

## Implementation Strategy

1. Add strict outcome and price-bar models.
2. Add focused calculator tests before wiring API/CLI.
3. Implement pure calculator behavior.
4. Add persistence and service orchestration.
5. Add local API and CLI.
6. Run focused regression validation and stop before PnL, alerts, execution, or backtests.
