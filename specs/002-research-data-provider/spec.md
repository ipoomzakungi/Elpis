# Feature Specification: Research Data Provider Layer

**Feature Branch**: `002-research-data-provider`  
**Created**: 2026-04-26  
**Status**: Draft  
**Input**: Add a generic research data provider layer for Elpis so market data ingestion can use Binance, Yahoo Finance, and local files without hardcoding provider-specific logic inside feature engineering, regime classification, or dashboard code.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use Provider-Agnostic Downloads While Preserving Binance Flow (Priority: P1)

The researcher wants to download market data through a provider-aware layer, while the existing Binance BTCUSDT 15m OI Regime Lab flow continues to work exactly as a research workflow.

**Why this priority**: Modular ingestion is only useful if it preserves the completed OI Regime Lab baseline and becomes the shared entry point for future research data.

**Independent Test**: Can be fully tested by requesting a Binance BTCUSDT 15m download through the provider-aware download flow, processing features, and verifying that the dashboard still displays price, range, open interest, funding, volume, regimes, and data quality.

**Acceptance Scenarios**:

1. **Given** the Binance provider is selected with BTCUSDT and 15m, **When** the user downloads data, **Then** OHLCV, open interest, and funding rate research datasets are downloaded from public Binance USD-M Futures data sources and stored for reproducible local research.
2. **Given** the existing OI Regime Lab workflow is used, **When** the user runs the previous Binance download, process, and dashboard flow, **Then** it remains functional through the provider layer without requiring user-visible behavior changes.
3. **Given** provider-specific data is downloaded, **When** downstream feature processing or regime classification runs, **Then** it consumes normalized research datasets without directly depending on Binance-specific behavior.

---

### User Story 2 - Use OHLCV-Only Research Sources (Priority: P2)

The researcher wants to download long-history OHLCV datasets from Yahoo Finance for stocks, ETFs, indices, futures proxies, and macro proxy assets, and receive clear capability messages when derivative-specific data is unavailable.

**Why this priority**: Long-history OHLCV baselines are needed to compare crypto OI regime behavior against broader market contexts without implying that every provider has open interest or funding data.

**Independent Test**: Can be fully tested by selecting Yahoo Finance, downloading OHLCV for SPY or GC=F, and requesting open interest or funding from the same provider to confirm a clear unsupported-capability response.

**Acceptance Scenarios**:

1. **Given** Yahoo Finance is selected with SPY and a supported timeframe, **When** the user downloads data, **Then** the system stores an OHLCV-only research dataset with provider metadata.
2. **Given** Yahoo Finance is selected with GC=F or QQQ, **When** the user requests supported OHLCV data, **Then** the system validates the symbol and timeframe before attempting the download.
3. **Given** Yahoo Finance is selected, **When** the user requests open interest or funding rate data, **Then** the system returns a clear unsupported-capability response instead of failing silently or producing empty derivative datasets.

---

### User Story 3 - Validate Imported Local Research Files (Priority: P3)

The researcher wants to use local CSV or Parquet files as research datasets when those files contain valid timestamps and required market-data columns.

**Why this priority**: Local imports let the project compare vendor exports, manually curated datasets, and future sources without adding provider-specific logic to downstream research workflows.

**Independent Test**: Can be fully tested by validating one sample file with valid OHLCV columns and one sample file with schema or timestamp problems, then confirming the validation report identifies each issue.

**Acceptance Scenarios**:

1. **Given** a local CSV or Parquet file contains valid timestamp, open, high, low, close, and volume columns, **When** the user validates or imports it, **Then** the system accepts it as an OHLCV research dataset.
2. **Given** a local file contains optional open interest columns, **When** the user validates or imports it, **Then** the system marks open interest as available for that dataset.
3. **Given** a local file contains optional funding rate columns, **When** the user validates or imports it, **Then** the system marks funding rate as available for that dataset.
4. **Given** a local file has missing required columns, unparseable timestamps, duplicate timestamps, or missing required values, **When** the user validates it, **Then** the system returns a validation report that identifies the failing checks and does not treat the file as ready research data.

---

### User Story 4 - See Provider Capabilities in the Dashboard (Priority: P4)

The researcher wants the dashboard to show the selected provider, symbol, timeframe, and provider capabilities so unavailable open interest or funding data is explicit rather than confusing.

