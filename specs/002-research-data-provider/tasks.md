# Tasks: Research Data Provider Layer

**Input**: Design documents from `/specs/002-research-data-provider/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Required by the feature plan. Test tasks are included before implementation tasks in each user story phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- All task descriptions include exact file paths

## Path Conventions

- **Backend**: `backend/src/`, `backend/tests/`
- **Frontend**: `frontend/src/`
- **Feature docs**: `specs/002-research-data-provider/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the minimum package/dependency scaffolding for provider implementation.

- [X] T001 Add yfinance dependency for YahooFinanceProvider in backend/pyproject.toml
- [X] T002 Create provider package initializer in backend/src/providers/__init__.py
- [X] T003 [P] Create provider unit test module placeholder in backend/tests/unit/test_provider_capabilities.py
- [X] T004 [P] Create provider unsupported-capability test module placeholder in backend/tests/unit/test_provider_unsupported_capabilities.py
- [X] T005 [P] Create provider API contract test module placeholder in backend/tests/contract/test_provider_api_contracts.py
- [X] T006 [P] Create provider integration test module placeholder in backend/tests/integration/test_provider_download_flow.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared models, errors, schemas, registry, and service wiring that all provider stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T007 Create provider Pydantic models for ProviderInfo, ProviderSymbol, ProviderCapability, ProviderDownloadRequest, ProviderDownloadResult, UnsupportedCapability, DataArtifact, and LocalDatasetValidationReport in backend/src/models/providers.py
- [X] T008 Create provider exception classes for provider-not-found, unsupported-capability, provider-validation, provider-unavailable, and local-file-validation failures in backend/src/providers/errors.py
- [X] T009 Create normalized Polars schema constants and validation helpers for OHLCV, open interest, and funding data in backend/src/providers/base.py
- [X] T010 Define the DataProvider Protocol with metadata, validation, and fetch methods in backend/src/providers/base.py
- [X] T011 Create static ProviderRegistry with list, lookup, and metadata helpers in backend/src/providers/registry.py
- [X] T012 Add provider registry dependency factory in backend/src/api/dependencies.py
- [X] T013 Extend FastAPI exception handling for provider errors in backend/src/main.py
- [X] T014 Add provider-aware save/load path helpers while preserving Binance alias filenames in backend/src/repositories/parquet_repo.py
- [X] T015 Update FeatureEngine optional-derivative handling so OHLCV-only rows are not dropped only because OI/funding columns are absent in backend/src/services/feature_engine.py
- [X] T016 Add foundational unit tests for normalized schema validation in backend/tests/unit/test_provider_capabilities.py
- [X] T017 Add foundational unit tests for ProviderRegistry lookup and unknown-provider errors in backend/tests/unit/test_provider_capabilities.py

**Checkpoint**: Provider foundation compiles, registry can be resolved, and feature processing can accept OHLCV-only datasets.

---

## Phase 3: User Story 1 - Use Provider-Agnostic Downloads While Preserving Binance Flow (Priority: P1) MVP

**Goal**: User can download Binance BTCUSDT 15m OHLCV, open interest, and funding through the provider layer while existing OI Regime Lab behavior remains compatible.

**Independent Test**: Request Binance BTCUSDT 15m through the provider-aware downloader, process features, and verify the existing Binance artifacts and dashboard data path still work.

### Tests for User Story 1

- [X] T018 [P] [US1] Add BinanceProvider mocked OHLCV/OI/funding integration tests in backend/tests/integration/test_binance_provider_flow.py
- [X] T019 [US1] Add backward-compatible POST /api/v1/download contract test in backend/tests/contract/test_provider_api_contracts.py
- [X] T020 [US1] Add provider-aware Binance POST /api/v1/data/download contract test in backend/tests/contract/test_provider_api_contracts.py
- [X] T021 [P] [US1] Add Binance provider metadata unit tests in backend/tests/unit/test_provider_capabilities.py

### Implementation for User Story 1

