# Tasks: Public Data Bootstrapper

**Input**: Design documents from `specs/009-public-data-bootstrapper/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Tests are required by the feature plan and quickstart. Automated tests must use mocked Binance/Yahoo responses or synthetic fixtures and must not run real external downloads.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `ID, optional parallel marker, optional story label, description`

- **[P]**: Can run in parallel with other tasks in the same phase because it touches different files or has no dependency on incomplete tasks
- **Story label**: User story label for story phases only
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the focused 009 package and shared model/API placeholders.

- [ ] T001 Create `backend/src/data_bootstrap/__init__.py` for the public bootstrap package
- [ ] T002 Create `backend/src/data_bootstrap/binance_public.py` with public Binance bootstrap module skeleton
- [ ] T003 Create `backend/src/data_bootstrap/yahoo_public.py` with Yahoo OHLCV bootstrap module skeleton
- [ ] T004 Create `backend/src/data_bootstrap/processing.py` with processed feature output module skeleton
- [ ] T005 Create `backend/src/data_bootstrap/orchestration.py` with public bootstrap orchestration skeleton
- [ ] T006 Create `backend/src/data_bootstrap/report_store.py` with ignored report path helper skeleton
- [ ] T007 Create `backend/src/models/data_bootstrap.py` with enum and schema placeholders from `specs/009-public-data-bootstrapper/data-model.md`
- [ ] T008 Extend `backend/src/api/routes/data_sources.py` with bootstrap route placeholders
- [ ] T009 Verify the existing data-source router registration for bootstrap endpoints in `backend/src/main.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared schemas, path safety, report storage, and compatibility scaffolding required before user stories.

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T010 [P] Add data bootstrap model validation tests in `backend/tests/unit/test_data_bootstrap_models.py`
- [ ] T011 [P] Add output path safety tests in `backend/tests/unit/test_data_bootstrap_processing.py`
- [ ] T012 [P] Add report store path and list/read skeleton tests in `backend/tests/unit/test_data_bootstrap_report_store.py`
- [ ] T013 Implement `DataBootstrapProvider`, `DataBootstrapStatus`, `DataBootstrapAssetStatus`, and `DataBootstrapArtifactType` in `backend/src/models/data_bootstrap.py`
- [ ] T014 Implement `PublicDataBootstrapRequest`, `DataBootstrapPlanItem`, `DataBootstrapArtifact`, `DataBootstrapAssetResult`, `PublicDataBootstrapRun`, and list/detail response models in `backend/src/models/data_bootstrap.py`
- [ ] T015 Implement research-only acknowledgement, symbol normalization, timeframe allowlists, and forbidden scope rejection in `backend/src/models/data_bootstrap.py`
- [ ] T016 Implement safe raw, processed, and report output path helpers in `backend/src/data_bootstrap/processing.py`
- [ ] T017 Implement bootstrap report root, run id, summary JSON path, and Markdown path helpers in `backend/src/data_bootstrap/report_store.py`
- [ ] T018 Implement compatibility imports or wrappers from `backend/src/data_sources/bootstrap.py` to `backend/src/data_bootstrap/orchestration.py` if existing 008 code still references the old module
- [ ] T019 Verify generated bootstrap raw, processed, and report paths remain covered by `scripts/check_generated_artifacts.ps1`

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Bootstrap Public Crypto Research Data (Priority: P1) MVP

**Goal**: Start a public/no-key Binance crypto bootstrap that produces per-asset outcomes, raw artifacts, processed feature files, and limitation labels for BTCUSDT, ETHUSDT, SOLUSDT, and optional crypto assets.

**Independent Test**: Request the default crypto bootstrap with mocked public Binance responses and confirm each requested asset has downloaded/skipped/failed status, row counts, date ranges, output paths, and source limitations.

### Tests for User Story 1

- [ ] T020 [P] [US1] Add Binance public request planning tests in `backend/tests/unit/test_data_bootstrap_binance.py`
- [ ] T021 [P] [US1] Add Binance pagination/date-window tests with mocked responses in `backend/tests/unit/test_data_bootstrap_binance.py`
- [ ] T022 [P] [US1] Add Binance limited OI/funding limitation label tests in `backend/tests/unit/test_data_bootstrap_binance.py`
- [ ] T023 [P] [US1] Add Binance processed feature schema tests in `backend/tests/unit/test_data_bootstrap_processing.py`
- [ ] T024 [P] [US1] Add mocked Binance bootstrap integration test in `backend/tests/integration/test_data_bootstrap_flow.py`
- [ ] T025 [P] [US1] Add bootstrap create endpoint contract tests for Binance crypto results in `backend/tests/contract/test_data_sources_api_contracts.py`

### Implementation for User Story 1

