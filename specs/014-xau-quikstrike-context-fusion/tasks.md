# Tasks: XAU QuikStrike Context Fusion

**Input**: Design documents from `specs/014-xau-quikstrike-context-fusion/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification. Test tasks are listed before implementation tasks in each phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the 014 package, schema, route, frontend, fixture, and artifact guard skeletons without implementing fusion behavior.

- [X] T001 Create backend package marker in `backend/src/xau_quikstrike_fusion/__init__.py`
- [X] T002 Create schema module placeholder in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T003 [P] Create source loader module placeholder in `backend/src/xau_quikstrike_fusion/loaders.py`
- [X] T004 [P] Create matching module placeholder in `backend/src/xau_quikstrike_fusion/matching.py`
- [X] T005 [P] Create fusion module placeholder in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T006 [P] Create basis module placeholder in `backend/src/xau_quikstrike_fusion/basis.py`
- [X] T007 [P] Create orchestration module placeholder in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [X] T008 [P] Create report-store module placeholder in `backend/src/xau_quikstrike_fusion/report_store.py`
- [X] T009 Create local API route placeholder in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [X] T010 Register the fusion router with the v0 API prefix in `backend/src/main.py`
- [X] T011 [P] Add XAU QuikStrike fusion frontend type placeholders in `frontend/src/types/index.ts`
- [X] T012 [P] Add XAU QuikStrike fusion API client placeholders in `frontend/src/services/api.ts`
- [X] T013 Add placeholder QuikStrike Fusion panel section in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T014 Create synthetic fusion fixture folder marker in `backend/tests/fixtures/xau_quikstrike_fusion/.gitkeep`
- [X] T015 Add `backend/data/reports/xau_quikstrike_fusion/` and `data/reports/xau_quikstrike_fusion/` generated artifact coverage in `.gitignore`
- [X] T016 Add fusion artifact guard denied paths in `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared schemas, path safety, report-store helpers, and route skeleton behavior required by all user stories.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [X] T017 [P] Add schema validation tests for fusion enums, ids, request validation, and forbidden secret/session fields in `backend/tests/unit/test_xau_quikstrike_fusion_models.py`
- [X] T018 [P] Add report-store path safety tests for fusion report roots and artifact paths in `backend/tests/unit/test_xau_quikstrike_fusion_report_store.py`
- [X] T019 [P] Add API route registration smoke tests in `backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py`
- [X] T020 [P] Add shared synthetic Vol2Vol and Matrix report fixture helpers in `backend/tests/helpers/test_xau_quikstrike_fusion_data.py`
- [X] T021 Implement `XauFusionSourceType`, `XauFusionMatchStatus`, `XauFusionAgreementStatus`, `XauFusionContextStatus`, `XauFusionReportStatus`, and `XauFusionArtifactType` in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T022 Implement `XauQuikStrikeFusionRequest`, `XauQuikStrikeSourceRef`, `XauFusionMatchKey`, `XauFusionSourceValue`, and `XauFusionCoverageSummary` in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T023 Implement `XauFusionRow`, `XauFusionMissingContextItem`, `XauFusionBasisState`, `XauFusionContextSummary`, and `XauFusionDownstreamResult` in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T024 Implement `XauFusionVolOiInputRow`, `XauQuikStrikeFusionReport`, `XauQuikStrikeFusionSummary`, and table response models in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T025 Implement safe id, forbidden field, and research-only validation helpers in `backend/src/models/xau_quikstrike_fusion.py`
- [X] T026 Implement path-safe fusion report root and artifact path helpers in `backend/src/xau_quikstrike_fusion/report_store.py`
- [X] T027 Implement fusion artifact metadata helper and JSON serialization helpers in `backend/src/xau_quikstrike_fusion/report_store.py`
- [X] T028 Implement route skeleton responses and structured placeholder errors in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [X] T029 Verify frontend placeholder types and API client exports compile in `frontend/src/types/index.ts` and `frontend/src/services/api.ts`
- [X] T030 Verify generated artifact path coverage for fusion paths using `scripts/check_generated_artifacts.ps1`