- [X] T022 [US1] Implement BinanceProvider metadata, symbol validation, timeframe validation, and public USD-M Futures capability flags in backend/src/providers/binance_provider.py
- [X] T023 [US1] Move Binance OHLCV normalization behind BinanceProvider.fetch_ohlcv in backend/src/providers/binance_provider.py
- [X] T024 [US1] Move Binance open interest normalization behind BinanceProvider.fetch_open_interest in backend/src/providers/binance_provider.py
- [X] T025 [US1] Move Binance funding rate normalization behind BinanceProvider.fetch_funding_rate in backend/src/providers/binance_provider.py
- [X] T026 [US1] Register BinanceProvider in the static provider registry in backend/src/providers/registry.py
- [X] T027 [US1] Refactor DataDownloader to resolve providers through ProviderRegistry and download requested data types in backend/src/services/data_downloader.py
- [X] T028 [US1] Adapt existing POST /api/v1/download to delegate to provider=binance while keeping DownloadResponse shape in backend/src/api/routes/market_data.py
- [X] T029 [US1] Add provider-aware POST /api/v1/data/download route for Binance-compatible downloads in backend/src/api/routes/providers.py
- [X] T030 [US1] Register providers router with /api/v1 prefix in backend/src/main.py
- [X] T031 [US1] Ensure provider-aware Binance saves still produce readable btcusdt_15m_ohlcv, btcusdt_15m_oi, and btcusdt_15m_funding aliases in backend/src/repositories/parquet_repo.py

**Checkpoint**: Binance provider path works, existing Binance endpoint remains compatible, and existing feature processing still works for BTCUSDT 15m.

---

## Phase 4: User Story 2 - Use OHLCV-Only Research Sources (Priority: P2)

**Goal**: User can download Yahoo Finance OHLCV for SPY or GC=F and receives clear unsupported-capability behavior for OI/funding.

**Independent Test**: Download Yahoo Finance OHLCV for SPY or GC=F using mocked yfinance data and request OI/funding to verify structured unsupported-capability responses.

### Tests for User Story 2

- [X] T032 [P] [US2] Add YahooFinanceProvider mocked OHLCV integration tests in backend/tests/integration/test_yahoo_finance_provider_flow.py
- [X] T033 [P] [US2] Add Yahoo Finance unsupported OI/funding unit tests in backend/tests/unit/test_provider_unsupported_capabilities.py
- [X] T034 [P] [US2] Add Yahoo Finance provider metadata unit tests in backend/tests/unit/test_provider_capabilities.py
- [X] T035 [P] [US2] Add provider-aware Yahoo Finance POST /api/v1/data/download contract tests in backend/tests/contract/test_provider_api_contracts.py

### Implementation for User Story 2

- [X] T036 [US2] Implement YahooFinanceProvider metadata, curated symbols, timeframe validation, and OHLCV-only capability flags in backend/src/providers/yahoo_finance_provider.py
- [X] T037 [US2] Implement YahooFinanceProvider.fetch_ohlcv using yfinance-compatible responses converted to normalized Polars OHLCV schema in backend/src/providers/yahoo_finance_provider.py
- [X] T038 [US2] Implement YahooFinanceProvider.fetch_open_interest and fetch_funding_rate unsupported-capability behavior in backend/src/providers/yahoo_finance_provider.py
- [X] T039 [US2] Register YahooFinanceProvider in the static provider registry in backend/src/providers/registry.py
- [X] T040 [US2] Ensure DataDownloader records skipped unsupported Yahoo Finance data types in ProviderDownloadResult in backend/src/services/data_downloader.py
- [X] T041 [US2] Ensure provider-aware Parquet filenames safely handle Yahoo symbols such as SPY and GC=F in backend/src/repositories/parquet_repo.py

**Checkpoint**: Yahoo Finance OHLCV-only downloads work through the provider-aware path and unsupported derivative data requests are explicit.

---

## Phase 5: User Story 3 - Validate Imported Local Research Files (Priority: P3)

**Goal**: User can validate CSV or Parquet local research datasets for OHLCV and optional OI/funding capabilities.

**Independent Test**: Validate one good local OHLCV file and multiple invalid files for missing columns, bad timestamps, duplicate timestamps, and missing values.

### Tests for User Story 3

- [X] T042 [P] [US3] Add LocalFileProvider valid OHLCV CSV and Parquet validation tests in backend/tests/unit/test_local_file_provider.py
- [X] T043 [US3] Add LocalFileProvider optional open interest and funding capability detection tests in backend/tests/unit/test_local_file_provider.py
- [X] T044 [US3] Add LocalFileProvider invalid schema, unparseable timestamp, duplicate timestamp, and missing value tests in backend/tests/unit/test_local_file_provider.py
- [X] T045 [P] [US3] Add local_file provider POST /api/v1/data/download contract tests in backend/tests/contract/test_provider_api_contracts.py

### Implementation for User Story 3

