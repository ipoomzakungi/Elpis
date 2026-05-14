# Tasks: XAU Forward Research Journal

**Input**: Design documents from `specs/015-xau-forward-research-journal/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification. Test tasks are listed before implementation tasks in each story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the 015 package, schema, route, frontend, fixture, and artifact guard skeletons without implementing journal behavior.

- [X] T001 Create backend package marker in `backend/src/xau_forward_journal/__init__.py`
- [X] T002 Create schema module placeholder in `backend/src/models/xau_forward_journal.py`
- [ ] T003 [P] Create journal entry builder module placeholder in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T004 [P] Create outcome module placeholder in `backend/src/xau_forward_journal/outcome.py`
- [ ] T005 [P] Create orchestration module placeholder in `backend/src/xau_forward_journal/orchestration.py`
- [X] T006 [P] Create report-store module placeholder in `backend/src/xau_forward_journal/report_store.py`
- [ ] T007 Create local API route placeholder in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T008 Register the forward journal router with the v0 API prefix in `backend/src/main.py`
- [ ] T009 [P] Add XAU forward journal frontend type placeholders in `frontend/src/types/index.ts`
- [ ] T010 [P] Add XAU forward journal API client placeholders in `frontend/src/services/api.ts`
- [ ] T011 Add placeholder Forward Journal panel section in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T012 Create synthetic forward journal fixture folder marker in `backend/tests/fixtures/xau_forward_journal/.gitkeep`
- [X] T013 Add `backend/data/reports/xau_forward_journal/` and `data/reports/xau_forward_journal/` generated artifact coverage in `.gitignore`
- [X] T014 Add forward journal artifact guard denied paths in `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared schemas, validation helpers, path safety, report-store helpers, and route skeleton behavior required by all user stories.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [X] T015 [P] Add schema validation tests for journal enums, ids, request validation, and forbidden secret/session fields in `backend/tests/unit/test_xau_forward_journal_models.py`
- [X] T016 [P] Add report-store path safety tests for journal report roots and artifact paths in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [ ] T017 [P] Add API route registration smoke tests in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [ ] T018 [P] Add shared synthetic source report fixture helpers in `backend/tests/helpers/test_xau_forward_journal_data.py`
- [X] T019 Implement `XauForwardJournalSourceType`, `XauForwardJournalEntryStatus`, `XauForwardOutcomeWindow`, `XauForwardOutcomeLabel`, `XauForwardOutcomeStatus`, and `XauForwardArtifactType` in `backend/src/models/xau_forward_journal.py`
- [X] T020 Implement `XauForwardJournalCreateRequest`, `XauForwardOutcomeUpdateRequest`, and `XauForwardSourceReportRef` in `backend/src/models/xau_forward_journal.py`
- [X] T021 Implement `XauForwardSnapshotContext`, `XauForwardWallSummary`, `XauForwardReactionSummary`, and `XauForwardMissingContextItem` in `backend/src/models/xau_forward_journal.py`
- [X] T022 Implement `XauForwardOutcomeObservation`, `XauForwardJournalEntry`, `XauForwardJournalSummary`, `XauForwardJournalListResponse`, and `XauForwardOutcomeResponse` in `backend/src/models/xau_forward_journal.py`
- [X] T023 Implement safe id, forbidden field, note text, and research-only acknowledgement validation helpers in `backend/src/models/xau_forward_journal.py`
- [X] T024 Implement path-safe journal report root and artifact path helpers in `backend/src/xau_forward_journal/report_store.py`
- [X] T025 Implement journal artifact metadata helper and JSON serialization helpers in `backend/src/xau_forward_journal/report_store.py`
- [ ] T026 Implement route skeleton responses and structured placeholder errors in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T027 Verify frontend placeholder types and API client exports compile in `frontend/src/types/index.ts` and `frontend/src/services/api.ts`
- [ ] T028 Verify generated artifact path coverage for journal paths using `scripts/check_generated_artifacts.ps1`

**Checkpoint**: Foundation ready. User stories can be implemented after T001-T028.

---

## Phase 3: User Story 1 - Record A Research Snapshot (Priority: P1) MVP

**Goal**: Create an immutable forward journal entry from existing local report ids with source provenance, snapshot context, top wall summaries, reaction summaries, NO_TRADE reasons, missing context, pending outcomes, and research-only limitations.

**Independent Test**: Create one journal entry from synthetic source report identifiers and verify source references, snapshot metadata, walls, reactions, NO_TRADE reasons, missing context, pending outcomes, artifacts, and research-only limitations without outcome candles.

### Tests for User Story 1

