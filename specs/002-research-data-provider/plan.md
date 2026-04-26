# Implementation Plan: Research Data Provider Layer

**Branch**: `002-research-data-provider` | **Date**: 2026-04-26 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/002-research-data-provider/spec.md`

## Summary

Add a provider-agnostic research data layer for Elpis without redesigning the existing OI Regime Lab. The implementation will introduce provider abstractions under `backend/src/providers/`, keep provider-specific raw API handling inside concrete provider classes, normalize provider outputs into common Polars DataFrame schemas, and route new provider-aware downloads through a registry-backed service. The existing Binance BTCUSDT 15m OHLCV/open-interest/funding flow must continue to work, while Yahoo Finance adds OHLCV-only research downloads and LocalFileProvider adds CSV/Parquet schema validation. Frontend changes stay intentionally narrow: provider selection, symbol/timeframe inputs, capability metadata, and explicit unsupported-capability messaging for OI and funding panels.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.x  
**Primary Dependencies**: FastAPI, Pydantic, Pydantic Settings, Polars, DuckDB, Parquet/PyArrow, httpx, yfinance for OHLCV-only Yahoo Finance research, Next.js, Tailwind CSS, lightweight-charts/Recharts  
**Storage**: Existing local `data/raw`, `data/processed`, and optional DuckDB views; Parquet remains the canonical local research storage  
**Testing**: pytest, pytest-asyncio, backend contract/integration/unit tests, frontend `npm run build`  
**Target Platform**: Local development on Windows/macOS/Linux  
**Project Type**: Web application with FastAPI backend and Next.js dashboard  
**Performance Goals**: Existing Binance 30-day BTCUSDT 15m flow completes within current v0 targets; Yahoo Finance OHLCV request for SPY or GC=F completes within 2 minutes; provider metadata endpoints respond fast enough for dashboard startup; dashboard capability display appears within 5 seconds of loading available data  
**Constraints**: Preserve existing Binance endpoint compatibility; no live trading, private API keys, order execution, Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML model training; feature engineering remains provider-agnostic and timestamp-safe  
**Scale/Scope**: v0 local single-user research platform, three initial providers (`binance`, `yahoo_finance`, `local_file`), curated initial symbols/timeframes, no dynamic plugin marketplace

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Research-First Architecture | PASS | The feature expands research data ingestion only; no execution or trading decisions are added. |
| II. Language Split | PASS | Python remains backend/research layer, TypeScript remains dashboard layer, and no Rust execution component is introduced in v0. |
| III. Frontend Stack | PASS | Dashboard changes stay within the existing Next.js/TypeScript/Tailwind setup. |
| IV. Backend Stack | PASS | Provider metadata and download routes remain FastAPI/Pydantic. |
| V. Data Processing | PASS | Provider outputs normalize to Polars DataFrames before storage or feature processing. yfinance compatibility data is converted immediately to Polars. |
| VI. Storage v0 | PASS | DuckDB and Parquet remain local research storage; no server database is added. |
| VII. Storage v1+ | N/A | PostgreSQL and ClickHouse are explicitly out of scope for v0. |
| VIII. Event Architecture | PASS | No Kafka, Redpanda, NATS, or other event backbone is introduced. |
| IX. Data-Source Principle | PASS | Binance uses public official USD-M Futures market data; Yahoo Finance is documented as OHLCV-only; LocalFileProvider validates imported research files. |
| X. TradingView Principle | N/A | No TradingView or Pine Script dependency is added. |
| XI. Reliability Principle | PASS | Provider validation, capability metadata, and structured unsupported responses prevent raw connector assumptions from leaking downstream. |
| XII. Live Trading Principle | PASS | No live or paper execution capability is added. |

**Gate Result**: PASS. No constitution violations require justification.

## Design Overview

### Data Provider Interface

Create `backend/src/providers/base.py` with a typed provider contract for research data sources:

- `get_provider_info()` returns provider metadata and capability flags.
- `get_supported_symbols()` returns curated or provider-discovered research symbols.
- `get_supported_timeframes()` returns provider-supported timeframe values.
- `validate_symbol(symbol)` returns a normalized symbol or raises a structured validation error.
- `validate_timeframe(timeframe)` returns a normalized timeframe or raises a structured validation error.
- `fetch_ohlcv(request)` returns normalized OHLCV as a Polars DataFrame.
- `fetch_open_interest(request)` returns normalized open interest as a Polars DataFrame or raises unsupported capability.
- `fetch_funding_rate(request)` returns normalized funding as a Polars DataFrame or raises unsupported capability.

The concrete providers are:

- `BinanceProvider`: wraps the existing Binance public USD-M Futures logic and owns Binance payload parsing/rate-limit handling.
- `YahooFinanceProvider`: owns yfinance interaction, supports OHLCV only, and rejects OI/funding requests with explicit unsupported-capability responses.
- `LocalFileProvider`: owns CSV/Parquet reads and schema validation, detecting OHLCV plus optional OI/funding capabilities from file columns.

### Provider Registry

Create `backend/src/providers/registry.py` with a simple static registry for v0:

- Register initial providers by canonical names: `binance`, `yahoo_finance`, `local_file`.
- Resolve provider names case-insensitively and return structured `PROVIDER_NOT_FOUND` errors for unknown names.
- Expose `list_providers()`, `get_provider(name)`, and `get_provider_info(name)` helpers for routes and services.
- Avoid runtime plugin loading in v0 to keep the architecture small and testable.

### Normalized Schema

All provider fetch methods return Polars DataFrames with common schemas before storage:

```text
OHLCV schema:
timestamp: Datetime UTC-compatible
provider: string
symbol: string
timeframe: string
open: float
high: float
low: float
close: float
volume: float
quote_volume: float | null
trades: int | null
taker_buy_volume: float | null
source: string | null