- [ ] T026 [US1] Implement Binance public bootstrap request planning in `backend/src/data_bootstrap/binance_public.py`
- [ ] T027 [US1] Implement Binance public OHLCV download adapter using existing public provider/client behavior in `backend/src/data_bootstrap/binance_public.py`
- [ ] T028 [US1] Implement Binance public open-interest download adapter with unavailable and shallow-history handling in `backend/src/data_bootstrap/binance_public.py`
- [ ] T029 [US1] Implement Binance public funding-rate download adapter with unavailable and shallow-history handling in `backend/src/data_bootstrap/binance_public.py`
- [ ] T030 [US1] Implement chronological Binance request window planning for 15m, 1h, and 1d timeframes in `backend/src/data_bootstrap/binance_public.py`
- [ ] T031 [US1] Implement raw Binance OHLCV, open-interest, and funding Parquet writes under ignored `data/raw/binance/` paths in `backend/src/data_bootstrap/processing.py`
- [ ] T032 [US1] Implement Binance normalized feature creation and `{symbol}_{timeframe}_features.parquet` writes under ignored `data/processed/` paths in `backend/src/data_bootstrap/processing.py`
- [ ] T033 [US1] Implement per-crypto asset downloaded/skipped/failed aggregation in `backend/src/data_bootstrap/orchestration.py`
- [ ] T034 [US1] Implement Binance source limitation, unsupported, and missing-data action aggregation in `backend/src/data_bootstrap/orchestration.py`
- [ ] T035 [US1] Persist crypto bootstrap metadata and asset summaries in `backend/src/data_bootstrap/report_store.py`
- [ ] T036 [US1] Wire POST `/api/v1/data-sources/bootstrap/public` for crypto bootstrap requests in `backend/src/api/routes/data_sources.py`

**Checkpoint**: User Story 1 should be independently functional and testable with mocked public Binance responses.

---

## Phase 4: User Story 2 - Bootstrap Yahoo Proxy OHLCV Research Data (Priority: P2)

**Goal**: Bootstrap Yahoo Finance OHLCV proxy assets while clearly labeling unsupported derivatives, IV, gold options OI, futures OI, and XAUUSD execution capabilities.

**Independent Test**: Request SPY, QQQ, GLD, GC=F, and optional BTC-USD with mocked Yahoo responses and verify OHLCV-only outputs plus unsupported capability labels.

### Tests for User Story 2

- [ ] T037 [P] [US2] Add Yahoo request planning tests in `backend/tests/unit/test_data_bootstrap_yahoo.py`
- [ ] T038 [P] [US2] Add Yahoo OHLCV-only unsupported capability label tests in `backend/tests/unit/test_data_bootstrap_yahoo.py`
- [ ] T039 [P] [US2] Add Yahoo empty-row and bad-column failure tests in `backend/tests/unit/test_data_bootstrap_yahoo.py`
- [ ] T040 [P] [US2] Add Yahoo processed feature schema tests in `backend/tests/unit/test_data_bootstrap_processing.py`
- [ ] T041 [P] [US2] Add mocked Yahoo proxy bootstrap integration test in `backend/tests/integration/test_data_bootstrap_flow.py`
- [ ] T042 [P] [US2] Add bootstrap create endpoint contract tests for Yahoo proxy results in `backend/tests/contract/test_data_sources_api_contracts.py`

### Implementation for User Story 2

- [ ] T043 [US2] Implement Yahoo request planning for SPY, QQQ, GLD, GC=F, and optional BTC-USD in `backend/src/data_bootstrap/yahoo_public.py`
- [ ] T044 [US2] Implement Yahoo OHLCV download adapter using existing Yahoo provider behavior in `backend/src/data_bootstrap/yahoo_public.py`
- [ ] T045 [US2] Implement Yahoo OHLCV-only unsupported capability labels in `backend/src/data_bootstrap/yahoo_public.py`
- [ ] T046 [US2] Implement GLD and GC=F gold proxy limitation notes in `backend/src/data_bootstrap/yahoo_public.py`
- [ ] T047 [US2] Implement raw Yahoo OHLCV Parquet writes under ignored `data/raw/yahoo/` paths in `backend/src/data_bootstrap/processing.py`
- [ ] T048 [US2] Implement Yahoo processed feature creation and `{symbol}_{timeframe}_features.parquet` writes under ignored `data/processed/` paths in `backend/src/data_bootstrap/processing.py`
- [ ] T049 [US2] Add Yahoo asset aggregation and failure handling to `backend/src/data_bootstrap/orchestration.py`
- [ ] T050 [US2] Persist Yahoo proxy summaries and limitations in `backend/src/data_bootstrap/report_store.py`

**Checkpoint**: User Stories 1 and 2 should both be independently functional with mocked public providers.

---

