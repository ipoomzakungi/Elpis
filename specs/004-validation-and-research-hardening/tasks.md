# Tasks: Validation and Research Hardening

**Input**: Design documents from `/specs/004-validation-and-research-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Tests are included because the feature specification explicitly requires measurable validation, backend tests, frontend build validation, API contract checks, real-data missing-data handling, and artifact guard checks.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested as an independent research-hardening increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other marked tasks in the same phase because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: Maps implementation tasks to user stories from `spec.md`.
- Every task includes exact repository file paths.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare test helpers and CI/artifact-guard scaffolding without changing backtest behavior.

- [x] T001 [P] Create validation test data builders for processed feature rows in `backend/tests/helpers/test_backtest_validation_data.py`
- [x] T002 [P] Add validation report fixture helpers for runs, trades, metrics, and equity rows in `backend/tests/helpers/test_backtest_validation_reports.py`
- [x] T003 [P] Create artifact guard script placeholder with ignored-path policy constants in `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add shared schemas, storage, and routing structure required by all validation stories.

**CRITICAL**: No user story implementation should begin until this phase is complete.

- [x] T004 Add validation request/response, capital sizing, stress profile, sensitivity, walk-forward, coverage, and concentration schemas in `backend/src/models/backtest.py`
- [x] T005 Add validation artifact enum values and backward-compatible report fields in `backend/src/models/backtest.py`
- [x] T006 [P] Create validation orchestration module with empty runner interfaces in `backend/src/backtest/validation.py`
- [x] T007 Add validation artifact write/read/list methods under `data/reports/{validation_run_id}` in `backend/src/backtest/report_store.py`
- [x] T008 Add validation report JSON and Markdown composition entry points in `backend/src/reports/writer.py`
- [x] T009 Register static validation API route skeletons before dynamic backtest run routes in `backend/src/api/routes/backtests.py`
- [x] T010 [P] Add frontend validation types for run summaries, reports, stress rows, sensitivity rows, walk-forward rows, and concentration rows in `frontend/src/types/index.ts`

**Checkpoint**: Foundation ready; user story implementation can now begin in priority order or in parallel where files do not conflict.

---

## Phase 3: User Story 1 - Correct Baselines, Sizing, and Equity (Priority: P1) MVP

**Goal**: Ensure buy-and-hold, active sizing, no-leverage caps, equity curves, and metrics cannot mislead researchers through accounting artifacts.

**Independent Test**: Run controlled backtests with buy-and-hold, active strategies, tiny stop distances, open positions, and multiple modes, then verify sizing, capping, equity, drawdown, and metric labels.

### Tests for User Story 1

- [x] T011 [P] [US1] Add buy-and-hold capital fraction sizing tests in `backend/tests/integration/test_backtest_comparison_flow.py`
- [x] T012 [P] [US1] Add no-leverage notional cap and cap-event tests in `backend/tests/unit/test_backtest_portfolio.py` and `backend/tests/integration/test_backtest_comparison_flow.py`
- [x] T013 [P] [US1] Add per-mode metric separation and comparison-label tests in `backend/tests/unit/test_backtest_metrics.py` and `backend/tests/integration/test_backtest_comparison_flow.py`
- [x] T014 [P] [US1] Add mark-to-market total equity and realized-only labeling tests in `backend/tests/unit/test_backtest_equity_mark_to_market.py`

### Implementation for User Story 1

