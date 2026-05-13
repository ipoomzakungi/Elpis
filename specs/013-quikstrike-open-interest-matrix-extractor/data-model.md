# Data Model: QuikStrike Open Interest Matrix Extractor

**Date**: 2026-05-13
**Feature**: 013-quikstrike-open-interest-matrix-extractor

## Enums

### QuikStrikeMatrixViewType

- `open_interest_matrix`
- `oi_change_matrix`
- `volume_matrix`

### QuikStrikeMatrixValueType

- `open_interest`
- `oi_change`
- `volume`

### QuikStrikeMatrixOptionType

- `call`
- `put`
- `combined`

### QuikStrikeMatrixExtractionStatus

- `completed`
- `partial`
- `blocked`
- `failed`

### QuikStrikeMatrixMappingStatus

- `valid`
- `partial`
- `blocked`

### QuikStrikeMatrixCellState

- `available`
- `unavailable`
- `blank`
- `invalid`

### QuikStrikeMatrixArtifactType

- `raw_normalized_rows_json`
- `raw_normalized_rows_parquet`
- `raw_metadata`
- `processed_xau_vol_oi_csv`
- `processed_xau_vol_oi_parquet`
- `conversion_metadata`
- `report_json`
- `report_markdown`

## Sanitized Input Models

### QuikStrikeMatrixMetadata

Fields:

- `capture_timestamp`
- `product`
- `option_product_code`
- `futures_symbol`
- `source_menu`
- `selected_view_type`
- `selected_view_label`
- `table_title`
- `raw_visible_text`
- `warnings`
- `limitations`

Validation:

- Product must identify Gold/OG/GC for supported extraction.
- `source_menu` must identify the Open Interest Matrix / Heatmap surface.
- `selected_view_type` must map to a supported matrix view.
- `raw_visible_text` must be sanitized visible text only.
- No field may contain cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, private full URLs, account/order/wallet data, or endpoint replay payloads.

### QuikStrikeMatrixTableSnapshot

Fields:

- `view_type`
- `html_table`
- `caption`
- `header_rows`
- `body_rows`
- `metadata`
- `warnings`
- `limitations`

Validation:

- Must contain sanitized table HTML or sanitized row arrays.
- Must not contain full page HTML, scripts, forms, hidden inputs, headers, cookies, viewstate values, screenshots, or private URLs.
- Must include at least one candidate header row and one candidate body row to produce a completed extraction.

### QuikStrikeMatrixHeaderCell

Fields:

- `text`
- `column_index`
- `row_index`
- `colspan`
- `rowspan`
- `expiration`
- `dte`
- `futures_symbol`
- `future_reference_price`
- `option_type`
- `warnings`

Validation:

- Header text must be sanitized visible text.
- Expiration must be extracted from visible header content or inherited from a visible column group.
- Option type may be `call`, `put`, or `combined`.

### QuikStrikeMatrixBodyCell

Fields:

- `row_index`
- `column_index`
- `strike`
- `row_label`
- `column_label`
- `raw_value`
- `numeric_value`
- `cell_state`
- `option_type`
- `expiration`
- `dte`
- `futures_symbol`
- `future_reference_price`

Validation:

- `strike` is required for conversion-eligible rows.
- `expiration` is required for conversion-eligible rows.
- `numeric_value` is required only when `cell_state=available`.
- Blank, dash, and unavailable markers must not become numeric zero.
- Negative, signed, parenthesized, and comma-formatted values should normalize only when unambiguous.

## Extraction Models

### QuikStrikeMatrixNormalizedRow

Fields:

- `row_id`
- `extraction_id`
- `capture_timestamp`
- `product`
- `option_product_code`
- `futures_symbol`
- `source_menu`
- `view_type`
- `strike`
- `expiration`
- `dte`
- `future_reference_price`
- `option_type`
- `value`
- `value_type`
- `cell_state`
- `table_row_label`
- `table_column_label`
- `extraction_warnings`
- `extraction_limitations`

Validation:

- `row_id` must be stable for extraction id, view, strike, expiration, option side, and value type.
- `value_type` must match the view mapping.
- `value` may be null only for unavailable cells.
- Conversion-eligible rows must have strike, expiration, option type, value type, and numeric value.

