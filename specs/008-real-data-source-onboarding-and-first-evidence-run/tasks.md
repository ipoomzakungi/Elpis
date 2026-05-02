# Tasks: Real Data-Source Onboarding And First Evidence Run

**Input**: Design documents from `/specs/008-real-data-source-onboarding-and-first-evidence-run/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Required by the feature specification. Write focused tests before implementation in each user-story phase.

**Organization**: Tasks are grouped by user story so readiness, preflight, first-run execution, and dashboard inspection can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: Applies only to user-story phases.
- Every task includes an exact repository path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the feature shell without implementing user-story behavior.

- [X] T001 Create backend data-source package marker in backend/src/data_sources/__init__.py
- [X] T002 Create data-source schema module shell in backend/src/models/data_sources.py
- [X] T003 Create data-source API route skeleton in backend/src/api/routes/data_sources.py
- [X] T004 Create /data-sources dashboard placeholder route in frontend/src/app/data-sources/page.tsx
- [X] T005 [P] Create shared data-source test fixtures in backend/tests/helpers/test_data_source_data.py
- [X] T006 Verify generated data-source artifacts remain covered by .gitignore and scripts/check_generated_artifacts.ps1
- [X] T007 Add data-source structured error helpers in backend/src/api/validation.py
- [X] T008 Register data-source API router in backend/src/main.py
- [X] T009 Add data-source frontend type placeholders in frontend/src/types/index.ts
- [X] T010 Add data-source API client placeholders in frontend/src/services/api.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared schemas and service skeletons required by every user story.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T011 Implement DataSourceProviderType, DataSourceReadinessStatus, DataSourceTier, DataSourceWorkflowType, and FirstEvidenceRunStatus enums in backend/src/models/data_sources.py
- [X] T012 Implement DataSourceCapability, DataSourceProviderStatus, DataSourceMissingDataAction, DataSourceReadiness, DataSourcePreflightRequest, DataSourcePreflightResult, FirstEvidenceRunRequest, and FirstEvidenceRunResult schemas in backend/src/models/data_sources.py
- [X] T013 [P] Create static provider capability matrix skeleton in backend/src/data_sources/capabilities.py
- [X] T014 [P] Create readiness service skeleton with env-presence helper in backend/src/data_sources/readiness.py
- [X] T015 [P] Create missing-data instruction service skeleton in backend/src/data_sources/missing_data.py
- [X] T016 [P] Create preflight service skeleton in backend/src/data_sources/preflight.py
- [X] T017 [P] Create first evidence run orchestration skeleton in backend/src/data_sources/first_run.py

**Checkpoint**: Foundation ready. All user stories can now be implemented in priority order.

---

## Phase 3: User Story 1 - Review Data-Source Readiness (Priority: P1)

**Goal**: A researcher can see which public, local, optional paid, and forbidden sources are ready, missing, optional, unsupported, or forbidden without secret leakage.

**Independent Test**: Run readiness with no paid provider keys and one simulated configured key; verify Binance/Yahoo/local rows, optional vendor status, unsupported Yahoo capabilities, and no returned secret values.

### Tests for User Story 1

- [X] T018 [P] [US1] Add provider readiness and optional key detection tests in backend/tests/unit/test_data_source_readiness.py
- [X] T019 [US1] Add no-secret-leakage tests for readiness payloads in backend/tests/unit/test_data_source_readiness.py
- [X] T020 [P] [US1] Add provider capability matrix tests in backend/tests/unit/test_data_source_capabilities.py
- [X] T021 [US1] Add readiness and capabilities API contract tests in backend/tests/contract/test_data_sources_api_contracts.py

### Implementation for User Story 1

- [X] T022 [US1] Implement Binance, Yahoo, local, optional vendor, CME/QuikStrike, and forbidden credential capability rows in backend/src/data_sources/capabilities.py
- [X] T023 [US1] Implement unsupported capability label helpers for Yahoo and forbidden v0 credentials in backend/src/data_sources/capabilities.py
- [X] T024 [US1] Implement provider readiness detection with presence-only optional env var checks in backend/src/data_sources/readiness.py
- [X] T025 [US1] Implement no-secret serialization safeguards for provider status output in backend/src/models/data_sources.py
- [X] T026 [US1] Implement GET /api/v1/data-sources/readiness in backend/src/api/routes/data_sources.py
- [X] T027 [US1] Implement GET /api/v1/data-sources/capabilities in backend/src/api/routes/data_sources.py

**Checkpoint**: User Story 1 should pass unit and contract tests independently.

---

## Phase 4: User Story 2 - Receive Missing-Data Instructions (Priority: P2)

**Goal**: A researcher can preflight crypto, proxy, XAU, and optional vendor data readiness and receive clear download/process/import/configuration instructions.

**Independent Test**: Request crypto, proxy, XAU, and optional vendor preflight with missing inputs; verify Binance, Yahoo, XAU schema, and optional vendor instructions are returned and blocked workflows remain visible.

### Tests for User Story 2

- [X] T028 [P] [US2] Add missing-data instruction tests for crypto, proxy, XAU, and optional vendors in backend/tests/unit/test_data_source_missing_data.py
- [X] T029 [P] [US2] Add local-file schema capability detection tests in backend/tests/unit/test_data_source_preflight.py
- [X] T030 [US2] Add preflight API contract tests in backend/tests/contract/test_data_sources_api_contracts.py
- [X] T031 [P] [US2] Add public/no-key MVP preflight integration test in backend/tests/integration/test_data_source_public_mvp_flow.py
- [X] T032 [P] [US2] Add optional paid provider keys missing but non-blocking integration test in backend/tests/integration/test_data_source_optional_keys.py
- [X] T033 [P] [US2] Add XAU local file readiness integration test with synthetic CSV/Parquet fixtures in backend/tests/integration/test_data_source_xau_local_file.py

### Implementation for User Story 2

- [X] T034 [US2] Implement crypto Binance download/process missing-data instructions in backend/src/data_sources/missing_data.py
- [X] T035 [US2] Implement proxy Yahoo OHLCV missing-data instructions and OHLCV-only limitations in backend/src/data_sources/missing_data.py
- [X] T036 [US2] Implement XAU local options OI schema instructions and optional columns in backend/src/data_sources/missing_data.py
- [X] T037 [US2] Implement optional paid vendor configuration instructions without requiring keys in backend/src/data_sources/missing_data.py
- [X] T038 [US2] Implement crypto processed feature readiness checks and path safety in backend/src/data_sources/preflight.py
- [X] T039 [US2] Implement proxy OHLCV readiness checks and unsupported capability labeling in backend/src/data_sources/preflight.py
- [X] T040 [US2] Implement XAU local file schema readiness by reusing feature 006 validation in backend/src/data_sources/preflight.py
- [X] T041 [US2] Implement optional provider key preflight checks as non-blocking results in backend/src/data_sources/preflight.py
- [X] T042 [US2] Implement GET /api/v1/data-sources/missing-data and POST /api/v1/data-sources/preflight in backend/src/api/routes/data_sources.py

**Checkpoint**: User Story 2 should pass missing-data, preflight, contract, and integration tests independently.

---

## Phase 5: User Story 3 - Run The First Evidence Workflow (Priority: P3)

**Goal**: A researcher can start the first evidence workflow after preflight and receive one evidence result that links or references completed feature 005, 006, and 007 reports.

**Independent Test**: Use ignored synthetic fixtures for automated tests to run one ready workflow and one blocked workflow, then verify the response includes first_run_id, linked execution_run_id, blocked workflow visibility, missing-data checklist, and research-only warnings.

### Tests for User Story 3

- [X] T043 [US3] Add first evidence run API contract tests in backend/tests/contract/test_data_sources_api_contracts.py
- [X] T044 [P] [US3] Add first evidence run integration flow with ready and blocked workflows in backend/tests/integration/test_first_evidence_run_flow.py
- [X] T045 [P] [US3] Add first evidence run delegation tests for feature 007 request mapping in backend/tests/unit/test_data_source_first_run.py

### Implementation for User Story 3

- [X] T046 [US3] Implement FirstEvidenceRunRequest normalization and research-only acknowledgement validation in backend/src/models/data_sources.py
- [X] T047 [US3] Implement preflight-to-ResearchExecutionRunRequest translation in backend/src/data_sources/first_run.py
- [X] T048 [US3] Implement first evidence run orchestration by delegating to ResearchExecutionOrchestrator in backend/src/data_sources/first_run.py
- [X] T049 [US3] Implement first evidence run wrapper persistence or reference lookup under ignored report paths in backend/src/data_sources/report_store.py
- [X] T050 [US3] Implement POST /api/v1/evidence/first-run in backend/src/api/routes/data_sources.py
- [X] T051 [US3] Implement GET /api/v1/evidence/first-run/{run_id} in backend/src/api/routes/data_sources.py

**Checkpoint**: User Story 3 should pass first-run contract and integration tests independently.

---

## Phase 6: User Story 4 - Inspect Onboarding And Evidence Results In The Dashboard (Priority: P4)

**Goal**: A researcher can inspect readiness, capability labels, optional key status, missing-data actions, and first evidence run status from `/data-sources`.

**Independent Test**: Start the frontend and open `/data-sources`; verify readiness cards, provider capability matrix, missing-data checklist, first-run status/report links, and research-only disclaimer render without console/runtime errors.

### Tests for User Story 4

- [ ] T052 [US4] Add frontend type coverage for data-source responses through production build expectations in frontend/src/types/index.ts

### Implementation for User Story 4

- [ ] T053 [US4] Implement full data-source API client methods in frontend/src/services/api.ts
- [ ] T054 [US4] Render source readiness cards in frontend/src/app/data-sources/page.tsx
- [ ] T055 [US4] Render provider capability matrix and unsupported capability labels in frontend/src/app/data-sources/page.tsx
- [ ] T056 [US4] Render optional provider key status as configured or missing only in frontend/src/app/data-sources/page.tsx
- [ ] T057 [US4] Render missing-data checklist and XAU local file requirements in frontend/src/app/data-sources/page.tsx
- [ ] T058 [US4] Render first evidence run status and linked report IDs in frontend/src/app/data-sources/page.tsx
- [ ] T059 [US4] Render research-only disclaimer and no-execution limitations in frontend/src/app/data-sources/page.tsx
- [ ] T060 [US4] Add Data Sources navigation link in frontend/src/components/ui/Header.tsx

**Checkpoint**: User Story 4 should compile with `npm run build` and be smoke-testable in the browser.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, smoke checks, and scope review across the complete feature.

- [ ] T061 Run backend import check from backend/src/main.py
- [ ] T062 Run full backend pytest suite for backend/tests/
- [ ] T063 Run frontend install and production build using frontend/package.json
- [ ] T064 Run generated artifact guard using scripts/check_generated_artifacts.ps1
- [ ] T065 Run data-source readiness, capabilities, missing-data, preflight, and first-run API smoke flow from specs/008-real-data-source-onboarding-and-first-evidence-run/quickstart.md
- [ ] T066 Run /data-sources dashboard smoke flow from specs/008-real-data-source-onboarding-and-first-evidence-run/quickstart.md
- [ ] T067 Review forbidden v0 scope in backend/pyproject.toml, frontend/package.json, .github/workflows/validation.yml, backend/src/, and frontend/src/
- [ ] T068 Update final validation notes and completion status in specs/008-real-data-source-onboarding-and-first-evidence-run/tasks.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup and blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundation and is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundation and uses US1 capability labels.
- **User Story 3 (Phase 5)**: Depends on US2 preflight behavior.
- **User Story 4 (Phase 6)**: Depends on API behavior from US1, US2, and US3.
- **Polish (Phase 7)**: Depends on all selected user stories.

### User Story Dependencies

- **US1 Review Readiness**: Can start after Foundation and should be delivered first.
- **US2 Missing-Data Instructions**: Can start after Foundation but should reuse US1 capability labels.
- **US3 First Evidence Workflow**: Requires US2 preflight behavior.
- **US4 Dashboard Inspection**: Requires the API responses from US1 through US3.

### Within Each User Story

- Tests before implementation.
- Models before services.
- Services before endpoints.
- API client/types before dashboard rendering.
- Story checkpoints before moving to the next phase.

## Parallel Opportunities

- Setup task T005 can run independently after the package paths are known.
- Foundation skeleton tasks T013 through T017 can run in parallel after schemas are available.
- US1 unit tests T018 through T020 can be drafted in parallel; T021 modifies the shared contract test file.
- US2 integration tests T031 through T033 can be drafted in parallel because they use different files.
- US3 integration/unit tests T044 and T045 can be drafted in parallel.
- US4 rendering tasks should be sequenced within `frontend/src/app/data-sources/page.tsx` because they share one page file.

## Parallel Example: User Story 1

```text
Task: "Add provider readiness and optional key detection tests in backend/tests/unit/test_data_source_readiness.py"
Task: "Add provider capability matrix tests in backend/tests/unit/test_data_source_capabilities.py"
Task: "Implement Binance, Yahoo, local, optional vendor, CME/QuikStrike, and forbidden credential capability rows in backend/src/data_sources/capabilities.py"
```

## Parallel Example: User Story 2

```text
Task: "Add public/no-key MVP preflight integration test in backend/tests/integration/test_data_source_public_mvp_flow.py"
Task: "Add optional paid provider keys missing but non-blocking integration test in backend/tests/integration/test_data_source_optional_keys.py"
Task: "Add XAU local file readiness integration test with synthetic CSV/Parquet fixtures in backend/tests/integration/test_data_source_xau_local_file.py"
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 Setup.
2. Complete Phase 2 Foundation.
3. Complete Phase 3 User Story 1.
4. Validate readiness, capabilities, no-secret behavior, and readiness endpoints.
5. Commit and push the stable MVP checkpoint.

### Incremental Delivery

1. Add US1 readiness and capability visibility.
2. Add US2 missing-data and preflight behavior.
3. Add US3 first evidence run delegation.
4. Add US4 dashboard inspection.
5. Run final validation and forbidden-scope review.

### Validation Commands

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q

cd ../frontend
npm install
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## Notes

- Keep this feature research-only.
- Do not add live trading, paper trading, shadow trading, private trading keys, broker integration, real execution, wallet/private keys, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training.
- Do not return secret values, partial values, hashes, or masked values.
- Do not treat Yahoo Finance as a source for crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD execution data.
- Synthetic data is allowed only in automated tests and smoke validation.
- Generated raw data, processed data, reports, `.env` files, and local import files must remain ignored and untracked.
