# Data Model: Public Data Bootstrapper

## Enums

### DataBootstrapProvider

| Value | Meaning |
|-------|---------|
| `binance_public` | Binance public market and public derivatives endpoints for crypto research. |
| `yahoo_finance` | Yahoo Finance OHLCV proxy source. |
| `xau_local_import` | XAU options OI local CSV/Parquet import instructions only. |

### DataBootstrapStatus

| Value | Meaning |
|-------|---------|
| `completed` | All requested bootstrap items completed. |
| `partial` | At least one item completed and at least one was skipped or failed. |
| `blocked` | No requested item produced usable processed output. |
| `failed` | Unexpected run-level failure occurred. |

### DataBootstrapAssetStatus

| Value | Meaning |
|-------|---------|
| `downloaded` | Source data was fetched and processed output was written. |
| `skipped` | Item was intentionally skipped due to unsupported source, unsupported timeframe, disabled source, or local-import-only scope. |
| `failed` | Item was attempted but did not produce usable output. |

### DataBootstrapArtifactType

| Value | Meaning |
|-------|---------|
| `raw_ohlcv` | Raw OHLCV source file. |
| `raw_open_interest` | Raw open-interest source file. |
| `raw_funding_rate` | Raw funding-rate source file. |
| `processed_features` | Processed feature file used by preflight/evidence workflows. |
| `bootstrap_report` | Saved bootstrap metadata or summary report. |

## Entities

### PublicDataBootstrapRequest

Request to run a public/no-key bootstrap.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `include_binance` | bool | No | Defaults true. |
| `binance_symbols` | list[string] | No | Defaults BTCUSDT, ETHUSDT, SOLUSDT. |
| `optional_binance_symbols` | list[string] | No | Optional BNBUSDT, XRPUSDT, DOGEUSDT. |
| `binance_timeframes` | list[string] | No | Defaults `15m`; allowed `15m`, `1h`, `1d`. |
| `include_binance_open_interest` | bool | No | Defaults true, but missing/limited data is non-blocking. |
| `include_binance_funding` | bool | No | Defaults true, but missing/limited data is non-blocking. |
| `include_yahoo` | bool | No | Defaults true. |
| `yahoo_symbols` | list[string] | No | Defaults SPY, QQQ, GLD, GC=F. |
| `yahoo_timeframes` | list[string] | No | Defaults `1d`. |
| `days` | integer | No | Requested recent history window when explicit start/end is absent. |
| `start_time` | datetime or null | No | Optional start timestamp. |
| `end_time` | datetime or null | No | Optional end timestamp. |
| `run_preflight_after` | bool | No | Defaults true to show readiness transition after files are written. |
| `include_xau_local_instructions` | bool | No | Defaults true. |
| `research_only_acknowledged` | bool | Yes | Must be true. |

Validation rules:

- `research_only_acknowledged` must be true.
- Symbols and timeframes must be normalized and allowlisted for this public MVP.
- Requests for private trading, broker, wallet, order execution, or paid-vendor bootstrap credentials are rejected.
- Yahoo requests for OI, funding, IV, gold options OI, futures OI, or XAUUSD execution are labeled unsupported, not downloaded.

### DataBootstrapPlanItem

One planned source/symbol/timeframe operation before download.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `provider` | `DataBootstrapProvider` | Yes | Source to use. |
| `symbol` | string | Yes | Source symbol. |
| `timeframe` | string | Yes | Requested timeframe. |
| `data_types` | list[string] | Yes | OHLCV plus optional derivatives for Binance; OHLCV only for Yahoo. |
| `unsupported_capabilities` | list[string] | Yes | Explicit unsupported labels. |
| `limitations` | list[string] | Yes | Source limitations shown before and after run. |

### DataBootstrapArtifact

Local generated file reference.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `artifact_type` | `DataBootstrapArtifactType` | Yes | Raw, processed, or report artifact. |
| `provider` | `DataBootstrapProvider` | Yes | Source provider. |
| `path` | path | Yes | Project-local ignored path. |
| `row_count` | integer | Yes | Non-negative row count. |
| `start_timestamp` | datetime or null | No | First row timestamp. |
| `end_timestamp` | datetime or null | No | Last row timestamp. |
| `limitations` | list[string] | Yes | Artifact-level limitations. |

