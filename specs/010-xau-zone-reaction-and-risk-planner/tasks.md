# Tasks: XAU Zone Reaction and Risk Planner

**Input**: Design documents from `specs/010-xau-zone-reaction-and-risk-planner/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Required by the feature specification and user request. Automated tests must use synthetic XAU Vol-OI reports and synthetic reaction contexts only; they must not require live feeds, external downloads, private keys, broker access, or generated data committed to git.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing after shared setup and foundation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other tasks in the same phase because it touches different files or has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an exact file path.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the focused 010 package, model/API placeholders, report-store surface, and frontend placeholders without changing existing XAU wall generation.

- [ ] T001 Create `backend/src/xau_reaction/__init__.py` for the XAU reaction package
- [ ] T002 Create `backend/src/xau_reaction/freshness.py` with module skeleton and public function placeholders
- [ ] T003 Create `backend/src/xau_reaction/vol_regime.py` with module skeleton and public function placeholders
- [ ] T004 Create `backend/src/xau_reaction/open_regime.py` with module skeleton and public function placeholders
- [ ] T005 Create `backend/src/xau_reaction/acceptance.py` with module skeleton and public function placeholders
- [ ] T006 Create `backend/src/xau_reaction/classifier.py` with module skeleton and public function placeholders
- [ ] T007 Create `backend/src/xau_reaction/risk_plan.py` with module skeleton and public function placeholders
- [ ] T008 Create `backend/src/xau_reaction/report_store.py` with report persistence skeleton
- [ ] T009 Create `backend/src/xau_reaction/orchestration.py` with reaction report orchestration skeleton
- [ ] T010 Create `backend/src/models/xau_reaction.py` with schema placeholders from `specs/010-xau-zone-reaction-and-risk-planner/data-model.md`
- [ ] T011 Create `backend/src/api/routes/xau_reaction.py` with route placeholders from `specs/010-xau-zone-reaction-and-risk-planner/contracts/api.md`
- [ ] T012 [P] Add XAU reaction frontend type placeholders in `frontend/src/types/index.ts`
- [ ] T013 [P] Add XAU reaction frontend API client placeholders in `frontend/src/services/api.ts`
- [ ] T014 [P] Add placeholder reaction-report section in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T015 Verify generated `data/reports/xau_reaction/` paths are covered by `.gitignore` and `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared schemas, route registration, error handling, artifact persistence contracts, and synthetic fixtures required before user stories.

**CRITICAL**: No user story work can begin until this phase is complete.

### Tests for Foundation

- [ ] T016 [P] Add XAU reaction schema validation tests in `backend/tests/unit/test_xau_reaction_models.py`
- [ ] T017 [P] Add XAU reaction report-store path safety tests in `backend/tests/unit/test_xau_reaction_report_store.py`
- [ ] T018 [P] Add shared synthetic feature 006 report fixture helpers in `backend/tests/helpers/test_xau_reaction_data.py`
- [ ] T019 [P] Add route registration smoke tests in `backend/tests/contract/test_xau_reaction_api_contracts.py`

### Implementation for Foundation

- [ ] T020 Implement shared enums `XauReactionLabel`, freshness/open/volatility/acceptance states, report status, artifact type, artifact format, and event-risk state in `backend/src/models/xau_reaction.py`
- [ ] T021 Implement input schemas `XauReactionReportRequest`, `XauIntradayFreshnessInput`, `XauVolRegimeInput`, `XauOpenRegimeInput`, and `XauAcceptanceInput` in `backend/src/models/xau_reaction.py`
- [ ] T022 Implement output schemas `XauFreshnessState`, `XauVolRegimeState`, `XauOpenRegimeState`, `XauAcceptanceState`, `XauReactionRow`, `XauRiskPlan`, `XauReactionReport`, and `XauReactionReportSummary` in `backend/src/models/xau_reaction.py`
- [ ] T023 Implement response wrapper schemas for report list, reactions table, and risk-plan table in `backend/src/models/xau_reaction.py`
- [ ] T024 Implement research-only request validation, filesystem-safe report id validation, numeric bounds, and forbidden extra field behavior in `backend/src/models/xau_reaction.py`
- [ ] T025 Implement XAU reaction API error helpers or route-local structured errors in `backend/src/api/routes/xau_reaction.py`
- [ ] T026 Register `backend/src/api/routes/xau_reaction.py` under `/api/v1/xau` in `backend/src/main.py`
- [ ] T027 Implement report root and safe report directory helpers for `data/reports/xau_reaction/` in `backend/src/xau_reaction/report_store.py`
- [ ] T028 Add XAU reaction JSON and Markdown writer placeholders in `backend/src/reports/writer.py`

