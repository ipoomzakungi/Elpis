# Data Model: XAU Forward Research Journal

**Date**: 2026-05-14  
**Feature**: 015-xau-forward-research-journal

## Enums

### XauForwardJournalSourceType

- `quikstrike_vol2vol`
- `quikstrike_matrix`
- `xau_quikstrike_fusion`
- `xau_vol_oi`
- `xau_reaction`

### XauForwardJournalEntryStatus

- `completed`
- `partial`
- `blocked`
- `failed`

### XauForwardOutcomeWindow

- `30m`
- `1h`
- `4h`
- `session_close`
- `next_day`

### XauForwardOutcomeLabel

- `wall_held`
- `wall_rejected`
- `wall_accepted_break`
- `moved_to_next_wall`
- `reversed_before_target`
- `stayed_inside_range`
- `no_trade_was_correct`
- `inconclusive`
- `pending`

### XauForwardOutcomeStatus

- `pending`
- `completed`
- `partial`
- `inconclusive`
- `conflict`
- `blocked`

### XauForwardArtifactType

- `metadata`
- `entry_json`
- `outcomes_json`
- `report_json`
- `report_markdown`

## Request Models

### XauForwardJournalCreateRequest

Fields:

- `snapshot_time`
- `capture_session`
- `vol2vol_report_id`
- `matrix_report_id`
- `fusion_report_id`
- `xau_vol_oi_report_id`
- `xau_reaction_report_id`
- `spot_price_at_snapshot`
- `futures_price_at_snapshot`
- `basis`
- `session_open_price`
- `event_news_flag`
- `notes`
- `persist_report`
- `research_only_acknowledged`

Validation:

- Source report ids are required and must be filesystem-safe ids.
- `snapshot_time` is required and must be timezone-aware or normalized to UTC.
- Prices and basis must be numeric when supplied; prices must be positive.
- `research_only_acknowledged` must be true.
- Notes must reject cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, private full URLs, endpoint replay payloads, account/order/wallet data, broker fields, execution fields, and unsupported performance claims.
- Missing optional snapshot context is allowed and must be represented as unavailable.

### XauForwardOutcomeUpdateRequest

Fields:

- `outcomes`
- `update_note`
- `research_only_acknowledged`

Validation:

- `research_only_acknowledged` must be true.
- At least one outcome window must be included.
- Each window must be one of the supported outcome windows.
- Labels must be one of the supported outcome labels.
- Missing OHLC data may only produce `pending` or `inconclusive`.
- Updating an existing non-pending label requires `update_note`.
- Notes must reject forbidden secret/session/execution/performance wording.

## Core Models

### XauForwardSourceReportRef

Fields:

- `source_type`
- `report_id`
- `status`
- `created_at`
- `product`
- `expiration`
- `expiration_code`
- `row_count`
- `warnings`
- `limitations`
- `artifact_paths`

Validation:

- `source_type` must match one of the supported report families.
- Product must be compatible with XAU/Gold/OG/GC for completed journal entries.
- Source warnings and limitations are inherited by the journal entry.

### XauForwardSnapshotContext

Fields:

- `snapshot_time`
- `capture_session`
- `product`
- `expiration`
- `expiration_code`
- `spot_price_at_snapshot`
- `futures_price_at_snapshot`
- `basis`
- `session_open_price`
- `event_news_flag`
- `missing_context`
- `notes`

Validation:

- Snapshot time and capture session are required.
- Missing optional values are represented in `missing_context`.
- Basis is either user supplied or computed only when enough explicit inputs exist.

### XauForwardWallSummary

Fields:

- `summary_id`
- `wall_type`
- `source_report_id`
- `strike`
- `expiration`
- `expiration_code`
- `option_type`
- `open_interest`
- `oi_change`
- `volume`
- `wall_score`
- `rank`
- `notes`
- `limitations`

Validation:

- `strike` is required.
- At least one of open interest, OI change, volume, or wall score must be available.
- Rank is positive and deterministic within each wall type.

### XauForwardReactionSummary

Fields:

- `reaction_id`
- `source_report_id`
- `wall_id`
- `zone_id`
- `reaction_label`
- `confidence_label`
- `no_trade_reasons`
- `bounded_risk_annotation_count`
- `notes`
- `limitations`

Validation:

- Reaction label and source report id are required.
- NO_TRADE reasons are preserved when present.
- Risk annotations are summaries only and not executable instructions.

### XauForwardMissingContextItem

Fields:

- `context_key`
- `status`
- `severity`
- `message`
- `source_report_ids`
- `blocks_outcome_label`
- `blocks_reaction_review`

Validation:

- Message must be research-only and must not make performance claims.

### XauForwardOutcomeObservation

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
- `reference_wall_id`
- `reference_wall_level`
- `next_wall_reference`
- `notes`
- `limitations`
- `updated_at`

Validation:

- Window is required.
- Label defaults to `pending`.
- OHLC values must be internally consistent when all are supplied.
- Missing OHLC data keeps label `pending` or `inconclusive`.
- Non-pending labels require sufficient observation context or an explicit note.

### XauForwardJournalEntry

Fields:

- `journal_id`
- `status`
- `created_at`
- `updated_at`
- `snapshot`
- `source_reports`
- `top_oi_walls`
- `top_oi_change_walls`
- `top_volume_walls`
- `reaction_summaries`
- `missing_context`
- `outcomes`
- `notes`
- `warnings`
- `limitations`
- `research_only_warnings`
- `artifacts`

Validation:

- Journal id is filesystem-safe.
- Snapshot is immutable after creation.
- Outcomes may be updated without mutating source report summaries.
- At least one source report limitation must be present in completed entries.

## Response Models

### XauForwardJournalSummary

Fields:

- `journal_id`
- `status`
- `snapshot_time`
- `capture_session`
- `product`
- `expiration`
- `expiration_code`
- `fusion_report_id`
- `xau_vol_oi_report_id`
- `xau_reaction_report_id`
- `outcome_status`
- `completed_outcome_count`
- `pending_outcome_count`
- `no_trade_count`
- `warning_count`

### XauForwardJournalListResponse

Fields:

- `entries`

### XauForwardOutcomeResponse

Fields:

- `journal_id`
- `outcomes`
- `updated_at`
- `warnings`
- `limitations`

## State Transitions

```text
entry requested
  -> blocked   (source reports missing/incompatible or request unsafe)
  -> partial   (sources load with warnings or optional context missing)
  -> completed (sources load and required snapshot summaries are available)

outcome window
  -> pending       (default or no data)
  -> inconclusive  (data insufficient for a stronger label)
  -> completed     (non-pending label with enough context)
  -> conflict      (update changes previous non-pending label without accepted note)
  -> blocked       (invalid window, unsafe request, or impossible OHLC values)
```

## Persistence Contract

Generated journal artifacts:

```text
data/reports/xau_forward_journal/<journal_id>/
|-- metadata.json
|-- entry.json
|-- outcomes.json
|-- report.json
`-- report.md
```

All generated artifacts must remain ignored and untracked.