- [x] T015 [US1] Implement capital-fraction sizing and no-leverage notional cap calculation in `backend/src/backtest/portfolio.py`
- [x] T016 [US1] Preserve price-only and no-trade baselines while marking buy-and-hold as passive capital-based baseline in `backend/src/strategies/baselines.py`
- [x] T017 [US1] Route buy-and-hold through capital sizing and active strategies through capped risk sizing in `backend/src/backtest/engine.py`
- [x] T018 [US1] Add cap-event, realized equity, unrealized PnL, total equity, and equity-basis fields to core backtest schemas in `backend/src/models/backtest.py`
- [x] T019 [US1] Build mark-to-market total equity and drawdown from close prices for open positions in `backend/src/backtest/engine.py`
- [x] T020 [US1] Promote per-mode strategy and baseline metrics while relabeling any aggregate summary as comparison-only in `backend/src/backtest/metrics.py`
- [x] T021 [US1] Update report JSON and Markdown labels for independent mode metrics, passive baselines, cap events, and realized versus total equity in `backend/src/reports/writer.py`
- [x] T022 [US1] Update backend API metrics response rows for per-mode strategy and baseline categories in `backend/src/api/routes/backtests.py`
- [x] T023 [US1] Update frontend backtest report tables for separate active strategy and passive baseline metrics in `frontend/src/app/backtests/page.tsx`
- [x] T024 [US1] Update frontend summary cards to avoid unlabeled global portfolio return display in `frontend/src/components/panels/BacktestSummaryCards.tsx`
- [x] T025 [US1] Update frontend equity and trade type fields for cap events and realized/total equity in `frontend/src/types/index.ts`

**Checkpoint**: US1 should pass its unit tests and a controlled multi-mode backtest should show separate, correctly labeled active strategy and baseline metrics.

---

## Phase 4: User Story 2 - Stress Costs and Parameter Robustness (Priority: P2)

**Goal**: Evaluate whether results remain stable under higher costs and modest parameter changes without making profitability claims.

**Independent Test**: Run one saved configuration through the four predefined cost profiles and a bounded parameter grid, then verify stress/sensitivity tables and fragility flags.

### Tests for User Story 2

- [x] T026 [P] [US2] Add fee/slippage stress profile tests in `backend/tests/unit/test_backtest_cost_stress.py`
- [x] T027 [P] [US2] Add bounded parameter grid and fragility flag tests in `backend/tests/unit/test_backtest_sensitivity.py`
- [x] T028 [P] [US2] Add stress and sensitivity artifact integration tests in `backend/tests/integration/test_backtest_validation_flow.py`

### Implementation for User Story 2

- [x] T029 [US2] Implement predefined `normal`, `high_fee`, `high_slippage`, and `worst_reasonable_cost` profiles in `backend/src/backtest/validation.py`
- [x] T030 [US2] Implement stress reruns for each eligible strategy and baseline mode in `backend/src/backtest/validation.py`
- [x] T031 [US2] Implement bounded parameter sensitivity grid execution and grid-size validation in `backend/src/backtest/validation.py`
- [x] T032 [US2] Implement fragility flag calculation for isolated strong parameter settings in `backend/src/backtest/validation.py`
- [x] T033 [US2] Persist stress and sensitivity output tables as validation artifacts in `backend/src/backtest/report_store.py`
- [x] T034 [US2] Add stress and sensitivity sections to validation report JSON and Markdown in `backend/src/reports/writer.py`
- [x] T035 [US2] Add stress and sensitivity validation endpoints in `backend/src/api/routes/backtests.py`
- [x] T036 [US2] Add validation API client methods for stress and sensitivity endpoints in `frontend/src/services/api.ts`
- [x] T037 [US2] Add stress and sensitivity frontend types in `frontend/src/types/index.ts`
- [x] T038 [US2] Render fee/slippage stress and parameter sensitivity tables in `frontend/src/app/backtests/page.tsx`

**Checkpoint**: US2 should produce stress and sensitivity report sections for all eligible modes without claiming profitability or live readiness.

---

## Phase 5: User Story 3 - Validate Across Time Windows (Priority: P3)

**Goal**: Split historical data chronologically and report per-window behavior without introducing model training, paper trading, shadow trading, or live trading.

**Independent Test**: Run validation over enough rows for at least three windows and over too few rows for one window, then verify date ranges, row counts, metrics, and insufficiency notes.

### Tests for User Story 3

