# Data Model: Free Public Derivatives Data Expansion

**Date**: 2026-05-12  
**Feature**: 011-free-public-derivatives-data-expansion

## Enums

### FreeDerivativesSource

- `cftc_cot`
- `gvz`
- `deribit_public_options`

### FreeDerivativesRunStatus

- `completed`
- `partial`
- `blocked`
- `failed`

### FreeDerivativesSourceStatus

- `completed`
- `partial`
- `skipped`
- `failed`

### FreeDerivativesArtifactType

- `raw_cftc`
- `processed_cftc`
- `raw_gvz`
- `processed_gvz`
- `raw_deribit_instruments`
- `raw_deribit_summary`
- `processed_deribit_options`
- `processed_deribit_walls`
- `run_metadata`
- `run_json`
- `run_markdown`

### CftcCotReportCategory

- `futures_only`
- `futures_and_options_combined`

### DeribitOptionType

- `call`
- `put`
- `unknown`

## Core Request Models

### FreeDerivativesBootstrapRequest

Fields:

- `include_cftc`: boolean, default true
- `include_gvz`: boolean, default true
- `include_deribit`: boolean, default true
- `cftc`: `CftcCotRequest | null`
- `gvz`: `GvzRequest | null`
- `deribit`: `DeribitOptionsRequest | null`
- `run_label`: optional string
- `report_format`: `json`, `markdown`, or `both`, default `both`
- `research_only_acknowledged`: boolean

Validation:

- `research_only_acknowledged` must be true.
- At least one source must be enabled.
- Disabled source sections are ignored.
- The request must not include credentials, account ids, order parameters, wallet fields, or paid-vendor key fields.

### CftcCotRequest

Fields:

- `years`: list of integer years
- `categories`: list of `CftcCotReportCategory`
- `source_urls`: optional list of public source URLs for explicit runs
- `local_fixture_paths`: optional list of local CSV/ZIP paths for fixture/import mode
- `market_filters`: list of strings, default includes gold and COMEX-oriented terms

Validation:

- Years must be reasonable four-digit years.
- Categories must remain explicit.
- Local paths must be safe local paths.
- Source URLs must be public HTTP(S) URLs and must not include credentials.

### GvzRequest

Fields:

- `series_id`: default `GVZCLS`
- `start_date`: optional date
- `end_date`: optional date
- `source_url`: optional public source URL for explicit runs
- `local_fixture_path`: optional local CSV path

Validation:

- `series_id` defaults to `GVZCLS` and should not be changed without a visible limitation.
- `start_date` must be on or before `end_date` when both are present.
- Local path must be safe.
- Source URL must not contain credentials.

### DeribitOptionsRequest

Fields:

- `underlyings`: list of strings, default `BTC`, `ETH`
- `include_expired`: boolean, default false
- `snapshot_timestamp`: optional datetime
- `fixture_instruments_path`: optional local JSON path
- `fixture_summary_path`: optional local JSON path

Validation:

- Underlyings are normalized uppercase and deduplicated.
- Unsafe symbols and path traversal are rejected.
- Only public option market-data fields are accepted.
- No account, order, private endpoint, or credential fields are accepted.

## Run And Artifact Models

### FreeDerivativesBootstrapRun

Fields:

- `run_id`
- `status`: `FreeDerivativesRunStatus`
- `created_at`
- `completed_at`
- `request`: `FreeDerivativesBootstrapRequest`
- `source_results`: list of `FreeDerivativesSourceResult`
- `artifacts`: list of `FreeDerivativesArtifact`
- `warnings`: list of strings
- `limitations`: list of strings
- `missing_data_actions`: list of strings or structured actions
- `research_only_warnings`: list of strings

Relationships:

- Has many `FreeDerivativesSourceResult`.
- Has many `FreeDerivativesArtifact`.
- Is summarized by `FreeDerivativesBootstrapRunSummary`.

### FreeDerivativesBootstrapRunSummary

Fields:

- `run_id`
- `status`
- `created_at`
- `completed_at`
- `completed_source_count`
- `partial_source_count`
- `failed_source_count`
- `artifact_count`
- `warning_count`
- `limitation_count`

### FreeDerivativesSourceResult

Fields:

- `source`: `FreeDerivativesSource`
- `status`: `FreeDerivativesSourceStatus`
- `requested_items`: list of strings
- `completed_items`: list of strings
- `skipped_items`: list of strings
- `failed_items`: list of strings
- `row_count`: integer
- `instrument_count`: integer
- `coverage_start`
- `coverage_end`
- `snapshot_timestamp`
- `artifacts`: list of `FreeDerivativesArtifact`
- `warnings`: list of strings
- `limitations`: list of strings
- `missing_data_actions`: list of strings or structured actions

