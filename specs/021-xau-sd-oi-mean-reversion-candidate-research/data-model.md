# Data Model: XAU SD OI Mean Reversion Candidate Research

**Date**: 2026-06-07
**Feature**: 021-xau-sd-oi-mean-reversion-candidate-research

## Enums

### XauSdOiCandidateSide

- `long_reversion_candidate`
- `short_reversion_candidate`
- `no_trade`
- `breakout_risk`

### XauSdOiStretchZone

- `upper_2sd_to_3sd`
- `lower_2sd_to_3sd`
- `outside_3sd`
- `inside_normal_range`
- `unavailable`

### XauSdOiConfirmationState

- `unavailable`
- `neutral`
- `rejection`
- `close_back_inside`
- `acceptance`

### XauSdOiIvState

- `unavailable`
- `stable`
- `compressing`
- `expanding`

### XauSdOiFlowState

- `unavailable`
- `neutral`
- `not_breakout_confirmed`
- `flow_through_wall`

### XauSdOiWallState

- `unavailable`
- `no_mapped_wall`
- `nearest_wall_present`

### XauSdOiReadinessState

- `candidate_ready`
- `monitor_only`
- `breakout_risk`
- `blocked_missing_context`

## Entities

### XauSdOiCandidateReason

Fields:

- `reason_code`
- `message`
- `severity`

Validation:

- Text fields are normalized and cannot be blank.

### XauSdOiCandidateTarget

Fields:

- `label`
- `level`
- `source`

Validation:

- `level` may be null only when the source reference is unavailable.

### XauSdOiCandidateInvalidation

Fields:

- `label`
- `level`
- `source`

Validation:

- Invalidation references are research-only and must not imply order placement.

### XauSdOiCandidate

Fields:

- `candidate_id`
- `map_id`
- `wall_id`
- `session_date`
- `timestamp`
- `side`
- `stretch_zone`
- `traded_price`
- `gc_price`
- `basis`
- `nearest_wall_level`
- `nearest_wall_distance`
- `nearest_wall_oi_change`
- `nearest_wall_volume`
- `expected_range_source`
- `lower_1sd`
- `upper_1sd`
- `lower_2sd`
- `upper_2sd`
- `lower_3sd`
- `upper_3sd`
- `lower_3_5sd`
- `upper_3_5sd`
- `target_1`
- `target_2`
- `target_3`
- `stop_reference`
- `confirmation_state`
- `iv_state`
- `flow_state`
- `oi_wall_state`
- `readiness_state`
- `reasons`
- `targets`
- `invalidations`
- `no_signal_reasons`
- `limitations`
- `signal_allowed`
- `research_only`

Validation:

- `signal_allowed` must be false.
- `research_only` must be true.
- `candidate_id` and `map_id` cannot be blank.
- Null wall OI-change and volume values remain null.

### XauSdOiCandidateSet

Fields:

- `map_id`
- `session_date`
- `timestamp`
- `candidate_count`
- `candidates`
- `no_signal_reasons`
- `limitations`
- `signal_allowed`
- `research_only`

Validation:

- `candidate_count` must equal the number of candidates.
- `signal_allowed` must be false.
- `research_only` must be true.

## State Rules

```text
missing basis/range/traded price/session open
  -> side = no_trade
  -> readiness_state = blocked_missing_context
  -> signal_allowed = false

upper_2sd <= traded_price <= upper_3sd
and rejection/close_back_inside
and IV not expanding
and flow not through wall
  -> side = short_reversion_candidate
  -> target_1 = upper_1sd
  -> target_2 = session open or range midpoint
  -> stop_reference = upper_3_5sd

lower_3sd <= traded_price <= lower_2sd
and rejection/close_back_inside
and IV not expanding
and flow not through wall
  -> side = long_reversion_candidate
  -> target_1 = lower_1sd
  -> target_2 = session open or range midpoint
  -> stop_reference = lower_3_5sd

traded_price beyond 3SD
or IV expanding + flow-through-wall + acceptance
  -> side = breakout_risk

lower_2sd <= traded_price <= upper_2sd
  -> side = no_trade
  -> readiness_state = monitor_only
```
