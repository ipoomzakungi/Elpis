# Tasks: QuikStrike Open Interest Matrix Extractor

**Input**: Design documents from `specs/013-quikstrike-open-interest-matrix-extractor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included because the feature specification requires unit tests, integration tests, API contract tests if routes are added, frontend build validation, and artifact guard validation.

**Organization**: Tasks are grouped by user story so each increment can be implemented and tested independently.

## Phase 1: Setup

**Purpose**: Create the feature package, schema module, route/dashboard placeholders, fixture directory, and artifact guard coverage.

- [x] T001 Create `backend/src/quikstrike_matrix/__init__.py`
- [x] T002 Create `backend/src/models/quikstrike_matrix.py`
- [x] T003 [P] Create `backend/src/quikstrike_matrix/table_reader.py` placeholder
- [x] T004 [P] Create `backend/src/quikstrike_matrix/metadata.py` placeholder
- [x] T005 [P] Create `backend/src/quikstrike_matrix/extraction.py` placeholder
- [x] T006 [P] Create `backend/src/quikstrike_matrix/conversion.py` placeholder
- [x] T007 [P] Create `backend/src/quikstrike_matrix/report_store.py` placeholder
- [x] T008 [P] Create `backend/src/quikstrike_matrix/local_browser.py` placeholder
- [x] T009 Create `backend/src/api/routes/quikstrike_matrix.py` route placeholder
- [x] T010 Register the QuikStrike Matrix router in `backend/src/main.py`
- [x] T011 [P] Add QuikStrike Matrix frontend type placeholders in `frontend/src/types/index.ts`
- [x] T012 [P] Add QuikStrike Matrix API client placeholders in `frontend/src/services/api.ts`
- [x] T013 Add placeholder QuikStrike Matrix status section in `frontend/src/app/xau-vol-oi/page.tsx`
- [x] T014 Create `backend/tests/fixtures/quikstrike_matrix/.gitkeep`
- [x] T015 Add artifact guard coverage for `data/raw/quikstrike_matrix/`, `data/processed/quikstrike_matrix/`, and `data/reports/quikstrike_matrix/` in `.gitignore` and `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundation

**Purpose**: Add core schemas, privacy guards, path-safe report roots, route skeletons, and foundational tests that block all user stories.

- [x] T016 [P] Add schema validation tests in `backend/tests/unit/test_quikstrike_matrix_models.py`
- [x] T017 [P] Add forbidden secret/session field tests in `backend/tests/unit/test_quikstrike_matrix_models.py`
- [x] T018 [P] Add report-store path safety tests in `backend/tests/unit/test_quikstrike_matrix_report_store.py`
- [x] T019 [P] Add route registration smoke tests in `backend/tests/contract/test_quikstrike_matrix_api_contracts.py`
- [x] T020 Implement matrix view, value type, option type, extraction status, mapping status, cell state, and artifact enums in `backend/src/models/quikstrike_matrix.py`
- [x] T021 Implement strict schemas for metadata, table snapshots, header cells, body cells, normalized rows, validation results, extraction results, conversion results, artifacts, and reports in `backend/src/models/quikstrike_matrix.py`
- [x] T022 Implement safe id, safe local path, and forbidden field validation helpers in `backend/src/models/quikstrike_matrix.py`
- [x] T023 Implement local-only, research-only, no-secret, no-endpoint-replay, and artifact-scope limitation constants in `backend/src/quikstrike_matrix/extraction.py`
- [x] T024 Implement path-safe report-store root helpers for matrix raw, processed, and report paths in `backend/src/quikstrike_matrix/report_store.py`
- [x] T025 Implement artifact metadata helper in `backend/src/quikstrike_matrix/report_store.py`
- [x] T026 Implement route skeleton functions with structured placeholder responses in `backend/src/api/routes/quikstrike_matrix.py`
- [x] T027 Confirm `backend/src/main.py` imports cleanly with the registered route placeholder

**Checkpoint**: Foundation ready. User story work can begin.

---

## Phase 3: User Story 1 - Extract Gold Open Interest Matrix Tables Locally (Priority: P1) MVP

**Goal**: Parse sanitized HTML table fixtures for OI Matrix, OI Change Matrix, and Volume Matrix into normalized local research rows.

**Independent Test**: Synthetic sanitized HTML fixtures for all three target views produce normalized rows with product, source menu, view type, strike, expiration, option type, value, value type, table labels, warnings, and limitations.

### Tests for User Story 1

