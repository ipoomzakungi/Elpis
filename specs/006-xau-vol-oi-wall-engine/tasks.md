# Tasks: XAU Vol-OI Wall Engine

**Input**: Design documents from `specs/006-xau-vol-oi-wall-engine/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Required by the feature specification. Test tasks are listed before implementation tasks inside each user story.

**Organization**: Tasks are grouped by user story so each story can be implemented and verified independently after setup and foundation.

## Phase 1: Setup

**Purpose**: Create the additive XAU feature surface without changing existing provider, backtest, validation, or research modules.

- [X] T001 Create the XAU backend package marker in backend/src/xau/__init__.py
- [X] T002 Create the XAU model module placeholder in backend/src/models/xau.py
- [ ] T003 Create the XAU API route module placeholder in backend/src/api/routes/xau.py
- [ ] T004 Create the XAU dashboard route placeholder in frontend/src/app/xau-vol-oi/page.tsx
- [ ] T005 [P] Create shared XAU fixture helpers for synthetic local options files in backend/tests/helpers/test_xau_data.py
- [ ] T006 [P] Verify generated XAU data/report exclusions are covered by .gitignore and scripts/check_generated_artifacts.ps1

## Phase 2: Foundation

**Purpose**: Establish shared schemas, route wiring, report persistence scaffolding, and dashboard/API type placeholders that block all user stories.

- [X] T007 Define XAU enum and Pydantic schema skeletons in backend/src/models/xau.py
- [ ] T008 Add XAU-specific API validation helper functions in backend/src/api/validation.py
- [ ] T009 Register the XAU API router under `/api/v1/xau/vol-oi` in backend/src/main.py
- [X] T010 Create local import service skeleton in backend/src/xau/imports.py
- [X] T011 Create basis-adjustment service skeleton in backend/src/xau/basis.py
- [X] T012 Create volatility expected-range service skeleton in backend/src/xau/volatility.py
- [ ] T013 Create OI wall scoring service skeleton in backend/src/xau/walls.py
- [ ] T014 Create zone classification service skeleton in backend/src/xau/zones.py
- [ ] T015 Create XAU report orchestration skeleton in backend/src/xau/orchestration.py
- [ ] T016 Create XAU report store skeleton in backend/src/xau/report_store.py
- [ ] T017 Add grouped XAU JSON/Markdown writer skeleton in backend/src/reports/writer.py
- [ ] T018 Add XAU frontend type placeholders in frontend/src/types/index.ts
- [ ] T019 Add XAU frontend API client placeholders in frontend/src/services/api.ts
- [ ] T020 Create shared XAU API contract test scaffold in backend/tests/contract/test_xau_api_contracts.py

## Phase 3: User Story 1 - Load Gold Derivatives Research Data (Priority: P1)

**Goal**: A researcher can submit a local CSV/Parquet gold options OI dataset and receive clear validation results or actionable missing-data instructions.

**Independent Test**: Run a report request against a synthetic local options OI file with required columns and confirm accepted/rejected row counts, missing-column errors, unsafe-path rejection, and research-only limitations without requiring external data.

### Tests for User Story 1

- [X] T021 [US1] Add local CSV/Parquet required-column validation tests in backend/tests/unit/test_xau_imports.py
- [X] T022 [US1] Add timestamp, expiry, strike, option type, and open-interest parse tests in backend/tests/unit/test_xau_imports.py
- [X] T023 [US1] Add unsafe path and unreadable file tests in backend/tests/unit/test_xau_imports.py
- [X] T024 [US1] Add missing-data instruction tests for absent OI files and missing columns in backend/tests/unit/test_xau_imports.py
- [ ] T025 [P] [US1] Add local import integration flow with synthetic CSV and Parquet files in backend/tests/integration/test_xau_import_flow.py
- [ ] T026 [P] [US1] Add report creation contract tests for validation errors in backend/tests/contract/test_xau_api_contracts.py

### Implementation for User Story 1

- [X] T027 [US1] Implement required and optional gold options OI column constants in backend/src/xau/imports.py
- [X] T028 [US1] Implement safe local file path resolution for XAU source files in backend/src/xau/imports.py
- [X] T029 [US1] Implement CSV and Parquet loading with Polars in backend/src/xau/imports.py
- [X] T030 [US1] Implement timestamp/date parsing and session selection in backend/src/xau/imports.py
- [X] T031 [US1] Implement expiry parsing and days-to-expiry calculation in backend/src/xau/imports.py
- [X] T032 [US1] Implement strike, option type, open-interest, and optional numeric column normalization in backend/src/xau/imports.py
- [X] T033 [US1] Implement row-level validation notes, accepted row counts, and rejected row counts in backend/src/xau/imports.py
- [ ] T034 [US1] Implement local import preflight and missing-data instructions in backend/src/xau/orchestration.py
- [ ] T035 [US1] Persist source validation metadata in backend/src/xau/report_store.py

## Phase 4: User Story 2 - Map Futures Strikes To Spot-Equivalent Levels (Priority: P2)

**Goal**: A researcher can see futures strike walls mapped to XAUUSD spot-equivalent levels with auditable basis inputs and expected range labels.

**Independent Test**: Submit a synthetic imported dataset plus manual or computed spot/futures references and confirm basis, spot-equivalent levels, IV expected move, 1SD range, optional 2SD range, and unavailable-IV behavior.

### Tests for User Story 2

- [X] T036 [US2] Add computed and manual basis tests in backend/tests/unit/test_xau_basis.py
- [X] T037 [US2] Add futures strike to spot-equivalent mapping tests in backend/tests/unit/test_xau_basis.py
- [X] T038 [P] [US2] Add IV expected move, 1SD, 2SD, and unavailable-IV tests in backend/tests/unit/test_xau_volatility.py
- [ ] T039 [P] [US2] Add basis and expected range integration assertions in backend/tests/integration/test_xau_vol_oi_flow.py

### Implementation for User Story 2

- [X] T040 [US2] Implement basis input validation and manual-basis handling in backend/src/xau/basis.py
- [X] T041 [US2] Implement computed `futures_spot_basis` snapshots in backend/src/xau/basis.py
- [X] T042 [US2] Implement futures strike to spot-equivalent level mapping in backend/src/xau/basis.py
- [X] T043 [US2] Implement timestamp alignment status and basis limitation notes in backend/src/xau/basis.py
- [X] T044 [US2] Implement IV-based expected move and 1SD range calculation in backend/src/xau/volatility.py
- [X] T045 [US2] Implement optional 2SD stress range calculation in backend/src/xau/volatility.py
- [X] T046 [US2] Implement realized-volatility, manual, and unavailable range labels in backend/src/xau/volatility.py
- [ ] T047 [US2] Integrate basis snapshots and expected range outputs into report orchestration in backend/src/xau/orchestration.py

## Phase 5: User Story 3 - Classify Research Zones With Transparent Scores (Priority: P3)

**Goal**: A researcher can inspect wall scores and zone classifications that are explainable, source-labeled, and explicitly not trading signals.

**Independent Test**: Generate a report from synthetic call/put OI rows and confirm OI share, expiry weight, freshness factor, wall score, wall type, zone labels, notes, limitations, no-trade warnings, and persisted wall/zone tables.

### Tests for User Story 3

- [ ] T048 [P] [US3] Add OI share, expiry weight, freshness factor, and wall score tests in backend/tests/unit/test_xau_walls.py
- [ ] T049 [P] [US3] Add put wall, call wall, mixed wall, and unknown wall classification tests in backend/tests/unit/test_xau_walls.py
- [ ] T050 [P] [US3] Add support, resistance, pin-risk, squeeze-risk, breakout, reversal, and no-trade zone tests in backend/tests/unit/test_xau_zones.py
- [ ] T051 [P] [US3] Add no-profitability and no-live-readiness wording tests for zone notes in backend/tests/unit/test_xau_zones.py
- [ ] T052 [P] [US3] Add full scoring and zone integration flow assertions in backend/tests/integration/test_xau_vol_oi_flow.py

### Implementation for User Story 3

- [ ] T053 [US3] Implement total-expiry OI and OI share calculation in backend/src/xau/walls.py
- [ ] T054 [US3] Implement bounded near-expiry weighting in backend/src/xau/walls.py
- [ ] T055 [US3] Implement freshness factor from optional OI change and volume in backend/src/xau/walls.py
- [ ] T056 [US3] Implement transparent `wall_score = oi_share * expiry_weight * freshness_factor` in backend/src/xau/walls.py
- [ ] T057 [US3] Implement put, call, mixed, and unknown wall type classification in backend/src/xau/walls.py
- [ ] T058 [US3] Implement wall limitation notes for missing OI change, volume, IV, and basis in backend/src/xau/walls.py
- [ ] T059 [US3] Implement support and resistance candidate classification in backend/src/xau/zones.py
- [ ] T060 [US3] Implement pin-risk and squeeze-risk zone classification in backend/src/xau/zones.py
- [ ] T061 [US3] Implement breakout candidate, reversal candidate, and no-trade zone classification in backend/src/xau/zones.py
- [ ] T062 [US3] Implement zone explanation notes, confidence labels, and no-trade warnings in backend/src/xau/zones.py
- [ ] T063 [US3] Integrate wall scoring and zone classification into backend/src/xau/orchestration.py
- [ ] T064 [US3] Persist wall and zone tables as Parquet artifacts in backend/src/xau/report_store.py

## Phase 6: User Story 4 - Inspect XAU Wall Reports (Priority: P4)

**Goal**: A researcher can list, open, and inspect saved XAU Vol-OI reports through API endpoints and a focused dashboard page.

**Independent Test**: Create a report with synthetic local data, then retrieve report metadata, walls, and zones through API endpoints and confirm the dashboard page renders selector, basis snapshot, expected range, tables, warnings, and research-only disclaimer.

### Tests for User Story 4

- [ ] T065 [US4] Add report list/detail/walls/zones API contract tests in backend/tests/contract/test_xau_api_contracts.py
- [ ] T066 [US4] Add missing report and structured XAU error contract tests in backend/tests/contract/test_xau_api_contracts.py
- [ ] T067 [P] [US4] Add frontend type/build coverage for XAU responses in frontend/src/types/index.ts

### Implementation for User Story 4

- [ ] T068 [US4] Implement report metadata, wall table, zone table, JSON, and Markdown persistence in backend/src/xau/report_store.py
- [ ] T069 [US4] Add XAU report JSON and Markdown sections to backend/src/reports/writer.py
- [ ] T070 [US4] Implement `POST /api/v1/xau/vol-oi/reports` in backend/src/api/routes/xau.py
- [ ] T071 [US4] Implement `GET /api/v1/xau/vol-oi/reports` and `GET /api/v1/xau/vol-oi/reports/{report_id}` in backend/src/api/routes/xau.py
- [ ] T072 [US4] Implement `GET /api/v1/xau/vol-oi/reports/{report_id}/walls` and `/zones` in backend/src/api/routes/xau.py
- [ ] T073 [US4] Implement XAU report API client methods in frontend/src/services/api.ts
- [ ] T074 [US4] Implement report selector, status summary, basis snapshot, and expected range cards in frontend/src/app/xau-vol-oi/page.tsx
- [ ] T075 [US4] Implement basis-adjusted wall table and zone classification table in frontend/src/app/xau-vol-oi/page.tsx
- [ ] T076 [US4] Render missing-data warnings, source limitation notes, no-trade warnings, and research-only disclaimer in frontend/src/app/xau-vol-oi/page.tsx

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verify the complete feature through documented backend, frontend, artifact, API, dashboard, and forbidden-scope checks.

- [ ] T077 Run backend import check from backend/src/main.py
- [ ] T078 Run full backend pytest suite for backend/tests/
- [ ] T079 Run frontend install and production build using frontend/package.json
- [ ] T080 Run generated artifact guard using scripts/check_generated_artifacts.ps1
- [ ] T081 Run XAU Vol-OI API smoke flow from specs/006-xau-vol-oi-wall-engine/quickstart.md
- [ ] T082 Run dashboard smoke flow for `/xau-vol-oi` from specs/006-xau-vol-oi-wall-engine/quickstart.md
- [ ] T083 Review forbidden v0 scope in backend/pyproject.toml, frontend/package.json, .github/workflows/validation.yml, backend/src/, and frontend/src/
- [ ] T084 Update final validation notes and completion status in specs/006-xau-vol-oi-wall-engine/tasks.md

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 Setup must finish before Phase 2 Foundation.
- Phase 2 Foundation must finish before any user story.
- User stories can be implemented incrementally in priority order: US1, US2, US3, US4.
- Final validation runs after all user stories are complete.

### User Story Dependencies

- **US1** is the MVP and can run after foundation because it validates local input data and missing-data instructions.
- **US2** depends on US1 normalized rows because basis mapping and volatility ranges attach to imported rows.
- **US3** depends on US1 and US2 because wall scores need normalized rows and spot-equivalent levels.
- **US4** depends on US1-US3 because the dashboard and report endpoints inspect persisted report outputs.

## Parallel Execution Examples

### Setup/Foundation

```text
Task T005 can run in parallel with T006.
Tasks T010, T011, T012, T013, and T014 can run in parallel after T007.
Tasks T018 and T019 can run in parallel with backend skeleton tasks after T007.
```

### User Story 1

```text
Tasks T021, T025, and T026 should not be edited by one worker in the same file, but T025 and T026 can run in parallel with the unit-test work because they touch different files.
Tasks T028 and T029 should be sequenced unless their function boundaries in imports.py are agreed first.
```

### User Story 2

```text
Tasks T036 and T038 can run in parallel because basis and volatility tests are in different files.
Tasks T040-T043 can run in parallel with T044-T046 because basis.py and volatility.py are independent before orchestration integration.
```

### User Story 3

```text
Tasks T048 and T050 can run in parallel because wall and zone tests are in different files.
Tasks T053-T058 can run in parallel with T059-T062 because walls.py and zones.py are separate before orchestration integration.
```

### User Story 4

```text
Tasks T065 and T067 can run in parallel because backend contract tests and frontend types are separate.
Tasks T070-T072 can run in parallel with T073-T076 after report persistence is available.
```

## Implementation Strategy

### MVP First

Complete Phases 1-3 first. That yields a research-only local XAU options OI import path with clear validation errors and missing-data instructions.

### Incremental Delivery

1. Finish Setup and Foundation.
2. Deliver US1 and verify local data validation.
3. Add US2 basis mapping and expected ranges.
4. Add US3 transparent wall scoring and zone labels.
5. Add US4 report/API/dashboard inspection.
6. Run final validation and forbidden-scope review.

### Guardrails

- Do not treat Yahoo Finance GC=F or GLD as gold options OI, futures OI, IV, or XAUUSD spot execution data.
- Do not emit buy/sell signals, profitability claims, predictive claims, safety claims, or live-readiness claims.
- Do not add live trading, paper trading, shadow trading, private keys, broker integration, real execution, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML.
- Do not commit imported local datasets or generated report artifacts.