**Checkpoint**: Shared schemas, route surface, fixtures, and report storage contracts are ready.

---

## Phase 3: User Story 1 - Classify Zone Reactions From XAU Wall Evidence (Priority: P1) MVP

**Goal**: Classify synthetic XAU wall/zone scenarios into the six required reaction labels without emitting buy/sell execution signals.

**Independent Test**: Use synthetic feature 006 wall/zone rows plus precomputed freshness, volatility, open, and acceptance states to verify all six labels, confidence labels, explanations, invalidation/target references, and no-trade reasons.

### Tests for User Story 1

- [ ] T029 [P] [US1] Add classifier tests for `REVERSAL_CANDIDATE` and rejection evidence in `backend/tests/unit/test_xau_reaction_classifier.py`
- [ ] T030 [P] [US1] Add classifier tests for `BREAKOUT_CANDIDATE`, `SQUEEZE_RISK`, and `VACUUM_TO_NEXT_WALL` in `backend/tests/unit/test_xau_reaction_classifier.py`
- [ ] T031 [P] [US1] Add classifier tests for `PIN_MAGNET` and near-expiry high-OI evidence in `backend/tests/unit/test_xau_reaction_classifier.py`
- [ ] T032 [P] [US1] Add classifier tests for `NO_TRADE` gates and no buy/sell wording in `backend/tests/unit/test_xau_reaction_classifier.py`
- [ ] T033 [P] [US1] Add deterministic priority and tie-break tests in `backend/tests/unit/test_xau_reaction_classifier.py`

### Implementation for User Story 1

- [ ] T034 [US1] Implement reaction row id creation and source wall/zone traceability helpers in `backend/src/xau_reaction/classifier.py`
- [ ] T035 [US1] Implement hard no-trade gate evaluation for missing source context, unavailable basis, stale/prior-day/unknown freshness, thin hard blocks, conflicting evidence, and event-risk blocks in `backend/src/xau_reaction/classifier.py`
- [ ] T036 [US1] Implement `PIN_MAGNET` classification from near-expiry large OI near spot inside 1SD range in `backend/src/xau_reaction/classifier.py`
- [ ] T037 [US1] Implement `SQUEEZE_RISK` classification from accepted wall break with IV edge stress or flow expansion evidence in `backend/src/xau_reaction/classifier.py`
- [ ] T038 [US1] Implement `VACUUM_TO_NEXT_WALL` classification from low-OI gap and distant next-wall evidence in `backend/src/xau_reaction/classifier.py`
- [ ] T039 [US1] Implement `BREAKOUT_CANDIDATE` classification from close plus next-bar hold beyond wall buffer in `backend/src/xau_reaction/classifier.py`
- [ ] T040 [US1] Implement `REVERSAL_CANDIDATE` classification from high-score wall, rejection, stretched sigma, and fresh data in `backend/src/xau_reaction/classifier.py`
- [ ] T041 [US1] Implement fallback `NO_TRADE`, confidence labels, explanation notes, no-trade reasons, invalidation levels, target references, and next-wall references in `backend/src/xau_reaction/classifier.py`

**Checkpoint**: User Story 1 is independently testable with synthetic state fixtures and produces all six labels.

---

## Phase 4: User Story 2 - Gate Reactions With Freshness And Volatility Context (Priority: P2)

**Goal**: Compute intraday freshness and IV/RV/VRP context so stale, thin, prior-day, and volatility-stress cases affect confidence or no-trade outcomes.