- [x] T028 [P] [US1] Add OI Matrix table parser tests in `backend/tests/unit/test_quikstrike_matrix_table_reader.py`
- [x] T029 [P] [US1] Add OI Change Matrix table parser tests in `backend/tests/unit/test_quikstrike_matrix_table_reader.py`
- [x] T030 [P] [US1] Add Volume Matrix table parser tests in `backend/tests/unit/test_quikstrike_matrix_table_reader.py`
- [x] T031 [P] [US1] Add expiration column, DTE, futures symbol, and reference price header parsing tests in `backend/tests/unit/test_quikstrike_matrix_table_reader.py`
- [x] T032 [P] [US1] Add call/put/combined option-side parsing tests in `backend/tests/unit/test_quikstrike_matrix_table_reader.py`
- [x] T033 [P] [US1] Add metadata parser tests for Gold/Open Interest Matrix visible text in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T034 [P] [US1] Add normalized row builder tests for all three views in `backend/tests/unit/test_quikstrike_matrix_extraction.py`

### Implementation for User Story 1

- [x] T035 [US1] Implement Gold matrix metadata parsing in `backend/src/quikstrike_matrix/metadata.py`
- [x] T036 [US1] Implement sanitized HTML table ingestion and forbidden markup rejection in `backend/src/quikstrike_matrix/table_reader.py`
- [x] T037 [US1] Implement header row expansion for expiration groups, DTE, futures symbol, reference price, and option side in `backend/src/quikstrike_matrix/table_reader.py`
- [x] T038 [US1] Implement strike row extraction excluding totals, subtotals, separators, and non-strike labels in `backend/src/quikstrike_matrix/table_reader.py`
- [x] T039 [US1] Implement body cell extraction into table cell models in `backend/src/quikstrike_matrix/table_reader.py`
- [x] T040 [US1] Implement view-to-value-type mapping for OI, OI Change, and Volume Matrix in `backend/src/quikstrike_matrix/extraction.py`
- [x] T041 [US1] Implement normalized row creation with source limitations and stable row ids in `backend/src/quikstrike_matrix/extraction.py`

**Checkpoint**: User Story 1 can extract synthetic matrix tables into normalized rows.

---

## Phase 4: User Story 2 - Validate Table Mapping Before Conversion (Priority: P2)

**Goal**: Fail closed when matrix table structure, strike mapping, expiration mapping, option side, or numeric values are uncertain.

**Independent Test**: Fixture cases with missing tables, missing strikes, missing expirations, blank cells, invalid cells, duplicate rows, and combined-only columns produce explicit validation states and block conversion when required.

### Tests for User Story 2

- [x] T042 [P] [US2] Add table presence and no-row validation tests in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T043 [P] [US2] Add missing strike and missing expiration blocker tests in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T044 [P] [US2] Add blank, dash, unavailable, and explicit zero cell tests in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T045 [P] [US2] Add signed, negative, parenthesized, and comma-formatted numeric parsing tests in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T046 [P] [US2] Add duplicate row warning/blocking tests in `backend/tests/unit/test_quikstrike_matrix_extraction.py`
- [x] T047 [P] [US2] Add no-secret persistence tests for extraction results and reports in `backend/tests/unit/test_quikstrike_matrix_extraction.py`

### Implementation for User Story 2

- [x] T048 [US2] Implement matrix mapping validation for table presence, strike rows, expiration columns, option-side mapping, and numeric cell counts in `backend/src/quikstrike_matrix/extraction.py`
- [x] T049 [US2] Implement unavailable cell handling so blanks and dashes remain unavailable rather than zero in `backend/src/quikstrike_matrix/extraction.py`
- [x] T050 [US2] Implement OI Change numeric parsing for negative, signed, parenthesized, and comma-formatted values in `backend/src/quikstrike_matrix/extraction.py`
- [x] T051 [US2] Implement duplicate normalized row detection and deterministic warning/blocking behavior in `backend/src/quikstrike_matrix/extraction.py`
- [x] T052 [US2] Implement completed, partial, blocked, and failed extraction status assembly in `backend/src/quikstrike_matrix/extraction.py`
- [x] T053 [US2] Implement privacy-safe warning and limitation propagation in `backend/src/quikstrike_matrix/extraction.py`

**Checkpoint**: User Story 2 can validate table structure and block unsafe conversion.

---

## Phase 5: User Story 3 - Convert Valid Matrix Rows Into XAU Vol-OI Input (Priority: P3)

**Goal**: Convert validated matrix rows into XAU Vol-OI compatible local input while preserving source limitations and blocking unsafe rows.

**Independent Test**: Valid synthetic matrix rows produce XAU Vol-OI compatible rows for open interest, OI change, and volume; missing strike/expiration or unavailable cells block or omit rows as specified.

### Tests for User Story 3