Validation:

- Counts must be non-negative.
- A completed source should have at least one processed artifact.
- Failed and skipped sources must include a warning or missing-data action.

### FreeDerivativesArtifact

Fields:

- `artifact_type`: `FreeDerivativesArtifactType`
- `source`: `FreeDerivativesSource`
- `path`
- `format`: `json`, `csv`, `parquet`, `markdown`, or `zip`
- `rows`: optional non-negative integer
- `created_at`
- `limitations`: list of strings

Validation:

- Artifact paths must remain under configured `data/raw`, `data/processed`, or `data/reports/free_derivatives` roots.
- Reported paths should be project-relative when possible.

## CFTC Models

### CftcCotGoldRecord

Fields:

- `report_date`
- `report_category`: `CftcCotReportCategory`
- `market_name`
- `exchange_name`
- `cftc_contract_market_code`
- `commodity_name`
- `noncommercial_long`
- `noncommercial_short`
- `noncommercial_spread`
- `commercial_long`
- `commercial_short`
- `total_reportable_long`
- `total_reportable_short`
- `nonreportable_long`
- `nonreportable_short`
- `open_interest`
- `source_file`
- `source_row_number`

Validation:

- `report_date` is required.
- Gold/COMEX relevance must be explicitly recorded by filter fields.
- Numeric positioning fields are nullable because report formats can differ.

### CftcGoldPositioningSummary

Fields:

- `report_date`
- `report_category`
- `market_name`
- `exchange_name`
- `open_interest`
- `noncommercial_net`
- `commercial_net`
- `total_reportable_net`
- `nonreportable_net`
- `week_over_week_noncommercial_net_change`
- `week_over_week_open_interest_change`
- `limitations`

Validation:

- Summary rows must retain report category.
- Week-over-week fields are null for the first available row or missing prior dates.

## GVZ Models

### GvzDailyCloseRecord

Fields:

- `date`
- `series_id`
- `close`
- `source`
- `is_missing`
- `limitations`

Validation:

- `series_id` defaults to `GVZCLS`.
- `close` is nullable only for explicitly marked missing dates.
- Limitations must include proxy labeling.

### GvzGapSummary

Fields:

- `start_date`
- `end_date`
- `observed_row_count`
- `missing_date_count`
- `missing_dates`
- `limitations`

Validation:

- Missing dates are informational, not fabricated values.

## Deribit Models

### DeribitOptionInstrument

Fields:

- `instrument_name`
- `underlying`
- `expiry`
- `strike`
- `option_type`: `DeribitOptionType`
- `is_active`
- `raw_payload`

Validation:

- Instrument name is required.
- Expiry, strike, and option type may be parsed from instrument name when not provided by the source.
- Unsupported underlyings are skipped with limitations.

### DeribitOptionSummarySnapshot

Fields:

- `snapshot_timestamp`
- `instrument_name`
- `underlying`
- `expiry`
- `strike`
- `option_type`
- `open_interest`
- `mark_iv`
- `bid_iv`
- `ask_iv`
- `underlying_price`
- `volume`
- `delta`
- `gamma`
- `vega`
- `theta`
- `raw_payload`

Validation:

- At least `instrument_name` and `underlying` are required.
- Missing public fields remain null and are reflected in limitations.
- Private/account/order fields are not accepted.

### DeribitOptionWallSnapshot

Fields:

- `snapshot_timestamp`
- `underlying`
- `expiry`
- `strike`
- `option_type`
- `total_open_interest`
- `average_mark_iv`
- `bid_iv`
- `ask_iv`
- `underlying_price`
- `volume`
- `instrument_count`
- `limitations`

Validation:

- Aggregations must group by underlying, expiry, strike, and option type.
- Rows with no usable open interest can still be retained as partial context if IV is present, but limitations must state OI is unavailable.

## State Transitions

### Run Status

```text
requested -> running -> completed
requested -> running -> partial
requested -> running -> blocked
requested -> running -> failed
```

- `completed`: all enabled sources completed.
- `partial`: at least one enabled source completed and at least one source was partial, skipped, or failed.
- `blocked`: no enabled sources could run because request or local fixture requirements were invalid or missing.
- `failed`: unexpected orchestration-level failure before source results could be preserved.

### Source Status

```text
planned -> completed
planned -> partial
planned -> skipped
planned -> failed
```

- `completed`: processed output exists for the source.
- `partial`: raw or partial processed output exists but some requested fields/items are missing.
- `skipped`: source was enabled but unavailable or unsupported for requested items.
- `failed`: source attempted and failed with no usable output.