- [X] T046 [US3] Implement LocalFileProvider metadata and capability-limitation reporting in backend/src/providers/local_file_provider.py
- [X] T047 [US3] Implement LocalFileProvider CSV and Parquet reads using Polars in backend/src/providers/local_file_provider.py
- [X] T048 [US3] Implement LocalFileProvider required OHLCV column validation in backend/src/providers/local_file_provider.py
- [X] T049 [US3] Implement LocalFileProvider timestamp parseability and duplicate timestamp validation in backend/src/providers/local_file_provider.py
- [X] T050 [US3] Implement LocalFileProvider missing required value validation in backend/src/providers/local_file_provider.py
- [X] T051 [US3] Implement LocalFileProvider optional OI and funding capability detection in backend/src/providers/local_file_provider.py
- [X] T052 [US3] Register LocalFileProvider in the static provider registry in backend/src/providers/registry.py
- [X] T053 [US3] Wire LocalFileProvider validation/import results into provider-aware download orchestration in backend/src/services/data_downloader.py

**Checkpoint**: Local CSV/Parquet datasets are accepted only when validation passes and produce clear validation reports otherwise.

---

## Phase 6: User Story 4 - See Provider Capabilities in the Dashboard (Priority: P4)

**Goal**: User can see selected provider, capabilities, symbol, timeframe, and unsupported OI/funding messaging in the dashboard.

**Independent Test**: Switch between Binance and Yahoo Finance in the dashboard; verify Binance shows OI/funding data paths and Yahoo Finance shows "Not supported by this provider" for OI/funding panels.

### Tests for User Story 4

- [X] T054 [US4] Add GET /api/v1/providers contract test in backend/tests/contract/test_provider_api_contracts.py
- [X] T055 [US4] Add GET /api/v1/providers/{provider_name} contract test in backend/tests/contract/test_provider_api_contracts.py
- [X] T056 [US4] Add GET /api/v1/providers/{provider_name}/symbols contract test in backend/tests/contract/test_provider_api_contracts.py

### Implementation for User Story 4

- [X] T057 [US4] Implement GET /api/v1/providers, GET /api/v1/providers/{provider_name}, and GET /api/v1/providers/{provider_name}/symbols in backend/src/api/routes/providers.py
- [X] T058 [US4] Add TypeScript provider metadata and provider-aware download types in frontend/src/types/index.ts
- [X] T059 [US4] Add provider API client methods for providers, symbols, and provider-aware download in frontend/src/services/api.ts
- [X] T060 [US4] Update useMarketData to accept provider capabilities and avoid unsupported OI/funding calls in frontend/src/hooks/useMarketData.ts
- [X] T061 [US4] Create ProviderPanel for provider selection and capability metadata in frontend/src/components/panels/ProviderPanel.tsx
- [X] T062 [US4] Integrate ProviderPanel, selected provider, selected symbol, selected timeframe, and provider-aware download into dashboard page in frontend/src/app/page.tsx
- [X] T063 [US4] Render "Not supported by this provider" in open interest and funding chart sections when capabilities are unavailable in frontend/src/app/page.tsx

**Checkpoint**: Dashboard shows provider context and capability status without breaking unsupported OI/funding sections.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verification, cleanup, documentation alignment, and v0 guardrail checks across all stories.

- [X] T064 [P] Update quickstart notes for final implemented endpoint behavior in specs/002-research-data-provider/quickstart.md
- [X] T065 [P] Add or update provider limitation documentation in specs/002-research-data-provider/plan.md
- [X] T066 Run backend import check documented in specs/002-research-data-provider/quickstart.md
- [X] T067 Run full backend pytest suite documented in specs/002-research-data-provider/quickstart.md
- [X] T068 Run frontend build documented in specs/002-research-data-provider/quickstart.md
- [X] T069 Run Binance provider-aware smoke test documented in specs/002-research-data-provider/quickstart.md
- [X] T070 Run Yahoo Finance OHLCV and unsupported-capability smoke tests documented in specs/002-research-data-provider/quickstart.md
- [X] T071 Run LocalFileProvider validation smoke test documented in specs/002-research-data-provider/quickstart.md
- [X] T072 Review backend/pyproject.toml and source paths for forbidden v0 technologies documented in specs/002-research-data-provider/quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; can start immediately.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories.
- **US1 Binance Provider Compatibility (Phase 3)**: Depends on Foundational; MVP path.
- **US2 Yahoo Finance OHLCV (Phase 4)**: Depends on Foundational; can start after registry and shared models exist, but should integrate after US1 downloader behavior is stable.
- **US3 Local File Validation (Phase 5)**: Depends on Foundational; can run in parallel with US2 after registry and shared models exist.
- **US4 Dashboard Capabilities (Phase 6)**: Depends on provider metadata routes and at least one provider implementation; best after US1 and provider list endpoints exist.
- **Polish (Phase 7)**: Depends on selected user stories being complete.