### QuikStrikeMatrixMappingValidation

Fields:

- `status`
- `table_present`
- `strike_rows_found`
- `expiration_columns_found`
- `option_side_mapping`
- `numeric_cell_count`
- `unavailable_cell_count`
- `duplicate_row_count`
- `blocked_reasons`
- `warnings`
- `limitations`

Validation:

- `valid` requires table presence, at least one strike row, at least one expiration column, and at least one numeric data cell.
- `blocked` must include at least one blocked reason.
- Duplicate rows must be visible as warnings or blocked reasons depending on whether a deterministic merge is possible.

### QuikStrikeMatrixExtractionRequest

Fields:

- `requested_views`
- `metadata_by_view`
- `tables_by_view`
- `run_label`
- `persist_report`
- `research_only_acknowledged`

Validation:

- `research_only_acknowledged` must be true.
- At least one requested view is required.
- Requested views must match supplied sanitized metadata/table snapshots.
- Payload must reject forbidden fields or text indicating cookies, tokens, headers, viewstate, HAR, screenshots, credentials, account/order/wallet data, private full URLs, or endpoint replay material.

### QuikStrikeMatrixExtractionResult

Fields:

- `extraction_id`
- `status`
- `created_at`
- `completed_at`
- `requested_views`
- `completed_views`
- `partial_views`
- `missing_views`
- `row_count`
- `strike_count`
- `expiration_count`
- `unavailable_cell_count`
- `mapping`
- `conversion_eligible`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- `completed` requires all requested views to produce usable rows and valid mapping.
- `partial` is used when at least one requested view produces rows but one or more views or validation gates are incomplete.
- `blocked` is used when no requested views can safely produce rows.
- `conversion_eligible` must be false unless required fields and mapping gates are valid.

## Conversion Models

### QuikStrikeMatrixXauVolOiRow

Fields:

- `date` or `timestamp`
- `expiry`
- `strike`
- `option_type`
- `open_interest`
- `oi_change`
- `volume`
- `source`
- `source_menu`
- `source_view`
- `source_extraction_id`
- `table_row_label`
- `table_column_label`
- `futures_symbol`
- `dte`
- `underlying_futures_price`
- `limitations`

Validation:

- `open_interest` is populated only from `open_interest_matrix` rows.
- `oi_change` is populated only from `oi_change_matrix` rows.
- `volume` is populated only from `volume_matrix` rows.
- Missing cells are not emitted as zero-valued rows.
- Rows require valid strike and expiration mapping.

### QuikStrikeMatrixConversionResult

Fields:

- `conversion_id`
- `extraction_id`
- `status`
- `row_count`
- `output_artifacts`
- `blocked_reasons`
- `warnings`
- `limitations`

Validation:

- Blocked conversion must include at least one blocked reason.
- Completed conversion must include at least one processed artifact.
- Conversion limitations must state that output is XAU Vol-OI local research input only.

## Report And Artifact Models

### QuikStrikeMatrixArtifact

Fields:

- `artifact_type`
- `path`
- `format`
- `rows`
- `created_at`
- `limitations`

Validation:

- Artifact paths must stay under `data/raw/quikstrike_matrix/`, `data/processed/quikstrike_matrix/`, or `data/reports/quikstrike_matrix/`.
- Reported paths should be project-relative where possible.

### QuikStrikeMatrixExtractionReport

Fields:

- `extraction_id`
- `status`
- `created_at`
- `completed_at`
- `request_summary`
- `view_summaries`
- `row_count`
- `strike_count`
- `expiration_count`
- `unavailable_cell_count`
- `mapping`
- `conversion_result`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- Report text must state local-only and research-only limitations.
- Report must not include cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, account/order/wallet fields, endpoint replay payloads, or private full URLs.

## State Transitions

### Extraction Status

```text
requested -> running -> completed
requested -> running -> partial
requested -> running -> blocked
requested -> running -> failed
```

- `completed`: all requested matrix views produced rows and mapping is valid.
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
- `blocked`: extraction is partial, strike/expiration mapping is invalid, required fields are missing, or no rows are eligible.
- `failed`: unexpected conversion failure after eligibility passed.
