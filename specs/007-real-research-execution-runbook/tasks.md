# Tasks: Real Research Execution Runbook

**Input**: Design documents from `specs/007-real-research-execution-runbook/`
**Prerequisites**: `plan.md` (required), `spec.md` (required), `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Required by the feature spec. Each user-story phase includes unit, integration, or contract tests before implementation tasks.

**Organization**: Tasks are grouped by user story to keep each increment independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and does not depend on incomplete tasks.
- **[Story]**: User story label, required only for user-story phases.
- Every task includes an exact repository path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the 007 package, API/UI placeholders, and test helper entry points.

- [X] T001 Create `backend/src/research_execution/__init__.py` package marker
- [X] T002 [P] Create `backend/src/models/research_execution.py` placeholder for execution schemas
- [X] T003 [P] Create `backend/src/api/routes/research_execution.py` route placeholder
- [X] T004 [P] Create `/evidence` placeholder page in `frontend/src/app/evidence/page.tsx`
- [X] T005 [P] Create shared synthetic evidence fixtures in `backend/tests/helpers/test_research_execution_data.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared schemas, stores, validation helpers, routes, and frontend API/type scaffolding that all stories depend on.

**Critical**: No user story implementation should start until this phase is complete.

- [X] T006 Implement workflow status, decision, workflow type, request, config, preflight, result, evidence, run, and summary schemas in `backend/src/models/research_execution.py`
- [X] T007 [P] Create execution report store skeleton and artifact path helpers in `backend/src/research_execution/report_store.py`
- [X] T008 [P] Create execution preflight skeleton and shared result builders in `backend/src/research_execution/preflight.py`
- [X] T009 [P] Create evidence aggregation skeleton and decision-rule placeholders in `backend/src/research_execution/aggregation.py`
- [X] T010 [P] Create execution orchestration skeleton in `backend/src/research_execution/orchestration.py`
- [X] T011 Add research execution API validation helpers in `backend/src/api/validation.py`
- [X] T012 Register research execution router in `backend/src/main.py`
- [X] T013 Add grouped evidence JSON and Markdown writer skeleton hooks in `backend/src/reports/writer.py`
- [X] T014 [P] Add research execution frontend type placeholders in `frontend/src/types/index.ts`
- [X] T015 Add research execution API client placeholders in `frontend/src/services/api.ts`
- [X] T016 Verify research execution generated report exclusions in `.gitignore` and `scripts/check_generated_artifacts.ps1`
- [X] T017 [P] Create research execution API contract test scaffold in `backend/tests/contract/test_research_execution_api_contracts.py`

**Checkpoint**: Foundation ready. Backend imports should still pass before user-story work begins.

---

## Phase 3: User Story 1 - Run Crypto Research Execution (Priority: P1) MVP

**Goal**: Start a crypto research execution run with one ready asset and one missing asset, preserving both completed and blocked outcomes.

**Independent Test**: Use synthetic processed features for one crypto asset and omit another asset, then verify the execution run records both outcomes with report references or missing-data instructions.

### Tests for User Story 1

- [X] T018 [P] [US1] Add execution config validation and forbidden field tests in `backend/tests/unit/test_research_execution_config.py`
- [X] T019 [P] [US1] Add crypto processed-feature preflight tests in `backend/tests/unit/test_research_execution_preflight.py`
- [ ] T020 [US1] Add basic run/list/detail API contract tests in `backend/tests/contract/test_research_execution_api_contracts.py`
- [ ] T021 [P] [US1] Add mixed ready/missing crypto integration test in `backend/tests/integration/test_research_execution_crypto_flow.py`

### Implementation for User Story 1

