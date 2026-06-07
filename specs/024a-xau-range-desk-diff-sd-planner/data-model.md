# Data Model: XAU Range Desk / Diff-SD Planner

## Enums

### XauRangeDeskReadiness

- `ready`
- `partial`
- `blocked`

### XauRangeDeskLevelKind

- `lower_3sd`
- `lower_2sd`
- `lower_1sd`
- `mean`
- `upper_1sd`
- `upper_2sd`
- `upper_3sd`
- `session_open`
- `oi_wall`

### XauRangeDeskZoneKind

- `no_trade_inside_1sd`
- `upper_stretch_2sd_to_3sd`
- `lower_stretch_2sd_to_3sd`

## Entities

### XauRangeDeskPlanRequest

- `session_date`
- `traded_instrument`
- `futures_symbol`
- `future_reference_price`
- `traded_reference_price`
- `session_open_price`
- `levels`
- `oi_walls`
- `research_only_acknowledged`

Validation:

- Reference prices must be positive.
- Level labels must be unique.
- Research-only acknowledgement is required.

### XauRangeDeskBasisSnapshot

- `future_reference_price`
- `traded_reference_price`
- `diff_points`
- `traded_offset`
- `formula`

### XauRangeDeskMappedLevel

- `label`
- `futures_level`
- `mapped_traded_level`
- `distance_from_traded_reference`
- `source`

### XauRangeDeskMappedWall

- `wall_id`
- `wall_type`
- `futures_level`
- `mapped_traded_level`
- `distance_from_traded_reference`
- `open_interest`
- `oi_change`
- `volume`
- `source`

### XauRangeDeskZone

- `zone`
- `lower_traded_level`
- `upper_traded_level`
- `meaning`

### XauRangeDeskTargetPlan

- `side`
- `target_1`
- `target_2`
- `target_3`
- `invalidation_reference`
- `planning_note`

### XauRangeDeskPlan

- `session_date`
- `traded_instrument`
- `futures_symbol`
- `readiness`
- `basis_snapshot`
- `block_size_points`
- `futures_levels`
- `traded_levels`
- `mapped_oi_walls`
- `zones`
- `target_plans`
- `missing_inputs`
- `limitations`
- `no_signal_reasons`
- `research_only`
- `signal_allowed`

Validation:

- `signal_allowed` must be false.
- `research_only` must be true.
- No-signal reasons are required.

## State Rules

```text
diff_points = future_reference_price - traded_reference_price
traded_offset = traded_reference_price - future_reference_price
mapped_traded_level = futures_level + traded_offset

lower_1sd + upper_1sd present
  -> no_trade_inside_1sd zone available

lower_2sd + lower_3sd present
  -> lower_stretch_2sd_to_3sd zone available

upper_2sd + upper_3sd present
  -> upper_stretch_2sd_to_3sd zone available

required SD levels missing
  -> readiness = partial
  -> missing_inputs includes level names

all required SD levels and at least one OI wall present
  -> readiness = ready
```
