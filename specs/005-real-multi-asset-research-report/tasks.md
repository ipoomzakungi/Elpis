# Tasks: Real Multi-Asset Research Report

**Input**: Design documents from `specs/005-real-multi-asset-research-report/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included because the plan explicitly requires unit, integration, contract, frontend build, backend regression, and artifact-guard validation.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested as an independent research increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other marked tasks in the same phase because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: Maps the task to a specific user story from spec.md.
- Every task includes an exact file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the minimal research package, test fixture locations, and frontend route shell needed by later phases.

- [X] T001 Create research package directory and `backend/src/research/__init__.py`
- [X] T002 [P] Create frontend research route directory and placeholder `frontend/src/app/research/page.tsx`
- [X] T003 [P] Create shared research test fixture helpers in `backend/tests/helpers/research_data.py`
- [X] T004 [P] Create research test package marker in `backend/tests/helpers/__init__.py`
- [X] T005 Review generated artifact paths for research reports in `scripts/check_generated_artifacts.ps1`

**Checkpoint**: Research package and fixture locations exist; no runtime behavior is changed yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared schemas, route/store skeletons, and aggregation contracts that all user stories depend on.

**Critical**: No user story implementation should begin until this phase is complete.

- [X] T006 Add research request, asset config, capability, preflight, result, and summary schemas in `backend/src/models/research.py`
- [X] T007 Add research report artifact enum values or mapping support in `backend/src/models/backtest.py`
- [X] T008 Create grouped research report store skeleton in `backend/src/research/report_store.py`
- [X] T009 Create preflight module skeleton in `backend/src/research/preflight.py`
- [X] T010 Create aggregation module skeleton in `backend/src/research/aggregation.py`
- [X] T011 Create orchestration service skeleton in `backend/src/research/orchestration.py`
- [X] T012 Add research-specific API validation helpers in `backend/src/api/validation.py`
- [X] T013 Create research API route skeleton in `backend/src/api/routes/research.py`
- [X] T014 Register research routes in `backend/src/main.py`
- [X] T015 Add grouped research report JSON/Markdown writer entry points in `backend/src/reports/writer.py`
- [X] T016 Add frontend research response and table types in `frontend/src/types/index.ts`
- [X] T017 Add research API client method placeholders in `frontend/src/services/api.ts`

**Checkpoint**: Shared schemas and route/store skeletons are ready for story implementation.

---

## Phase 3: User Story 1 - Run Real Multi-Asset Research (Priority: P1)

**Goal**: A researcher can run a grouped report where available assets complete and missing assets return actionable instructions without synthetic fallback.

**Independent Test**: Start a multi-asset run with one processed crypto-like feature file and one missing asset; verify the completed asset is persisted, the missing asset is blocked with instructions, and the grouped report can be listed/read.

### Tests for User Story 1

- [X] T018 [P] [US1] Add research config validation tests in `backend/tests/unit/test_research_config.py`
- [X] T019 [P] [US1] Add missing-data preflight tests in `backend/tests/unit/test_research_preflight.py`
- [X] T020 [P] [US1] Add research run/list/detail API contract tests in `backend/tests/contract/test_research_api_contracts.py`
- [X] T021 [P] [US1] Add mixed available/missing asset integration test in `backend/tests/integration/test_research_multi_asset_flow.py`

### Implementation for User Story 1

- [X] T022 [US1] Implement normalized research config validation and forbidden field rejection in `backend/src/models/research.py`
- [X] T023 [US1] Implement processed feature path resolution and path safety in `backend/src/research/preflight.py`
- [X] T024 [US1] Implement missing-data and unreadable-file preflight statuses in `backend/src/research/preflight.py`
- [X] T025 [US1] Implement missing-data instruction generation in `backend/src/research/preflight.py`
- [X] T026 [US1] Implement grouped research run id creation and request normalization in `backend/src/research/orchestration.py`
- [X] T027 [US1] Implement orchestration for ready assets and blocked assets in `backend/src/research/orchestration.py`
- [X] T028 [US1] Persist research metadata, config, and asset summary artifacts in `backend/src/research/report_store.py`
- [X] T029 [US1] Implement grouped research report JSON and Markdown output for run status and blocked assets in `backend/src/reports/writer.py`
- [X] T030 [US1] Implement run, list, and detail endpoints in `backend/src/api/routes/research.py`
- [X] T031 [US1] Add research list/detail API client methods in `frontend/src/services/api.ts`

**Checkpoint**: US1 is independently usable as an MVP grouped research run with completed and blocked asset rows.

---

## Phase 4: User Story 2 - Compare Regime Strategies With Baselines (Priority: P2)

**Goal**: A researcher can compare regime-aware strategies with price-only baselines per asset while separating crypto OI/funding research from Yahoo OHLCV-only research.

**Independent Test**: Run one crypto-like asset and one Yahoo OHLCV-only asset; verify strategy/baseline comparison rows exist and OI/funding support is labeled correctly.

### Tests for User Story 2

- [X] T032 [P] [US2] Add Binance, Yahoo, and local-file capability tests in `backend/tests/unit/test_research_capabilities.py`
- [X] T033 [P] [US2] Add Yahoo OHLCV-only integration test in `backend/tests/integration/test_research_yahoo_flow.py`
- [X] T034 [P] [US2] Add comparison endpoint contract tests in `backend/tests/contract/test_research_api_contracts.py`

### Implementation for User Story 2

- [X] T035 [US2] Implement provider capability snapshot generation in `backend/src/research/preflight.py`
- [X] T036 [US2] Implement processed feature column capability detection in `backend/src/research/preflight.py`
- [X] T037 [US2] Implement unsupported OI/funding labeling for Yahoo and proxy assets in `backend/src/research/preflight.py`
- [X] T038 [US2] Implement gold proxy limitation notes for GC=F and GLD in `backend/src/research/preflight.py`
- [X] T039 [US2] Build per-asset backtest and validation requests from research config in `backend/src/research/orchestration.py`
- [X] T040 [US2] Aggregate per-strategy and per-baseline comparison rows in `backend/src/research/aggregation.py`
- [X] T041 [US2] Persist `strategy_comparison.parquet` in `backend/src/research/report_store.py`
- [X] T042 [US2] Add comparison section to grouped JSON and Markdown reports in `backend/src/reports/writer.py`
- [X] T043 [US2] Implement comparison endpoint in `backend/src/api/routes/research.py`

**Checkpoint**: US2 supports source-aware strategy-vs-baseline comparison without confusing crypto OI/funding research with OHLCV-only proxies.

---

## Phase 5: User Story 3 - Review Robustness Across Assets (Priority: P3)

**Goal**: A researcher can review stress survival, parameter sensitivity, walk-forward stability, regime coverage, concentration warnings, and evidence-based classifications by asset.

**Independent Test**: Open or fetch a grouped report for completed assets and verify each completed asset has validation summaries and an evidence-based classification.

### Tests for User Story 3

- [X] T044 [P] [US3] Add aggregation classification tests in `backend/tests/unit/test_research_aggregation.py`
- [X] T045 [P] [US3] Add validation summary aggregation tests in `backend/tests/unit/test_research_validation_summary.py`
- [X] T046 [P] [US3] Add validation section endpoint contract tests in `backend/tests/contract/test_research_api_contracts.py`
- [X] T047 [P] [US3] Add crypto-like validation aggregation integration test in `backend/tests/integration/test_research_crypto_flow.py`

### Implementation for User Story 3

- [X] T048 [US3] Aggregate stress survival rows by asset in `backend/src/research/aggregation.py`
- [X] T049 [US3] Aggregate parameter sensitivity fragility by asset in `backend/src/research/aggregation.py`
- [X] T050 [US3] Aggregate walk-forward stability by asset in `backend/src/research/aggregation.py`
- [X] T051 [US3] Aggregate regime coverage rows by asset in `backend/src/research/aggregation.py`
- [X] T052 [US3] Aggregate trade concentration warnings by asset in `backend/src/research/aggregation.py`
- [X] T053 [US3] Implement robust, fragile, missing-data, inconclusive, and not-worth-continuing classification rules in `backend/src/research/aggregation.py`
- [X] T054 [US3] Persist stress, walk-forward, regime, and concentration summary artifacts in `backend/src/research/report_store.py`
- [X] T055 [US3] Add validation aggregation sections to grouped JSON and Markdown reports in `backend/src/reports/writer.py`
- [X] T056 [US3] Implement validation aggregation endpoint in `backend/src/api/routes/research.py`

**Checkpoint**: US3 provides cross-asset robustness evidence and classifications without profitability or live-readiness claims.

---

## Phase 6: User Story 4 - Inspect a Grouped Research Report (Priority: P4)

**Goal**: A researcher can inspect grouped research reports in the dashboard with asset summary, capability badges, warnings, comparisons, validation summaries, limitations, and disclaimers.

**Independent Test**: Start the dashboard, open `/research`, select a grouped report, and verify all required grouped report sections render.

### Tests for User Story 4

- [X] T057 [P] [US4] Add frontend research type coverage through production build expectations in `frontend/src/types/index.ts`
- [X] T058 [P] [US4] Add dashboard smoke checklist notes in `specs/005-real-multi-asset-research-report/quickstart.md`

### Implementation for User Story 4

- [X] T059 [US4] Add full research API client methods in `frontend/src/services/api.ts`
- [X] T060 [US4] Implement `/research` run selector and status summary in `frontend/src/app/research/page.tsx`
- [X] T061 [US4] Render asset summary table and capability badges in `frontend/src/app/research/page.tsx`
- [X] T062 [US4] Render missing-data warning panel and source limitation notes in `frontend/src/app/research/page.tsx`
- [X] T063 [US4] Render strategy-vs-baseline comparison table in `frontend/src/app/research/page.tsx`
- [X] T064 [US4] Render stress survival and walk-forward stability tables in `frontend/src/app/research/page.tsx`
- [X] T065 [US4] Render regime coverage and concentration warning tables in `frontend/src/app/research/page.tsx`
- [X] T066 [US4] Render research-only disclaimer in `frontend/src/app/research/page.tsx`
- [X] T067 [US4] Add navigation link to research reports in `frontend/src/components/ui/Header.tsx`

**Checkpoint**: US4 provides a focused dashboard inspection view without redesigning the app.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, compatibility checks, guardrail review, and documentation alignment.

- [ ] T068 Run backend import check from `backend/src/main.py`
- [ ] T069 Run full backend pytest suite for `backend/tests/`
- [ ] T070 Run frontend install and production build using `frontend/package.json`
- [ ] T071 Run generated artifact guard using `scripts/check_generated_artifacts.ps1`
- [ ] T072 Run research API smoke flow from `specs/005-real-multi-asset-research-report/quickstart.md`
- [ ] T073 Run dashboard smoke flow for `/research` from `specs/005-real-multi-asset-research-report/quickstart.md`
- [ ] T074 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T075 Update final validation notes in `specs/005-real-multi-asset-research-report/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on US1 because it enriches completed asset results with comparison/capability detail.
- **User Story 3 (Phase 5)**: Depends on US1 and benefits from US2 comparison rows.
- **User Story 4 (Phase 6)**: Depends on API and aggregation outputs from US1-US3.
- **Polish (Phase 7)**: Depends on completed desired user stories.

