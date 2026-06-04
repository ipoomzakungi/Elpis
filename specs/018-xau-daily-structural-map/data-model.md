# Data Model: XAU Daily Structural Map

**Date**: 2026-06-04
**Feature**: 018-xau-daily-structural-map

## Enums

### XauDailyStructuralMapReadiness

- `structural_map_ready`
- `partial_missing_basis`
- `partial_missing_expected_range`
- `partial_missing_session_open`
- `blocked_insufficient_context`

### XauDailyStructuralMapWallMappingStatus

- `mapped`
- `basis_unavailable`
- `range_unavailable`
- `unavailable`

## Entities

### XauDailyStructuralMapRange

Fields:

- `expected_range_source`
- `report_level_iv`
- `fractional_dte`
- `lower_1sd`
- `upper_1sd`
- `lower_2sd`
- `upper_2sd`
- `lower_3sd`
- `upper_3sd`
- `limitations`

### XauDailyStructuralMapBasis

Fields:

- `basis`
- `basis_source`
- `basis_mapping_available`
- `basis_timestamp_alignment_status`
- `limitations`

Validation:

- Available mapping requires a basis.
- Unavailable mapping uses `basis_source = unavailable`.

### XauDailyStructuralMapWall

Fields:

- `wall_id`
- `expiry`
- `expiration_code`
- `strike`
- `wall_type`
- `open_interest`
- `oi_change`
- `volume`
- `wall_score`
- `freshness_state`
- `spot_equivalent_level`
- `distance_to_traded_price`
- `distance_to_session_open`
- `inside_1sd`
- `inside_2sd`
- `near_expected_range_boundary`
- `open_side_vs_wall`
- `mapping_status`
- `limitations`

Validation:

- Mapped walls require `spot_equivalent_level`.
- Missing basis leaves mapped price fields null.

### XauDailyStructuralMap

Fields:

- `map_id`
- `session_date`
- `created_at`
- `source_product`
- `option_product_code`
- `futures_symbol`
- `expiration_code`
- `expiry_date`
- `reference_futures_price`
- `traded_instrument`
- `traded_reference_price`
- `basis`
- `basis_source`
- `basis_mapping_available`
- `basis_timestamp_alignment_status`
- `expected_range_source`
- `report_level_iv`
- `fractional_dte`
- `lower_1sd`
- `upper_1sd`
- `lower_2sd`
- `upper_2sd`
- `lower_3sd`
- `upper_3sd`
- `session_open_price`
- `session_open_source`
- `session_open_available`
- `open_side_vs_1sd`
- `open_distance_points`
- `wall_count`
- `walls`
- `data_quality_state`
- `signal_allowed`
- `no_signal_reasons`
- `limitations`

Validation:

- `signal_allowed` must be false.
- `wall_count` must equal the number of wall rows.
- Complete maps still include a no-signal reason because Feature 018 is map-only.

## State Rules

```text
range available + basis available + walls present + session open available
  -> data_quality_state = structural_map_ready
  -> signal_allowed = false

basis unavailable
  -> spot-equivalent wall levels = null
  -> add "Basis mapping unavailable."

expected range unavailable
  -> SD fields = null
  -> add "Expected range unavailable."

session open unavailable
  -> session-open fields = null
  -> data_quality_state = partial_missing_session_open

range unavailable + basis unavailable, or no walls
  -> data_quality_state = blocked_insufficient_context
```

## Forward-Journal Compatibility

Maps preserve stable ids, source product, session date, expected-range source, basis readiness, wall ids, no-signal reasons, and limitations. Later forward outcome labels should attach to these stable fields without mutating the original map.