**Checkpoint**: Foundation ready. User stories can be implemented after T001-T030.

---

## Phase 3: User Story 1 - Fuse Vol2Vol and Matrix Context (Priority: P1) MVP

**Goal**: Load one Vol2Vol report and one Matrix report, validate source compatibility, match rows by key, create fused rows, and preserve source provenance/agreement.

**Independent Test**: Synthetic Vol2Vol and Matrix reports fuse into rows with correct strike, expiration, option side, value type, provenance, coverage, and source agreement state.

### Tests for User Story 1

- [X] T031 [P] [US1] Add loader tests for existing Vol2Vol and Matrix source report reads in `backend/tests/unit/test_xau_quikstrike_fusion_loaders.py`
- [X] T032 [P] [US1] Add source compatibility tests for Gold/OG/GC and incompatible product blocking in `backend/tests/unit/test_xau_quikstrike_fusion_loaders.py`
- [X] T033 [P] [US1] Add match-key normalization tests for strike, expiration, expiration code, option type, and value type in `backend/tests/unit/test_xau_quikstrike_fusion_matching.py`
- [X] T034 [P] [US1] Add source agreement and disagreement tests in `backend/tests/unit/test_xau_quikstrike_fusion_matching.py`
- [X] T035 [P] [US1] Add fused-row provenance and no-silent-overwrite tests in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`
- [X] T036 [P] [US1] Add MVP integration test for synthetic Vol2Vol plus Matrix fusion in `backend/tests/integration/test_xau_quikstrike_fusion_flow.py`

### Implementation for User Story 1

- [X] T037 [US1] Implement Vol2Vol report loading through existing feature 012 report store in `backend/src/xau_quikstrike_fusion/loaders.py`
- [X] T038 [US1] Implement Matrix report loading through existing feature 013 report store in `backend/src/xau_quikstrike_fusion/loaders.py`
- [X] T039 [US1] Implement source report compatibility validation for product, status, row availability, warnings, and limitations in `backend/src/xau_quikstrike_fusion/loaders.py`
- [X] T040 [US1] Implement source-row normalization into `XauFusionSourceValue` in `backend/src/xau_quikstrike_fusion/loaders.py`
- [X] T041 [US1] Implement fusion match-key creation and value-type mapping in `backend/src/xau_quikstrike_fusion/matching.py`
- [X] T042 [US1] Implement matched, Vol2Vol-only, Matrix-only, conflict, and blocked match statuses in `backend/src/xau_quikstrike_fusion/matching.py`
- [X] T043 [US1] Implement coverage summary calculation in `backend/src/xau_quikstrike_fusion/matching.py`
- [X] T044 [US1] Implement source agreement/disagreement evaluation without overwriting source values in `backend/src/xau_quikstrike_fusion/matching.py`
- [X] T045 [US1] Implement fused row creation and stable fusion row ids in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T046 [US1] Implement MVP fusion orchestration that loads sources, matches rows, builds coverage, and assembles an in-memory report in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [X] T047 [US1] Persist MVP metadata and fused rows to JSON/Markdown report artifacts in `backend/src/xau_quikstrike_fusion/report_store.py`

**Checkpoint**: US1 delivers a testable MVP fusion report from saved source reports.

---

## Phase 4: User Story 2 - Explain Missing XAU Reaction Context (Priority: P2)

**Goal**: Generate structured basis, IV/range, open-regime, candle-acceptance, realized-volatility, source-quality, and source-agreement context statuses so conservative reaction output is explainable.

**Independent Test**: Fused rows with missing basis/range/open/candle inputs produce a missing-context checklist and do not fabricate values.

### Tests for User Story 2

- [X] T048 [P] [US2] Add basis status tests for available, unavailable, invalid, and conflicting references in `backend/tests/unit/test_xau_quikstrike_fusion_basis.py`
- [X] T049 [P] [US2] Add spot-equivalent level calculation tests in `backend/tests/unit/test_xau_quikstrike_fusion_basis.py`
- [X] T050 [P] [US2] Add missing context checklist tests for basis, IV/range, open, candle, RV, source quality, and source agreement in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`
- [X] T051 [P] [US2] Add no-fabricated-context regression tests in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`
- [X] T052 [P] [US2] Add integration test proving missing open/candle context keeps downstream notes conservative in `backend/tests/integration/test_xau_quikstrike_fusion_flow.py`

### Implementation for User Story 2

- [X] T053 [US2] Implement optional futures/spot basis state calculation in `backend/src/xau_quikstrike_fusion/basis.py`
- [X] T054 [US2] Implement spot-equivalent level calculation and unavailable-basis behavior in `backend/src/xau_quikstrike_fusion/basis.py`
- [X] T055 [US2] Implement IV/range status detection from Vol2Vol range and volatility-style context in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T056 [US2] Implement realized-volatility, session-open, and candle-acceptance context status generation from optional request inputs in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T057 [US2] Implement structured missing-context checklist generation in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T058 [US2] Attach missing-context notes to fusion rows and report context summary in `backend/src/xau_quikstrike_fusion/fusion.py`
- [X] T059 [US2] Integrate basis state and missing context into fusion orchestration in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [X] T060 [US2] Persist basis state and missing-context checklist in JSON/Markdown fusion reports in `backend/src/xau_quikstrike_fusion/report_store.py`

**Checkpoint**: US2 explains why downstream reaction output may remain NO_TRADE or low confidence.

---

## Phase 5: User Story 3 - Produce XAU Vol-OI Compatible Fused Input (Priority: P3)

**Goal**: Convert valid fused rows into XAU Vol-OI compatible local input and optionally reuse existing XAU Vol-OI and XAU reaction orchestration.

**Independent Test**: Valid fused rows produce XAU Vol-OI compatible rows; unsafe strike/expiry/option/value mappings are blocked or marked partial; optional downstream reports are linked when requested and eligible.

### Tests for User Story 3

- [ ] T061 [P] [US3] Add fused XAU Vol-OI conversion tests for Matrix OI/OI Change/Volume and Vol2Vol context preservation in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`
- [ ] T062 [P] [US3] Add blocked conversion tests for missing strike, expiration, option type, and value mapping in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`
- [ ] T063 [P] [US3] Add downstream XAU Vol-OI orchestration integration test in `backend/tests/integration/test_xau_quikstrike_fusion_flow.py`
- [ ] T064 [P] [US3] Add downstream XAU reaction orchestration integration test with conservative NO_TRADE notes in `backend/tests/integration/test_xau_quikstrike_fusion_flow.py`
- [ ] T065 [P] [US3] Add forbidden wording tests for downstream fusion notes in `backend/tests/unit/test_xau_quikstrike_fusion_fusion.py`

### Implementation for User Story 3

- [ ] T066 [US3] Implement fused XAU Vol-OI input row creation in `backend/src/xau_quikstrike_fusion/fusion.py`
- [ ] T067 [US3] Implement conversion eligibility and blocked/partial conversion reasons in `backend/src/xau_quikstrike_fusion/fusion.py`
- [ ] T068 [US3] Implement fused input artifact persistence metadata in `backend/src/xau_quikstrike_fusion/report_store.py`
- [ ] T069 [US3] Integrate optional XAU Vol-OI report creation through existing feature 006 orchestration in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [ ] T070 [US3] Integrate optional XAU reaction report creation through existing feature 010 orchestration in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [ ] T071 [US3] Implement downstream result summary with linked report ids, no-trade count, and conservative notes in `backend/src/xau_quikstrike_fusion/orchestration.py`
- [ ] T072 [US3] Persist downstream result and fused XAU input row counts in fusion reports in `backend/src/xau_quikstrike_fusion/report_store.py`

**Checkpoint**: US3 can feed the existing XAU research chain without duplicating wall scoring or reaction logic.

---

## Phase 6: User Story 4 - Inspect Fusion and Downstream Outcomes (Priority: P4)

**Goal**: Expose saved fusion reports through local API endpoints and a compact `/xau-vol-oi` dashboard panel.

**Independent Test**: Saved complete, partial, and blocked fusion reports can be listed, inspected, and shown in the dashboard with coverage, missing context, linked report ids, and disclaimers.

### Tests for User Story 4

- [ ] T073 [P] [US4] Add create fusion report API contract tests in `backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py`
- [ ] T074 [P] [US4] Add list/detail/rows/missing-context API contract tests in `backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py`
- [ ] T075 [P] [US4] Add missing source report, incompatible source report, missing fusion report, and invalid request API contract tests in `backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py`
- [ ] T076 [P] [US4] Add report-store list/detail/rows/missing-context read tests in `backend/tests/unit/test_xau_quikstrike_fusion_report_store.py`
- [ ] T077 [P] [US4] Add frontend API type and client compile coverage via `frontend/src/types/index.ts` and `frontend/src/services/api.ts`

### Implementation for User Story 4

- [ ] T078 [US4] Implement full report save/read/list behavior in `backend/src/xau_quikstrike_fusion/report_store.py`
- [ ] T079 [US4] Implement `POST /api/v1/xau/quikstrike-fusion/reports` in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [ ] T080 [US4] Implement `GET /api/v1/xau/quikstrike-fusion/reports` and `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}` in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [ ] T081 [US4] Implement `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}/rows` and `/missing-context` in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [ ] T082 [US4] Implement structured API errors for validation, source not found, incompatible sources, blocked fusion, and report not found in `backend/src/api/routes/xau_quikstrike_fusion.py`
- [ ] T083 [US4] Implement XAU QuikStrike fusion request, summary, detail, row, and missing-context frontend types in `frontend/src/types/index.ts`
- [ ] T084 [US4] Implement `createXauQuikStrikeFusionReport`, `listXauQuikStrikeFusionReports`, `getXauQuikStrikeFusionReport`, `getXauQuikStrikeFusionRows`, and `getXauQuikStrikeFusionMissingContext` in `frontend/src/services/api.ts`
- [ ] T085 [US4] Render QuikStrike Fusion report selector, selected source report ids, status, fused row count, strike coverage, and expiry coverage in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T086 [US4] Render source agreement/disagreement, basis status, IV/range status, open/candle context status, and missing-context checklist in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T087 [US4] Render generated artifact paths, linked XAU Vol-OI report id, linked XAU reaction report id, all-NO_TRADE state, and research-only disclaimer in `frontend/src/app/xau-vol-oi/page.tsx`

**Checkpoint**: US4 makes fusion and downstream outcomes visible through local API and dashboard inspection.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation alignment, artifact safety, and forbidden-scope review.

- [ ] T088 Update `specs/014-xau-quikstrike-context-fusion/quickstart.md` if implemented API request or response examples changed
- [ ] T089 Run backend import check from `backend/src/main.py`
- [ ] T090 Run focused unit tests for `backend/tests/unit/test_xau_quikstrike_fusion_*.py`
- [ ] T091 Run focused integration tests for `backend/tests/integration/test_xau_quikstrike_fusion_*.py`
- [ ] T092 Run focused API contract tests for `backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py`
- [ ] T093 Run the full backend test suite from `backend/tests/`
- [ ] T094 Run frontend dependency install and production build from `frontend/package.json`
- [ ] T095 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [ ] T096 Run the API smoke flow documented in `specs/014-xau-quikstrike-context-fusion/quickstart.md` without committing generated reports
- [ ] T097 Run the dashboard smoke flow for `/xau-vol-oi` documented in `specs/014-xau-quikstrike-context-fusion/quickstart.md`
- [ ] T098 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T099 Confirm generated fusion artifacts remain ignored and untracked using `git status --ignored --short`
- [ ] T100 Update final validation notes and task completion status in `specs/014-xau-quikstrike-context-fusion/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 3 because missing-context items attach to fused rows and source coverage.
- **Phase 5 US3**: Depends on Phase 3 and uses Phase 4 context for conservative downstream notes.
- **Phase 6 US4**: Depends on Phases 3-5 for complete API/dashboard payloads.
- **Phase 7 Polish**: Depends on all implemented phases.