- [x] T039 [P] [US3] Add chronological walk-forward split tests in `backend/tests/unit/test_backtest_walk_forward.py`
- [x] T040 [P] [US3] Add insufficient-window integration tests in `backend/tests/integration/test_backtest_walk_forward_flow.py`

### Implementation for User Story 3

- [x] T041 [US3] Implement chronological non-overlapping split generation in `backend/src/backtest/validation.py`
- [x] T042 [US3] Implement per-split validation runs, row counts, trade counts, and insufficient-data status in `backend/src/backtest/validation.py`
- [x] T043 [US3] Persist walk-forward split output tables in `backend/src/backtest/report_store.py`
- [x] T044 [US3] Add walk-forward section to validation report JSON and Markdown in `backend/src/reports/writer.py`
- [x] T045 [US3] Add walk-forward validation endpoint in `backend/src/api/routes/backtests.py`
- [x] T046 [US3] Add walk-forward frontend types in `frontend/src/types/index.ts`
- [x] T047 [US3] Add walk-forward API client method and render chronological split table in `frontend/src/services/api.ts` and `frontend/src/app/backtests/page.tsx`

**Checkpoint**: US3 should show chronological validation windows and clearly mark insufficient windows without hidden omissions.

---

## Phase 6: User Story 4 - Audit Regime Coverage and Trade Concentration (Priority: P4)

**Goal**: Reveal whether results depend on sparse regimes, too few trades, concentrated winners, loss streaks, or unrecovered drawdowns.

**Independent Test**: Run a known trade set and feature dataset, then verify regime counts, trade concentration, top/worst trades, consecutive losses, and drawdown recovery status.

### Tests for User Story 4

- [x] T048 [P] [US4] Add regime coverage tests for expected and unknown regimes in `backend/tests/unit/test_backtest_regime_coverage.py`
- [x] T049 [P] [US4] Add trade concentration and drawdown recovery tests in `backend/tests/unit/test_backtest_concentration.py`
- [x] T050 [P] [US4] Add concentration endpoint contract tests in `backend/tests/contract/test_backtest_validation_contracts.py`

### Implementation for User Story 4

- [x] T051 [US4] Implement regime bar counts, trades per regime, and return by regime in `backend/src/backtest/validation.py`
- [x] T052 [US4] Implement top 1, top 5, and top 10 trade profit contribution plus best/worst trade extraction in `backend/src/backtest/metrics.py`
- [x] T053 [US4] Implement maximum consecutive losses and drawdown recovery status/time helpers in `backend/src/backtest/metrics.py`
- [x] T054 [US4] Assemble regime coverage and trade concentration report sections in `backend/src/backtest/validation.py`
- [x] T055 [US4] Persist coverage and concentration artifacts in `backend/src/backtest/report_store.py`
- [x] T056 [US4] Add coverage and concentration sections to validation report JSON and Markdown in `backend/src/reports/writer.py`
- [x] T057 [US4] Add concentration and coverage endpoint in `backend/src/api/routes/backtests.py`
- [x] T058 [US4] Add coverage and concentration frontend types in `frontend/src/types/index.ts`
- [x] T059 [US4] Render regime coverage, best/worst trades, concentration warnings, and drawdown recovery status in `frontend/src/app/backtests/page.tsx`

**Checkpoint**: US4 should expose concentration and regime weaknesses directly in API/report/dashboard output.

---

## Phase 7: User Story 5 - Run Real-Data Research Validation and Automated Checks (Priority: P5)

**Goal**: Support real BTCUSDT 15m validation when processed features exist and add automated repository validation without private secrets.

**Independent Test**: Attempt real-data validation with and without processed features, then run backend tests, frontend build, and artifact guard checks.

### Tests for User Story 5

- [x] T060 [P] [US5] Add validation run/list/detail API contract tests in `backend/tests/contract/test_backtest_validation_contracts.py`
- [x] T061 [P] [US5] Add real-data validation success and missing-data instruction tests in `backend/tests/integration/test_real_data_validation_flow.py`
- [x] T062 [P] [US5] Add generated artifact guard tests for ignored outputs in `backend/tests/integration/test_generated_artifact_guard.py`

