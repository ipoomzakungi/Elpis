# Tasks: XAU Forward Journal Outcome Price Updater

**Input**: Design documents from `specs/016-xau-forward-journal-outcome-price-updater/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required by the feature specification. Test tasks are listed before implementation tasks in each story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete tasks.
- **[Story]**: User story label for story phases only.
- Every task includes an explicit file path.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the feature 016 module, model, route, frontend, fixture, and artifact placeholders without implementing behavior.

- [X] T001 Create price data module placeholder in `backend/src/xau_forward_journal/price_data.py`
- [X] T002 Create price outcome module placeholder in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T003 Add price-source model placeholders in `backend/src/models/xau_forward_journal.py`
- [X] T004 Add price-update report-store placeholder methods in `backend/src/xau_forward_journal/report_store.py`
- [X] T005 Add price coverage and price update route placeholders in `backend/src/api/routes/xau_forward_journal.py`
- [X] T006 [P] Add synthetic price fixture folder marker in `backend/tests/fixtures/xau_forward_journal_price/.gitkeep`
- [X] T007 [P] Add price data unit test placeholder in `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T008 [P] Add price outcome unit test placeholder in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T009 [P] Add price update integration test placeholder in `backend/tests/integration/test_xau_forward_journal_price_update_flow.py`
- [X] T010 Add frontend price coverage type placeholders in `frontend/src/types/index.ts`
- [X] T011 Add frontend price update API client placeholders in `frontend/src/services/api.ts`
- [X] T012 Add placeholder price coverage display area to Forward Journal panel in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T013 Verify existing generated artifact guard covers price-update report roots in `scripts/check_generated_artifacts.ps1`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared schemas, validation, path safety, source labels, and route skeleton behavior required by all user stories.

**CRITICAL**: No user story implementation should start until this phase is complete.

- [X] T014 [P] Add enum and request/response validation tests for price labels, coverage statuses, directions, and forbidden fields in `backend/tests/unit/test_xau_forward_journal_models.py`
- [X] T015 [P] Add OHLC schema validation tests for required columns, aliases, duplicates, ordering, missing files, and impossible OHLC values in `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T016 [P] Add source-label limitation tests for spot, GC futures, Yahoo GC=F, GLD, local CSV, local Parquet, and unknown proxy in `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T017 [P] Add price update artifact path-safety and serialization tests in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [X] T018 [P] Add route registration and placeholder contract tests for price update and coverage endpoints in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [X] T019 Implement `XauForwardPriceSourceLabel`, `XauForwardPriceCoverageStatus`, `XauForwardPriceDirection`, and price artifact enum values in `backend/src/models/xau_forward_journal.py`
- [X] T020 Implement `XauForwardPriceDataUpdateRequest` and `XauForwardPriceCoverageRequest` in `backend/src/models/xau_forward_journal.py`
- [X] T021 Implement `XauForwardOhlcCandle`, `XauForwardPriceSource`, `XauForwardOutcomeWindowRange`, and `XauForwardPriceCoverageWindow` in `backend/src/models/xau_forward_journal.py`
- [X] T022 Implement `XauForwardPriceOutcomeMetrics`, `XauForwardMissingCandleItem`, `XauForwardPriceCoverageSummary`, `XauForwardPriceOutcomeUpdateReport`, `XauForwardPriceCoverageResponse`, and `XauForwardPriceOutcomeUpdateResponse` in `backend/src/models/xau_forward_journal.py`
- [X] T023 Extend `XauForwardOutcomeObservation` with optional range, direction, price source, coverage, and price update id fields in `backend/src/models/xau_forward_journal.py`
- [X] T024 Extend XAU forward journal forbidden-content validation for price update request paths, notes, and source fields in `backend/src/models/xau_forward_journal.py`
- [X] T025 Implement price-source validation, proxy limitation helpers, and price-data exceptions in `backend/src/xau_forward_journal/price_data.py`
- [X] T026 Implement path-safe OHLC file resolution and CSV/Parquet format detection in `backend/src/xau_forward_journal/price_data.py`
- [X] T027 Implement price outcome constants, window ordering, and error types in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T028 Implement price-update artifact path helpers and JSON/Markdown serialization stubs in `backend/src/xau_forward_journal/report_store.py`
- [X] T029 Implement structured placeholder errors for price coverage and price update routes in `backend/src/api/routes/xau_forward_journal.py`
- [X] T030 Add frontend price coverage/update TypeScript types in `frontend/src/types/index.ts`
- [X] T031 Add frontend price coverage/update API client method signatures in `frontend/src/services/api.ts`

