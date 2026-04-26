# Tasks: Backtest and Reporting Engine

**Input**: Design documents from `/specs/003-backtest-reporting-engine/`  
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md)

**Tests**: Test tasks are included because the specification, plan, and quickstart require backend unit, integration, contract, compatibility, and frontend build validation.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested as an independent increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks in the same phase
- **[Story]**: Maps a task to a user story (`US1`, `US2`, `US3`, `US4`)
- Every task includes an exact file path

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the minimal source and test file structure for the backtest/reporting feature.

- [X] T001 Create backend package initializers in backend/src/backtest/__init__.py, backend/src/strategies/__init__.py, and backend/src/reports/__init__.py
- [X] T002 [P] Create backend test skeleton files in backend/tests/unit/test_backtest_metrics.py, backend/tests/unit/test_backtest_portfolio.py, backend/tests/unit/test_grid_strategy.py, backend/tests/unit/test_breakout_strategy.py, and backend/tests/unit/test_baselines.py
- [X] T003 [P] Create backend integration and contract test skeleton files in backend/tests/integration/test_backtest_engine_flow.py, backend/tests/integration/test_backtest_comparison_flow.py, backend/tests/integration/test_backtest_reproducibility.py, backend/tests/integration/test_backtest_compatibility.py, and backend/tests/contract/test_backtest_api_contracts.py
- [X] T004 [P] Create frontend report inspection skeleton files in frontend/src/app/backtests/page.tsx, frontend/src/components/charts/EquityCurveChart.tsx, frontend/src/components/charts/DrawdownChart.tsx, and frontend/src/components/panels/BacktestSummaryCards.tsx
- [X] T005 Review and preserve generated report artifact ignore rules in .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared schemas, fixtures, artifact paths, and error handling used by every user story.

**Critical**: No user story implementation should begin until this phase is complete.

- [X] T006 [P] Define backtest enums, request schemas, run schemas, trade schemas, equity schemas, metric schemas, and artifact schemas in backend/src/models/backtest.py
- [X] T007 [P] Add synthetic processed-feature DataFrame builders and isolated report directory fixtures in backend/tests/conftest.py
- [X] T008 Implement report directory configuration and path resolution helpers in backend/src/config.py
- [X] T009 [P] Implement JSON and Markdown report composition helpers in backend/src/reports/writer.py
- [X] T010 Implement report artifact read/write/list foundations under data/reports in backend/src/backtest/report_store.py
- [X] T011 Add shared backtest validation and not-found error helpers in backend/src/api/validation.py

**Checkpoint**: Foundation ready. User story implementation can begin.

---

## Phase 3: User Story 1 - Run Research Backtests From Processed Features (Priority: P1)

**Goal**: Run a reproducible v0 backtest from processed BTCUSDT 15m-style feature data and save metadata, trades, equity, metrics, and report artifacts.

**Independent Test**: Run a synthetic processed-feature backtest and verify deterministic run metadata, trade log, equity curve, metrics, report artifacts, and structured failures without any live trading behavior.

### Tests for User Story 1

- [X] T012 [P] [US1] Add unit tests for total return, drawdown, profit factor, win rate, expectancy, no-trade, only-win, and only-loss metrics in backend/tests/unit/test_backtest_metrics.py
- [X] T013 [P] [US1] Add unit tests for fixed fractional sizing, fees, slippage, long/short PnL, max-one-position, end-of-data exits, and stop-first same-bar exits in backend/tests/unit/test_backtest_portfolio.py
- [X] T014 [P] [US1] Add integration tests for deterministic synthetic backtest artifacts under an isolated reports path in backend/tests/integration/test_backtest_engine_flow.py
- [X] T015 [P] [US1] Add contract tests for POST /api/v1/backtests/run success, missing features, invalid config, and no-trade responses in backend/tests/contract/test_backtest_api_contracts.py

### Implementation for User Story 1