- [ ] T029 [P] [US1] Add source report loading tests for Vol2Vol, Matrix, Fusion, XAU Vol-OI, and XAU Reaction refs in `backend/tests/unit/test_xau_forward_journal_entry_builder.py`
- [ ] T030 [P] [US1] Add source compatibility tests for Gold/OG/GC, missing reports, incompatible products, and partial source warnings in `backend/tests/unit/test_xau_forward_journal_entry_builder.py`
- [ ] T031 [P] [US1] Add snapshot context tests for optional spot, futures, basis, session open, event flag, and missing context in `backend/tests/unit/test_xau_forward_journal_entry_builder.py`
- [ ] T032 [P] [US1] Add top wall summary tests for OI, OI Change, and Volume ranks in `backend/tests/unit/test_xau_forward_journal_entry_builder.py`
- [ ] T033 [P] [US1] Add reaction summary tests for labels, NO_TRADE reasons, bounded risk annotation counts, and limitations in `backend/tests/unit/test_xau_forward_journal_entry_builder.py`
- [ ] T034 [P] [US1] Add journal entry persistence tests for metadata, entry JSON, outcomes JSON, report JSON, Markdown, and artifact refs in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [ ] T035 [P] [US1] Add create-entry integration test using synthetic source report ids in `backend/tests/integration/test_xau_forward_journal_flow.py`
- [ ] T036 [P] [US1] Add create-entry API contract tests for valid, missing source report, incompatible source report, and invalid request cases in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`

### Implementation for User Story 1

- [ ] T037 [US1] Implement source report ref loading from existing local report outputs in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T038 [US1] Implement source compatibility validation for product, expiration context, capture session, status, warnings, and limitations in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T039 [US1] Implement snapshot context derivation and unavailable optional input handling in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T040 [US1] Implement top OI, OI Change, and Volume wall summary selection in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T041 [US1] Implement reaction label, NO_TRADE reason, bounded risk annotation, and missing-context summary extraction in `backend/src/xau_forward_journal/entry_builder.py`
- [ ] T042 [US1] Implement default pending outcome windows for 30m, 1h, 4h, session close, and next day in `backend/src/xau_forward_journal/outcome.py`
- [ ] T043 [US1] Implement create-entry orchestration that assembles a journal entry and preserves immutable snapshot data in `backend/src/xau_forward_journal/orchestration.py`
- [ ] T044 [US1] Implement metadata, entry JSON, outcomes JSON, report JSON, and Markdown persistence for created entries in `backend/src/xau_forward_journal/report_store.py`
- [ ] T045 [US1] Implement `POST /api/v1/xau/forward-journal/entries` in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T046 [US1] Implement structured create-entry API errors for validation, source not found, incompatible sources, blocked entry, and forbidden field requests in `backend/src/api/routes/xau_forward_journal.py`

**Checkpoint**: US1 delivers a testable MVP journal entry from saved source reports.

---

## Phase 4: User Story 2 - Add Later Outcome Labels (Priority: P2)

**Goal**: Update a saved journal entry with later price outcome windows while preserving the original snapshot and keeping missing or insufficient outcome data pending or inconclusive.

**Independent Test**: Update an existing synthetic journal entry with one or more outcome windows and verify status, price context, labels, notes, conflict handling, persistence, and immutable snapshot behavior.

### Tests for User Story 2

- [ ] T047 [P] [US2] Add outcome window validation tests for supported windows, timestamps, OHLC consistency, and missing data in `backend/tests/unit/test_xau_forward_journal_outcome.py`
- [ ] T048 [P] [US2] Add outcome label rule tests for pending, inconclusive, wall_held, wall_rejected, wall_accepted_break, moved_to_next_wall, reversed_before_target, stayed_inside_range, and no_trade_was_correct in `backend/tests/unit/test_xau_forward_journal_outcome.py`
- [ ] T049 [P] [US2] Add no-fabricated-candle regression tests for missing and partial OHLC observations in `backend/tests/unit/test_xau_forward_journal_outcome.py`
- [ ] T050 [P] [US2] Add outcome conflict update tests requiring an update note for changing non-pending labels in `backend/tests/unit/test_xau_forward_journal_outcome.py`
- [ ] T051 [P] [US2] Add outcome persistence read/write tests in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [ ] T052 [P] [US2] Add outcome update integration test proving snapshot fields remain immutable in `backend/tests/integration/test_xau_forward_journal_flow.py`
- [ ] T053 [P] [US2] Add outcome API contract tests for update, get outcomes, invalid window, missing entry, and conflict cases in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`

### Implementation for User Story 2