**Checkpoint**: Foundation ready. User stories can be implemented after T001-T031.

---

## Phase 3: User Story 1 - Update Outcomes From Price Data (Priority: P1) MVP

**Goal**: Update a saved Forward Journal entry from approved OHLC candles, compute observed high/low/close/range/direction where coverage is complete, preserve immutable snapshot evidence, and persist an outcome update report.

**Independent Test**: Load one synthetic journal entry with pending windows, apply synthetic complete OHLC candles for one or more windows, and verify updated outcomes include computed metrics while original snapshot/source fields remain unchanged.

### Tests for User Story 1

- [X] T032 [P] [US1] Add OHLC CSV and Parquet loading tests with synthetic complete candles in `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T033 [P] [US1] Add complete-window metric tests for high, low, close, range, observed timestamps, and candle counts in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T034 [P] [US1] Add direction calculation tests for up, down, flat, and unavailable snapshot price in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T035 [P] [US1] Add immutable snapshot regression test for price-derived updates in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T036 [P] [US1] Add price update report persistence tests for coverage JSON, report JSON, report Markdown, entry JSON, and outcomes JSON in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [X] T037 [P] [US1] Add integration test updating a synthetic journal entry from synthetic complete candles in `backend/tests/integration/test_xau_forward_journal_price_update_flow.py`
- [X] T038 [P] [US1] Add API contract tests for successful `POST /outcomes/from-price-data`, missing journal, missing OHLC file, invalid OHLC schema, and forbidden content in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`

### Implementation for User Story 1

- [X] T039 [US1] Implement OHLC CSV and Parquet loading with normalized candle output in `backend/src/xau_forward_journal/price_data.py`
- [X] T040 [US1] Implement OHLC schema, timestamp, duplicate, ordering, and high-low-open-close validation in `backend/src/xau_forward_journal/price_data.py`
- [X] T041 [US1] Implement fixed `30m`, `1h`, and `4h` window calculation from journal snapshot time in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T042 [US1] Implement complete-window coverage detection and observed candle slicing in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T043 [US1] Implement high, low, close, range, observation start/end, and candle count metric calculation in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T044 [US1] Implement direction-from-snapshot calculation with unavailable direction when snapshot price is missing in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T045 [US1] Implement price-derived outcome observation construction for complete windows in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T046 [US1] Implement price update orchestration that loads the journal entry, applies complete-window outcomes, and preserves immutable snapshot/source fields in `backend/src/xau_forward_journal/orchestration.py`
- [X] T047 [US1] Implement price update report persistence and refreshed journal outcome persistence in `backend/src/xau_forward_journal/report_store.py`
- [X] T048 [US1] Implement `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data` in `backend/src/api/routes/xau_forward_journal.py`
- [X] T049 [US1] Implement structured price update API errors for missing journal, missing OHLC file, invalid source, invalid schema, conflict, forbidden field, and unsafe note cases in `backend/src/api/routes/xau_forward_journal.py`

**Checkpoint**: US1 delivers the MVP: a pending journal entry can be updated from complete synthetic OHLC candles without mutating original snapshot evidence.

---

## Phase 4: User Story 2 - Review Price Coverage Before Or After Update (Priority: P2)

**Goal**: Return per-window source coverage, missing candle checklist, and proxy limitations without requiring raw file inspection or outcome mutation.

**Independent Test**: Request coverage for a synthetic journal entry against synthetic candles with complete, partial, and missing windows and verify coverage summary, missing checklist, source labels, and proxy notes.

### Tests for User Story 2

