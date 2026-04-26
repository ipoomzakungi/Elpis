# Tasks: OI Regime Lab v0

**Input**: Design documents from `/specs/001-oi-regime-lab/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Tests will be added in Polish phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/src/`, `frontend/src/`
- Paths follow plan.md structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create backend project structure with pyproject.toml at backend/pyproject.toml
- [ ] T002 Create frontend project structure with Next.js at frontend/
- [ ] T003 [P] Create data directories (data/raw, data/processed, data/reports) at data/
- [ ] T004 [P] Create backend __init__.py files at backend/src/__init__.py, backend/src/models/__init__.py, backend/src/services/__init__.py, backend/src/repositories/__init__.py, backend/src/api/__init__.py, backend/src/api/routes/__init__.py
- [ ] T005 [P] Create .gitignore with data/, __pycache__, .env, node_modules at .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Create Pydantic models for MarketData, OpenInterest, FundingRate in backend/src/models/market_data.py
- [ ] T007 [P] Create Pydantic models for Feature and Regime in backend/src/models/features.py and backend/src/models/regime.py
- [ ] T008 [P] Create Pydantic model for DataQuality in backend/src/models/market_data.py
- [ ] T009 Create configuration settings (paths, API URLs, periods) in backend/src/config.py
- [ ] T010 [P] Create Parquet repository for file operations in backend/src/repositories/parquet_repo.py
- [ ] T011 [P] Create DuckDB repository for SQL operations in backend/src/repositories/duckdb_repo.py
- [ ] T012 Create FastAPI app entry point with CORS and router setup in backend/src/main.py
- [ ] T013 [P] Create FastAPI dependencies (repositories, services) in backend/src/api/dependencies.py
- [ ] T014 [P] Create TypeScript types for all entities in frontend/src/types/index.ts
- [ ] T015 [P] Create API client service in frontend/src/services/api.ts
- [ ] T016 [P] Create data fetching hooks in frontend/src/hooks/useMarketData.ts

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Download Market Data (Priority: P1) 🎯 MVP

**Goal**: User can download BTCUSDT 15m OHLCV, Open Interest, and Funding Rate data from Binance Futures

**Independent Test**: Trigger data download via API and verify Parquet files are created with correct timestamps and values

### Implementation for User Story 1

- [ ] T017 [P] [US1] Create Binance API client with rate limiting in backend/src/services/binance_client.py
- [ ] T018 [P] [US1] Create OHLCV download endpoint (POST /api/v1/download) in backend/src/api/routes/market_data.py
- [ ] T019 [US1] Implement OHLCV data download from /fapi/v1/klines in backend/src/services/data_downloader.py
- [ ] T020 [US1] Implement Open Interest download from /futures/data/openInterestHist in backend/src/services/data_downloader.py
- [ ] T021 [US1] Implement Funding Rate download from /fapi/v1/fundingRate in backend/src/services/data_downloader.py
- [ ] T022 [US1] Implement Parquet save for OHLCV at data/raw/btcusdt_15m_ohlcv.parquet in backend/src/repositories/parquet_repo.py
- [ ] T023 [US1] Implement Parquet save for Open Interest at data/raw/btcusdt_15m_oi.parquet in backend/src/repositories/parquet_repo.py
- [ ] T024 [US1] Implement Parquet save for Funding Rate at data/raw/btcusdt_15m_funding.parquet in backend/src/repositories/parquet_repo.py
- [ ] T025 [US1] Create GET /api/v1/market-data/ohlcv endpoint in backend/src/api/routes/market_data.py
- [ ] T026 [US1] Create GET /api/v1/market-data/open-interest endpoint in backend/src/api/routes/market_data.py
- [ ] T027 [US1] Create GET /api/v1/market-data/funding-rate endpoint in backend/src/api/routes/market_data.py

**Checkpoint**: User can download data via API and query it back. Parquet files exist in data/raw/.

---

## Phase 4: User Story 2 - Compute Features and Classify Regimes (Priority: P2)

**Goal**: User can process raw data into features and classify each bar into RANGE, BREAKOUT_UP, BREAKOUT_DOWN, or AVOID

**Independent Test**: Process downloaded data through feature pipeline and verify regime labels are assigned correctly

### Implementation for User Story 2

- [ ] T028 [P] [US2] Implement ATR computation (14-period) in backend/src/services/feature_engine.py
- [ ] T029 [P] [US2] Implement range_high, range_low, range_mid computation (20-period) in backend/src/services/feature_engine.py
- [ ] T030 [P] [US2] Implement OI change percentage computation in backend/src/services/feature_engine.py
- [ ] T031 [P] [US2] Implement volume ratio computation (20-period avg) in backend/src/services/feature_engine.py
- [ ] T032 [P] [US2] Implement funding rate features (current, change, cumsum) in backend/src/services/feature_engine.py
- [ ] T033 [US2] Implement data merge by timestamp (OHLCV + OI + Funding) in backend/src/services/feature_engine.py
- [ ] T034 [US2] Implement regime classification rules in backend/src/services/regime_classifier.py
- [ ] T035 [US2] Create POST /api/v1/process endpoint in backend/src/api/routes/features.py
- [ ] T036 [US2] Create GET /api/v1/features endpoint in backend/src/api/routes/features.py
- [ ] T037 [US2] Create GET /api/v1/regimes endpoint in backend/src/api/routes/regimes.py
- [ ] T038 [US2] Implement feature Parquet save at data/processed/btcusdt_15m_features.parquet in backend/src/repositories/parquet_repo.py
- [ ] T039 [US2] Implement DuckDB views for features in backend/src/repositories/duckdb_repo.py

