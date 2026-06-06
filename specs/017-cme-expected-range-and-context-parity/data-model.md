# Data Model: CME Expected Range And Context Parity

**Date**: 2026-06-04
**Feature**: 017-cme-expected-range-and-context-parity

## Enums

### XauExpectedRangeSource

- `cme_native`
- `derived_from_iv`
- `unavailable`

### XauExpectedRangeExtractionQuality

- `complete`
- `partial`
- `unavailable`

### XauExpectedRangeSourceStatus

- `preliminary`
- `final`
- `unknown`

## Entities

### XauExpectedRangeSnapshot

Fields:

- `source_report_id`
- `source_view`
- `capture_timestamp`
- `official_release_ts`
- `source_status`
- `product`
- `option_product_code`
- `futures_symbol`
- `expiration_code`
- `expiry_date`
- `reference_futures_price`
- `report_level_iv`
- `vol_settle`
- `fractional_dte`
- `cme_numeric_1sd`
- `cme_numeric_2sd`
- `cme_numeric_3sd`
- `upper_1sd`
- `lower_1sd`
- `upper_2sd`
- `lower_2sd`
- `upper_3sd`
- `lower_3sd`
- `range_source`
- `extraction_quality`
- `limitations`

Validation:

- `cme_native` requires numeric 1SD, 2SD, 3SD and all upper/lower bands.
- `derived_from_iv` requires reference futures price, report-level IV, fractional DTE, computed 1SD, 2SD, 3SD, and all upper/lower bands.
- `unavailable` requires at least one limitation.
- Text fields are normalized and cannot be blank.
- Limitations are deduplicated.

### XauExpectedRange

Extended fields:

- `report_level_iv`
- `fractional_dte`
- `cme_numeric_1sd`
- `cme_numeric_2sd`
- `cme_numeric_3sd`
- `lower_3sd`
- `upper_3sd`
- `range_source`
- `extraction_quality`

Validation:

- Existing unavailable-range validation remains.
- Available ranges still require reference price, expected move, and 1SD bounds.

### XauQuikStrikeFusionReport

Additional field:

- `expected_range_snapshot`

Validation:

- Optional. Existing fusion validation still controls completed/blocked report state.

### XauVolOiReport

Additional field:

- `expected_range_snapshot`

Validation:

- Optional. Existing XAU report expected-range behavior remains compatible.

## State Rules

```text
CME native numeric fields complete
  -> range_source = cme_native
  -> extraction_quality = complete

CME native numeric fields missing, IV inputs complete
  -> range_source = derived_from_iv
  -> extraction_quality = complete
  -> add fallback limitation

Only range_label or per-strike vol_settle exists
  -> range_source = unavailable
  -> extraction_quality = unavailable
  -> no numeric bands created
```

## No-Lookahead Fields

- `capture_timestamp` records when the local research snapshot was captured.
- `official_release_ts` records when the source was officially usable, if known.
- `source_status` records preliminary, final, or unknown status.

These fields are required for later backtesting discipline but Feature 017 does not run a strategy backtest.
