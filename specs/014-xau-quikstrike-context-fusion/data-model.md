# Data Model: XAU QuikStrike Context Fusion

**Date**: 2026-05-13  
**Feature**: 014-xau-quikstrike-context-fusion

## Enums

### XauFusionSourceType

- `vol2vol`
- `matrix`
- `fused`

### XauFusionMatchStatus

- `matched`
- `vol2vol_only`
- `matrix_only`
- `conflict`
- `blocked`

### XauFusionAgreementStatus

- `agreement`
- `disagreement`
- `unavailable`
- `not_comparable`

### XauFusionContextStatus

- `available`
- `partial`
- `unavailable`
- `conflict`
- `blocked`

### XauFusionReportStatus

- `completed`
- `partial`
- `blocked`
- `failed`

### XauFusionArtifactType

- `metadata`
- `fused_rows_json`
- `fused_rows_parquet`
- `xau_vol_oi_input_csv`
- `xau_vol_oi_input_parquet`
- `report_json`
- `report_markdown`

## Request Models

### XauQuikStrikeFusionRequest

Fields:

- `vol2vol_report_id`
- `matrix_report_id`
- `xauusd_spot_reference`
- `gc_futures_reference`
- `session_open_price`
- `realized_volatility`
- `candle_context`
- `create_xau_vol_oi_report`
- `create_xau_reaction_report`
- `run_label`
- `persist_report`
- `research_only_acknowledged`

Validation:

- `vol2vol_report_id` and `matrix_report_id` are required filesystem-safe ids.
- `research_only_acknowledged` must be true.
- Spot/futures/session/open prices must be positive when supplied.
- Realized volatility must be positive when supplied.
- The request must reject cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, private full URLs, endpoint replay payloads, account/order/wallet data, broker fields, and execution fields.
- Downstream report creation flags are optional and must not imply live or paper trading.

### XauQuikStrikeSourceRef

Fields:

- `source_type`
- `report_id`
- `status`
- `product`
- `option_product_code`
- `row_count`
- `conversion_status`
- `warnings`
- `limitations`
- `artifact_paths`

Validation:

- Source type must be `vol2vol` or `matrix`.
- Product must be compatible with Gold/OG/GC for completed fusion.
- Source limitations are inherited by the fusion report.

## Matching Models

### XauFusionMatchKey

Fields:

- `strike`
- `expiration`
- `expiration_code`
- `expiration_key`
- `option_type`
- `value_type`

Validation:

- `strike` is required for matchable rows.
- `expiration_key` is required and is derived from calendar expiration when available, otherwise expiration code.
- `option_type` is required. `combined` does not match `call` or `put` automatically.
- `value_type` is required and must preserve source semantics.

### XauFusionSourceValue

Fields:

- `source_type`
- `source_report_id`
- `source_row_id`
- `value`
- `value_type`
- `source_view`
- `strike`
- `expiration`
- `expiration_code`
- `option_type`
- `future_reference_price`
- `dte`
- `vol_settle`
- `range_label`
- `sigma_label`
- `warnings`
- `limitations`

Validation:

- Source row id and report id must be safe strings.
- Numeric values may be null only when source context is unavailable.
- Source warnings and limitations must be sanitized and research-only.

### XauFusionCoverageSummary

Fields:

- `matched_key_count`
- `vol2vol_only_key_count`
- `matrix_only_key_count`
- `conflict_key_count`
- `blocked_key_count`
- `strike_count`
- `expiration_count`
- `option_type_count`
- `value_type_count`

Validation:

- Counts must be non-negative.
- Coverage should be derived from normalized match keys, not raw source row order.

## Fusion Models

### XauFusionRow

Fields:

- `fusion_row_id`
- `fusion_report_id`
- `match_key`
- `source_type`
- `match_status`
- `agreement_status`
- `vol2vol_value`
- `matrix_value`
- `basis_points`
- `spot_equivalent_level`
- `source_agreement_notes`
- `missing_context_notes`
- `warnings`
- `limitations`

Validation:

- `fusion_row_id` must be stable for report id and match key.
- `source_type=fused` requires at least one Vol2Vol value and one Matrix value.
- Source values are never overwritten; both source value objects remain visible when present.
- `spot_equivalent_level` is null unless basis status is available.
- `blocked` rows must include a warning or missing-context note.

### XauFusionMissingContextItem

Fields:

- `context_key`
- `status`
- `severity`
- `message`
- `blocks_conversion`
- `blocks_reaction_confidence`
- `source_refs`

Validation:

- Status must be one of `available`, `partial`, `unavailable`, `conflict`, or `blocked`.
- Blocking items must include an explanatory message.
- Messages must not claim profitability, prediction, safety, or live readiness.

### XauFusionBasisState

Fields:

- `status`
- `xauusd_spot_reference`
- `gc_futures_reference`
- `basis_points`
- `calculation_note`
- `warnings`

