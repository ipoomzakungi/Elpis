# Data Model: QuikStrike Local Highcharts Extractor

**Date**: 2026-05-13
**Feature**: 012-quikstrike-local-highcharts-extractor

## Enums

### QuikStrikeViewType

- `intraday_volume`
- `eod_volume`
- `open_interest`
- `oi_change`
- `churn`

### QuikStrikeSeriesType

- `put`
- `call`
- `vol_settle`
- `ranges`
- `unknown`

### QuikStrikeOptionType

- `put`
- `call`

### QuikStrikeExtractionStatus

- `completed`
- `partial`
- `blocked`
- `failed`

### QuikStrikeStrikeMappingConfidence

- `high`
- `partial`
- `conflict`
- `unknown`

### QuikStrikeArtifactType

- `raw_normalized_rows_json`
- `raw_normalized_rows_parquet`
- `raw_metadata`
- `processed_xau_vol_oi_csv`
- `processed_xau_vol_oi_parquet`
- `conversion_metadata`
- `report_json`
- `report_markdown`

## Sanitized Input Models

### QuikStrikeDomMetadata

Fields:

- `product`
- `option_product_code`
- `futures_symbol`
- `expiration`
- `dte`
- `future_reference_price`
- `source_view`
- `selected_view_type`
- `surface`
- `raw_header_text`
- `raw_selector_text`
- `warnings`
- `limitations`

Validation:

- Product must identify Gold/OG/GC for supported extraction.
- `surface` must identify `QUIKOPTIONS VOL2VOL`.
- `selected_view_type` must map to a supported `QuikStrikeViewType`.
- `raw_header_text` and `raw_selector_text` must be sanitized visible text only.
- No field may contain cookies, tokens, headers, viewstate values, HAR content, screenshots, or private full URLs.

### QuikStrikePoint

Fields:

- `series_type`: `QuikStrikeSeriesType`
- `x`
- `y`
- `name`
- `category`
- `strike_id`
- `range_label`
- `sigma_label`
- `metadata_keys`

Validation:

- `x` and `y` must be numeric when used for Put/Call values.
- `strike_id` is optional but contributes to mapping confidence.
- Metadata is restricted to safe key names and must not include raw secret/session payloads.

### QuikStrikeSeriesSnapshot

Fields:

- `series_name`
- `series_type`: `QuikStrikeSeriesType`
- `point_count`
- `points`: list of `QuikStrikePoint`
- `warnings`
- `limitations`

Validation:

- Put and Call series must be distinguishable for conversion.
- Vol Settle and Ranges are optional context series but must be preserved when present.

### QuikStrikeHighchartsSnapshot

Fields:

- `chart_title`
- `view_type`: `QuikStrikeViewType`
- `series`: list of `QuikStrikeSeriesSnapshot`
- `chart_warnings`
- `chart_limitations`

Validation:

- Must not contain raw browser globals or full chart object dumps beyond sanitized series and points.
- Must include at least one supported Put or Call series to produce rows.

## Extraction Request And Result Models

### QuikStrikeExtractionRequest

Fields:

- `requested_views`: list of `QuikStrikeViewType`
- `dom_metadata_by_view`: mapping of `QuikStrikeViewType` to `QuikStrikeDomMetadata`
- `highcharts_by_view`: mapping of `QuikStrikeViewType` to `QuikStrikeHighchartsSnapshot`
- `run_label`
- `report_format`: `json`, `markdown`, or `both`
- `research_only_acknowledged`

Validation:

- `research_only_acknowledged` must be true.
- At least one requested view is required.
- Payload must reject forbidden fields or text indicating cookies, tokens, headers, viewstate, HAR, screenshots, credentials, account/order/wallet data, private full URLs, or endpoint replay material.
- Requested views must match the supplied sanitized DOM/chart view types.

### QuikStrikeNormalizedRow

Fields:

- `row_id`
- `extraction_id`
- `capture_timestamp`
- `product`
- `option_product_code`
- `futures_symbol`
- `expiration`
- `dte`
- `future_reference_price`
- `view_type`: `QuikStrikeViewType`
- `strike`
- `strike_id`
- `option_type`: `QuikStrikeOptionType`
- `value`
- `value_type`
- `vol_settle`
- `range_label`
- `sigma_label`
- `source_view`
- `strike_mapping_confidence`: `QuikStrikeStrikeMappingConfidence`
- `extraction_warnings`
- `extraction_limitations`