### User Story Dependencies

- **US1 (P1)**: Required MVP. No dependency on later stories.
- **US2 (P2)**: Requires US1 fused rows and source coverage.
- **US3 (P3)**: Requires US1 fused rows; benefits from US2 context statuses.
- **US4 (P4)**: Requires saved report/read models from US1-US3.

### Parallel Opportunities

- T003-T008 can run in parallel after T001-T002.
- T017-T020 can run in parallel before schema/helper implementation.
- T031-T036 can run in parallel because they target distinct test concerns.
- T048-T052 can run in parallel after US1 tests and fixtures exist.
- T061-T065 can run in parallel after conversion model shape exists.
- T073-T077 can run in parallel after report models and route skeletons exist.
- Frontend tasks T083-T087 should be coordinated because they touch shared frontend files.

---

## Parallel Example: User Story 1

```text
Task: "Add loader tests for existing Vol2Vol and Matrix source report reads in backend/tests/unit/test_xau_quikstrike_fusion_loaders.py"
Task: "Add match-key normalization tests for strike, expiration, expiration code, option type, and value type in backend/tests/unit/test_xau_quikstrike_fusion_matching.py"
Task: "Add fused-row provenance and no-silent-overwrite tests in backend/tests/unit/test_xau_quikstrike_fusion_fusion.py"
Task: "Add MVP integration test for synthetic Vol2Vol plus Matrix fusion in backend/tests/integration/test_xau_quikstrike_fusion_flow.py"
```