Validation:

- `available` requires positive spot and futures references.
- `basis_points` is null unless status is available.
- The calculation note must identify that spot-equivalent levels are research annotations only.

### XauFusionContextSummary

Fields:

- `basis_status`
- `iv_range_status`
- `open_regime_status`
- `candle_acceptance_status`
- `realized_volatility_status`
- `source_agreement_status`
- `missing_context`

Validation:

- Each status is required.
- Missing context checklist must include absent basis, IV/range, open, candle, and RV context when unavailable.

## Conversion And Downstream Models

### XauFusionVolOiInputRow

Fields:

- `date`
- `timestamp`
- `expiry`
- `expiration_code`
- `strike`
- `spot_equivalent_strike`
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
- `source_report_ids`
- `source_agreement_status`
- `limitations`

Validation:

- Strike, expiration or expiration code, option type, and at least one usable value field are required.
- Spot-equivalent strike is optional and requires available basis.
- Matrix OI/OI Change/Volume mappings and Vol2Vol current-expiry context must be preserved without silent overwrite.

### XauFusionDownstreamResult

Fields:

- `xau_vol_oi_report_id`
- `xau_reaction_report_id`
- `xau_report_status`
- `reaction_report_status`
- `reaction_row_count`
- `no_trade_count`
- `all_reactions_no_trade`
- `notes`

Validation:

- Linked report ids are optional and safe when present.
- If all reactions are NO_TRADE, notes must explain missing or conflicting context when known.

## Report Models

### XauQuikStrikeFusionReport

Fields:

- `report_id`
- `status`
- `created_at`
- `completed_at`
- `request`
- `vol2vol_source`
- `matrix_source`
- `coverage`
- `context_summary`
- `basis_state`
- `fused_row_count`
- `xau_vol_oi_input_row_count`
- `fused_rows`
- `downstream_result`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- Report id must be filesystem-safe.
- `completed` requires at least one fused or source-only row and no blocking source compatibility issue.
- `partial` is allowed when rows exist but optional context or downstream creation is incomplete.
- `blocked` requires at least one blocked reason or missing context item.
- Report text must not include secret/session fields or execution claims.

### XauQuikStrikeFusionSummary

Fields:

- `report_id`
- `status`
- `created_at`
- `vol2vol_report_id`
- `matrix_report_id`
- `fused_row_count`
- `strike_count`
- `expiration_count`
- `basis_status`
- `iv_range_status`
- `open_regime_status`
- `candle_acceptance_status`
- `xau_vol_oi_report_id`
- `xau_reaction_report_id`
- `all_reactions_no_trade`
- `warning_count`

Validation:

- Counts must be non-negative.
- Linked report ids are optional and safe when present.

## Relationships

```text
XauQuikStrikeFusionRequest (1) -> (1) Vol2Vol QuikStrikeExtractionReport
XauQuikStrikeFusionRequest (1) -> (1) Matrix QuikStrikeMatrixExtractionReport
Vol2Vol rows (many) + Matrix rows (many) -> XauFusionRow (many)
XauQuikStrikeFusionReport (1) -> XauFusionVolOiInputRow (many)
XauQuikStrikeFusionReport (0..1) -> XauVolOiReport from feature 006
XauQuikStrikeFusionReport (0..1) -> XauReactionReport from feature 010
XauQuikStrikeFusionReport (1) -> XauFusionMissingContextItem (many)
```

## State Rules

- A fusion report is `blocked` when either source report is missing, product compatibility fails, source reports have no usable rows, or join-key mapping is unsafe.
- A fusion report is `partial` when fusion rows exist but optional context, basis, IV/range, open/candle context, downstream XAU Vol-OI creation, or reaction creation is unavailable.
- A fusion report is `completed` when source reports are compatible, fusion rows are created, missing context is explicitly reported, and requested downstream steps either complete or are not requested.
- Source disagreements do not automatically block fusion, but they must be visible and may block downstream conversion when they affect required fields.
- Missing basis does not block futures-strike fusion but prevents spot-equivalent levels.
- Missing session open, candle acceptance, IV/range, or realized volatility should preserve conservative downstream reaction output.

## Validation Rules

- IDs must be filesystem-safe and must not allow path traversal.
- Generated artifact paths must remain under ignored fusion, XAU, QuikStrike, or report roots.
- No payload, report, row, warning, limitation, or artifact may include cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, private full URLs, or endpoint replay payloads.
- `research_only_acknowledged` must be true for fusion creation.
- Optional basis references must be positive and internally consistent when supplied.
- Fused XAU Vol-OI rows require valid strike, expiration or expiration code, option type, and at least one value field.
- Downstream reaction reports must not be made less conservative by fabricated missing context.
- Reports and dashboard responses must not emit buy/sell wording as execution signals or claim profitability, predictive power, safety, or live readiness.