- [ ] T054 [US2] Implement OHLC observation validation and supported outcome window checks in `backend/src/xau_forward_journal/outcome.py`
- [ ] T055 [US2] Implement conservative outcome label status rules for pending, inconclusive, and completed labels in `backend/src/xau_forward_journal/outcome.py`
- [ ] T056 [US2] Implement conflict detection for non-pending label updates and required update notes in `backend/src/xau_forward_journal/outcome.py`
- [ ] T057 [US2] Implement outcome update application without mutating original snapshot fields in `backend/src/xau_forward_journal/outcome.py`
- [ ] T058 [US2] Implement persisted outcome update reads and writes in `backend/src/xau_forward_journal/report_store.py`
- [ ] T059 [US2] Integrate outcome updates into journal orchestration in `backend/src/xau_forward_journal/orchestration.py`
- [ ] T060 [US2] Implement `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes` in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T061 [US2] Implement `GET /api/v1/xau/forward-journal/entries/{journal_id}/outcomes` in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T062 [US2] Implement structured outcome API errors for not found, invalid outcome update, conflict, forbidden field, and unsafe notes in `backend/src/api/routes/xau_forward_journal.py`

**Checkpoint**: US2 allows forward outcome labels to be attached without rewriting snapshot evidence.

---

## Phase 5: User Story 3 - Inspect Forward Evidence (Priority: P3)

**Goal**: Expose saved journal entries through local API endpoints and a compact `/xau-vol-oi` Forward Journal dashboard panel.

**Independent Test**: List saved entries and open one detail view to inspect source report ids, snapshot context, top walls, reactions, NO_TRADE reasons, missing context, outcome labels, notes, artifact paths, and research-only disclaimer.

### Tests for User Story 3

- [ ] T063 [P] [US3] Add list and detail API contract tests for saved journal entries in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [ ] T064 [P] [US3] Add missing journal entry API contract tests in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [ ] T065 [P] [US3] Add report-store list and detail read tests in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [ ] T066 [P] [US3] Add frontend type and API client compile coverage via `frontend/src/types/index.ts` and `frontend/src/services/api.ts`
- [ ] T067 [P] [US3] Add dashboard data-shape regression coverage for Forward Journal fields in `frontend/src/app/xau-vol-oi/page.tsx`

### Implementation for User Story 3

- [ ] T068 [US3] Implement saved journal list and detail reads in `backend/src/xau_forward_journal/report_store.py`
- [ ] T069 [US3] Implement `GET /api/v1/xau/forward-journal/entries` in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T070 [US3] Implement `GET /api/v1/xau/forward-journal/entries/{journal_id}` in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T071 [US3] Implement structured list/detail API errors for missing entries and invalid ids in `backend/src/api/routes/xau_forward_journal.py`
- [ ] T072 [US3] Implement XAU forward journal request, summary, detail, outcome, wall, reaction, and missing-context frontend types in `frontend/src/types/index.ts`
- [ ] T073 [US3] Implement `createXauForwardJournalEntry`, `listXauForwardJournalEntries`, `getXauForwardJournalEntry`, `updateXauForwardJournalOutcomes`, and `getXauForwardJournalOutcomes` in `frontend/src/services/api.ts`
- [ ] T074 [US3] Load forward journal entries, selected detail, and selected outcomes for `/xau-vol-oi` in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T075 [US3] Render Forward Journal entry selector, snapshot time, capture session, source report ids, status, and artifact paths in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T076 [US3] Render top walls, reaction labels, NO_TRADE reasons, missing context checklist, and bounded risk annotation counts in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T077 [US3] Render outcome-window status, labels, notes, pending state, local-only text, and research-only disclaimer in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T078 [US3] Render loading, empty, and error states for the Forward Journal section in `frontend/src/app/xau-vol-oi/page.tsx`

**Checkpoint**: US3 makes forward evidence visible through local API and dashboard inspection.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation alignment, artifact safety, API/dashboard smoke, and forbidden-scope review.

- [ ] T079 Update `specs/015-xau-forward-research-journal/quickstart.md` if implemented API request or response examples changed
- [ ] T080 Run backend import check from `backend/src/main.py`
- [ ] T081 Run focused unit tests for `backend/tests/unit/test_xau_forward_journal_*.py`
- [ ] T082 Run focused integration tests for `backend/tests/integration/test_xau_forward_journal_*.py`
- [ ] T083 Run focused API contract tests for `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [ ] T084 Run the full backend test suite from `backend/tests/`
- [ ] T085 Run frontend dependency install and production build from `frontend/package.json`
- [ ] T086 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [ ] T087 Run the API smoke flow documented in `specs/015-xau-forward-research-journal/quickstart.md` without committing generated journal reports
- [ ] T088 Run the dashboard smoke flow for `/xau-vol-oi` documented in `specs/015-xau-forward-research-journal/quickstart.md`
- [ ] T089 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T090 Confirm generated journal artifacts remain ignored and untracked using repository root `git status --ignored --short`
- [ ] T091 Update final validation notes and task completion status in `specs/015-xau-forward-research-journal/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 3 because outcome updates require an existing journal entry.
- **Phase 5 US3**: Depends on Phases 3-4 for complete API/dashboard payloads.
- **Phase 6 Polish**: Depends on all implemented phases.