### Implementation for User Story 5

- [x] T063 [US5] Implement full validation run/list/detail endpoint behavior in `backend/src/api/routes/backtests.py`
- [x] T064 [US5] Implement real-data processed feature preflight and actionable missing-data instructions in `backend/src/backtest/validation.py`
- [x] T065 [US5] Add validation-specific not-found and invalid-config helpers in `backend/src/api/validation.py`
- [x] T066 [US5] Store full validation report metadata, warnings, source identity, and artifact references in `backend/src/backtest/report_store.py`
- [x] T067 [US5] Add frontend validation run/list/detail API client methods in `frontend/src/services/api.ts`
- [x] T068 [US5] Render validation report selector, warnings, source identity, and research-only disclaimers in `frontend/src/app/backtests/page.tsx`
- [x] T069 [US5] Implement generated artifact guard script checks for `data/reports`, `data/processed`, `*.parquet`, `*.duckdb`, `.env*`, `.venv`, `.next`, and `node_modules` in `scripts/check_generated_artifacts.ps1`
- [x] T070 [US5] Add GitHub Actions backend, frontend, and artifact guard workflow in `.github/workflows/validation.yml`
- [x] T071 [US5] Update validation quickstart with final endpoint names and CI commands in `specs/004-validation-and-research-hardening/quickstart.md`

**Checkpoint**: US5 should validate real-data readiness, give clear missing-data instructions, and provide repeatable automated checks without secrets.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, documentation alignment, and guardrail review across all stories.