**Checkpoint**: User can process data via API and query features/regimes. Processed Parquet exists in data/processed/.

---

## Phase 5: User Story 3 - Research Dashboard (Priority: P3)

**Goal**: User can view candlestick charts, OI, funding rate, volume, regime labels, and data quality in web dashboard

**Independent Test**: Open dashboard in browser and verify all charts and panels display correctly

### Implementation for User Story 3

- [ ] T040 [P] [US3] Create dashboard layout with Header component in frontend/src/app/layout.tsx and frontend/src/components/ui/Header.tsx
- [ ] T041 [P] [US3] Create CandlestickChart component with range lines in frontend/src/components/charts/CandlestickChart.tsx
- [ ] T042 [P] [US3] Create OIChart component with OI change overlay in frontend/src/components/charts/OIChart.tsx
- [ ] T043 [P] [US3] Create FundingChart component in frontend/src/components/charts/FundingChart.tsx
- [ ] T044 [P] [US3] Create VolumeChart component with volume ratio in frontend/src/components/charts/VolumeChart.tsx
- [ ] T045 [P] [US3] Create RegimePanel component in frontend/src/components/panels/RegimePanel.tsx
- [ ] T046 [P] [US3] Create DataQualityPanel component in frontend/src/components/panels/DataQualityPanel.tsx
- [ ] T047 [US3] Create main dashboard page integrating all charts in frontend/src/app/page.tsx
- [ ] T048 [US3] Create GET /api/v1/data-quality endpoint in backend/src/api/routes/data_quality.py
- [ ] T049 [US3] Implement data quality checks (missing, duplicates, last updated) in backend/src/services/data_quality.py
- [ ] T050 [US3] Add download and process buttons to dashboard in frontend/src/app/page.tsx
- [ ] T051 [US3] Add LoadingSpinner component in frontend/src/components/ui/LoadingSpinner.tsx
- [ ] T052 [US3] Configure Tailwind CSS and global styles in frontend/tailwind.config.ts and frontend/src/app/globals.css

**Checkpoint**: Full dashboard is functional with all charts, regime labels, and data quality panel.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T053 [P] Add error handling and logging to all backend services in backend/src/services/
- [ ] T054 [P] Add input validation to all API endpoints in backend/src/api/routes/
- [ ] T055 [P] Create quickstart validation script in backend/tests/test_quickstart.py
- [ ] T056 [P] Add unit tests for feature engine in backend/tests/unit/test_feature_engine.py
- [ ] T057 [P] Add unit tests for regime classifier in backend/tests/unit/test_regime_classifier.py
- [ ] T058 [P] Add unit tests for Binance client in backend/tests/unit/test_binance_client.py
- [ ] T059 [P] Add integration tests for data download flow in backend/tests/integration/test_download_flow.py
- [ ] T060 [P] Add integration tests for feature processing in backend/tests/integration/test_feature_flow.py
- [ ] T061 [P] Add contract tests for all API endpoints in backend/tests/contract/
- [ ] T062 Run quickstart.md validation and fix issues
- [ ] T063 Code cleanup and refactoring

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on Foundational phase, may use US1 data
- **User Story 3 (Phase 5)**: Depends on Foundational phase, consumes US1/US2 APIs
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Uses raw data from US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Consumes APIs from US1/US2 but should be independently testable

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003, T004, T005)
- All Foundational tasks marked [P] can run in parallel (T007, T008, T010, T011, T013, T014, T015, T016)
- Within US1: T017 and T018 can run in parallel
- Within US2: T028, T029, T030, T031, T032 can run in parallel (different feature computations)
- Within US3: T040, T041, T042, T043, T044, T045, T046 can run in parallel (different components)
- Polish tasks T053-T061 can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch Binance client and download endpoint together:
Task: "T017 [P] [US1] Create Binance API client with rate limiting in backend/src/services/binance_client.py"
Task: "T018 [P] [US1] Create OHLCV download endpoint (POST /api/v1/download) in backend/src/api/routes/market_data.py"

# After download is implemented, save tasks can run in parallel:
Task: "T022 [US1] Implement Parquet save for OHLCV"
Task: "T023 [US1] Implement Parquet save for Open Interest"
Task: "T024 [US1] Implement Parquet save for Funding Rate"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T016) - CRITICAL
3. Complete Phase 3: User Story 1 (T017-T027)
4. **STOP and VALIDATE**: Test data download via API
5. Verify Parquet files in data/raw/

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test data download → MVP!
3. Add User Story 2 → Test feature processing → Research ready!
4. Add User Story 3 → Test dashboard → Full v0!
5. Each story adds value without breaking previous stories

### First Vertical Slice (Recommended Start)

Implement only tasks T001-T027 first:
1. Create backend project structure
2. Create Binance public data client
3. Download BTCUSDT 15m klines
4. Download BTCUSDT open interest history
5. Save raw data to Parquet
6. Create endpoints to query downloaded data
7. Do not build strategy yet
8. Do not build live trading

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- No live trading, no private API keys, no Rust/ClickHouse/Kafka/Kubernetes/ML in v0