### User Story Dependencies

- **US1 (P1)**: Required MVP. No dependency on later stories.
- **US2 (P2)**: Requires a saved journal entry from US1.
- **US3 (P3)**: Requires saved journal entries and outcomes from US1-US2.

### Parallel Opportunities

- T003-T006 can run in parallel after T001-T002.
- T009-T010 can run in parallel with backend placeholders after route shape is known.
- T015-T018 can run in parallel before schema/helper implementation.
- T029-T036 can run in parallel because they target distinct US1 test concerns.
- T047-T053 can run in parallel because they target distinct US2 validation, persistence, integration, and contract concerns.
- T063-T067 can run in parallel after report-store and API payload shapes exist.
- Frontend tasks T072-T078 should be coordinated because they touch shared frontend files.

---

## Parallel Example: User Story 1

```text
Task: "Add source report loading tests for Vol2Vol, Matrix, Fusion, XAU Vol-OI, and XAU Reaction refs in backend/tests/unit/test_xau_forward_journal_entry_builder.py"
Task: "Add snapshot context tests for optional spot, futures, basis, session open, event flag, and missing context in backend/tests/unit/test_xau_forward_journal_entry_builder.py"
Task: "Add top wall summary tests for OI, OI Change, and Volume ranks in backend/tests/unit/test_xau_forward_journal_entry_builder.py"
Task: "Add create-entry API contract tests for valid, missing source report, incompatible source report, and invalid request cases in backend/tests/contract/test_xau_forward_journal_api_contracts.py"
```

## Parallel Example: User Story 2

```text
Task: "Add outcome window validation tests for supported windows, timestamps, OHLC consistency, and missing data in backend/tests/unit/test_xau_forward_journal_outcome.py"
Task: "Add no-fabricated-candle regression tests for missing and partial OHLC observations in backend/tests/unit/test_xau_forward_journal_outcome.py"
Task: "Add outcome conflict update tests requiring an update note for changing non-pending labels in backend/tests/unit/test_xau_forward_journal_outcome.py"
Task: "Add outcome API contract tests for update, get outcomes, invalid window, missing entry, and conflict cases in backend/tests/contract/test_xau_forward_journal_api_contracts.py"
```

## Parallel Example: User Story 3

```text
Task: "Add list and detail API contract tests for saved journal entries in backend/tests/contract/test_xau_forward_journal_api_contracts.py"
Task: "Add report-store list and detail read tests in backend/tests/unit/test_xau_forward_journal_report_store.py"
Task: "Add frontend type and API client compile coverage via frontend/src/types/index.ts and frontend/src/services/api.ts"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1.
4. Validate with focused model, entry-builder, report-store, integration, and create-entry API tests.
5. Stop and review journal source references, snapshot immutability, top walls, reaction summaries, missing context, pending outcomes, and research-only limitations.

### Incremental Delivery

1. Setup + foundation create the package, schemas, route skeleton, report-store safety, and fixtures.
2. US1 adds source report loading, immutable journal entry creation, summary extraction, and create API.
3. US2 adds outcome-window validation, conservative labels, conflict handling, and update/get outcome API.
4. US3 adds list/detail API and dashboard inspection.
5. Polish validates the full workflow, frontend, artifact guard, and forbidden scope.

### Validation Commands

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_forward_journal_*.py -v
python -m pytest tests/integration/test_xau_forward_journal_*.py -v
python -m pytest tests/contract/test_xau_forward_journal_api_contracts.py -v
python -m pytest tests/ -q

cd ../frontend
npm install
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## Notes

- Do not implement new QuikStrike extraction menus in this feature.
- Do not store cookies, tokens, headers, HAR files, screenshots, viewstate, private URLs, credentials, or endpoint replay payloads.
- Do not add live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet/private-key handling, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- Do not fabricate spot, futures, basis, session open, event, candle, volatility, or outcome data.
- Do not claim profitability, predictive power, safety, or live readiness.
- Keep generated journal, QuikStrike, XAU, fusion, reaction, and evidence artifacts ignored and untracked.