Open interest schema:
timestamp: Datetime UTC-compatible
provider: string
symbol: string
timeframe: string
open_interest: float
open_interest_value: float | null
source: string | null

Funding rate schema:
timestamp: Datetime UTC-compatible
provider: string
symbol: string
timeframe: string
funding_rate: float
mark_price: float | null
source: string | null
```

Provider metadata is stored alongside artifacts either in response metadata and/or lightweight sidecar metadata. For backward compatibility, the default Binance BTCUSDT 15m filenames remain readable by the existing feature pipeline; provider-aware names are added for new providers and symbols.

### API Changes

Add `backend/src/api/routes/providers.py` and register it in `backend/src/main.py`:

- `GET /api/v1/providers` lists provider metadata.
- `GET /api/v1/providers/{provider_name}` returns one provider's metadata.
- `GET /api/v1/providers/{provider_name}/symbols` returns supported symbols and limitation notes.
- `POST /api/v1/data/download` accepts provider-aware download/import requests.

Keep existing Binance-oriented routes for compatibility:

- `POST /api/v1/download` remains available and delegates to the provider-aware path with `provider=binance` and the existing BTCUSDT defaults.
- Existing read/process routes continue to work for Binance BTCUSDT 15m.

Add structured error handling for unsupported capability responses:

- `UNSUPPORTED_CAPABILITY` for valid provider/data type combinations that the provider does not support.
- `PROVIDER_NOT_FOUND` for unknown providers.
- `LOCAL_FILE_VALIDATION_FAILED` for failed local schema/timestamp/value checks.

### Dashboard Changes

Keep the dashboard as the first usable research screen. Update only enough to support provider visibility:

- Fetch provider list and show provider selection.
- Show provider capability metadata for OHLCV, open interest, funding rate, and authentication requirement.
- Show selected symbol and timeframe controls based on provider metadata.
- Route downloads through `POST /api/v1/data/download` for new provider-aware requests.
- Preserve current Download Data and Process Features behavior for default Binance BTCUSDT 15m.
- Render "Not supported by this provider" in OI and funding sections when provider metadata marks those capabilities unavailable.

### Migration Strategy

1. Add provider models, provider errors, normalized schema helpers, registry, and tests without changing existing endpoints.
2. Move existing Binance raw payload handling behind `BinanceProvider` while keeping `BinanceClient` behavior or adapting it internally.
3. Refactor `DataDownloader` to resolve providers through the registry and save normalized outputs through the existing Parquet repository.
4. Add the provider-aware API routes and adapt `POST /api/v1/download` to call the new path for Binance defaults.
5. Add Yahoo Finance OHLCV-only support and unsupported capability tests.
6. Add LocalFileProvider validation and tests.
7. Update feature processing to tolerate OHLCV-only datasets without dropping all rows due to missing derivative columns.
8. Update the dashboard capability display and run backend/frontend checks.

### Testing Plan

- Existing backend tests must continue passing.
- Unit tests for provider capability metadata for all providers.
- Unit tests for unsupported capability behavior, especially Yahoo Finance OI/funding.
- Integration test for `BinanceProvider` using mocked public API responses for OHLCV, OI, and funding.
- Integration test for `YahooFinanceProvider` using mocked yfinance/data response and no real network.
- LocalFileProvider schema validation tests for valid OHLCV, optional OI, optional funding, missing columns, unparseable timestamps, duplicate timestamps, and missing required values.
- API contract tests for `GET /api/v1/providers`, `GET /api/v1/providers/{provider_name}`, `GET /api/v1/providers/{provider_name}/symbols`, and `POST /api/v1/data/download`.
- Backward compatibility tests for existing `POST /api/v1/download` and existing Binance process/dashboard data path.
- Frontend build must pass after provider selection/capability UI changes.

## Project Structure

### Documentation (this feature)

```text
specs/002-research-data-provider/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
`-- tasks.md              # Created later by /speckit.tasks
```

### Source Code (repository root)

