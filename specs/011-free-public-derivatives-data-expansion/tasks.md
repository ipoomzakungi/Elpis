# Tasks: Free Public Derivatives Data Expansion

**Input**: Design documents from `specs/011-free-public-derivatives-data-expansion/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Required by the feature specification. Write focused tests before implementing each behavior slice and confirm they fail before implementation.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated as an independent research-only increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other tasks in the same phase because it touches different files or non-overlapping sections.
- **[Story]**: User story label for story phases only.
- All implementation tasks include exact file paths.

---

## Phase 1: Setup

**Purpose**: Create the feature skeleton, route surfaces, placeholders, and fixture locations without implementing source logic.

- [X] T001 Create free derivatives package marker in `backend/src/free_derivatives/__init__.py`
- [X] T002 Create free derivatives schema module placeholder in `backend/src/models/free_derivatives.py`
- [X] T003 Create CFTC module placeholder in `backend/src/free_derivatives/cftc.py`
- [X] T004 Create GVZ module placeholder in `backend/src/free_derivatives/gvz.py`
- [X] T005 Create Deribit module placeholder in `backend/src/free_derivatives/deribit.py`
- [X] T006 Create processing module placeholder in `backend/src/free_derivatives/processing.py`
- [X] T007 Create orchestration module placeholder in `backend/src/free_derivatives/orchestration.py`
- [X] T008 Create report store module placeholder in `backend/src/free_derivatives/report_store.py`
- [X] T009 Create API route placeholder in `backend/src/api/routes/free_derivatives.py`
- [X] T010 Register free derivatives route placeholder in `backend/src/main.py`
- [X] T011 [P] Add free derivatives frontend type placeholders in `frontend/src/types/index.ts`
- [X] T012 [P] Add free derivatives frontend API client placeholders in `frontend/src/services/api.ts`
- [X] T013 [P] Add placeholder free derivatives section in `frontend/src/app/data-sources/page.tsx`
- [X] T014 [P] Create free derivatives fixture directory marker in `backend/tests/fixtures/free_derivatives/.gitkeep`
- [X] T015 Verify ignored generated output coverage for `data/raw/cftc/`, `data/raw/gvz/`, `data/raw/deribit/`, `data/processed/cftc/`, `data/processed/gvz/`, `data/processed/deribit/`, and `data/reports/free_derivatives/` in `.gitignore` and `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational

**Purpose**: Add shared schemas, guardrails, path safety, limitation constants, and route registration behavior that block all user stories.

**Critical**: No source-specific user story implementation should begin until this phase is complete.