**Independent Test**: Submit synthetic freshness and volatility inputs and verify freshness status, VRP values, IV edge state, RV extension state, confidence impact, and no-trade gate behavior.

### Tests for User Story 2

- [ ] T042 [P] [US2] Add freshness tests for `VALID`, `THIN`, `STALE`, `PRIOR_DAY`, and `UNKNOWN` in `backend/tests/unit/test_xau_reaction_freshness.py`
- [ ] T043 [P] [US2] Add freshness tests for missing timestamps, future timestamps, zero contracts, and confidence/no-trade impact in `backend/tests/unit/test_xau_reaction_freshness.py`
- [ ] T044 [P] [US2] Add realized volatility calculation tests in `backend/tests/unit/test_xau_reaction_vol_regime.py`
- [ ] T045 [P] [US2] Add IV/RV/VRP regime tests for IV premium, balanced, RV premium, and unknown states in `backend/tests/unit/test_xau_reaction_vol_regime.py`
- [ ] T046 [P] [US2] Add IV edge stress and RV-only extension tests in `backend/tests/unit/test_xau_reaction_vol_regime.py`

### Implementation for User Story 2

- [ ] T047 [US2] Implement timezone-safe intraday timestamp age calculation in `backend/src/xau_reaction/freshness.py`
- [ ] T048 [US2] Implement freshness precedence for `UNKNOWN`, `PRIOR_DAY`, `STALE`, `THIN`, and `VALID` in `backend/src/xau_reaction/freshness.py`
- [ ] T049 [US2] Implement freshness confidence impact and no-trade reason generation in `backend/src/xau_reaction/freshness.py`
- [ ] T050 [US2] Implement realized volatility calculation from price series and supplied RV passthrough in `backend/src/xau_reaction/vol_regime.py`
- [ ] T051 [US2] Implement `vrp = implied_volatility - realized_volatility` and VRP regime classification in `backend/src/xau_reaction/vol_regime.py`
- [ ] T052 [US2] Implement IV expected-range edge state classification in `backend/src/xau_reaction/vol_regime.py`
- [ ] T053 [US2] Implement RV extension state classification and volatility confidence impact notes in `backend/src/xau_reaction/vol_regime.py`
- [ ] T054 [US2] Integrate freshness and volatility state generation into `backend/src/xau_reaction/orchestration.py`

**Checkpoint**: User Stories 1 and 2 can classify using computed freshness and volatility context.

---

## Phase 5: User Story 3 - Use Session Open And Candle Reaction As Confirmation Evidence (Priority: P3)

**Goal**: Compute session-open context and wall acceptance/rejection states before promoting wall zones into reaction candidates.

**Independent Test**: Use synthetic open and candle OHLC/next-open inputs to verify open side, open distance, flip state, open support/resistance, wick rejection, failed breakout, accepted beyond wall, and confirmed breakout.

### Tests for User Story 3

- [ ] T055 [P] [US3] Add opening regime tests for open side and open distance in `backend/tests/unit/test_xau_reaction_open_regime.py`
- [ ] T056 [P] [US3] Add opening regime tests for crossed-open-without-acceptance and accepted flip in `backend/tests/unit/test_xau_reaction_open_regime.py`
- [ ] T057 [P] [US3] Add opening regime tests for support/resistance boundary context in `backend/tests/unit/test_xau_reaction_open_regime.py`
- [ ] T058 [P] [US3] Add acceptance tests for wick rejection and failed breakout in `backend/tests/unit/test_xau_reaction_acceptance.py`
- [ ] T059 [P] [US3] Add acceptance tests for accepted beyond wall and confirmed breakout in `backend/tests/unit/test_xau_reaction_acceptance.py`
- [ ] T060 [P] [US3] Add acceptance edge-case tests for missing next-bar open, zero buffer, and invalid OHLC order in `backend/tests/unit/test_xau_reaction_acceptance.py`

### Implementation for User Story 3