**Why this priority**: Capability visibility prevents false research assumptions and keeps the dashboard usable for both derivative-rich crypto datasets and OHLCV-only baselines.

**Independent Test**: Can be fully tested by switching between Binance and Yahoo Finance in the dashboard and confirming that open interest and funding panels display data for Binance and "Not supported by this provider" for Yahoo Finance.

**Acceptance Scenarios**:

1. **Given** any provider is selected, **When** the dashboard loads, **Then** it displays the selected provider, selected symbol, selected timeframe, and capability status for OHLCV, open interest, and funding rate.
2. **Given** the selected provider does not support open interest, **When** the dashboard renders the open interest area, **Then** it shows "Not supported by this provider" instead of an error or broken chart.
3. **Given** the selected provider does not support funding rate, **When** the dashboard renders the funding area, **Then** it shows "Not supported by this provider" instead of an error or broken chart.

### Edge Cases

- The selected provider name is unknown or disabled.
- The selected symbol is not supported by the provider.
- The selected timeframe is not supported by the provider.
- A provider supports OHLCV but not open interest or funding rate.
- A provider is temporarily unavailable, rate-limited, or returns incomplete data.
- Yahoo Finance has no available data for an otherwise valid symbol or period.
- Local file validation finds duplicate timestamps after parsing timestamps to a common time basis.
- Local file validation finds missing required values in one or more required OHLCV columns.
- Existing Binance-specific endpoints are used after the provider layer is introduced.
- Feature processing receives OHLCV-only data and derivative fields are unavailable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a generic DataProvider contract with `get_provider_info()`, `get_supported_symbols()`, `get_supported_timeframes()`, `fetch_ohlcv()`, `fetch_open_interest()`, `fetch_funding_rate()`, `validate_symbol()`, and `validate_timeframe()` capabilities.
- **FR-002**: System MUST expose provider capability metadata including provider identifier, OHLCV support, open interest support, funding rate support, authentication requirement, supported symbols, supported timeframes, and data-source limitations.
- **FR-003**: System MUST route new research data downloads through the provider layer so feature engineering, regime classification, and dashboard logic do not contain provider-specific download behavior.
- **FR-004**: System MUST include a Binance provider for crypto research data that supports OHLCV, open interest, and funding rate data.
- **FR-005**: Binance provider MUST preserve the existing BTCUSDT 15m OI Regime Lab download, process, and dashboard flow.
- **FR-006**: Binance provider MUST use only public Binance USD-M Futures market-data sources and MUST NOT use private Binance APIs, account endpoints, order endpoints, private keys, or execution data.
- **FR-007**: System MUST include a Yahoo Finance provider for long-history OHLCV research data for stocks, ETFs, indices, futures proxies, macro proxy assets, and OHLCV-only crypto references when available.
- **FR-008**: Yahoo Finance provider MUST support OHLCV for at least SPY or GC=F and SHOULD expose common research symbols such as SPY, QQQ, GC=F, and BTC-USD when available.
- **FR-009**: Yahoo Finance provider MUST report open interest and funding rate as unsupported capabilities and MUST return a clear unsupported-capability response whenever those data types are requested.
- **FR-010**: System MUST include a LocalFile provider for imported CSV and Parquet research datasets.
- **FR-011**: LocalFile provider MUST accept OHLCV datasets only when timestamp, open, high, low, close, and volume requirements are satisfied.
- **FR-012**: LocalFile provider MUST mark open interest as available only when required open interest columns are present and valid.
- **FR-013**: LocalFile provider MUST mark funding rate as available only when required funding rate columns are present and valid.
- **FR-014**: LocalFile provider MUST validate required columns, timestamp column presence, timestamp parseability, duplicate timestamps, and missing required values before a local file is treated as ready research data.
- **FR-015**: System MUST expose provider-aware endpoints for listing providers (`GET /api/v1/providers`), reading provider details (`GET /api/v1/providers/{provider_name}`), reading provider symbols (`GET /api/v1/providers/{provider_name}/symbols`), and requesting provider-aware data downloads (`POST /api/v1/data/download`).
- **FR-016**: Provider-aware download requests MUST include provider, symbol, timeframe, requested data types, and research date range or history length.
- **FR-017**: Existing Binance-oriented endpoints MAY remain for backward compatibility, but any new download logic MUST use the provider layer internally.
- **FR-018**: System MUST store downloaded or imported datasets with enough metadata to identify provider, symbol, timeframe, data type, download/import time, and capability availability.
- **FR-019**: Feature processing MUST NOT assume every dataset has open interest or funding rate data.
- **FR-020**: When open interest or funding rate data is unavailable, feature processing MUST compute applicable OHLCV-based outputs and mark derivative-dependent outputs as unavailable or skipped with a clear reason.
- **FR-021**: API responses MUST clearly distinguish unsupported provider capabilities from provider errors, invalid requests, missing data, and validation failures.
- **FR-022**: Dashboard MUST show selected provider, provider capabilities, selected symbol, and selected timeframe.
- **FR-023**: Dashboard MUST show "Not supported by this provider" for open interest or funding sections when those capabilities are unavailable.
- **FR-024**: Dashboard MUST continue to display price, range, volume, regime, and data-quality views for datasets whose available capabilities support those views.
- **FR-025**: System MUST surface provider and data-source limitations in user-facing status or documentation so research assumptions are visible.
- **FR-026**: System MUST remain a v0 research platform and MUST NOT introduce live trading, private exchange API keys, order execution, wallet/private-key handling, leverage execution, real position management, Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML model training.

