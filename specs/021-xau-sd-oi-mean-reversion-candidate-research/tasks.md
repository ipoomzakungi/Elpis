# Tasks: XAU SD OI Mean Reversion Candidate Research

**Input**: Design documents from `specs/021-xau-sd-oi-mean-reversion-candidate-research/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

## Phase 1: Setup

- [X] T001 Create Feature 021 specification in `specs/021-xau-sd-oi-mean-reversion-candidate-research/spec.md`
- [X] T002 Create Feature 021 implementation plan in `specs/021-xau-sd-oi-mean-reversion-candidate-research/plan.md`
- [X] T003 [P] Create Feature 021 research notes in `specs/021-xau-sd-oi-mean-reversion-candidate-research/research.md`
- [X] T004 [P] Create Feature 021 data model in `specs/021-xau-sd-oi-mean-reversion-candidate-research/data-model.md`
- [X] T005 [P] Create Feature 021 classifier contract in `specs/021-xau-sd-oi-mean-reversion-candidate-research/contracts/api.md`
- [X] T006 [P] Create Feature 021 quickstart in `specs/021-xau-sd-oi-mean-reversion-candidate-research/quickstart.md`
- [X] T007 Create Feature 021 requirements checklist in `specs/021-xau-sd-oi-mean-reversion-candidate-research/checklists/requirements.md`
- [X] T008 Create Feature 021 tasks in `specs/021-xau-sd-oi-mean-reversion-candidate-research/tasks.md`

## Phase 2: Foundational Models

- [X] T009 Add candidate enums and Pydantic models in `backend/src/models/xau_sd_oi_candidate.py`
- [X] T010 Add model validators that enforce `signal_allowed=false`, `research_only=true`, candidate count parity, and no blank ids in `backend/src/models/xau_sd_oi_candidate.py`

## Phase 3: User Story 1 - Classify One Timestamp Candidate

- [X] T011 [P] [US1] Add upper 2SD-3SD rejection test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T012 [P] [US1] Add lower 2SD-3SD rejection test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T013 [P] [US1] Add inside +/-2SD monitor/no-trade test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T014 [US1] Implement candidate classifier in `backend/src/xau_sd_oi_candidate/classifier.py`
- [X] T015 [US1] Export classifier package in `backend/src/xau_sd_oi_candidate/__init__.py`

## Phase 4: User Story 2 - Preserve Missing And Breakout Context

- [X] T016 [P] [US2] Add missing-basis no-trade test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T017 [P] [US2] Add breakout-risk override test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T018 [P] [US2] Add null OI-change and volume preservation test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`
- [X] T019 [P] [US2] Add derived 3.5SD limitation test in `backend/tests/unit/test_xau_sd_oi_mean_reversion_candidate.py`

## Phase 5: Polish & Validation

- [X] T020 Run candidate tests from backend: `python -m pytest tests/unit/test_xau_sd_oi_mean_reversion_candidate.py -q`
- [X] T021 Run Feature 018 tests from backend: `python -m pytest tests/unit/test_xau_daily_structural_map.py -q`
- [X] T022 Run Feature 017 tests from backend: `python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q`
- [X] T023 Run field inventory tests from repo root: `python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q`
- [X] T024 Run backend import check from backend: `python -c "from src.main import app; print('backend import ok')"`
- [X] T025 Run ruff on touched Python files
- [X] T026 Confirm no live trading, paper trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell live signal, alert, PnL, or backtest was added

## Dependencies & Execution Order

- Phase 1 setup has no dependencies.
- Phase 2 models block classifier implementation.
- Phase 3 is the MVP candidate slice.
- Phase 4 adds missing-context and breakout-risk guardrails.
- Phase 5 validation depends on implemented phases.

## Implementation Strategy

1. Add strict models.
2. Add focused tests.
3. Implement the pure classifier.
4. Run focused and regression validation.
5. Stop before outcomes, alerts, signals, PnL, or backtests.