- [ ] T061 [US3] Implement open side and open distance classification in `backend/src/xau_reaction/open_regime.py`
- [ ] T062 [US3] Implement open flip state without assuming full flip before acceptance in `backend/src/xau_reaction/open_regime.py`
- [ ] T063 [US3] Implement open as support/resistance/boundary context in `backend/src/xau_reaction/open_regime.py`
- [ ] T064 [US3] Implement OHLC and buffer validation helpers in `backend/src/xau_reaction/acceptance.py`
- [ ] T065 [US3] Implement wick rejection and failed breakout classification in `backend/src/xau_reaction/acceptance.py`
- [ ] T066 [US3] Implement accepted beyond wall and confirmed breakout classification using close plus next-bar hold in `backend/src/xau_reaction/acceptance.py`
- [ ] T067 [US3] Integrate open-regime and acceptance-state generation into `backend/src/xau_reaction/orchestration.py`
- [ ] T068 [US3] Connect computed open and acceptance states to classifier calls in `backend/src/xau_reaction/orchestration.py`

**Checkpoint**: User Stories 1 through 3 can classify using computed freshness, volatility, open, and candle context.

---

## Phase 6: User Story 4 - Review Bounded Research Risk Plans (Priority: P4)

**Goal**: Create bounded research-only risk-plan annotations for non-`NO_TRADE` reactions and omit entry plans for `NO_TRADE`.

**Independent Test**: Use classified reaction rows with risk configuration to verify entry condition text, invalidation, stop buffer, targets, capped recovery legs, cancel conditions, risk notes, minimum reward/risk handling, and no plan for `NO_TRADE`.

### Tests for User Story 4

- [ ] T069 [P] [US4] Add risk planner tests for non-`NO_TRADE` reaction annotations in `backend/tests/unit/test_xau_reaction_risk_plan.py`
- [ ] T070 [P] [US4] Add risk planner tests for no entry plan on `NO_TRADE` in `backend/tests/unit/test_xau_reaction_risk_plan.py`
- [ ] T071 [P] [US4] Add risk planner tests for capped recovery legs, max total risk notes, and minimum reward/risk states in `backend/tests/unit/test_xau_reaction_risk_plan.py`
- [ ] T072 [P] [US4] Add risk planner tests for forbidden martingale, unlimited averaging, execution-ready, and live-readiness wording in `backend/tests/unit/test_xau_reaction_risk_plan.py`

### Implementation for User Story 4

- [ ] T073 [US4] Implement risk plan id creation and reaction-to-plan linking in `backend/src/xau_reaction/risk_plan.py`
- [ ] T074 [US4] Implement entry condition text, invalidation level, stop buffer, target 1, and target 2 annotations for non-`NO_TRADE` reactions in `backend/src/xau_reaction/risk_plan.py`
- [ ] T075 [US4] Implement no-plan behavior for `NO_TRADE` reactions in `backend/src/xau_reaction/risk_plan.py`
- [ ] T076 [US4] Implement max total risk cap notes, bounded recovery legs, and no unlimited averaging behavior in `backend/src/xau_reaction/risk_plan.py`
- [ ] T077 [US4] Implement minimum reward/risk state calculation and unavailable/below-minimum notes in `backend/src/xau_reaction/risk_plan.py`
- [ ] T078 [US4] Implement cancel condition generation from freshness, acceptance, volatility, open, and event-risk context in `backend/src/xau_reaction/risk_plan.py`
- [ ] T079 [US4] Integrate bounded risk planning into `backend/src/xau_reaction/orchestration.py`

**Checkpoint**: User Stories 1 through 4 produce reaction rows and bounded research-only risk plans.

---

## Phase 7: User Story 5 - Inspect Reaction Reports Through API And Dashboard (Priority: P5)

**Goal**: Create, persist, list, retrieve, and inspect XAU reaction reports through API endpoints and `/xau-vol-oi`.

**Independent Test**: Create a synthetic reaction report, retrieve list/detail/reactions/risk-plan endpoints, and confirm the dashboard renders required panels and tables without execution-signal wording.

### Tests for User Story 5