- [x] T054 [P] [US3] Add OI Matrix to open interest conversion tests in `backend/tests/unit/test_quikstrike_matrix_conversion.py`
- [x] T055 [P] [US3] Add OI Change Matrix to OI change conversion tests in `backend/tests/unit/test_quikstrike_matrix_conversion.py`
- [x] T056 [P] [US3] Add Volume Matrix to volume conversion tests in `backend/tests/unit/test_quikstrike_matrix_conversion.py`
- [x] T057 [P] [US3] Add blocked conversion tests for missing strike, missing expiration, unavailable-only cells, and invalid mapping in `backend/tests/unit/test_quikstrike_matrix_conversion.py`
- [x] T058 [P] [US3] Add report-store processed artifact writer tests in `backend/tests/unit/test_quikstrike_matrix_report_store.py`

### Implementation for User Story 3

- [x] T059 [US3] Implement conversion eligibility checks in `backend/src/quikstrike_matrix/conversion.py`
- [x] T060 [US3] Implement OI Matrix row conversion to `open_interest` fields in `backend/src/quikstrike_matrix/conversion.py`
- [x] T061 [US3] Implement OI Change Matrix row conversion to `oi_change` fields in `backend/src/quikstrike_matrix/conversion.py`
- [x] T062 [US3] Implement Volume Matrix row conversion to `volume` fields in `backend/src/quikstrike_matrix/conversion.py`
- [x] T063 [US3] Implement conversion warning and limitation propagation in `backend/src/quikstrike_matrix/conversion.py`
- [x] T064 [US3] Implement processed CSV/Parquet and conversion metadata writers in `backend/src/quikstrike_matrix/report_store.py`

**Checkpoint**: User Story 3 can produce XAU Vol-OI compatible local input from valid matrix rows.

---

## Phase 6: User Story 4 - Inspect Matrix Extraction Status (Priority: P4)

**Goal**: Expose saved extraction status, row counts, coverage, warnings, conversion status, artifact paths, and disclaimers through local API and dashboard inspection.

**Independent Test**: Saved synthetic extraction reports can be listed, inspected, opened by row/conversion endpoint, and rendered in the `/xau-vol-oi` status panel without exposing secrets or execution wording.

### Tests for User Story 4

- [x] T065 [P] [US4] Add API contract tests for create matrix extraction from sanitized fixture in `backend/tests/contract/test_quikstrike_matrix_api_contracts.py`
- [x] T066 [P] [US4] Add API contract tests for list, detail, rows, and conversion endpoints in `backend/tests/contract/test_quikstrike_matrix_api_contracts.py`
- [x] T067 [P] [US4] Add API contract tests for invalid requests, missing extraction ids, blocked conversion, and secret-bearing payload rejection in `backend/tests/contract/test_quikstrike_matrix_api_contracts.py`
- [x] T068 [P] [US4] Add integration flow test for all three matrix views in `backend/tests/integration/test_quikstrike_matrix_flow.py`
- [x] T069 [P] [US4] Add local browser adapter skeleton tests in `backend/tests/unit/test_quikstrike_matrix_local_browser.py`

### Implementation for User Story 4

- [x] T070 [US4] Implement full report metadata, normalized rows, conversion rows, JSON report, and Markdown report persistence in `backend/src/quikstrike_matrix/report_store.py`
- [x] T071 [US4] Implement saved extraction list, detail, rows, and conversion reads in `backend/src/quikstrike_matrix/report_store.py`
- [x] T072 [US4] Implement `POST /api/v1/quikstrike-matrix/extractions/from-fixture` in `backend/src/api/routes/quikstrike_matrix.py`
- [x] T073 [US4] Implement `GET /api/v1/quikstrike-matrix/extractions` and detail endpoint in `backend/src/api/routes/quikstrike_matrix.py`
- [x] T074 [US4] Implement rows and conversion endpoints in `backend/src/api/routes/quikstrike_matrix.py`
- [x] T075 [US4] Implement structured validation, missing-data, blocked conversion, and not-found errors in `backend/src/api/routes/quikstrike_matrix.py`
- [x] T076 [US4] Implement local browser adapter skeleton that rejects cookies, tokens, headers, viewstate, HAR, screenshots, credentials, and private URLs in `backend/src/quikstrike_matrix/local_browser.py`
- [x] T077 [US4] Implement QuikStrike Matrix request/response frontend types in `frontend/src/types/index.ts`
- [x] T078 [US4] Implement QuikStrike Matrix API client methods in `frontend/src/services/api.ts`
- [x] T079 [US4] Render QuikStrike Matrix status, view coverage, row/strike/expiry counts, warnings, conversion status, generated paths, and disclaimer in `frontend/src/app/xau-vol-oi/page.tsx`

**Checkpoint**: User Story 4 can inspect saved matrix extraction reports through API and dashboard.

---

## Phase 7: Polish & Final Validation

**Purpose**: Validate the full feature, update documentation if implementation differs, and perform forbidden-scope review.