### User Story Dependencies

- **User Story 1 (P1)**: Required MVP and compatibility base for existing OI Regime Lab behavior.
- **User Story 2 (P2)**: Depends on provider foundation; uses shared download route/service created for US1.
- **User Story 3 (P3)**: Depends on provider foundation; can be implemented independently of Yahoo Finance.
- **User Story 4 (P4)**: Depends on provider metadata endpoints and capability data from US1/US2/US3.

### Within Each User Story

- Write tests first and confirm they fail before implementation.
- Implement provider models/services before routes.
- Implement routes before frontend API clients.
- Keep existing Binance endpoint compatibility checks in place before changing dashboard defaults.

### Parallel Opportunities

- Setup placeholders T003-T006 can run in parallel.
- Foundational model and registry tests T016-T017 should run sequentially because they share backend/tests/unit/test_provider_capabilities.py.
- US1 tests T018 and T021 can run in parallel before US1 implementation; T019-T020 should run sequentially because they share backend/tests/contract/test_provider_api_contracts.py.
- US2 tests T032-T035 can run in parallel before Yahoo implementation.
- US3 tests T042 and T045 can run in parallel before LocalFile implementation; T043-T044 should run sequentially because they share backend/tests/unit/test_local_file_provider.py.
- US4 API contract tests T054-T056 should run sequentially because they share backend/tests/contract/test_provider_api_contracts.py.
- US2 and US3 implementation can proceed in parallel after the shared provider registry and downloader contract are stable.

---

## Parallel Example: User Story 1

```bash
# Launch Binance compatibility tests together:
Task: "T018 [P] [US1] Add BinanceProvider mocked OHLCV/OI/funding integration tests in backend/tests/integration/test_binance_provider_flow.py"
Task: "T021 [P] [US1] Add Binance provider metadata unit tests in backend/tests/unit/test_provider_capabilities.py"
```

Write T019 and T020 sequentially because both edit backend/tests/contract/test_provider_api_contracts.py.

## Parallel Example: User Story 2

```bash
# Launch Yahoo Finance tests together:
Task: "T032 [P] [US2] Add YahooFinanceProvider mocked OHLCV integration tests in backend/tests/integration/test_yahoo_finance_provider_flow.py"
Task: "T033 [P] [US2] Add Yahoo Finance unsupported OI/funding unit tests in backend/tests/unit/test_provider_unsupported_capabilities.py"
Task: "T034 [P] [US2] Add Yahoo Finance provider metadata unit tests in backend/tests/unit/test_provider_capabilities.py"
Task: "T035 [P] [US2] Add provider-aware Yahoo Finance POST /api/v1/data/download contract tests in backend/tests/contract/test_provider_api_contracts.py"
```

## Parallel Example: User Story 3

```bash
# Launch LocalFileProvider validation tests together:
Task: "T042 [P] [US3] Add LocalFileProvider valid OHLCV CSV and Parquet validation tests in backend/tests/unit/test_local_file_provider.py"
Task: "T045 [P] [US3] Add local_file provider POST /api/v1/data/download contract tests in backend/tests/contract/test_provider_api_contracts.py"
```

Write T043 and T044 sequentially because both edit backend/tests/unit/test_local_file_provider.py.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 setup and Phase 2 provider foundation.
2. Complete Phase 3 tests and implementation for Binance provider compatibility.
3. Stop and validate existing BTCUSDT 15m download, process, and dashboard behavior.
4. Keep `/api/v1/download` compatible before expanding to Yahoo or local files.

### Incremental Delivery

1. Provider foundation -> registry, models, errors, schema helpers.
2. US1 -> Binance provider path and backward compatibility.
3. US2 -> Yahoo Finance OHLCV-only source and unsupported capability behavior.
4. US3 -> LocalFileProvider validation.
5. US4 -> dashboard provider/capability visibility.
6. Polish -> quickstart smoke checks, full tests, frontend build, v0 forbidden-tech review.

### Validation Gates

1. Existing backend tests continue passing after US1.
2. Provider unit/integration/contract tests pass after US2 and US3.
3. Frontend build passes after US4.
4. Quickstart smoke checks pass before commit.

## Notes

- [P] tasks use different files or are test cases that can be written independently.
- Tasks that modify the same file are intentionally sequential to avoid edit conflicts.
- No task introduces live trading, private API keys, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML.
- Generated data files under data/raw, data/processed, data/reports, Parquet, and DuckDB artifacts must not be committed.