Validation:

- `row_id` must be stable for extraction id, view, strike, option side, and value type.
- `value` must be numeric.
- Put/Call rows must include `option_type`.
- `strike_mapping_confidence=high` is required for automatic XAU Vol-OI conversion.
- Rows with partial/conflict/unknown mapping can be stored but are not conversion-eligible.

### QuikStrikeStrikeMappingValidation

Fields:

- `confidence`: `QuikStrikeStrikeMappingConfidence`
- `method`
- `matched_point_count`
- `unmatched_point_count`
- `conflict_count`
- `evidence`
- `warnings`
- `limitations`

Validation:

- Evidence must be sanitized and value-oriented; no raw private DOM/request/session content.
- Any conflict should prevent high confidence.

### QuikStrikeExtractionResult

Fields:

- `extraction_id`
- `status`: `QuikStrikeExtractionStatus`
- `created_at`
- `completed_at`
- `requested_views`
- `completed_views`
- `partial_views`
- `missing_views`
- `row_count`
- `put_row_count`
- `call_row_count`
- `strike_mapping`: `QuikStrikeStrikeMappingValidation`
- `conversion_eligible`
- `artifacts`: list of `QuikStrikeArtifact`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- `completed` requires all requested views to produce usable rows and high strike mapping confidence.
- `partial` is used when at least one view produces rows but one or more validation gates are incomplete.
- `blocked` is used when no requested views can safely produce rows.
- `conversion_eligible` must be false unless required fields and strike confidence are valid.

## Conversion Models

### QuikStrikeXauVolOiRow

Fields:

- `date` or `timestamp`
- `expiry`
- `strike`
- `option_type`
- `open_interest`
- `oi_change`
- `volume`
- `intraday_volume`
- `eod_volume`
- `churn`
- `implied_volatility`
- `underlying_futures_price`
- `source`
- `source_view`
- `source_extraction_id`
- `limitations`

Validation:

- `open_interest` is populated only from `open_interest` view rows.
- `oi_change` is populated only from `oi_change` view rows.
- `intraday_volume` and `eod_volume` are populated only from matching volume views.
- `churn` is preserved as context and not substituted for open interest.
- Rows require high strike mapping confidence.

### QuikStrikeConversionResult

Fields:

- `conversion_id`
- `extraction_id`
- `status`: `completed`, `blocked`, or `failed`
- `row_count`
- `output_artifacts`
- `blocked_reasons`
- `warnings`
- `limitations`

Validation:

- Blocked conversion must include at least one blocked reason.
- Completed conversion must include at least one processed artifact.

## Report And Artifact Models

### QuikStrikeArtifact

Fields:

- `artifact_type`: `QuikStrikeArtifactType`
- `path`
- `format`
- `rows`
- `created_at`
- `limitations`

Validation:

- Artifact paths must stay under `data/raw/quikstrike/`, `data/processed/quikstrike/`, or `data/reports/quikstrike/`.
- Reported paths should be project-relative where possible.

### QuikStrikeExtractionReport

Fields:

- `extraction_id`
- `status`
- `created_at`
- `completed_at`
- `request_summary`
- `view_summaries`
- `row_count`
- `strike_mapping`
- `conversion_result`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- Report text must state local-only and research-only limitations.
- Report must not include cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, account/order/wallet fields, or private full URLs.

## State Transitions

### Extraction Status

```text
requested -> running -> completed
requested -> running -> partial
requested -> running -> blocked
requested -> running -> failed
```

- `completed`: all requested views produced rows and strike mapping is high confidence.
- `partial`: at least one requested view produced rows but some views or validation gates are incomplete.
- `blocked`: no safe extraction could be produced.
- `failed`: unexpected local processing failure with no usable report beyond error metadata.

### Conversion Status

```text
requested -> completed
requested -> blocked
requested -> failed
```

- `completed`: processed XAU Vol-OI compatible output exists.
- `blocked`: extraction is partial, strike mapping is not high confidence, required fields are missing, or no rows are eligible.
- `failed`: unexpected conversion failure after eligibility passed.