Validation rules:

- Raw artifacts must resolve under `data/raw/`.
- Processed artifacts must resolve under `data/processed/`.
- Report artifacts must resolve under `data/reports/`.
- Path traversal and unsafe filename parts are rejected.

### DataBootstrapAssetResult

Per-asset bootstrap outcome.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `provider` | `DataBootstrapProvider` | Yes | Source provider. |
| `symbol` | string | Yes | Normalized symbol. |
| `timeframe` | string | Yes | Normalized timeframe. |
| `status` | `DataBootstrapAssetStatus` | Yes | Downloaded, skipped, or failed. |
| `row_count` | integer | Yes | Processed row count when available. |
| `start_timestamp` | datetime or null | No | Processed or source start timestamp. |
| `end_timestamp` | datetime or null | No | Processed or source end timestamp. |
| `raw_artifacts` | list[`DataBootstrapArtifact`] | Yes | Raw files written. |
| `processed_feature_path` | path or null | No | Feature file recognized by preflight when available. |
| `unsupported_capabilities` | list[string] | Yes | Unsupported labels such as Yahoo OI/funding/IV. |
| `warnings` | list[string] | Yes | Non-fatal warnings. |
| `limitations` | list[string] | Yes | Source/data limitations. |
| `missing_data_actions` | list[string] | Yes | Next actions when blocked or incomplete. |

### PublicDataBootstrapRun

Persisted run-level result.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `bootstrap_run_id` | string | Yes | Filesystem-safe run id. |
| `status` | `DataBootstrapStatus` | Yes | Completed, partial, blocked, or failed. |
| `created_at` | datetime | Yes | Run creation time. |
| `completed_at` | datetime or null | No | Run completion time. |
| `request` | `PublicDataBootstrapRequest` | Yes | Normalized request. |
| `asset_results` | list[`DataBootstrapAssetResult`] | Yes | One result per requested item. |
| `downloaded_count` | integer | Yes | Count of downloaded items. |
| `skipped_count` | integer | Yes | Count of skipped items. |
| `failed_count` | integer | Yes | Count of failed items. |
| `preflight_result` | object or null | No | Feature 008 preflight response after generated outputs. |
| `report_artifacts` | list[`DataBootstrapArtifact`] | Yes | JSON/Markdown metadata and summary artifacts. |
| `research_only_warnings` | list[string] | Yes | No execution/no claims warnings. |
| `limitations` | list[string] | Yes | Run-level source limitations. |
| `missing_data_actions` | list[string] | Yes | XAU local import and failed asset next actions. |

## Relationships

```text
PublicDataBootstrapRequest (1) -> (many) DataBootstrapPlanItem
PublicDataBootstrapRun (1) -> (many) DataBootstrapAssetResult
DataBootstrapAssetResult (1) -> (many) DataBootstrapArtifact
PublicDataBootstrapRun (0..1) -> (1) DataSourcePreflightResult from feature 008
PublicDataBootstrapRun (1) -> (many) DataBootstrapArtifact report files
```

## State Transitions

```text
[Requested]
  -> [Validated Research-Only Scope]
  -> [Plan Built]
  -> [Per-Asset Download Attempted]
  -> [Raw Artifact Written]
  -> [Processed Features Written]
  -> [Optional Preflight Run]
  -> [Report Persisted]
  -> [Completed or Partial]

[Per-Asset Download Attempted]
  -> [Skipped Unsupported Capability]
  -> [Failed With Actionable Reason]

[Validated Research-Only Scope]
  -> [Rejected Invalid or Forbidden Request]
```

## Invariants

- The workflow never requires or accepts private trading keys, broker credentials, wallet keys, order execution credentials, or paid provider keys.
- Yahoo Finance remains OHLCV-only in all plan, result, report, and dashboard fields.
- XAU options OI remains a local CSV/Parquet import path with schema instructions.
- Missing or shallow Binance public derivatives fields remain visible as limitations.
- Generated files remain under ignored `data/raw/`, `data/processed/`, and `data/reports/` paths.
- Processed features must use the naming convention expected by feature 008 preflight.
- Tests must use mocked provider responses or synthetic local fixtures, not live public downloads.
