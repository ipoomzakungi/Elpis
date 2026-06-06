# Tasks: CME Expected Range And Context Parity

**Input**: Design documents from `specs/017-cme-expected-range-and-context-parity/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/expected-range-snapshot.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification and are listed before implementation work.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create Speckit artifacts and expected-range model/test placeholders.

- [X] T001 Create Feature 017 specification in `specs/017-cme-expected-range-and-context-parity/spec.md`
- [X] T002 Create Feature 017 implementation plan in `specs/017-cme-expected-range-and-context-parity/plan.md`
- [X] T003 [P] Create Feature 017 research notes in `specs/017-cme-expected-range-and-context-parity/research.md`
- [X] T004 [P] Create Feature 017 data model in `specs/017-cme-expected-range-and-context-parity/data-model.md`
- [X] T005 [P] Create expected-range snapshot contract in `specs/017-cme-expected-range-and-context-parity/contracts/expected-range-snapshot.md`
- [X] T006 [P] Create quickstart validation guide in `specs/017-cme-expected-range-and-context-parity/quickstart.md`
- [X] T007 Create task list in `specs/017-cme-expected-range-and-context-parity/tasks.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared schemas and expected-range parity helper behavior required by all user stories.

- [X] T008 [P] Add expected-range source, extraction-quality, and source-status enums in `backend/src/models/xau.py`
- [X] T009 [P] Add `XauExpectedRangeSnapshot` schema in `backend/src/models/xau.py`
- [X] T010 Extend `XauExpectedRange` with report-level IV, fractional DTE, numeric SD, and 3SD fields in `backend/src/models/xau.py`
- [X] T011 Add optional expected-range snapshot propagation field to fusion reports in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T012 Add optional expected-range snapshot propagation field to XAU Vol-OI reports in `backend/src/models/xau.py`
- [X] T013 Add expected-range parity helper module in `backend/src/xau_quikstrike_fusion/expected_range.py`

**Checkpoint**: Expected-range context can be represented and attached without changing wall scoring.

---

## Phase 3: User Story 1 - Capture Expected Range Context (Priority: P1) MVP

**Goal**: Preserve native CME numeric bands when available, derive fallback bands only from approved report-level inputs, and block range-label-only numeric promotion.

**Independent Test**: Synthetic expected-range inputs produce native, derived, or unavailable snapshots with correct limitations.

### Tests for User Story 1

- [X] T014 [P] [US1] Add CME-native expected-range preservation test in `backend/tests/unit/test_xau_expected_range_context_parity.py`
- [X] T015 [P] [US1] Add IV-derived fallback expected-range test in `backend/tests/unit/test_xau_expected_range_context_parity.py`
- [X] T016 [P] [US1] Add range-label-only unavailable expected-range test in `backend/tests/unit/test_xau_expected_range_context_parity.py`

### Implementation for User Story 1

- [X] T017 [US1] Implement CME-native expected-range detection in `backend/src/xau_quikstrike_fusion/expected_range.py`
- [X] T018 [US1] Implement IV-derived fallback formula and limitation in `backend/src/xau_quikstrike_fusion/expected_range.py`
- [X] T019 [US1] Implement range-label and per-strike-IV limitations in `backend/src/xau_quikstrike_fusion/expected_range.py`
- [X] T020 [US1] Implement conversion from expected-range snapshot to report expected-range shape in `backend/src/xau_quikstrike_fusion/expected_range.py`

**Checkpoint**: Expected-range parity MVP is independently testable.

---

## Phase 4: User Story 2 - Propagate Parity Context (Priority: P2)

**Goal**: Make expected-range context available through report models while preserving missing basis and null Matrix semantics.

**Independent Test**: Synthetic report/model behavior preserves expected-range context, missing basis, and blank cells.

### Tests for User Story 2

- [X] T021 [P] [US2] Add missing-basis preservation test in `backend/tests/unit/test_xau_expected_range_context_parity.py`
- [X] T022 [P] [US2] Add blank Matrix cell null-preservation test in `backend/tests/unit/test_xau_expected_range_context_parity.py`
- [X] T023 [P] [US2] Update inventory integration tests in `research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py`

### Implementation for User Story 2

- [X] T024 [US2] Update systematic engine inventory default fields in `research_xau_vol_oi/systematic_engine_field_inventory.py`
- [X] T025 [US2] Preserve optional expected-range snapshot on fusion report model in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T026 [US2] Preserve optional expected-range snapshot on XAU Vol-OI report model in `backend/src/models/xau.py`

**Checkpoint**: Report models can carry the parity context needed for a future daily structural map.

---

## Phase 5: User Story 3 - Prepare Manual CME Field Discovery (Priority: P3)

**Goal**: Document a narrow safe manual-discovery checklist for future CME/QuikStrike page inspection.

**Independent Test**: Manual checklist names only permitted visible fields and excludes sensitive/session artifacts.

### Tests for User Story 3

- [X] T027 [P] [US3] Document manual CME discovery constraints in `specs/017-cme-expected-range-and-context-parity/quickstart.md`

### Implementation for User Story 3

- [ ] T028 [US3] Inspect an authenticated CME/QuikStrike page and record sanitized visible field locations in a future local artifact when the user provides an available page/session

**Checkpoint**: Manual discovery is scoped but not executed in this session.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, active plan pointer update, and forbidden-scope review.

- [X] T029 Run inventory tests from repository root: `python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q`
- [X] T030 Run expected-range parity tests from backend: `python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q`
- [X] T031 Run backend import check from backend: `python -c "from src.main import app; print('backend import ok')"`
- [ ] T032 Run full backend suite when the dirty worktree is ready for a broader validation checkpoint
- [X] T033 Confirm no live trading, broker integration, private keys, endpoint replay, paid vendor ingestion, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training was added

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on setup and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2 and can validate independently after expected-range schemas exist.
- **Phase 5 US3**: Depends on the documented discovery target; actual page inspection depends on user-provided page/session availability.
- **Phase 6 Polish**: Depends on implemented phases.

### User Story Dependencies

- **US1 (P1)**: Required MVP for expected-range parity.
- **US2 (P2)**: Uses US1 schemas/helpers but preserves report behavior independently.
- **US3 (P3)**: Documentation is complete; manual inspection is deferred until authenticated CME page access is available.

## Implementation Strategy

### MVP First

1. Complete setup and foundational schemas.
2. Implement US1 native/derived/unavailable expected-range behavior.
3. Validate with focused backend tests.
4. Add US2 propagation fields and inventory integration.
5. Stop before any signal or backtest work.

### Notes

- Feature 017 is data-parity work only.
- Feature 018 should build the daily structural map.
- Feature 019 should be the first appropriate place for a forward/historical 2SD research test.