- [X] T016 [P] [US1] Implement metrics calculations and undefined-ratio notes in backend/src/backtest/metrics.py
- [X] T017 [P] [US1] Implement position sizing, fee/slippage application, long/short accounting, stop/take-profit exits, stop-first ambiguity handling, and equity tracking in backend/src/backtest/portfolio.py
- [X] T018 [US1] Implement processed feature loading, required-column validation, final-bar signal skipping, next-bar-open entry, max-one-position orchestration, and deterministic run output in backend/src/backtest/engine.py
- [X] T019 [US1] Implement metadata.json, config.json, trades.parquet, equity.parquet, metrics.json, report.json, and optional report.md writes in backend/src/backtest/report_store.py
- [X] T020 [US1] Connect report summary composition to saved run outputs in backend/src/reports/writer.py
- [X] T021 [US1] Implement POST /api/v1/backtests/run endpoint in backend/src/api/routes/backtests.py
- [X] T022 [US1] Register the backtests router with the existing /api/v1 prefix in backend/src/main.py
- [X] T023 [US1] Update run-backtest quickstart validation notes for completed, failed, and no-trade runs in specs/003-backtest-reporting-engine/quickstart.md

**Checkpoint**: User Story 1 can run and inspect a completed local research backtest from processed feature data.

---

## Phase 4: User Story 2 - Compare Regime Strategies Against Baselines (Priority: P2)

**Goal**: Compare regime-aware grid/range and breakout modes against buy-and-hold, price-only breakout, and optional no-trade baselines under shared assumptions.

**Independent Test**: Run one report configuration that includes regime-aware strategies and baselines, then verify return, drawdown, trade, regime, strategy mode, and baseline comparison outputs.

### Tests for User Story 2

- [ ] T024 [P] [US2] Add unit tests for RANGE-only grid/range long and optional short signal behavior in backend/tests/unit/test_grid_strategy.py
- [ ] T025 [P] [US2] Add unit tests for BREAKOUT_UP and BREAKOUT_DOWN signal behavior and non-breakout suppression in backend/tests/unit/test_breakout_strategy.py
- [ ] T026 [P] [US2] Add unit tests for buy-and-hold, price-only breakout, and no-trade baseline generation in backend/tests/unit/test_baselines.py
- [ ] T027 [P] [US2] Add integration tests for strategy-vs-baseline comparison outputs in backend/tests/integration/test_backtest_comparison_flow.py

### Implementation for User Story 2

- [ ] T028 [US2] Implement RANGE-only grid/range signal generation with lower-range longs, optional upper-range shorts, midpoint or next-level take profit, ATR-buffered stops, and no martingale state in backend/src/strategies/grid_strategy.py
- [ ] T029 [US2] Implement BREAKOUT_UP and BREAKOUT_DOWN signal generation with optional shorts, stop-back-inside-range or ATR stops, and risk-multiple take profit in backend/src/strategies/breakout_strategy.py
- [ ] T030 [US2] Implement buy-and-hold, price-only breakout, and no-trade baseline generation in backend/src/strategies/baselines.py
- [ ] T031 [US2] Wire strategy mode dispatch, baseline dispatch, and shared accounting assumptions into backend/src/backtest/engine.py
- [ ] T032 [US2] Add return-by-regime, return-by-strategy-mode, return-by-symbol-provider, and baseline comparison calculations in backend/src/backtest/metrics.py
- [ ] T033 [US2] Persist strategy mode, regime performance, and baseline comparison sections in backend/src/reports/writer.py

**Checkpoint**: User Story 2 can compare regime-aware strategies with baselines without making profitability or live-readiness claims.

---

## Phase 5: User Story 3 - Inspect Backtest Reports Through API and Dashboard (Priority: P3)

**Goal**: Browse saved runs and inspect metrics, trades, equity, drawdown, regime performance, strategy comparisons, and baseline comparisons through the API and dashboard.