### User Story Dependencies

- **US1**: Required first vertical slice; validates real processed feature preflight and grouped persistence.
- **US2**: Adds strategy/baseline comparison and source capability correctness.
- **US3**: Adds validation hardening aggregation and classifications.
- **US4**: Adds dashboard inspection after backend contracts exist.

### Within Each User Story

- Tests should be added before implementation tasks.
- Models and schemas before services.
- Preflight and orchestration before endpoint behavior.
- Store/writer behavior before dashboard consumption.
- Story checkpoint should pass before moving to the next phase.

## Parallel Opportunities

- T002-T004 can run in parallel after T001.
- T008-T011 can run in parallel after T006-T007 define shared schemas.
- T018-T021 can run in parallel because they touch separate test files.
- T032-T034 can run in parallel because they touch separate test concerns/files.
- T044-T047 can run in parallel because they touch separate tests.
- T059 and T060-T067 should be sequenced by shared frontend files, but backend polish checks T068-T074 can be split after implementation.

## Parallel Example: User Story 1

```text
Task: "Add research config validation tests in backend/tests/unit/test_research_config.py"
Task: "Add missing-data preflight tests in backend/tests/unit/test_research_preflight.py"
Task: "Add research run/list/detail API contract tests in backend/tests/contract/test_research_api_contracts.py"
Task: "Add mixed available/missing asset integration test in backend/tests/integration/test_research_multi_asset_flow.py"
```