- [ ] T072 [P] Run backend import and full pytest validation documented in `specs/004-validation-and-research-hardening/quickstart.md`
- [ ] T073 [P] Run frontend install and production build documented in `frontend/package.json`
- [ ] T074 Run validation API smoke flow documented in `specs/004-validation-and-research-hardening/quickstart.md`
- [ ] T075 Run dashboard validation smoke flow documented in `specs/004-validation-and-research-hardening/quickstart.md`
- [ ] T076 Review dependencies and source for forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, and `.github/workflows/validation.yml`
- [ ] T077 Review generated artifact exclusions in `.gitignore` and `scripts/check_generated_artifacts.ps1`
- [ ] T078 Update task completion status and notes in `specs/004-validation-and-research-hardening/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational; MVP and prerequisite for trusting later validation outputs.
- **User Story 2 (Phase 4)**: Depends on Foundational and benefits from US1 accounting correctness.
- **User Story 3 (Phase 5)**: Depends on Foundational and benefits from US1 accounting correctness.
- **User Story 4 (Phase 6)**: Depends on Foundational and benefits from US1 metrics/equity correctness.
- **User Story 5 (Phase 7)**: Depends on validation artifacts and endpoints from US2-US4 for complete real-data and CI validation.
- **Polish (Phase 8)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational; should be completed first as the MVP because it fixes accounting correctness.
- **US2 (P2)**: Can start after Foundational, but final interpretation depends on US1 sizing/equity fixes.
- **US3 (P3)**: Can start after Foundational, but final metrics should use US1 corrected metrics.
- **US4 (P4)**: Can start after Foundational, but concentration and recovery should use US1 corrected equity/metrics.
- **US5 (P5)**: Should integrate after US1-US4 validation surfaces exist.

### Within Each User Story

- Write tests first and confirm they fail before implementation.
- Update models before services/runners.
- Update runners before report persistence.
- Update report persistence before API read endpoints.
- Update backend API/types before frontend rendering.
- Validate each story at its checkpoint before moving to lower-priority stories.

---

## Parallel Opportunities

- Setup tasks T001-T003 can run in parallel.
- Foundational tasks T006 and T010 can run in parallel after T004-T005 are understood; T007-T009 touch shared backend files and should be sequenced.
- Test files within each user story can be authored in parallel.
- Frontend type/API tasks can run in parallel with backend report writer tasks once endpoint contracts are stable.
- US2, US3, and US4 runner tests can be drafted in parallel after Foundational, but implementation should reconcile shared `backend/src/backtest/validation.py` changes carefully.

---

## Parallel Example: User Story 1

```bash
Task: "T011 [US1] Add buy-and-hold capital fraction sizing tests in backend/tests/unit/test_buy_hold_sizing.py"
Task: "T012 [US1] Add no-leverage notional cap and cap-event tests in backend/tests/unit/test_backtest_notional_cap.py"
Task: "T013 [US1] Add per-mode metric separation and comparison-label tests in backend/tests/unit/test_backtest_mode_metrics.py"
Task: "T014 [US1] Add mark-to-market total equity and realized-only labeling tests in backend/tests/unit/test_backtest_equity_mark_to_market.py"
```

## Parallel Example: User Story 2

```bash
Task: "T026 [US2] Add fee/slippage stress profile tests in backend/tests/unit/test_backtest_cost_stress.py"
Task: "T027 [US2] Add bounded parameter grid and fragility flag tests in backend/tests/unit/test_backtest_sensitivity.py"
Task: "T037 [US2] Add stress and sensitivity frontend types in frontend/src/types/index.ts"
```

## Parallel Example: User Story 3

```bash
Task: "T039 [US3] Add chronological walk-forward split tests in backend/tests/unit/test_backtest_walk_forward.py"
Task: "T040 [US3] Add insufficient-window integration tests in backend/tests/integration/test_backtest_walk_forward_flow.py"
Task: "T046 [US3] Add walk-forward frontend types and API client method in frontend/src/types/index.ts"
```

## Parallel Example: User Story 4

```bash
Task: "T048 [US4] Add regime coverage tests for expected and unknown regimes in backend/tests/unit/test_backtest_regime_coverage.py"
Task: "T049 [US4] Add trade concentration and drawdown recovery tests in backend/tests/unit/test_backtest_concentration.py"
Task: "T058 [US4] Add coverage and concentration frontend types in frontend/src/types/index.ts"
```

## Parallel Example: User Story 5

```bash
Task: "T060 [US5] Add validation run/list/detail API contract tests in backend/tests/contract/test_backtest_validation_contracts.py"
Task: "T061 [US5] Add real-data validation success and missing-data instruction tests in backend/tests/integration/test_real_data_validation_flow.py"
Task: "T070 [US5] Add GitHub Actions backend, frontend, and artifact guard workflow in .github/workflows/validation.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 for US1.
3. Run US1 unit tests and one controlled multi-mode backtest.
4. Stop and validate that accounting, sizing, equity, and per-mode labels are trustworthy before adding robustness layers.

### Incremental Delivery

1. US1: Correct accounting, sizing, equity, and metric labels.
2. US2: Add cost stress and sensitivity validation.
3. US3: Add chronological split validation.
4. US4: Add regime coverage and trade concentration analysis.
5. US5: Add real-data readiness, API/dashboard completeness, CI, and artifact guardrails.

### Parallel Team Strategy

1. Team completes Setup and Foundational phases together.
2. One engineer owns US1 because it touches shared accounting and metrics.
3. After US1 stabilizes, separate engineers can work US2, US3, and US4 tests/runners with careful coordination on `backend/src/backtest/validation.py`.
4. US5 integrates all validation outputs into real-data flow, CI, and final dashboard/report smoke validation.

---

## Notes

- Keep the feature research-only: do not add live trading, paper trading, shadow trading, private keys, broker integration, real order execution, wallet/private-key handling, Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML training.
- Do not claim profitability, predictive power, safety, or live-trading readiness in code, reports, dashboard text, tests, or documentation.
- Generated validation artifacts must remain under ignored data paths and must not be committed.
- Commit only stable checkpoints after relevant backend, frontend, API, dashboard, and artifact guard checks pass.
