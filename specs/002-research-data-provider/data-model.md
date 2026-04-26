# Data Model: Research Data Provider Layer

**Date**: 2026-04-26  
**Feature**: 002-research-data-provider

## Entities

### DataProvider

Represents a research data source capable of reporting metadata, validating requests, and fetching supported datasets.

| Field/Method | Type | Description | Validation |
|--------------|------|-------------|------------|
| name | string | Canonical provider identifier such as `binance`, `yahoo_finance`, or `local_file` | Required, lowercase snake_case |
| get_provider_info | function | Returns ProviderInfo | Must include all capability flags |
| get_supported_symbols | function | Returns ProviderSymbol list | Must be deterministic for curated v0 symbols |
| get_supported_timeframes | function | Returns supported timeframe strings | Must include provider-specific supported values |
| validate_symbol | function | Normalizes or rejects symbol | Must return clear validation error on unsupported symbol |
| validate_timeframe | function | Normalizes or rejects timeframe | Must return clear validation error on unsupported timeframe |
| fetch_ohlcv | function | Returns normalized OHLCV Polars DataFrame | Required for all initial providers when valid data exists |
| fetch_open_interest | function | Returns normalized OI Polars DataFrame or unsupported error | Unsupported for Yahoo; optional for LocalFile |
| fetch_funding_rate | function | Returns normalized funding Polars DataFrame or unsupported error | Unsupported for Yahoo; optional for LocalFile |

### ProviderInfo

Provider metadata shown through the API and dashboard.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| provider | string | Canonical provider identifier | Required |
| display_name | string | Human-readable provider name | Required |
| supports_ohlcv | boolean | Whether OHLCV can be requested | Required |
| supports_open_interest | boolean | Whether open interest can be requested | Required |
| supports_funding_rate | boolean | Whether funding rate can be requested | Required |
| requires_auth | boolean | Whether credentials are required | Required; false for all initial v0 providers |
| supported_timeframes | string[] | Supported timeframe values | Required, non-empty for OHLCV providers |
| default_symbol | string | Default symbol for provider | Optional |
| limitations | string[] | Provider data-source limitations | Required, can be empty |

### ProviderSymbol

Represents a provider-supported research symbol.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Provider-facing symbol | Required |
| display_name | string | User-facing label | Optional |
| asset_class | string | Crypto, equity, ETF, index, futures_proxy, macro_proxy, local_dataset, or other | Required |
| supports_ohlcv | boolean | Symbol-level OHLCV capability | Required |
| supports_open_interest | boolean | Symbol-level OI capability | Required |
| supports_funding_rate | boolean | Symbol-level funding capability | Required |
| notes | string[] | Limitations or source notes | Optional |

### ProviderCapability

Represents whether a provider supports a data type and what message to show when it does not.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| data_type | enum | `ohlcv`, `open_interest`, or `funding_rate` | Required |
| supported | boolean | Capability availability | Required |
| unsupported_reason | string | User-readable reason when unsupported | Required when supported is false |

### ProviderDownloadRequest

Provider-aware request to download or validate/import research data.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| provider | string | Provider identifier | Required, must exist in registry |
| symbol | string | Provider symbol | Required unless LocalFile request derives it from file metadata |
| timeframe | string | Requested timeframe | Required, provider-validated |
| days | integer | History length in days | Optional, 1 to 365 for v0 |
| start_time | datetime | Inclusive research start time | Optional |
| end_time | datetime | Inclusive research end time | Optional |
| data_types | string[] | Requested data types | Optional, defaults to provider-supported research defaults |
| local_file_path | string | Local CSV/Parquet path for LocalFileProvider | Required for local file validation/import requests |

### ProviderDownloadResult

Outcome of a provider-aware download.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| status | enum | `completed`, `partial`, or `failed` | Required |
| provider | string | Provider identifier | Required |
| symbol | string | Normalized symbol | Required |
| timeframe | string | Normalized timeframe | Required |
| completed_data_types | string[] | Data types successfully saved/imported | Required |
| skipped_data_types | UnsupportedCapability[] | Data types skipped for known reasons | Required, can be empty |
| artifacts | DataArtifact[] | Saved dataset references | Required, can be empty on failed validation |
| message | string | User-readable result summary | Required |
| warnings | string[] | Non-fatal provider/source warnings | Optional |

### UnsupportedCapability

Represents an explicitly unsupported data request.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| provider | string | Provider identifier | Required |
| data_type | string | Unsupported data type | Required |
| reason | string | Clear user-readable explanation | Required |

### DataArtifact