- [X] T022 [US1] Implement normalized crypto workflow config validation and forbidden field rejection in `backend/src/models/research_execution.py`
- [X] T023 [US1] Implement processed feature path resolution and path safety for crypto assets in `backend/src/research_execution/preflight.py`
- [X] T024 [US1] Implement missing, unreadable, empty, and incomplete crypto feature statuses and download/process instructions in `backend/src/research_execution/preflight.py`
- [ ] T025 [US1] Implement grouped execution run ID creation and request normalization in `backend/src/research_execution/orchestration.py`
- [ ] T026 [US1] Implement crypto workflow orchestration for ready and blocked assets using existing feature 005 reports in `backend/src/research_execution/orchestration.py`
- [ ] T027 [US1] Persist execution metadata, normalized config, preflight results, and crypto asset summaries in `backend/src/research_execution/report_store.py`
- [ ] T028 [US1] Add crypto completed/blocked workflow sections to evidence JSON and Markdown in `backend/src/reports/writer.py`
- [ ] T029 [US1] Implement POST, list, and detail route behavior for crypto execution runs in `backend/src/api/routes/research_execution.py`
- [ ] T030 [US1] Add research execution run/list/detail client methods in `frontend/src/services/api.ts`

**Checkpoint**: User Story 1 is independently testable with one ready crypto asset and one missing crypto asset.

---

## Phase 4: User Story 2 - Run Yahoo And Proxy OHLCV Research (Priority: P2)

**Goal**: Include Yahoo/proxy OHLCV assets while clearly labeling unsupported OI, funding, gold options OI, futures OI, IV, and XAUUSD execution capabilities.

**Independent Test**: Use one synthetic available OHLCV proxy asset and one unsupported capability request, then verify limitations stay visible in evidence.

### Tests for User Story 2

- [ ] T031 [P] [US2] Add unsupported proxy capability tests in `backend/tests/unit/test_research_execution_unsupported_capabilities.py`
- [ ] T032 [P] [US2] Add proxy OHLCV preflight tests in `backend/tests/unit/test_research_execution_preflight.py`
- [ ] T033 [P] [US2] Add Yahoo/proxy OHLCV integration flow in `backend/tests/integration/test_research_execution_proxy_flow.py`
- [ ] T034 [US2] Add proxy limitation API contract assertions in `backend/tests/contract/test_research_execution_api_contracts.py`

### Implementation for User Story 2

- [ ] T035 [US2] Implement proxy workflow config normalization and OHLCV-only defaults in `backend/src/models/research_execution.py`
- [ ] T036 [US2] Implement provider capability snapshot generation for proxy assets in `backend/src/research_execution/preflight.py`
- [ ] T037 [US2] Implement unsupported OI, funding, gold options OI, futures OI, IV, and XAUUSD execution labels in `backend/src/research_execution/preflight.py`
- [ ] T038 [US2] Implement GC=F and GLD gold proxy limitation notes in `backend/src/research_execution/preflight.py`
- [ ] T039 [US2] Implement proxy workflow orchestration using existing feature 005 reports or processed OHLCV inputs in `backend/src/research_execution/orchestration.py`
- [ ] T040 [US2] Aggregate proxy OHLCV workflow outcomes and research decisions in `backend/src/research_execution/aggregation.py`
- [ ] T041 [US2] Persist proxy workflow evidence and limitation summaries in `backend/src/research_execution/report_store.py`
- [ ] T042 [US2] Add proxy OHLCV and unsupported capability sections to evidence JSON and Markdown in `backend/src/reports/writer.py`
- [ ] T043 [US2] Return proxy limitation fields from execution detail and evidence routes in `backend/src/api/routes/research_execution.py`

**Checkpoint**: User Story 2 is independently testable with an OHLCV-only proxy asset and explicit unsupported capability labels.

---

## Phase 5: User Story 3 - Run XAU Vol-OI Research Workflow (Priority: P3)

**Goal**: Include XAU Vol-OI research with local gold options OI inputs, linked report IDs, source validation, basis, expected range, walls, zones, and missing-data instructions.

**Independent Test**: Use a synthetic local options OI fixture for one XAU workflow and a missing file for another, then verify completed and blocked outcomes.

### Tests for User Story 3

- [ ] T044 [P] [US3] Add XAU workflow config and local file validation tests in `backend/tests/unit/test_research_execution_preflight.py`
- [ ] T045 [P] [US3] Add missing XAU options OI integration test in `backend/tests/integration/test_research_execution_missing_xau.py`
- [ ] T046 [P] [US3] Add synthetic XAU local options integration test in `backend/tests/integration/test_research_execution_xau_flow.py`
- [ ] T047 [US3] Add XAU report reference contract assertions in `backend/tests/contract/test_research_execution_api_contracts.py`