## Phase 5: User Story 3 - Review Bootstrap Results And Evidence Readiness (Priority: P3)

**Goal**: Persist and retrieve bootstrap runs, include preflight readiness after generated outputs, and keep XAU options OI as a visible local-import workflow.

**Independent Test**: Review a saved bootstrap report and verify completed, skipped, and failed assets remain visible with output paths, limitations, preflight readiness, and XAU local import instructions.

### Tests for User Story 3

- [ ] T051 [P] [US3] Add report store write/list/read tests in `backend/tests/unit/test_data_bootstrap_report_store.py`
- [ ] T052 [P] [US3] Add preflight readiness transition tests in `backend/tests/integration/test_data_bootstrap_flow.py`
- [ ] T053 [P] [US3] Add XAU local import instruction tests in `backend/tests/unit/test_data_bootstrap_report_store.py`
- [ ] T054 [P] [US3] Add GET `/api/v1/data-sources/bootstrap/runs` contract tests in `backend/tests/contract/test_data_sources_api_contracts.py`
- [ ] T055 [P] [US3] Add GET `/api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}` and missing-run contract tests in `backend/tests/contract/test_data_sources_api_contracts.py`

### Implementation for User Story 3

- [ ] T056 [US3] Implement bootstrap summary JSON and Markdown persistence in `backend/src/data_bootstrap/report_store.py`
- [ ] T057 [US3] Implement bootstrap run list and detail reads in `backend/src/data_bootstrap/report_store.py`
- [ ] T058 [US3] Integrate feature 008 preflight execution after successful generated outputs in `backend/src/data_bootstrap/orchestration.py`
- [ ] T059 [US3] Add XAU local CSV/Parquet missing-data actions and schema instructions to bootstrap run results in `backend/src/data_bootstrap/orchestration.py`
- [ ] T060 [US3] Add report artifacts, downloaded/skipped/failed counts, and readiness summary fields to `backend/src/models/data_bootstrap.py`
- [ ] T061 [US3] Implement GET `/api/v1/data-sources/bootstrap/runs` in `backend/src/api/routes/data_sources.py`
- [ ] T062 [US3] Implement GET `/api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}` and structured not-found errors in `backend/src/api/routes/data_sources.py`

**Checkpoint**: User Stories 1 through 3 should provide a complete backend bootstrap and report review workflow.

---

## Phase 6: User Story 4 - Start Bootstrap From The Dashboard (Priority: P4)

**Goal**: Let a researcher start or inspect public bootstrap runs from the Data Sources dashboard while preserving source limitations, no-secret display, and research-only disclaimers.

**Independent Test**: Open `/data-sources`, start or inspect a public bootstrap run, and confirm status, downloaded assets, output paths, limitations, XAU local import requirements, and research-only copy render.

### Tests for User Story 4

- [ ] T063 [P] [US4] Add frontend type coverage for bootstrap responses in `frontend/src/types/index.ts`
- [ ] T064 [P] [US4] Add API client compile coverage for bootstrap methods in `frontend/src/services/api.ts`

### Implementation for User Story 4

- [ ] T065 [US4] Add data bootstrap response and request types in `frontend/src/types/index.ts`
- [ ] T066 [US4] Add `runPublicDataBootstrap`, `listPublicDataBootstrapRuns`, and `getPublicDataBootstrapRun` client methods in `frontend/src/services/api.ts`
- [ ] T067 [US4] Render public bootstrap controls and research-only copy in `frontend/src/app/data-sources/page.tsx`
- [ ] T068 [US4] Render bootstrap run selector or latest-run status in `frontend/src/app/data-sources/page.tsx`
- [ ] T069 [US4] Render downloaded, skipped, and failed asset tables in `frontend/src/app/data-sources/page.tsx`
- [ ] T070 [US4] Render raw/processed output paths, source limitation notes, and unsupported capability labels in `frontend/src/app/data-sources/page.tsx`
- [ ] T071 [US4] Render XAU local import requirements and next missing-data actions in `frontend/src/app/data-sources/page.tsx`
- [ ] T072 [US4] Render first evidence readiness/preflight summary from the bootstrap result in `frontend/src/app/data-sources/page.tsx`

**Checkpoint**: All user stories should be independently functional and visible through backend API and dashboard.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, artifact guard, and forbidden-scope review.