- [ ] T080 [P] [US5] Add create reaction report API contract tests in `backend/tests/contract/test_xau_reaction_api_contracts.py`
- [ ] T081 [P] [US5] Add list/detail/reactions/risk-plan API contract tests in `backend/tests/contract/test_xau_reaction_api_contracts.py`
- [ ] T082 [P] [US5] Add missing source report, invalid request, blocked source report, and missing reaction report contract tests in `backend/tests/contract/test_xau_reaction_api_contracts.py`
- [ ] T083 [P] [US5] Add end-to-end synthetic reaction report integration test in `backend/tests/integration/test_xau_reaction_flow.py`
- [ ] T084 [P] [US5] Add report persistence read/write tests for metadata, reactions, risk plans, JSON, and Markdown in `backend/tests/unit/test_xau_reaction_report_store.py`

### Implementation for User Story 5

- [ ] T085 [US5] Implement feature 006 source report loading and validation in `backend/src/xau_reaction/orchestration.py`
- [ ] T086 [US5] Implement full reaction report assembly with counts, warnings, limitations, artifacts, and research-only text in `backend/src/xau_reaction/orchestration.py`
- [ ] T087 [US5] Implement metadata, reaction row, risk plan row, JSON report, Markdown report, and optional Parquet persistence in `backend/src/xau_reaction/report_store.py`
- [ ] T088 [US5] Implement saved reaction report list/detail/reactions/risk-plan reads in `backend/src/xau_reaction/report_store.py`
- [ ] T089 [US5] Implement XAU reaction JSON and Markdown composition in `backend/src/reports/writer.py`
- [ ] T090 [US5] Implement `POST /api/v1/xau/reaction-reports` in `backend/src/api/routes/xau_reaction.py`
- [ ] T091 [US5] Implement `GET /api/v1/xau/reaction-reports` and `GET /api/v1/xau/reaction-reports/{report_id}` in `backend/src/api/routes/xau_reaction.py`
- [ ] T092 [US5] Implement `GET /api/v1/xau/reaction-reports/{report_id}/reactions` and `/risk-plan` in `backend/src/api/routes/xau_reaction.py`
- [ ] T093 [US5] Implement XAU reaction request/response types in `frontend/src/types/index.ts`
- [ ] T094 [US5] Implement `createXauReactionReport`, `listXauReactionReports`, `getXauReactionReport`, `getXauReactionRows`, and `getXauRiskPlanRows` in `frontend/src/services/api.ts`
- [ ] T095 [US5] Render reaction report selector, source report id, status, freshness badge, IV/RV/VRP panel, and session open panel in `frontend/src/app/xau-vol-oi/page.tsx`
- [ ] T096 [US5] Render acceptance/rejection state, reaction label table, bounded risk planner table, no-trade reasons, and research-only disclaimer in `frontend/src/app/xau-vol-oi/page.tsx`

**Checkpoint**: All user stories are independently functional through backend API and dashboard inspection.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation alignment, artifact guard, and forbidden-scope review.