- [X] T016 [P] Add schema validation tests for free derivatives enums, request acknowledgement, report format, safe ids, and extra-field rejection in `backend/tests/unit/test_free_derivatives_models.py`
- [X] T017 [P] Add report-store path safety tests for raw, processed, and report artifact roots in `backend/tests/unit/test_free_derivatives_report_store.py`
- [X] T018 [P] Add source limitation label tests for CFTC, GVZ, Deribit, public-only, and artifact-scope labels in `backend/tests/unit/test_free_derivatives_limitations.py`
- [X] T019 [P] Add route registration smoke tests for free derivatives endpoints in `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [X] T020 Implement free derivatives enums and core request/result schemas in `backend/src/models/free_derivatives.py`
- [X] T021 Implement CFTC, GVZ, Deribit, public-only, and artifact-scope limitation constants in `backend/src/free_derivatives/processing.py`
- [X] T022 Implement safe id, safe local path, source URL, and credential-field validation helpers in `backend/src/models/free_derivatives.py`
- [X] T023 Implement path-safe free derivatives report-store root helpers in `backend/src/free_derivatives/report_store.py`
- [X] T024 Implement free derivatives artifact metadata helper in `backend/src/free_derivatives/report_store.py`
- [X] T025 Implement route skeleton functions with structured placeholder responses in `backend/src/api/routes/free_derivatives.py`
- [X] T026 Register free derivatives router with the v0 API prefix in `backend/src/main.py`
- [X] T027 Add `cftc_cot`, `gvz`, and `deribit_public_options` provider enum entries in `backend/src/models/data_sources.py`
- [X] T028 Add foundational free source capability placeholders in `backend/src/data_sources/capabilities.py`
- [X] T029 Add foundational missing-data action placeholders in `backend/src/data_sources/missing_data.py`

**Checkpoint**: Foundation ready. Free derivatives package imports, schema validation, route registration, limitation labels, and path safety are in place.

---

## Phase 3: User Story 1 - Add Public CFTC Gold Positioning Context (Priority: P1) MVP

**Goal**: Collect or import public CFTC COT data, filter gold/COMEX rows, preserve futures-only versus futures-and-options labels, and produce a weekly broad positioning summary.

**Independent Test**: Use CFTC fixtures containing gold and non-gold rows, then verify raw preservation, processed gold-only rows, category separation, summary fields, limitations, and no fabricated values.

### Tests for User Story 1

- [X] T030 [P] [US1] Add CFTC request planner tests for years, categories, public URLs, and fixture paths in `backend/tests/unit/test_free_derivatives_cftc.py`
- [X] T031 [P] [US1] Add CFTC fixture parser tests for CSV and compressed-file style rows in `backend/tests/unit/test_free_derivatives_cftc.py`
- [X] T032 [P] [US1] Add CFTC gold/COMEX filter tests including non-gold exclusion in `backend/tests/unit/test_free_derivatives_cftc.py`
- [X] T033 [P] [US1] Add CFTC futures-only versus futures-and-options category separation tests in `backend/tests/unit/test_free_derivatives_cftc.py`
- [X] T034 [P] [US1] Add CFTC positioning summary tests for net and week-over-week fields in `backend/tests/unit/test_free_derivatives_cftc.py`
- [X] T035 [P] [US1] Add CFTC source limitation and no strike-level OI wording tests in `backend/tests/unit/test_free_derivatives_limitations.py`

### Implementation for User Story 1

- [X] T036 [US1] Implement CFTC request plan creation in `backend/src/free_derivatives/cftc.py`
- [X] T037 [US1] Implement CFTC local fixture and compressed CSV reading in `backend/src/free_derivatives/cftc.py`
- [X] T038 [US1] Implement CFTC row normalization for date, market, exchange, category, positioning, and open-interest fields in `backend/src/free_derivatives/cftc.py`
- [X] T039 [US1] Implement gold/COMEX row filtering with visible filter metadata in `backend/src/free_derivatives/cftc.py`
- [X] T040 [US1] Implement CFTC futures-only and futures-and-options combined category preservation in `backend/src/free_derivatives/cftc.py`
- [X] T041 [US1] Implement broad weekly gold positioning summary generation in `backend/src/free_derivatives/processing.py`
- [X] T042 [US1] Implement raw CFTC and processed CFTC artifact writers in `backend/src/free_derivatives/report_store.py`
- [X] T043 [US1] Connect CFTC source execution into bootstrap orchestration without enabling other sources in `backend/src/free_derivatives/orchestration.py`

**Checkpoint**: User Story 1 is independently functional with fixture CFTC gold positioning outputs and research-only limitations.

---

## Phase 4: User Story 2 - Add GVZ Gold Volatility Proxy Context (Priority: P2)

**Goal**: Collect or import public GVZ daily close rows, label GVZ as a GLD-options-derived proxy, show gaps, and write processed daily close outputs.

**Independent Test**: Use GVZ fixtures with normal rows and date gaps, then verify raw rows, processed daily close rows, gap summary, proxy limitations, and no CME IV surface wording.

### Tests for User Story 2

- [X] T044 [P] [US2] Add GVZ request planner tests for series id, date windows, public URL, and fixture path in `backend/tests/unit/test_free_derivatives_gvz.py`
- [X] T045 [P] [US2] Add GVZ CSV fixture parser tests for date and close normalization in `backend/tests/unit/test_free_derivatives_gvz.py`
- [X] T046 [P] [US2] Add GVZ missing-date and gap summary tests in `backend/tests/unit/test_free_derivatives_gvz.py`
- [X] T047 [P] [US2] Add GVZ proxy limitation tests that reject CME gold IV surface wording in `backend/tests/unit/test_free_derivatives_limitations.py`
- [X] T048 [P] [US2] Add GVZ partial/missing source result tests in `backend/tests/unit/test_free_derivatives_gvz.py`

### Implementation for User Story 2

- [X] T049 [US2] Implement GVZ request plan creation in `backend/src/free_derivatives/gvz.py`
- [X] T050 [US2] Implement GVZ local fixture CSV reading and public daily close payload normalization in `backend/src/free_derivatives/gvz.py`
- [X] T051 [US2] Implement GVZ date-window filtering and daily close validation in `backend/src/free_derivatives/gvz.py`
- [X] T052 [US2] Implement GVZ gap summary generation in `backend/src/free_derivatives/processing.py`
- [X] T053 [US2] Implement raw GVZ and processed GVZ artifact writers in `backend/src/free_derivatives/report_store.py`
- [X] T054 [US2] Add GVZ proxy limitation labels to source results in `backend/src/free_derivatives/processing.py`
- [X] T055 [US2] Connect GVZ source execution into bootstrap orchestration without requiring CFTC or Deribit in `backend/src/free_derivatives/orchestration.py`

**Checkpoint**: User Story 2 is independently functional with fixture GVZ proxy outputs and explicit proxy limitations.

---

## Phase 5: User Story 3 - Add Deribit Public Crypto Options IV/OI Snapshots (Priority: P3)

**Goal**: Normalize Deribit public option instruments and market summaries into crypto options IV/OI rows and processed option wall snapshots without private endpoints.

**Independent Test**: Use mocked or fixture Deribit instruments and summaries, then verify expiry, strike, option type, IV/OI fields, underlying price, greeks, partial-field limitations, raw JSON, and processed wall outputs.

### Tests for User Story 3

- [X] T056 [P] [US3] Add Deribit request planner tests for underlyings, expired flag, fixture paths, and snapshot timestamp in `backend/tests/unit/test_free_derivatives_deribit.py`
- [X] T057 [P] [US3] Add Deribit instrument parsing tests for expiry, strike, call, put, unsupported underlying, and unsafe symbol cases in `backend/tests/unit/test_free_derivatives_deribit.py`
- [X] T058 [P] [US3] Add Deribit public summary normalization tests for open interest, mark IV, bid IV, ask IV, underlying price, volume, and greeks in `backend/tests/unit/test_free_derivatives_deribit.py`
- [X] T059 [P] [US3] Add Deribit partial-field limitation tests for missing IV/OI fields in `backend/tests/unit/test_free_derivatives_deribit.py`
- [X] T060 [P] [US3] Add Deribit option wall aggregation tests by underlying, expiry, strike, and option type in `backend/tests/unit/test_free_derivatives_deribit.py`
- [X] T061 [P] [US3] Add Deribit public-only guard tests proving private/account/order fields are rejected in `backend/tests/unit/test_free_derivatives_models.py`
- [X] T062 [P] [US3] Add Deribit crypto-options-only limitation tests in `backend/tests/unit/test_free_derivatives_limitations.py`

### Implementation for User Story 3

- [X] T063 [US3] Implement Deribit public request plan creation in `backend/src/free_derivatives/deribit.py`
- [X] T064 [US3] Implement Deribit instrument fixture and public response parsing in `backend/src/free_derivatives/deribit.py`
- [X] T065 [US3] Implement Deribit instrument name parsing for underlying, expiry, strike, and option type in `backend/src/free_derivatives/deribit.py`
- [X] T066 [US3] Implement Deribit public option summary normalization in `backend/src/free_derivatives/deribit.py`
- [X] T067 [US3] Implement Deribit missing-field and unsupported-underlying limitations in `backend/src/free_derivatives/deribit.py`
- [X] T068 [US3] Implement Deribit option wall snapshot aggregation in `backend/src/free_derivatives/processing.py`
- [X] T069 [US3] Implement raw Deribit JSON and processed Deribit Parquet artifact writers in `backend/src/free_derivatives/report_store.py`
- [X] T070 [US3] Connect Deribit source execution into bootstrap orchestration without requiring CFTC or GVZ in `backend/src/free_derivatives/orchestration.py`

**Checkpoint**: User Story 3 is independently functional with fixture Deribit public crypto options snapshots and public-only guardrails.

---

## Phase 6: User Story 4 - Inspect Free Derivatives Readiness And Bootstrap Runs (Priority: P4)

**Goal**: Expose free derivatives readiness, run creation, run history, run detail, output paths, limitations, and missing-data actions through API and `/data-sources`.

**Independent Test**: Open the data-source readiness/API/dashboard surfaces after fixture runs and confirm CFTC, GVZ, and Deribit statuses, artifacts, limitations, missing actions, and no secret values are visible.

### Tests for User Story 4

- [ ] T071 [P] [US4] Add API contract tests for create free derivatives bootstrap run in `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [ ] T072 [P] [US4] Add API contract tests for list and detail free derivatives bootstrap runs in `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [ ] T073 [P] [US4] Add API contract tests for invalid requests, missing run ids, and blocked all-source runs in `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [ ] T074 [P] [US4] Add readiness and capability contract tests for `cftc_cot`, `gvz`, and `deribit_public_options` in `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [ ] T075 [P] [US4] Add integration fixture flow test for CFTC plus GVZ plus Deribit partial preservation in `backend/tests/integration/test_free_derivatives_flow.py`
- [ ] T076 [P] [US4] Add integration test proving responses contain no secret values or forbidden execution wording in `backend/tests/integration/test_free_derivatives_flow.py`
- [ ] T077 [P] [US4] Add report persistence read/write tests for metadata, JSON, Markdown, source results, and artifact references in `backend/tests/unit/test_free_derivatives_report_store.py`

### Implementation for User Story 4

- [ ] T078 [US4] Implement run status aggregation and partial-result preservation in `backend/src/free_derivatives/orchestration.py`
- [ ] T079 [US4] Implement full report metadata, JSON, and Markdown persistence in `backend/src/free_derivatives/report_store.py`
- [ ] T080 [US4] Implement saved run list and detail reads in `backend/src/free_derivatives/report_store.py`
- [ ] T081 [US4] Implement `POST /api/v1/data-sources/bootstrap/free-derivatives` in `backend/src/api/routes/free_derivatives.py`
- [ ] T082 [US4] Implement `GET /api/v1/data-sources/bootstrap/free-derivatives/runs` and `GET /api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}` in `backend/src/api/routes/free_derivatives.py`
- [ ] T083 [US4] Implement structured validation, missing-data, and not-found errors for free derivatives routes in `backend/src/api/routes/free_derivatives.py`
- [ ] T084 [US4] Extend data-source capability matrix entries in `backend/src/data_sources/capabilities.py`
- [ ] T085 [US4] Extend data-source readiness statuses for free public derivatives in `backend/src/data_sources/readiness.py`
- [ ] T086 [US4] Extend missing-data actions for free derivatives source fallback and XAU local OI reminder in `backend/src/data_sources/missing_data.py`
- [ ] T087 [US4] Implement free derivatives frontend request and response types in `frontend/src/types/index.ts`
- [ ] T088 [US4] Implement `runFreeDerivativesBootstrap`, `listFreeDerivativesRuns`, and `getFreeDerivativesRun` client methods in `frontend/src/services/api.ts`
- [ ] T089 [US4] Extend data-source dashboard data loading for free derivatives runs in `frontend/src/services/api.ts`
- [ ] T090 [US4] Render CFTC, GVZ, and Deribit readiness entries in `frontend/src/app/data-sources/page.tsx`
- [ ] T091 [US4] Render free derivatives run selector, source status table, output paths, limitations, and missing-data actions in `frontend/src/app/data-sources/page.tsx`
- [ ] T092 [US4] Render free derivatives research-only and no-secret disclaimer text in `frontend/src/app/data-sources/page.tsx`

**Checkpoint**: User Story 4 is independently functional through API and dashboard inspection.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, quickstart alignment, artifact guard, and forbidden-scope review.

- [ ] T093 [P] Update `specs/011-free-public-derivatives-data-expansion/quickstart.md` if implemented request or response examples changed
- [ ] T094 Run backend import check from `backend/src/main.py`
- [ ] T095 Run focused free derivatives unit tests from `backend/tests/unit/test_free_derivatives_*.py`
- [ ] T096 Run focused free derivatives integration tests from `backend/tests/integration/test_free_derivatives_*.py`
- [ ] T097 Run free derivatives API contract tests from `backend/tests/contract/test_free_derivatives_api_contracts.py`
- [ ] T098 Run full backend pytest suite from `backend/tests/`
- [ ] T099 Run frontend dependency install and production build from `frontend/package.json`
- [ ] T100 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [ ] T101 Run fixture API smoke flow from `specs/011-free-public-derivatives-data-expansion/quickstart.md` without committing generated artifacts
- [ ] T102 Run dashboard smoke flow for `/data-sources` from `specs/011-free-public-derivatives-data-expansion/quickstart.md`
- [ ] T103 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T104 Update final validation notes and task completion status in `specs/011-free-public-derivatives-data-expansion/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundation**: Depends on Setup and blocks all user stories.
- **Phase 3 US1 CFTC**: Depends on Foundation and is the MVP.
- **Phase 4 US2 GVZ**: Depends on Foundation; can run in parallel with US1 if files are coordinated.
- **Phase 5 US3 Deribit**: Depends on Foundation; can run in parallel with US1/US2 if processing/report-store integration is coordinated.
- **Phase 6 US4 API/Dashboard**: Depends on source slices enough to expose real run output shapes.
- **Phase 7 Polish**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: First MVP; no dependencies on other user stories after Foundation.
- **US2 (P2)**: Independent source slice after Foundation; shares orchestration/report-store integration points.
- **US3 (P3)**: Independent source slice after Foundation; shares orchestration/report-store integration points.
- **US4 (P4)**: Depends on the source result models and should be completed after at least one source slice, then finalized after all selected source slices.