- [X] T050 [P] [US2] Add outcome window calculation tests for `30m`, `1h`, `4h`, `session_close`, and `next_day` in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T051 [P] [US2] Add partial and missing coverage tests with explicit missing-candle checklist expectations in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T052 [P] [US2] Add session-close and next-day boundary limitation tests when trusted boundaries cannot be determined in `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T053 [P] [US2] Add proxy limitation tests for coverage summaries and update reports in `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T054 [P] [US2] Add coverage response serialization tests in `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [X] T055 [P] [US2] Add API contract tests for `GET /price-coverage`, invalid source label, missing file, missing journal, and forbidden query content in `backend/tests/contract/test_xau_forward_journal_api_contracts.py`

### Implementation for User Story 2

- [X] T056 [US2] Implement source-symbol consistency validation for XAUUSD spot, GC futures, Yahoo GC=F, GLD, local files, and unknown proxy in `backend/src/xau_forward_journal/price_data.py`
- [X] T057 [US2] Implement source metadata, row count, first/last timestamp, warnings, and proxy limitations in `backend/src/xau_forward_journal/price_data.py`
- [X] T058 [US2] Implement session-close and next-day window derivation with explicit boundary limitations when conventions are unavailable in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T059 [US2] Implement complete, partial, missing, invalid, and blocked coverage status evaluation for all five windows in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T060 [US2] Implement missing candle checklist generation for missing and partial windows in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T061 [US2] Implement coverage summary assembly with source label, source symbol, complete windows, partial windows, missing windows, warnings, limitations, and research-only warnings in `backend/src/xau_forward_journal/price_outcome.py`
- [X] T062 [US2] Integrate coverage read workflow into journal orchestration without mutating outcomes in `backend/src/xau_forward_journal/orchestration.py`
- [X] T063 [US2] Implement `GET /api/v1/xau/forward-journal/entries/{journal_id}/price-coverage` in `backend/src/api/routes/xau_forward_journal.py`
- [X] T064 [US2] Implement coverage API structured errors for invalid source, missing file, missing journal, invalid schema, blocked boundary, forbidden field, and unsafe query cases in `backend/src/api/routes/xau_forward_journal.py`
- [X] T065 [US2] Update price update orchestration to use full coverage summary so missing windows remain pending and partial windows become inconclusive in `backend/src/xau_forward_journal/orchestration.py`

**Checkpoint**: US2 exposes complete, partial, missing, and proxy-limited price coverage before or after an update.

---

## Phase 5: User Story 3 - Inspect Updated Outcomes In The Dashboard (Priority: P3)

**Goal**: Show price data source, coverage status, missing windows, updated outcome labels, proxy limitations, pending/inconclusive state, artifact paths, and research-only disclaimers in the existing `/xau-vol-oi` Forward Journal panel.

**Independent Test**: Open the Forward Journal panel for a synthetic entry after a price update and verify coverage, source labels, missing windows, proxy notes, updated metrics, and disclaimers are visible.

### Tests for User Story 3

- [X] T066 [P] [US3] Add frontend type compile coverage for price source, coverage, missing checklist, update report, and extended outcomes in `frontend/src/types/index.ts`
- [X] T067 [P] [US3] Add frontend API client compile coverage for price coverage and price update methods in `frontend/src/services/api.ts`
- [X] T068 [P] [US3] Add dashboard data-shape regression coverage for price coverage fields in `frontend/src/app/xau-vol-oi/page.tsx`

### Implementation for User Story 3

- [X] T069 [US3] Implement frontend `XauForwardPriceSource`, `XauForwardPriceCoverageWindow`, `XauForwardMissingCandleItem`, `XauForwardPriceCoverageResponse`, and `XauForwardPriceOutcomeUpdateResponse` types in `frontend/src/types/index.ts`
- [X] T070 [US3] Extend frontend `XauForwardOutcomeObservation` and dashboard data types with price source, range, direction, coverage, and price update fields in `frontend/src/types/index.ts`
- [X] T071 [US3] Implement `getXauForwardJournalPriceCoverage` and `updateXauForwardJournalOutcomesFromPriceData` client methods in `frontend/src/services/api.ts`
- [X] T072 [US3] Load selected journal price coverage together with existing Forward Journal entry and outcomes in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T073 [US3] Render price source label, source symbol, proxy limitation notes, and research-only text in the Forward Journal panel in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T074 [US3] Render per-window coverage status, missing windows, partial reasons, and missing candle checklist in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T075 [US3] Render updated outcome high, low, close, range, direction, coverage status, and price update artifact paths in `frontend/src/app/xau-vol-oi/page.tsx`
- [X] T076 [US3] Render loading, empty, and error states for price coverage data in `frontend/src/app/xau-vol-oi/page.tsx`

**Checkpoint**: US3 makes updated price outcomes and coverage limitations visible through the existing local dashboard.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation alignment, artifact safety, API/dashboard smoke, and forbidden-scope review.

- [X] T077 Update API and dashboard examples in `specs/016-xau-forward-journal-outcome-price-updater/quickstart.md` if implemented request or response shapes change
- [X] T078 Run backend import check from `backend/src/main.py`
- [X] T079 Run focused unit tests for `backend/tests/unit/test_xau_forward_journal_price_data.py`
- [X] T080 Run focused unit tests for `backend/tests/unit/test_xau_forward_journal_price_outcome.py`
- [X] T081 Run focused unit tests for `backend/tests/unit/test_xau_forward_journal_models.py` and `backend/tests/unit/test_xau_forward_journal_report_store.py`
- [X] T082 Run focused integration tests for `backend/tests/integration/test_xau_forward_journal_price_update_flow.py`
- [X] T083 Run focused API contract tests for `backend/tests/contract/test_xau_forward_journal_api_contracts.py`
- [X] T084 Run the full backend test suite from `backend/tests/`
- [X] T085 Run frontend dependency install and production build from `frontend/package.json`
- [X] T086 Run generated artifact guard from `scripts/check_generated_artifacts.ps1`
- [X] T087 Run the API smoke flow documented in `specs/016-xau-forward-journal-outcome-price-updater/quickstart.md` without committing generated price-update reports
- [X] T088 Run the dashboard smoke flow for `/xau-vol-oi` documented in `specs/016-xau-forward-journal-outcome-price-updater/quickstart.md`
- [X] T089 Review forbidden v0 scope in `backend/pyproject.toml`, `frontend/package.json`, `.github/workflows/validation.yml`, `backend/src/`, and `frontend/src/`
- [X] T090 Confirm generated price-update artifacts remain ignored and untracked using repository root `git status --ignored --short`
- [X] T091 Update final validation notes and task completion status in `specs/016-xau-forward-journal-outcome-price-updater/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: No dependencies.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks all user stories.
- **Phase 3 US1**: Depends on Phase 2 and is the MVP.
- **Phase 4 US2**: Depends on Phase 2. It can be developed alongside US1 after shared coverage primitives exist, but final update semantics should align with US1.
- **Phase 5 US3**: Depends on backend response shapes from US1 and US2.
- **Phase 6 Polish**: Depends on all implemented phases.