### Key Entities

- **DataProvider**: A research data-source abstraction that validates symbols and timeframes, reports capabilities, and fetches supported research datasets.
- **ProviderInfo**: Metadata describing a provider name, display label, supported capabilities, authentication requirement, supported symbols, supported timeframes, and known source limitations.
- **ProviderCapability**: A capability flag for OHLCV, open interest, or funding rate, including whether the provider supports it and the message shown when it does not.
- **ProviderSymbol**: A symbol or asset identifier available from a provider, including display label, asset class or market type, and provider-specific limitation notes.
- **DownloadRequest**: A user request to download or import research data for a provider, symbol, timeframe, date range or history length, and requested data types.
- **DownloadResult**: The outcome of a provider-aware download, including status, stored dataset references, provider metadata, completed data types, skipped data types, and any unsupported-capability messages.
- **LocalDatasetValidationReport**: Validation results for an imported local file, including required-column checks, timestamp checks, duplicate timestamp counts, missing required value counts, and detected optional capabilities.
- **MarketDataset**: A normalized research dataset for OHLCV, open interest, or funding rate values, tied to provider, symbol, timeframe, timestamps, and source metadata.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Existing Binance BTCUSDT 15m download, process, and dashboard flow completes successfully after the provider layer is introduced.
- **SC-002**: Provider listing reports Binance, Yahoo Finance, and LocalFile with correct OHLCV, open interest, funding rate, and authentication capability flags.
- **SC-003**: Yahoo Finance OHLCV download succeeds for at least one of SPY or GC=F within 2 minutes for a standard research request.
- **SC-004**: Requests for Yahoo Finance open interest or funding rate return a clear unsupported-capability response without creating misleading derivative datasets.
- **SC-005**: LocalFile validation accepts a valid sample CSV or Parquet OHLCV dataset and rejects samples with missing required columns, unparseable timestamps, duplicate timestamps, or missing required values.
- **SC-006**: Feature processing completes for OHLCV-only datasets without failing solely because open interest or funding rate is unavailable.
- **SC-007**: Dashboard displays provider, symbol, timeframe, and capability status within 5 seconds after loading available research data.
- **SC-008**: Dashboard displays "Not supported by this provider" for unavailable open interest or funding sections and shows no broken chart or runtime error for those sections.
- **SC-009**: At least 95% of invalid provider, symbol, timeframe, unsupported-capability, and local-file validation scenarios return structured user-readable responses.
- **SC-010**: Dependency and configuration review confirms no v0-forbidden technologies or live trading capabilities are introduced.

## Assumptions

- This feature remains local, single-user, and research-only for v0.
- No authentication is required for the initial Binance, Yahoo Finance, or LocalFile providers.
- Yahoo Finance is used for OHLCV baselines only and is not treated as a source for crypto open interest or funding data.
- Binance official open interest is acceptable for the v0 prototype but remains documented as insufficient for serious multi-year OI research.
- Local files are imported from trusted local research datasets; this feature validates schema and data quality but does not define a public upload product.
- OHLCV-based feature outputs are useful even when derivative-specific open interest or funding features are unavailable.
- Provider symbol and timeframe lists may start with a curated set and expand later as long as validation responses are explicit.
