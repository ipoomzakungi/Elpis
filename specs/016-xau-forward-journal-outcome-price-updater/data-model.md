# Data Model: XAU Forward Journal Outcome Price Updater

**Date**: 2026-05-14
**Feature**: 016-xau-forward-journal-outcome-price-updater

## Enums

### XauForwardPriceSourceLabel

- `true_xauusd_spot`
- `gc_futures`
- `yahoo_gc_f_proxy`
- `gld_etf_proxy`
- `local_csv`
- `local_parquet`
- `unknown_proxy`

### XauForwardPriceCoverageStatus

- `complete`
- `partial`
- `missing`
- `invalid`
- `blocked`

### XauForwardPriceDirection

- `up_from_snapshot`
- `down_from_snapshot`
- `flat_from_snapshot`
- `unavailable`

### XauForwardPriceArtifactType

- `price_coverage_json`
- `price_update_report_json`
- `price_update_report_markdown`

## Request Models

### XauForwardPriceDataUpdateRequest

Fields:

- `source_label`
- `source_symbol`
- `ohlc_path`
- `timestamp_column`
- `open_column`
- `high_column`
- `low_column`
- `close_column`
- `timezone`
- `update_note`
- `persist_report`
- `research_only_acknowledged`

Validation:

- `research_only_acknowledged` must be true.
- `source_label` must be one of the required price source labels.
- `source_symbol` is optional but, when supplied, must be consistent with the source label where the label implies GC futures, GC=F, GLD, or XAUUSD spot.
- `ohlc_path` must point to an approved local CSV/Parquet file or existing local public OHLC output path.
- Column names default to timestamp/open/high/low/close but may be overridden.
- Requests must reject cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, private full URLs, endpoint replay payloads, broker fields, order fields, wallet fields, execution fields, paid-vendor secrets, and unsupported performance claims.
- `update_note` is required when an update changes an existing non-pending outcome.

### XauForwardPriceCoverageRequest

Fields:

- `source_label`
- `source_symbol`
- `ohlc_path`
- `timestamp_column`
- `open_column`
- `high_column`
- `low_column`
- `close_column`
- `timezone`
- `research_only_acknowledged`

Validation:

- Same source, path, schema, and forbidden-content validation as `XauForwardPriceDataUpdateRequest`.
- Does not mutate journal outcomes.

## Core Models

### XauForwardOhlcCandle

Fields:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Validation:

- Timestamp must be normalized to UTC or rejected when ambiguous.
- Open, high, low, and close are required and positive.
- High must be greater than or equal to open, low, and close.
- Low must be less than or equal to open and close.
- Duplicate timestamps are invalid.
- Candles must be sorted deterministically by timestamp.

### XauForwardPriceSource

Fields:

- `source_label`
- `source_symbol`
- `source_path`
- `format`
- `row_count`
- `first_timestamp`
- `last_timestamp`
- `warnings`
- `limitations`

Validation:

- Label must be controlled.
- Local paths must be path-safe and must not contain private URLs or endpoint replay material.
- Proxy sources must include at least one proxy limitation note.
- `true_xauusd_spot` must not be assigned to GC futures, GC=F, GLD, or unknown local proxy data.

### XauForwardOutcomeWindowRange

Fields:

- `window`
- `required_start`
- `required_end`
- `boundary_basis`
- `limitations`

Validation:

- `required_end` must be after `required_start`.
- `30m`, `1h`, and `4h` are calculated from snapshot time.
- `session_close` and `next_day` must use known research session boundaries or carry a limitation that prevents completed status.

### XauForwardPriceCoverageWindow

Fields:

- `window`
- `status`
- `required_start`
- `required_end`
- `observed_start`
- `observed_end`
- `candle_count`
- `gap_count`
- `missing_reason`
- `partial_reason`
- `source_label`
- `source_symbol`
- `limitations`

Validation:

- `complete` requires sufficient candles to span the required start/end interval and no blocking gaps.
- `partial` requires at least one overlapping candle but incomplete coverage.
- `missing` requires no usable overlapping candles.
- `invalid` or `blocked` requires a validation reason.

### XauForwardPriceOutcomeMetrics

Fields:

- `window`
- `status`
- `label`
- `observation_start`
- `observation_end`
- `open`
- `high`
- `low`
- `close`
- `range`
- `snapshot_price`
- `direction`
- `source_label`
- `source_symbol`
- `notes`
- `limitations`

Validation:

- Complete coverage can compute high, low, close, and range.
- Direction is computed only when snapshot price is available.
- Missing coverage maps to pending outcome state.
- Partial coverage maps to inconclusive outcome state.
- Metrics must not imply trade direction, profitability, prediction, safety, or live readiness.

### XauForwardMissingCandleItem

Fields:

- `window`
- `required_start`
- `required_end`
- `status`
- `message`
- `action`

Validation:

- Each missing or partial window must have an item.
- Message must be research-only and must not include execution instructions.

### XauForwardPriceCoverageSummary

Fields:

- `journal_id`
- `snapshot_time`
- `source`
- `windows`
- `complete_windows`
- `partial_windows`
- `missing_windows`
- `missing_candle_checklist`
- `proxy_limitations`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- Must include all five required outcome windows.
- Must include exactly one source label.
- Must include proxy limitations for non-spot sources.

### XauForwardPriceOutcomeUpdateReport

Fields:

- `update_id`
- `journal_id`
- `created_at`
- `source`
- `coverage_summary`
- `updated_outcomes`
- `missing_candle_checklist`
- `proxy_limitations`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

Validation:

- Update id is filesystem-safe.
- Artifacts must remain under `data/reports/xau_forward_journal/<journal_id>/price_updates/`.
- Updated outcomes must preserve immutable snapshot/source/wall/reaction fields from the journal entry.
- Report text must not include trading, execution, profitability, predictive, safety, or live-readiness claims.

### Extended XauForwardOutcomeObservation

Additional fields:

- `range`
- `direction`
- `price_source_label`
- `price_source_symbol`
- `coverage_status`
- `coverage_reason`
- `price_update_id`

Validation:

- Existing outcome fields remain backward-compatible.
- Missing candles keep `status=pending` and `label=pending`.
- Partial candles set `status=inconclusive` and `label=inconclusive`.
- Complete windows may set computed metrics but must not create strategy claims.

## Response Models

### XauForwardPriceCoverageResponse

Fields:

- `journal_id`
- `coverage`
- `warnings`
- `limitations`
- `research_only_warnings`

### XauForwardPriceOutcomeUpdateResponse

Fields:

- `journal_id`
- `update_report`
- `outcomes`
- `coverage`
- `artifacts`
- `warnings`
- `limitations`
- `research_only_warnings`

## State Transitions

```text
price coverage window
  -> complete  (usable candles fully cover required interval)
  -> partial   (some overlap exists but interval is incomplete)
  -> missing   (no usable overlapping candles)
  -> invalid   (schema, OHLC, timestamp, or source validation fails)
  -> blocked   (request unsafe, journal missing, or boundary cannot be trusted)

outcome window from price update
  pending -> completed     (complete coverage with computed metrics)
  pending -> inconclusive  (partial coverage)
  pending -> pending       (missing coverage)
  completed/inconclusive -> conflict (non-pending change without update note)
```

## Persistence Contract

Generated price-update artifacts:

```text
data/reports/xau_forward_journal/<journal_id>/price_updates/
|-- <update_id>_coverage.json
|-- <update_id>_report.json
`-- <update_id>_report.md
```

Existing journal artifacts that may be refreshed:

```text
data/reports/xau_forward_journal/<journal_id>/
|-- metadata.json
|-- entry.json
|-- outcomes.json
|-- report.json
`-- report.md
```

All generated artifacts must remain ignored and untracked.