Represents a locally stored research dataset artifact.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| data_type | enum | `ohlcv`, `open_interest`, `funding_rate`, or `features` | Required |
| path | string | Project-relative local file path | Required |
| rows | integer | Number of rows saved | >= 0 |
| provider | string | Source provider | Required |
| symbol | string | Normalized symbol | Required |
| timeframe | string | Normalized timeframe | Required |
| first_timestamp | datetime | Earliest row timestamp | Optional |
| last_timestamp | datetime | Latest row timestamp | Optional |

### LocalDatasetValidationReport

Validation result for a CSV or Parquet local research file.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| file_path | string | Local source file path | Required |
| is_valid | boolean | Whether file can be used as research data | Required |
| detected_capabilities | string[] | Valid data types detected from columns | Required |
| required_columns_missing | string[] | Missing required OHLCV columns | Required, can be empty |
| timestamp_column | string | Timestamp column used | Required when detected |
| timestamp_parseable | boolean | Whether timestamp values parse successfully | Required |
| duplicate_timestamps | integer | Duplicate timestamp count | >= 0 |
| missing_required_values | Record<string, integer> | Missing count by required column | Required |
| errors | string[] | Blocking validation errors | Required, can be empty |
| warnings | string[] | Non-blocking validation notes | Optional |

## Normalized DataFrame Schemas

### OHLCV

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| timestamp | datetime | Yes | UTC-compatible bar time |
| provider | string | Yes | Source provider |
| symbol | string | Yes | Normalized symbol |
| timeframe | string | Yes | Normalized timeframe |
| open | float | Yes | > 0 |
| high | float | Yes | >= open and >= close |
| low | float | Yes | <= open and <= close |
| close | float | Yes | > 0 |
| volume | float | Yes | >= 0 |
| quote_volume | float/null | No | Available for Binance, optional otherwise |
| trades | int/null | No | Available for Binance, optional otherwise |
| taker_buy_volume | float/null | No | Available for Binance, optional otherwise |
| source | string/null | No | Provider/source note |

### Open Interest

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| timestamp | datetime | Yes | UTC-compatible measurement time |
| provider | string | Yes | Source provider |
| symbol | string | Yes | Normalized symbol |
| timeframe | string | Yes | Normalized timeframe |
| open_interest | float | Yes | > 0 |
| open_interest_value | float/null | No | Optional quote-currency value |
| source | string/null | No | Provider/source note |

### Funding Rate

| Column | Type | Required | Notes |
|--------|------|----------|-------|
| timestamp | datetime | Yes | UTC-compatible funding time |
| provider | string | Yes | Source provider |
| symbol | string | Yes | Normalized symbol |
| timeframe | string | Yes | Research alignment timeframe |
| funding_rate | float | Yes | Provider-valid rate |
| mark_price | float/null | No | Optional mark price |
| source | string/null | No | Provider/source note |

## Relationships

```text
ProviderRegistry (1) -> (many) DataProvider
DataProvider (1) -> (1) ProviderInfo
ProviderInfo (1) -> (many) ProviderSymbol
ProviderDownloadRequest (1) -> (1) DataProvider
ProviderDownloadResult (1) -> (many) DataArtifact
LocalFileProvider (1) -> (1) LocalDatasetValidationReport
MarketDataset OHLCV (1) -> (0..1) MarketDataset OpenInterest by timestamp
MarketDataset OHLCV (1) -> (0..1) MarketDataset FundingRate by timestamp/forward-fill alignment
MarketDataset OHLCV (1) -> (1) Feature dataset when processed
```

## State Transitions

### Provider-Aware Download

```text
[Requested]
  -> [Provider Resolved]
  -> [Symbol/Timeframe Validated]
  -> [Capabilities Checked]
  -> [Fetching Supported Data]
  -> [Normalized]
  -> [Saved]
  -> [Completed or Partial]

[Capabilities Checked]
  -> [Unsupported Capability Reported]

[Symbol/Timeframe Validated]
  -> [Validation Failed]
```

### Local File Validation

```text
[File Selected]
  -> [Readable Check]
  -> [Column Detection]
  -> [Timestamp Parsing]
  -> [Duplicate/Missing Value Checks]
  -> [Capability Detection]
  -> [Valid or Rejected]
```

## Validation Rules

- Provider name must resolve to a registered provider.
- Symbol and timeframe must be validated by the selected provider before fetching.
- Unsupported capabilities must be reported explicitly and must not produce misleading empty derivative datasets.
- OHLCV datasets must include parseable timestamps and non-null open, high, low, close, and volume columns.
- OHLCV high/low bounds must be internally consistent with open and close values.
- Local files with duplicate timestamps or missing required values must not be treated as ready research data.
- Feature processing must allow missing OI/funding columns while still requiring valid OHLCV columns.
- Binance provider must not require or accept private API keys for v0 data downloads.