**Independent Test**: Create one run, retrieve list/detail/trades/metrics/equity through API endpoints, and view the same report in the dashboard within the local v0 app.

### Tests for User Story 3

- [ ] T034 [US3] Add contract tests for GET /api/v1/backtests, GET /api/v1/backtests/{run_id}, GET /api/v1/backtests/{run_id}/trades, GET /api/v1/backtests/{run_id}/metrics, GET /api/v1/backtests/{run_id}/equity, and missing artifact responses in backend/tests/contract/test_backtest_api_contracts.py

### Implementation for User Story 3

- [ ] T035 [US3] Implement saved run listing and run detail artifact reads in backend/src/backtest/report_store.py
- [ ] T036 [US3] Implement GET /api/v1/backtests and GET /api/v1/backtests/{run_id} endpoints in backend/src/api/routes/backtests.py
- [ ] T037 [US3] Implement GET /api/v1/backtests/{run_id}/trades, GET /api/v1/backtests/{run_id}/metrics, and GET /api/v1/backtests/{run_id}/equity endpoints with pagination and structured errors in backend/src/api/routes/backtests.py
- [ ] T038 [P] [US3] Add BacktestRun, BacktestTrade, BacktestMetrics, BacktestEquityPoint, and BacktestArtifact TypeScript types in frontend/src/types/index.ts
- [ ] T039 [US3] Add backtest run/list/detail/trades/metrics/equity API client methods in frontend/src/services/api.ts
- [ ] T040 [P] [US3] Implement reusable equity curve chart in frontend/src/components/charts/EquityCurveChart.tsx
- [ ] T041 [P] [US3] Implement reusable drawdown chart in frontend/src/components/charts/DrawdownChart.tsx
- [ ] T042 [P] [US3] Implement compact summary metric cards in frontend/src/components/panels/BacktestSummaryCards.tsx
- [ ] T043 [US3] Implement /backtests report inspection page with run selector, summary cards, equity and drawdown charts, trade table, regime table, strategy table, baseline table, loading state, and error state in frontend/src/app/backtests/page.tsx
- [ ] T044 [US3] Add backtest report navigation entry to the existing dashboard header in frontend/src/components/ui/Header.tsx

**Checkpoint**: User Story 3 can inspect completed backtest reports from API endpoints and the dashboard.

---

## Phase 6: User Story 4 - Preserve Research-Only Reproducibility and Compatibility (Priority: P4)

**Goal**: Ensure saved reports document assumptions and limitations, reproduce from unchanged inputs, reject live-trading concepts, and preserve existing provider/feature/dashboard behavior.

**Independent Test**: Re-run a saved config on unchanged synthetic input and confirm identical outputs, while guardrail and compatibility tests confirm no forbidden v0 behavior or existing workflow regression.

### Tests for User Story 4

- [ ] T045 [P] [US4] Add unit tests rejecting live-trading fields, leverage above 1, max_positions above 1, invalid fee/slippage/risk, and unexpected config keys in backend/tests/unit/test_backtest_guardrails.py
- [ ] T046 [P] [US4] Add reproducibility integration tests comparing rerun trade logs, equity curves, metrics, and metadata for unchanged inputs in backend/tests/integration/test_backtest_reproducibility.py
- [ ] T047 [P] [US4] Add compatibility integration tests for existing provider metadata, download, feature processing, regime, and dashboard-support API flows in backend/tests/integration/test_backtest_compatibility.py

### Implementation for User Story 4

- [ ] T048 [US4] Enforce Pydantic extra-forbid config behavior, v0 leverage guardrails, max-one-position guardrails, and forbidden live-trading field rejection in backend/src/models/backtest.py
- [ ] T049 [US4] Add data identity, assumption snapshots, limitation notes, artifact content hashes, and deterministic config serialization in backend/src/backtest/report_store.py
- [ ] T050 [US4] Add research-only disclaimer and no-intrabar limitation text to JSON and Markdown reports in backend/src/reports/writer.py
- [ ] T051 [US4] Display assumptions, data identity, limitations, and no-profitability/no-live-readiness wording in frontend/src/app/backtests/page.tsx
- [ ] T052 [US4] Update reproducibility and forbidden-technology validation steps in specs/003-backtest-reporting-engine/quickstart.md