### Implementation for User Story 3

- [ ] T048 [US3] Implement XAU workflow config validation and local path safety in `backend/src/models/research_execution.py`
- [ ] T049 [US3] Implement XAU options OI file readiness and required schema instructions in `backend/src/research_execution/preflight.py`
- [ ] T050 [US3] Implement XAU existing report reference handling and missing report status in `backend/src/research_execution/orchestration.py`
- [ ] T051 [US3] Implement XAU workflow orchestration using existing feature 006 report store and local input readiness in `backend/src/research_execution/orchestration.py`
- [ ] T052 [US3] Aggregate XAU source validation, basis, expected range, wall count, zone count, warnings, and limitations in `backend/src/research_execution/aggregation.py`
- [ ] T053 [US3] Persist XAU workflow report references and evidence summaries in `backend/src/research_execution/report_store.py`
- [ ] T054 [US3] Add XAU workflow sections to evidence JSON and Markdown in `backend/src/reports/writer.py`
- [ ] T055 [US3] Return XAU workflow evidence and missing-data actions from execution routes in `backend/src/api/routes/research_execution.py`

**Checkpoint**: User Story 3 is independently testable with a synthetic local XAU options file and a missing XAU file.

---

## Phase 6: User Story 4 - Produce A Final Evidence Summary (Priority: P4)

**Goal**: Produce one final evidence report that links all workflow report IDs, preserves blocked workflows, and displays bounded research decisions in the API and dashboard.

**Independent Test**: Create an execution run with at least one completed workflow and one blocked workflow, then verify evidence, missing-data, and dashboard surfaces.

### Tests for User Story 4

- [ ] T056 [P] [US4] Add evidence decision rule tests in `backend/tests/unit/test_research_execution_aggregation.py`
- [ ] T057 [P] [US4] Add final evidence endpoint contract tests in `backend/tests/contract/test_research_execution_api_contracts.py`
- [ ] T058 [P] [US4] Add final mixed-workflow evidence integration test in `backend/tests/integration/test_research_execution_flow.py`
- [ ] T059 [P] [US4] Add frontend evidence type coverage through production build expectations in `frontend/src/types/index.ts`

### Implementation for User Story 4

- [ ] T060 [US4] Implement continue, refine, reject, data_blocked, and inconclusive decision rules in `backend/src/research_execution/aggregation.py`
- [ ] T061 [US4] Assemble final evidence summary across crypto, proxy, XAU, warnings, limitations, and missing-data actions in `backend/src/research_execution/orchestration.py`
- [ ] T062 [US4] Persist evidence summary JSON, Markdown, and missing-data checklist in `backend/src/research_execution/report_store.py`
- [ ] T063 [US4] Implement evidence and missing-data endpoints in `backend/src/api/routes/research_execution.py`
- [ ] T064 [US4] Add full execution run, evidence, and missing-data API client methods in `frontend/src/services/api.ts`
- [ ] T065 [US4] Add complete research execution frontend response types in `frontend/src/types/index.ts`
- [ ] T066 [US4] Implement `/evidence` run selector and workflow status cards in `frontend/src/app/evidence/page.tsx`
- [ ] T067 [US4] Render linked multi-asset and XAU report IDs in `frontend/src/app/evidence/page.tsx`
- [ ] T068 [US4] Render evidence decision table and missing-data checklist in `frontend/src/app/evidence/page.tsx`
- [ ] T069 [US4] Render limitations and research-only disclaimers in `frontend/src/app/evidence/page.tsx`
- [ ] T070 [US4] Add Evidence navigation link in `frontend/src/components/ui/Header.tsx`

**Checkpoint**: User Story 4 is independently testable through the API and `/evidence` dashboard.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the full feature, smoke-test documented workflows, and verify v0 scope constraints.