### Within Each User Story

- Write tests first and confirm they fail before implementation.
- Models and validation helpers before parsers.
- Parsers before processing summaries.
- Processing before artifact writers.
- Artifact writers before orchestration.
- Orchestration before API and dashboard behavior.
- Each checkpoint should pass focused tests before moving to the next story.

### Parallel Opportunities

- T003-T008 can run in parallel after T001-T002 because they create different modules.
- T011-T014 can run in parallel with backend setup because they touch frontend placeholders and fixtures.
- T016-T019 can run in parallel because they add separate foundational test files.
- T030-T035 can run in parallel before CFTC implementation.
- T044-T048 can run in parallel before GVZ implementation.
- T056-T062 can run in parallel before Deribit implementation.
- T071-T077 can run in parallel before API/orchestration persistence implementation.
- T087-T092 can be split across frontend types, API client, and page sections after backend response shapes stabilize.

---

## Parallel Example: User Story 1

```text
Task: "T030 [P] [US1] Add CFTC request planner tests for years, categories, public URLs, and fixture paths in backend/tests/unit/test_free_derivatives_cftc.py"
Task: "T031 [P] [US1] Add CFTC fixture parser tests for CSV and compressed-file style rows in backend/tests/unit/test_free_derivatives_cftc.py"
Task: "T035 [P] [US1] Add CFTC source limitation and no strike-level OI wording tests in backend/tests/unit/test_free_derivatives_limitations.py"
```