**Checkpoint**: User Story 4 preserves reproducibility, compatibility, and v0 research-only boundaries.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the whole feature, keep generated artifacts out of source control, and prepare a stable checkpoint.

- [ ] T053 [P] Run backend import and full pytest validation using the commands in specs/003-backtest-reporting-engine/quickstart.md
- [ ] T054 [P] Run frontend npm install and npm run build validation using the commands in specs/003-backtest-reporting-engine/quickstart.md
- [ ] T055 Run the manual backtest API smoke test from specs/003-backtest-reporting-engine/quickstart.md against backend/src/main.py
- [ ] T056 Run the dashboard report inspection smoke test from specs/003-backtest-reporting-engine/quickstart.md against frontend/src/app/backtests/page.tsx
- [ ] T057 Review source and docs for forbidden v0 technologies and live-trading claims in backend/src, frontend/src, specs/003-backtest-reporting-engine/spec.md, specs/003-backtest-reporting-engine/plan.md, and specs/003-backtest-reporting-engine/quickstart.md
- [ ] T058 Confirm generated report artifacts remain ignored and untracked by reviewing .gitignore and data/reports
- [ ] T059 Record final validation results and stable checkpoint notes in specs/003-backtest-reporting-engine/tasks.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup** has no dependencies and can start immediately.
- **Phase 2: Foundational** depends on Phase 1 and blocks every user story.
- **Phase 3: User Story 1** depends on Phase 2 and is the MVP.
- **Phase 4: User Story 2** depends on Phase 2, and can begin before US1 endpoints if engine interfaces are stable, but final comparison validation depends on the US1 engine and metrics.
- **Phase 5: User Story 3** depends on persisted report artifacts from US1 and comparison data from US2 for the complete dashboard experience.
- **Phase 6: User Story 4** depends on the implemented config, artifact, report, and dashboard flows from US1 through US3.
- **Phase 7: Polish** depends on all selected user stories being complete.

### User Story Dependencies

- **US1 (P1)**: MVP. Can start after Foundational. No dependency on other user stories.
- **US2 (P2)**: Can start after Foundational for strategy unit tests and implementations, then integrates with US1 engine outputs.
- **US3 (P3)**: Requires saved artifacts and report-store reads from US1, plus comparison shapes from US2 for full coverage.
- **US4 (P4)**: Validates and hardens the completed v0 feature while preserving existing workflows.

### Within Each User Story

- Write tests first and verify they fail before implementation.
- Models and shared fixtures precede services and endpoints.
- Strategy signal generation stays separate from portfolio accounting.
- Backend API endpoints precede frontend API client integration.
- Each checkpoint should pass its independent test before the next priority story is treated as complete.

---

## Parallel Opportunities

- T002, T003, T004 can run in parallel after T001 because they create different files.
- T006, T007, and T009 can run in parallel during Foundational once package skeletons exist.
- US1 tests T012 through T015 can run in parallel because they touch different test files.
- US1 implementation T016 and T017 can run in parallel before T018 integrates them.
- US2 tests T024 through T027 can run in parallel because they touch different files.
- US2 strategy implementations T028 through T030 can run in parallel before T031 integrates dispatch.
- US3 chart and panel components T040 through T042 can run in parallel with backend GET endpoint work T035 through T037.
- US4 tests T045 through T047 can run in parallel because they validate different risk areas.
- Polish validations T053 and T054 can run in parallel in separate terminals.

---

## Parallel Example: User Story 1