- [ ] T071 Run backend import check from `backend/src/main.py`
- [ ] T072 Run full backend pytest suite for `backend/tests/`
- [ ] T073 Run frontend install and production build using `frontend/package.json`
- [ ] T074 Run generated artifact guard using `scripts/check_generated_artifacts.ps1`
- [ ] T075 Run research execution API smoke flow from `specs/007-real-research-execution-runbook/quickstart.md`
- [ ] T076 Run Evidence dashboard smoke flow for `/evidence` from `specs/007-real-research-execution-runbook/quickstart.md`
- [ ] T077 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T078 Update final validation notes and completion status in `specs/007-real-research-execution-runbook/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundation**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2; can be implemented after or alongside US1, but final evidence quality improves after US1.
- **Phase 5 US3**: Depends on Phase 2; can be implemented independently from US1/US2 if feature 006 APIs are stable.
- **Phase 6 US4**: Depends on US1, US2, and US3 evidence shapes for the complete dashboard, though API skeleton can begin after Phase 2.
- **Phase 7 Polish**: Depends on all desired user stories.

### User Story Dependencies

- **US1 Crypto Research Execution**: MVP and first useful vertical slice.
- **US2 Proxy OHLCV Research**: Independent capability and limitation handling after foundation.
- **US3 XAU Vol-OI Workflow**: Independent XAU evidence reference handling after foundation.
- **US4 Final Evidence Summary**: Integrates available workflow outputs and should be completed after the workflow stories selected for release.

### Within Each User Story

- Write tests first and confirm they fail for missing behavior.
- Implement schema or preflight changes before orchestration.
- Implement orchestration before persistence.
- Implement persistence before API routes.
- Implement API client/types before dashboard rendering.
- Validate the story independently before marking its tasks complete.

---

## Parallel Opportunities

- T002, T003, T004, and T005 can run in parallel after T001.
- T007, T008, T009, T010, T014, and T017 can run in parallel after T006 boundaries are understood.
- US1 test files T018, T019, and T021 can be written in parallel; T020 shares the contract file and should be coordinated.
- US2 tests T031, T032, and T033 can be written in parallel; T034 shares the contract file and should be coordinated.
- US3 tests T044, T045, and T046 can be written in parallel; T047 shares the contract file and should be coordinated.
- US4 tests T056, T057, T058, and T059 touch different files and can be written in parallel.
- Dashboard rendering tasks in T066 through T069 share one page file and should be sequenced.

## Parallel Example: User Story 1

```text
Task: T018 Add execution config validation and forbidden field tests in backend/tests/unit/test_research_execution_config.py
Task: T019 Add crypto processed-feature preflight tests in backend/tests/unit/test_research_execution_preflight.py
Task: T021 Add mixed ready/missing crypto integration test in backend/tests/integration/test_research_execution_crypto_flow.py
```

## Parallel Example: User Story 2

```text
Task: T031 Add unsupported proxy capability tests in backend/tests/unit/test_research_execution_unsupported_capabilities.py
Task: T033 Add Yahoo/proxy OHLCV integration flow in backend/tests/integration/test_research_execution_proxy_flow.py
```

## Parallel Example: User Story 3

```text
Task: T045 Add missing XAU options OI integration test in backend/tests/integration/test_research_execution_missing_xau.py
Task: T046 Add synthetic XAU local options integration test in backend/tests/integration/test_research_execution_xau_flow.py
```

## Parallel Example: User Story 4

```text
Task: T056 Add evidence decision rule tests in backend/tests/unit/test_research_execution_aggregation.py
Task: T058 Add final mixed-workflow evidence integration test in backend/tests/integration/test_research_execution_flow.py
```

---

## Implementation Strategy

### MVP First

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1 crypto execution.
4. Validate US1 with one ready crypto asset and one missing crypto asset.
5. Commit the stable MVP checkpoint.

### Incremental Delivery

1. Add US1 crypto execution and validate.
2. Add US2 proxy OHLCV capability handling and validate.
3. Add US3 XAU workflow references and validate.
4. Add US4 final evidence summary and dashboard.
5. Complete Phase 7 smoke checks and forbidden-scope review.

### Scope Guardrails

- Do not create new strategy logic in feature 007.
- Do not substitute synthetic data for final real research runs.
- Keep generated evidence artifacts under ignored `data/reports/research_execution/`.
- Do not add live, paper, shadow, broker, private-key, wallet, real execution, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML behavior.