- [ ] T097 [P] Update `specs/010-xau-zone-reaction-and-risk-planner/quickstart.md` if implemented request or response examples changed
- [ ] T098 Run backend import check from `backend/src/main.py`
- [ ] T099 Run focused backend tests for XAU reaction unit, integration, and contract coverage from `backend/tests/`
- [ ] T100 Run full backend pytest suite from `backend/tests/`
- [ ] T101 Run frontend production build from `frontend/package.json`
- [ ] T102 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [ ] T103 Run API smoke flow documented in `specs/010-xau-zone-reaction-and-risk-planner/quickstart.md` without committing generated reports
- [ ] T104 Run dashboard smoke flow for `/xau-vol-oi` documented in `specs/010-xau-zone-reaction-and-risk-planner/quickstart.md`
- [ ] T105 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [ ] T106 Update final validation notes and task completion status in `specs/010-xau-zone-reaction-and-risk-planner/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundation**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2; integrates computed freshness/volatility into US1 classifier flow.
- **Phase 5 US3**: Depends on Phase 2; integrates computed open/acceptance state into US1 classifier flow.
- **Phase 6 US4**: Depends on US1 reaction rows.
- **Phase 7 US5**: Depends on US1-US4 behavior and report shapes.
- **Phase 8 Polish**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: First MVP. Can classify with synthetic precomputed context states after foundation.
- **US2 (P2)**: Adds computed freshness and volatility context. Can be developed after foundation and integrated with US1.
- **US3 (P3)**: Adds computed open and candle context. Can be developed after foundation and integrated with US1.
- **US4 (P4)**: Requires reaction rows from US1.
- **US5 (P5)**: Requires report assembly from US1-US4 for full API/dashboard behavior.

### Within Each User Story

- Write tests first and confirm they fail before implementation.
- Models and shared schemas before service behavior.
- Pure context modules before orchestration integration.
- Orchestration before API route behavior.
- API behavior before frontend rendering.
- Each checkpoint should pass focused tests before moving to the next story.

### Parallel Opportunities

- T002-T009 can run in parallel after package naming is fixed because they touch different files.
- T012-T014 can run in parallel with backend setup.
- T016-T019 can run in parallel in the foundation phase.
- T029-T033 can run in parallel because they add independent classifier cases in one test file only if coordinated; otherwise sequence within that file.
- T042-T046 can run in parallel across freshness and volatility test files.
- T055-T060 can run in parallel across open-regime and acceptance test files.
- T069-T072 can run in parallel if test sections are coordinated in the risk-plan test file.
- T080-T084 can run in parallel across contract, integration, and report-store test files.
- T093-T096 can run in parallel with backend API implementation after response shapes stabilize.

## Parallel Example: User Story 2

```text
Task: "T042 Add freshness tests for VALID, THIN, STALE, PRIOR_DAY, and UNKNOWN in backend/tests/unit/test_xau_reaction_freshness.py"
Task: "T044 Add realized volatility calculation tests in backend/tests/unit/test_xau_reaction_vol_regime.py"
Task: "T045 Add IV/RV/VRP regime tests for IV premium, balanced, RV premium, and unknown states in backend/tests/unit/test_xau_reaction_vol_regime.py"
```

## Parallel Example: User Story 3

```text
Task: "T055 Add opening regime tests for open side and open distance in backend/tests/unit/test_xau_reaction_open_regime.py"
Task: "T058 Add acceptance tests for wick rejection and failed breakout in backend/tests/unit/test_xau_reaction_acceptance.py"
Task: "T059 Add acceptance tests for accepted beyond wall and confirmed breakout in backend/tests/unit/test_xau_reaction_acceptance.py"
```

## Parallel Example: User Story 5

```text
Task: "T080 Add create reaction report API contract tests in backend/tests/contract/test_xau_reaction_api_contracts.py"
Task: "T083 Add end-to-end synthetic reaction report integration test in backend/tests/integration/test_xau_reaction_flow.py"
Task: "T084 Add report persistence read/write tests for metadata, reactions, risk plans, JSON, and Markdown in backend/tests/unit/test_xau_reaction_report_store.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1 with synthetic precomputed context states.
4. Stop and validate all classifier tests.
5. Confirm outputs remain research-only and contain no buy/sell execution wording.

### Incremental Delivery

1. Add US1 reaction classifier labels.
2. Add US2 freshness and volatility context engines.
3. Add US3 open and candle context engines.
4. Add US4 bounded risk planner annotations.
5. Add US5 report persistence, API endpoints, and dashboard inspection.
6. Finish Phase 8 validation and forbidden-scope review.

### Guardrails

- Do not redesign feature 006 XAU wall report generation.
- Do not add live trading, paper trading, shadow trading, broker integration, private keys, wallet/private-key handling, real execution, order routing, position management, Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML training.
- Do not emit buy/sell execution signals, profitability claims, predictive claims, safety claims, or live-readiness claims.
- Do not commit imported local datasets or generated report artifacts.

## Summary

- Total tasks: 106
- US1 tasks: 13
- US2 tasks: 13
- US3 tasks: 14
- US4 tasks: 11
- US5 tasks: 17
- Suggested MVP scope: Phase 1, Phase 2, and Phase 3 only