- [ ] T073 [P] Update public bootstrap quickstart notes if implementation endpoint behavior changes in `specs/009-public-data-bootstrapper/quickstart.md`
- [ ] T074 Run backend import check from `backend/src/main.py`
- [ ] T075 Run focused backend tests from `backend/tests/unit/test_data_bootstrap_binance.py`, `backend/tests/unit/test_data_bootstrap_yahoo.py`, `backend/tests/unit/test_data_bootstrap_processing.py`, `backend/tests/integration/test_data_bootstrap_flow.py`, and `backend/tests/contract/test_data_sources_api_contracts.py`
- [ ] T076 Run full backend pytest suite from `backend/tests/`
- [ ] T077 Run frontend production build from `frontend/package.json`
- [ ] T078 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [ ] T079 Run Ruff checks for `backend/src/data_bootstrap`, `backend/src/models/data_bootstrap.py`, `backend/src/api/routes/data_sources.py`, and new 009 tests
- [ ] T080 Run API smoke flow documented in `specs/009-public-data-bootstrapper/quickstart.md` without committing generated data
- [ ] T081 Run dashboard smoke flow for `/data-sources` documented in `specs/009-public-data-bootstrapper/quickstart.md`
- [ ] T082 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T083 Update final validation notes and task completion status in `specs/009-public-data-bootstrapper/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2; can be implemented after or in parallel with US1 once shared processing contracts are stable.
- **Phase 5 US3**: Depends on US1 and US2 result shapes because it persists and retrieves combined run reports.
- **Phase 6 US4**: Depends on US3 API/list/detail behavior.
- **Phase 7 Polish**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: First MVP. Delivers crypto public bootstrap and processed feature readiness.
- **US2 (P2)**: Can start after foundation; independent provider path but shares processing/output helpers with US1.
- **US3 (P3)**: Requires US1/US2 asset result models and report persistence.
- **US4 (P4)**: Requires backend endpoints and response shapes from US3.

### Within Each User Story

- Tests first and expected to fail before implementation.
- Models before processing/service code.
- Provider adapters before orchestration.
- Orchestration before API route behavior.
- API behavior before frontend rendering.
- Each checkpoint should pass focused tests before moving to the next story.

### Parallel Opportunities

- T001-T009 can be split by file after package naming is agreed.
- T010-T012 can run in parallel.
- T020-T025 can run in parallel before US1 implementation.
- T037-T042 can run in parallel before US2 implementation.
- T051-T055 can run in parallel before US3 implementation.
- T063-T064 can run in parallel before US4 implementation.
- T073 and T082 can run in parallel with final validation once behavior is stable.

## Parallel Example: User Story 1

```text
Task: "T020 Add Binance public request planning tests in backend/tests/unit/test_data_bootstrap_binance.py"
Task: "T021 Add Binance pagination/date-window tests with mocked responses in backend/tests/unit/test_data_bootstrap_binance.py"
Task: "T022 Add Binance limited OI/funding limitation label tests in backend/tests/unit/test_data_bootstrap_binance.py"
Task: "T023 Add Binance processed feature schema tests in backend/tests/unit/test_data_bootstrap_processing.py"
Task: "T024 Add mocked Binance bootstrap integration test in backend/tests/integration/test_data_bootstrap_flow.py"
Task: "T025 Add bootstrap create endpoint contract tests for Binance crypto results in backend/tests/contract/test_data_sources_api_contracts.py"
```

## Parallel Example: User Story 2

```text
Task: "T037 Add Yahoo request planning tests in backend/tests/unit/test_data_bootstrap_yahoo.py"
Task: "T038 Add Yahoo OHLCV-only unsupported capability label tests in backend/tests/unit/test_data_bootstrap_yahoo.py"
Task: "T039 Add Yahoo empty-row and bad-column failure tests in backend/tests/unit/test_data_bootstrap_yahoo.py"
Task: "T040 Add Yahoo processed feature schema tests in backend/tests/unit/test_data_bootstrap_processing.py"
Task: "T041 Add mocked Yahoo proxy bootstrap integration test in backend/tests/integration/test_data_bootstrap_flow.py"
Task: "T042 Add bootstrap create endpoint contract tests for Yahoo proxy results in backend/tests/contract/test_data_sources_api_contracts.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1 for Binance public crypto bootstrap.
4. Stop and validate focused Binance unit, integration, and contract tests.
5. Confirm generated data paths remain ignored and untracked.

### Incremental Delivery

1. Add US1 crypto public bootstrap.
2. Add US2 Yahoo OHLCV proxy bootstrap.
3. Add US3 report/list/detail and preflight readiness review.
4. Add US4 dashboard controls and run review.
5. Finish Phase 7 validation and forbidden-scope review.

### Testing Strategy

1. Write focused tests before implementation for each story.
2. Use mocked public provider responses and synthetic fixtures only in automated tests.
3. Do not run real external downloads in CI.
4. Run full backend tests, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope review before final completion.

## Notes

- [P] tasks are parallelizable when they touch different files or can be completed before dependent implementation.
- Generated `data/raw`, `data/processed`, and `data/reports` artifacts must not be staged.
- No task may introduce live trading, paper trading, shadow trading, private trading keys, broker integration, wallet/private-key handling, order execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