```text
backend/
|-- pyproject.toml                    # Add yfinance dependency for YahooFinanceProvider
|-- src/
|   |-- api/
|   |   |-- dependencies.py           # Add provider registry dependency
|   |   `-- routes/
|   |       |-- market_data.py        # Keep existing routes; delegate /download to provider flow
|   |       `-- providers.py          # New provider metadata and provider-aware download routes
|   |-- main.py                       # Register providers router
|   |-- models/
|   |   |-- market_data.py            # Extend download request/response models carefully
|   |   `-- providers.py              # Provider metadata, capability, download, validation models
|   |-- providers/
|   |   |-- __init__.py
|   |   |-- base.py                   # DataProvider protocol and normalized schema constants
|   |   |-- errors.py                 # Provider-specific structured exceptions
|   |   |-- registry.py               # Static v0 provider registry
|   |   |-- binance_provider.py       # Binance public USD-M Futures implementation
|   |   |-- yahoo_finance_provider.py # Yahoo Finance OHLCV-only implementation
|   |   `-- local_file_provider.py    # CSV/Parquet validation implementation
|   |-- repositories/
|   |   `-- parquet_repo.py           # Provider-aware save/load helpers, keep Binance aliases
|   `-- services/
|       |-- data_downloader.py        # Provider-aware download orchestration
|       `-- feature_engine.py         # Provider-agnostic optional OI/funding handling
`-- tests/
    |-- contract/
    |   `-- test_provider_api_contracts.py
    |-- integration/
    |   |-- test_binance_provider_flow.py
    |   |-- test_yahoo_finance_provider_flow.py
    |   `-- test_provider_download_flow.py
    `-- unit/
        |-- test_provider_capabilities.py
        |-- test_provider_unsupported_capabilities.py
        `-- test_local_file_provider.py

frontend/
|-- src/
|   |-- app/
|   |   `-- page.tsx                  # Provider controls and capability display
|   |-- components/
|   |   `-- panels/
|   |       `-- ProviderPanel.tsx      # Optional small panel if page grows too large
|   |-- hooks/
|   |   `-- useMarketData.ts          # Provider-aware fetch options, avoid unsupported calls
|   |-- services/
|   |   `-- api.ts                    # Provider endpoint client methods
|   `-- types/
|       `-- index.ts                  # Provider metadata and provider-aware request types
`-- tests/                            # Add only if frontend test harness already exists or is introduced later
```

**Structure Decision**: Keep the current two-app layout. Add a narrow provider package under `backend/src/providers/` and a single provider route module. Avoid broad service rewrites, new persistence systems, or frontend redesign.

## Implementation Phases

### Phase 0: Research Decisions

Documented in [research.md](research.md). Decisions cover the provider interface, registry, normalized Polars schemas, yfinance integration, LocalFile validation, unsupported capability errors, storage compatibility, and frontend scope.

### Phase 1: Design and Contracts

Documented in [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), and [quickstart.md](quickstart.md). Outputs define provider metadata, normalized datasets, download results, local validation reports, API response shapes, and verification steps.

### Phase 2: Task Generation

Use `/speckit.tasks` to create implementation tasks grouped by user story. Tasks must write tests first for provider behavior and keep each story independently testable.

### Phase 3: Provider Foundation

Implement provider models, errors, DataProvider protocol, normalized schema helpers, registry, and dependency wiring. Add unit tests for metadata and unsupported capabilities.

### Phase 4: Binance Migration and Compatibility

Move Binance-specific fetch/parse behavior behind `BinanceProvider`, refactor `DataDownloader` to use the provider registry, preserve `POST /api/v1/download`, and verify the existing BTCUSDT 15m flow.

### Phase 5: Yahoo Finance and Local File Providers

Add Yahoo Finance OHLCV-only support with mocked integration tests. Add LocalFileProvider validation for CSV/Parquet files and validation report tests.

### Phase 6: Provider API and Dashboard Metadata

Add provider metadata routes and provider-aware download route. Update the dashboard to show provider selection, capabilities, symbol/timeframe, and unsupported OI/funding messages.

### Phase 7: Verification and Smoke Test

Run backend unit/integration/contract tests, backend import check, frontend build, and a smoke test that verifies Binance remains functional and Yahoo Finance/LocalFile capability behavior is clear.

## Complexity Tracking

No constitution violations or excess architectural complexity are introduced. The provider registry is intentionally static for v0 to avoid plugin infrastructure and keep the migration small.

## Implemented Limitations

- The dashboard can list providers, show capability metadata, select symbols/timeframes, and route downloads through `POST /api/v1/data/download`.
- Existing chart, regime, data-quality, and process endpoints remain Binance-oriented in this slice. Non-Binance provider-aware downloads are persisted as raw artifacts, but provider-aware chart read/process routes are reserved for a later vertical slice.
- Yahoo Finance is OHLCV-only and must not be treated as a source for crypto open interest or funding data.
- LocalFileProvider validates CSV/Parquet schema and optional derivative columns, but the dashboard does not upload local files directly in this slice.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Research-first and no live trading | PASS | Design adds research ingestion only. |
| Allowed language/stack | PASS | Python/TypeScript only; yfinance is allowed for non-execution research data. |
| Polars and timestamp safety | PASS | Provider outputs normalize to Polars schemas before feature processing. |
| Local storage | PASS | Parquet/DuckDB remain the only storage choices. |
| Data-source limitations visible | PASS | Capability metadata and dashboard messages expose provider limitations. |
| Forbidden v0 technologies | PASS | No Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML, private keys, or execution endpoints. |

**Gate Result**: PASS. Ready for `/speckit.tasks`.