- [x] T080 Update `specs/013-quikstrike-open-interest-matrix-extractor/quickstart.md` if implemented request or response examples changed
- [x] T081 Run backend import check from `backend/src/main.py`
- [x] T082 Run focused QuikStrike Matrix unit tests from `backend/tests/unit/test_quikstrike_matrix_*.py`
- [x] T083 Run focused QuikStrike Matrix integration tests from `backend/tests/integration/test_quikstrike_matrix_*.py`
- [x] T084 Run QuikStrike Matrix API contract tests from `backend/tests/contract/test_quikstrike_matrix_api_contracts.py`
- [x] T085 Run full backend pytest suite from `backend/tests/`
- [x] T086 Run frontend dependency install and production build from `frontend/package.json`
- [x] T087 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [x] T088 Run sanitized fixture API smoke flow from `specs/013-quikstrike-open-interest-matrix-extractor/quickstart.md` without committing generated artifacts
- [x] T089 Run dashboard smoke flow for `/xau-vol-oi` from `specs/013-quikstrike-open-interest-matrix-extractor/quickstart.md`
- [x] T090 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [x] T091 Update final validation notes and task completion status in `specs/013-quikstrike-open-interest-matrix-extractor/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundation (Phase 2)**: Depends on Setup completion and blocks all user stories.
- **US1 Extract Tables (Phase 3)**: Depends on Foundation.
- **US2 Validate Mapping (Phase 4)**: Depends on Foundation and uses US1 parsed table cells.
- **US3 Convert Rows (Phase 5)**: Depends on US1 normalized rows and US2 validation.
- **US4 Inspect Status (Phase 6)**: Depends on extraction, validation, conversion, and report-store behavior.
- **Final Validation (Phase 7)**: Depends on all implemented user stories.

### User Story Dependencies

- **US1 (P1)**: MVP. Can be completed with synthetic fixtures after Foundation.
- **US2 (P2)**: Builds validation gates over US1 extracted cells.
- **US3 (P3)**: Requires US2 conversion eligibility checks.
- **US4 (P4)**: Requires saved extraction/conversion reports to inspect.

---

## Parallel Opportunities

- T003-T008 can run in parallel after T001-T002.
- T011-T012 can run in parallel with backend placeholders.
- T016-T019 can run in parallel before foundation implementation.
- US1 parser tests T028-T034 can run in parallel.
- US2 validation tests T042-T047 can run in parallel.
- US3 conversion tests T054-T058 can run in parallel.
- US4 API/integration/local adapter tests T065-T069 can run in parallel.

---

## Parallel Example: User Story 1

```text
Task: "Add OI Matrix table parser tests in backend/tests/unit/test_quikstrike_matrix_table_reader.py"
Task: "Add OI Change Matrix table parser tests in backend/tests/unit/test_quikstrike_matrix_table_reader.py"
Task: "Add Volume Matrix table parser tests in backend/tests/unit/test_quikstrike_matrix_table_reader.py"
Task: "Add metadata parser tests for Gold/Open Interest Matrix visible text in backend/tests/unit/test_quikstrike_matrix_extraction.py"
```

---

## Implementation Strategy

### MVP First

1. Complete Setup and Foundation.
2. Implement US1 with synthetic sanitized HTML tables.
3. Validate US1 independently before adding conversion.

### Incremental Delivery

1. US1 extracts normalized matrix rows.
2. US2 adds safety gates for mapping and missing cells.
3. US3 converts valid rows to XAU Vol-OI input.
4. US4 adds report/API/dashboard inspection.
5. Final validation confirms no generated/private data is committed and no forbidden scope was introduced.

### Scope Guard

Do not implement production QuikStrike endpoint replay, credential storage, private session persistence, live trading, paper trading, broker integration, paid-vendor automation, screenshot OCR, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML. Use synthetic HTML fixtures for automated tests and keep generated matrix data under ignored local paths.

---

## Final Validation Notes

- Backend import check passed: `python -c "from src.main import app; print('backend import ok')"`
- Focused Matrix unit tests passed: 31 tests.
- Focused Matrix integration tests passed: 2 tests.
- Matrix API contract tests passed: 4 tests.
- Full backend test suite passed: 488 tests.
- Frontend dependency install completed with existing npm audit findings and no dependency changes.
- Frontend production build passed.
- Generated artifact guard passed after fixture API smoke.
- Sanitized fixture API smoke passed for create/list/detail/rows/conversion, missing id, invalid request, and no-secret checks.
- Dashboard smoke passed by serving backend/frontend locally and confirming `/xau-vol-oi` renders the Matrix status panel.
- Forbidden-scope review found only guard/disclaimer text and existing backtest metric names; no forbidden runtime dependency or execution behavior was added.
