# Data Model: XAU Candidate Forward Outcomes

## Enums

### XauCandidateOutcomeWindow

- `30m`
- `1h`
- `4h`
- `session_close`
- `next_day`

### XauCandidateOutcomeCoverageStatus

- `complete`
- `partial`
- `missing`

### XauCandidateOutcomeLabel

- `target_hit`
- `stop_hit`
- `mean_reverted`
- `breakout_continued`
- `unresolved`
- `unavailable`

### XauCandidatePriceSourceKind

- `local_csv`
- `local_json`
- `local_parquet`
- `static_fixture`

## Entities

### XauCandidatePriceBar

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `source`

Validation:

- Timestamp is normalized to UTC.
- OHLC values must be positive and internally consistent.
- Volume remains optional.

### XauCandidatePriceSeriesSource

- `source_kind`
- `source_path`
- `row_count`
- `first_timestamp`
- `last_timestamp`
- `limitations`

Validation:

- Source paths are local paths only.
- Local proxy limitations are visible.

### XauCandidateOutcome

- `candidate_id`
- `map_id`
- `run_id`
- `session_date`
- `window`
- `entry_reference`
- `stop_reference`
- `target_1`
- `target_2`
- `target_3`
- `open`
- `high`
- `low`
- `close`
- `mfe_points`
- `mae_points`
- `hit_target_1`
- `hit_target_2`
- `hit_target_3`
- `hit_stop_reference`
- `returned_to_1sd`
- `touched_2sd`
- `touched_3sd`
- `touched_3_5sd`
- `touched_next_wall`
- `continued_breakout`
- `outcome_label`
- `price_source`
- `coverage_status`
- `limitations`
- `research_only`
- `signal_allowed`

Validation:

- `signal_allowed` must be false.
- `research_only` must be true.
- Missing bars keep OHLC and MFE/MAE null.
- Hit flags are booleans and do not imply order instructions.

### XauCandidateOutcomeSet

- `outcome_run_id`
- `map_id`
- `candidate_set_id`
- `session_date`
- `windows`
- `candidate_count`
- `outcome_count`
- `unavailable_count`
- `price_source`
- `outcomes`
- `no_signal_reasons`
- `limitations`
- `research_only`
- `signal_allowed`

Validation:

- `outcome_count` must match the number of outcomes.
- `unavailable_count` must match unavailable outcomes.
- `signal_allowed` must be false.
- `research_only` must be true.

### XauCandidateOutcomeRunRequest

- `candidate_set_path`
- `price_bars_path`
- `windows`
- `output_root`
- `overwrite`
- `timestamp_column`
- `open_column`
- `high_column`
- `low_column`
- `close_column`
- `volume_column`
- `timezone`
- `research_only_acknowledged`

Validation:

- Local file paths only.
- Research-only acknowledgement is required.

### XauCandidateOutcomeRunResult

- `outcome_run_id`
- `created_at`
- `candidate_set_id`
- `map_id`
- `candidate_count`
- `outcome_count`
- `unavailable_count`
- `artifact_paths`
- `outcome_set`
- `no_signal_reasons`
- `limitations`
- `research_only`
- `signal_allowed`

Validation:

- `signal_allowed` must be false.
- `research_only` must be true.

## State Rules

```text
no price bars for candidate window
  -> coverage_status = missing
  -> outcome_label = unavailable
  -> OHLC and MFE/MAE remain null

partial bars for candidate window
  -> coverage_status = partial
  -> OHLC computed from observed bars only
  -> limitation recorded

short reversion and low <= target_1
  -> returned_to_1sd = true
  -> outcome_label = mean_reverted

long reversion and high >= target_1
  -> returned_to_1sd = true
  -> outcome_label = mean_reverted

stop reference touched before target
  -> hit_stop_reference = true
  -> outcome_label = stop_hit

breakout risk and price extends beyond 3SD/3.5SD
  -> continued_breakout = true
  -> outcome_label = breakout_continued
```