## Parallel Example: User Story 2

```text
Task: "Add basis status tests for available, unavailable, invalid, and conflicting references in backend/tests/unit/test_xau_quikstrike_fusion_basis.py"
Task: "Add missing context checklist tests for basis, IV/range, open, candle, RV, source quality, and source agreement in backend/tests/unit/test_xau_quikstrike_fusion_fusion.py"
Task: "Add no-fabricated-context regression tests in backend/tests/unit/test_xau_quikstrike_fusion_fusion.py"
```

## Parallel Example: User Story 3

```text
Task: "Add fused XAU Vol-OI conversion tests for Matrix OI/OI Change/Volume and Vol2Vol context preservation in backend/tests/unit/test_xau_quikstrike_fusion_fusion.py"
Task: "Add downstream XAU Vol-OI orchestration integration test in backend/tests/integration/test_xau_quikstrike_fusion_flow.py"
Task: "Add forbidden wording tests for downstream fusion notes in backend/tests/unit/test_xau_quikstrike_fusion_fusion.py"
```

## Parallel Example: User Story 4

```text
Task: "Add create fusion report API contract tests in backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py"
Task: "Add list/detail/rows/missing-context API contract tests in backend/tests/contract/test_xau_quikstrike_fusion_api_contracts.py"
Task: "Add report-store list/detail/rows/missing-context read tests in backend/tests/unit/test_xau_quikstrike_fusion_report_store.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1.
4. Validate with focused loader, matching, fusion, and MVP integration tests.
5. Stop and review fused rows, coverage, provenance, and source agreement before downstream report creation.

### Incremental Delivery

1. Setup + foundation create the package, schemas, route skeleton, report-store safety, and fixtures.
2. US1 adds source report loading, matching, and fused rows.
3. US2 adds context transparency and basis/missing-context behavior.
4. US3 adds fused XAU input and optional downstream XAU report/reaction orchestration.
5. US4 adds API/dashboard inspection.
6. Polish validates the full workflow, frontend, artifact guard, and forbidden scope.

### Validation Commands

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_quikstrike_fusion_*.py -v
python -m pytest tests/integration/test_xau_quikstrike_fusion_*.py -v
python -m pytest tests/contract/test_xau_quikstrike_fusion_api_contracts.py -v
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
- Do not fabricate basis, IV/range, spot, open, candle, or realized-volatility data.
- Keep generated fusion, QuikStrike, XAU, and evidence artifacts ignored and untracked.