## Parallel Example: User Story 2

```text
Task: "Add Binance, Yahoo, and local-file capability tests in backend/tests/unit/test_research_capabilities.py"
Task: "Add Yahoo OHLCV-only integration test in backend/tests/integration/test_research_yahoo_flow.py"
Task: "Add comparison endpoint contract tests in backend/tests/contract/test_research_api_contracts.py"
```

## Parallel Example: User Story 3

```text
Task: "Add aggregation classification tests in backend/tests/unit/test_research_aggregation.py"
Task: "Add validation summary aggregation tests in backend/tests/unit/test_research_validation_summary.py"
Task: "Add validation section endpoint contract tests in backend/tests/contract/test_research_api_contracts.py"
Task: "Add crypto-like validation aggregation integration test in backend/tests/integration/test_research_crypto_flow.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundational schemas and skeletons.
3. Complete Phase 3 US1.
4. Stop and validate: backend import, focused research config/preflight/contract/integration tests, full backend tests.
5. Commit only after checks pass.

### Incremental Delivery

1. US1: grouped run with available and blocked assets.
2. US2: source-aware comparison and capability labeling.
3. US3: validation aggregation and evidence classification.
4. US4: dashboard inspection.
5. Polish: backend/frontend/artifact guard/smoke/forbidden-scope review.

### Guardrails

- Do not add live trading, paper trading, shadow trading, private keys, broker integration, real execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML.
- Do not substitute synthetic data for final real-data research reports.
- Do not commit generated files under `data/raw`, `data/processed`, `data/reports`, Parquet, DuckDB, build output, virtual environments, or `node_modules`.
- Do not claim profitability, predictive power, safety, or live readiness.