---

## Parallel Example: User Story 2

```text
Task: "T044 [P] [US2] Add GVZ request planner tests for series id, date windows, public URL, and fixture path in backend/tests/unit/test_free_derivatives_gvz.py"
Task: "T046 [P] [US2] Add GVZ missing-date and gap summary tests in backend/tests/unit/test_free_derivatives_gvz.py"
Task: "T047 [P] [US2] Add GVZ proxy limitation tests that reject CME gold IV surface wording in backend/tests/unit/test_free_derivatives_limitations.py"
```

---

## Parallel Example: User Story 3

```text
Task: "T056 [P] [US3] Add Deribit request planner tests for underlyings, expired flag, fixture paths, and snapshot timestamp in backend/tests/unit/test_free_derivatives_deribit.py"
Task: "T057 [P] [US3] Add Deribit instrument parsing tests for expiry, strike, call, put, unsupported underlying, and unsafe symbol cases in backend/tests/unit/test_free_derivatives_deribit.py"
Task: "T062 [P] [US3] Add Deribit crypto-options-only limitation tests in backend/tests/unit/test_free_derivatives_limitations.py"
```

---

## Parallel Example: User Story 4

```text
Task: "T071 [P] [US4] Add API contract tests for create free derivatives bootstrap run in backend/tests/contract/test_free_derivatives_api_contracts.py"
Task: "T075 [P] [US4] Add integration fixture flow test for CFTC plus GVZ plus Deribit partial preservation in backend/tests/integration/test_free_derivatives_flow.py"
Task: "T077 [P] [US4] Add report persistence read/write tests for metadata, JSON, Markdown, source results, and artifact references in backend/tests/unit/test_free_derivatives_report_store.py"
```

---

## Implementation Strategy

### MVP First: User Story 1 Only

1. Complete Phase 1 Setup.
2. Complete Phase 2 Foundation.
3. Complete Phase 3 CFTC COT slice.
4. Validate CFTC fixture parser, gold/COMEX filtering, category separation, processed summary, artifact paths, and limitations.
5. Stop and review before adding GVZ or Deribit.

### Incremental Delivery

1. Foundation creates schemas, route skeleton, report-store safety, and limitation labels.
2. US1 adds CFTC weekly broad gold positioning.
3. US2 adds GVZ daily proxy volatility.
4. US3 adds Deribit public crypto options snapshots.
5. US4 exposes the combined run lifecycle through API/readiness/dashboard.
6. Polish validates backend, frontend, artifact guard, smoke flows, and forbidden-scope review.

### Safety Rules

- Do not use private Deribit account or order endpoints.
- Do not require paid vendor credentials.
- Do not treat CFTC or GVZ as strike-level XAU options OI.
- Do not treat Deribit as gold/XAU data.
- Do not commit generated raw, processed, report, fixture-output, or local research files.
- Do not add live trading, paper trading, shadow trading, broker integration, wallet/private-key handling, real execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training.