### User Story Dependencies

- **US1 (P1)**: Required MVP. No dependency on later stories.
- **US2 (P2)**: Uses the same foundational price-data and coverage primitives as US1; independent coverage read can be demonstrated without mutating outcomes.
- **US3 (P3)**: Requires saved entries and backend coverage/update response shapes from US1-US2.

### Parallel Opportunities

- T006-T009 can run in parallel after setup begins because they create distinct fixture/test files.
- T014-T018 can run in parallel because they target distinct validation areas.
- T032-T038 can run in parallel because they target distinct US1 test concerns.
- T050-T055 can run in parallel because they target distinct US2 test concerns.
- T066-T068 can run in parallel with backend work once response shapes are stable.
- US1 and US2 can proceed in parallel after Phase 2 if work is coordinated around `price_outcome.py` and `orchestration.py`.

---

## Parallel Example: User Story 1

```text
Task: "Add OHLC CSV and Parquet loading tests with synthetic complete candles in backend/tests/unit/test_xau_forward_journal_price_data.py"
Task: "Add complete-window metric tests for high, low, close, range, observed timestamps, and candle counts in backend/tests/unit/test_xau_forward_journal_price_outcome.py"
Task: "Add price update report persistence tests for coverage JSON, report JSON, report Markdown, entry JSON, and outcomes JSON in backend/tests/unit/test_xau_forward_journal_report_store.py"
Task: "Add API contract tests for successful POST /outcomes/from-price-data, missing journal, missing OHLC file, invalid OHLC schema, and forbidden content in backend/tests/contract/test_xau_forward_journal_api_contracts.py"
```