```text
Task: "T012 [US1] Add unit tests for total return, drawdown, profit factor, win rate, expectancy, no-trade, only-win, and only-loss metrics in backend/tests/unit/test_backtest_metrics.py"
Task: "T013 [US1] Add unit tests for fixed fractional sizing, fees, slippage, long/short PnL, max-one-position, end-of-data exits, and stop-first same-bar exits in backend/tests/unit/test_backtest_portfolio.py"
Task: "T014 [US1] Add integration tests for deterministic synthetic backtest artifacts under an isolated reports path in backend/tests/integration/test_backtest_engine_flow.py"
Task: "T015 [US1] Add contract tests for POST /api/v1/backtests/run success, missing features, invalid config, and no-trade responses in backend/tests/contract/test_backtest_api_contracts.py"
```

## Parallel Example: User Story 2

```text
Task: "T024 [US2] Add unit tests for RANGE-only grid/range long and optional short signal behavior in backend/tests/unit/test_grid_strategy.py"
Task: "T025 [US2] Add unit tests for BREAKOUT_UP and BREAKOUT_DOWN signal behavior and non-breakout suppression in backend/tests/unit/test_breakout_strategy.py"
Task: "T026 [US2] Add unit tests for buy-and-hold, price-only breakout, and no-trade baseline generation in backend/tests/unit/test_baselines.py"
Task: "T027 [US2] Add integration tests for strategy-vs-baseline comparison outputs in backend/tests/integration/test_backtest_comparison_flow.py"
```

## Parallel Example: User Story 3

```text
Task: "T035 [US3] Implement saved run listing and run detail artifact reads in backend/src/backtest/report_store.py"
Task: "T040 [US3] Implement reusable equity curve chart in frontend/src/components/charts/EquityCurveChart.tsx"
Task: "T041 [US3] Implement reusable drawdown chart in frontend/src/components/charts/DrawdownChart.tsx"
Task: "T042 [US3] Implement compact summary metric cards in frontend/src/components/panels/BacktestSummaryCards.tsx"
```

## Parallel Example: User Story 4

```text
Task: "T045 [US4] Add unit tests rejecting live-trading fields, leverage above 1, max_positions above 1, invalid fee/slippage/risk, and unexpected config keys in backend/tests/unit/test_backtest_guardrails.py"
Task: "T046 [US4] Add reproducibility integration tests comparing rerun trade logs, equity curves, metrics, and metadata for unchanged inputs in backend/tests/integration/test_backtest_reproducibility.py"
Task: "T047 [US4] Add compatibility integration tests for existing provider metadata, download, feature processing, regime, and dashboard-support API flows in backend/tests/integration/test_backtest_compatibility.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundational schemas, fixtures, paths, and artifact primitives.
3. Complete Phase 3 User Story 1.
4. Stop and validate that a synthetic processed-feature backtest writes deterministic artifacts under `data/reports/{run_id}`.
5. Confirm no live-trading behavior, private API fields, or generated report artifacts are introduced.

### Incremental Delivery

1. Setup plus Foundational gives the shared backtest/report shell.
2. US1 gives a runnable local backtest and artifacts.
3. US2 adds regime-vs-baseline research comparisons.
4. US3 makes reports inspectable through API and dashboard.
5. US4 hardens reproducibility, compatibility, and research-only wording.

### Validation Strategy

1. Run backend unit tests for the story being implemented.
2. Run story-specific integration and contract tests.
3. Run `python -c "from src.main import app; print('backend import ok')"` from `backend` after backend API changes.
4. Run `npm run build` from `frontend` after dashboard changes.
5. Run the quickstart smoke path only after the implementation reaches a stable checkpoint.

---

## Notes

- Keep strategy signal logic in `backend/src/strategies/` and portfolio/accounting logic in `backend/src/backtest/portfolio.py`.
- Keep generated report artifacts under `data/reports/` and out of source control.
- Keep the feature research-only: no live trading, private keys, broker integration, real order execution, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML training.
- Do not redesign the existing provider, feature, regime, or dashboard root flows while adding the backtest report page.