## Parallel Example: User Story 2

```text
Task: "Add outcome window calculation tests for 30m, 1h, 4h, session_close, and next_day in backend/tests/unit/test_xau_forward_journal_price_outcome.py"
Task: "Add proxy limitation tests for coverage summaries and update reports in backend/tests/unit/test_xau_forward_journal_price_data.py"
Task: "Add coverage response serialization tests in backend/tests/unit/test_xau_forward_journal_report_store.py"
Task: "Add API contract tests for GET /price-coverage, invalid source label, missing file, missing journal, and forbidden query content in backend/tests/contract/test_xau_forward_journal_api_contracts.py"
```

## Parallel Example: User Story 3

```text
Task: "Add frontend type compile coverage for price source, coverage, missing checklist, update report, and extended outcomes in frontend/src/types/index.ts"
Task: "Add frontend API client compile coverage for price coverage and price update methods in frontend/src/services/api.ts"
Task: "Add dashboard data-shape regression coverage for price coverage fields in frontend/src/app/xau-vol-oi/page.tsx"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1 setup.
2. Complete Phase 2 foundation.
3. Complete Phase 3 US1.
4. Validate with focused price-data, price-outcome, report-store, integration, and update API tests.
5. Stop and review that complete synthetic candles update outcomes and preserve immutable snapshot evidence.

### Incremental Delivery

1. Setup + foundation add models, source labels, request validation, modules, and route/client placeholders.
2. US1 adds complete-candle outcome updates and persistence.
3. US2 adds standalone coverage reads, missing/partial semantics, and proxy coverage limitations.
4. US3 adds dashboard inspection.
5. Polish validates backend, frontend, artifact safety, API/dashboard smoke, and forbidden scope.

### Validation Commands

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_forward_journal_price_data.py -v
python -m pytest tests/unit/test_xau_forward_journal_price_outcome.py -v
python -m pytest tests/unit/test_xau_forward_journal_models.py tests/unit/test_xau_forward_journal_report_store.py -v
python -m pytest tests/integration/test_xau_forward_journal_price_update_flow.py -v
python -m pytest tests/contract/test_xau_forward_journal_api_contracts.py -v
python -m pytest tests/ -q

cd ../frontend
npm install
npm run build

cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## Notes

- Do not implement QuikStrike extraction, browser automation, endpoint replay, or paid-vendor ingestion in this feature.
- Do not store cookies, tokens, headers, HAR files, screenshots, viewstate, private URLs, credentials, or endpoint replay payloads.
- Do not add live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet/private-key handling, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- Do not fabricate spot, futures, candle, coverage, direction, or outcome data.
- Do not claim profitability, predictive power, safety, or live readiness.
- Keep generated journal, price-update, OHLC, and report artifacts ignored and untracked.

---

## Final Validation Notes

- Backend import check passed: `python -c "from src.main import app; print('backend import ok')"`.
- Focused backend feature suite passed: 56 tests across price data, price outcomes, models, report store, integration flow, and API contracts.
- Focused Ruff check passed on touched backend files and tests.
- Full backend suite passed: 646 tests.
- Frontend dependency install completed with existing npm audit warnings; production build passed with `npm run build`.
- Backend runtime smoke passed: `/health` and `/docs` returned 200 on local uvicorn.
- Frontend runtime smoke passed: `/xau-vol-oi` returned 200 on local Next dev server.
- Generated artifact guard passed, and `git status --ignored --short` showed generated data/build/cache paths remain ignored.
- No generated price-update reports were committed.
