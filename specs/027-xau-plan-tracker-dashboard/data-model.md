# Data Model: XAU Plan Tracker Dashboard

## Domain Summary

The dashboard consumes backend outputs from Feature 026:

- `XauPlanTrackerRunResult` (run summary)
- `XauPlanTrackerSnapshot` (per planning time)
- `XauPlanTrackerOrder` (per simulated order)

## Dashboard UI Model

### Run Summary View

- `run_id`
- `session_date`
- `created_at`
- `readiness`
- `snapshot_count`
- `tracked_order_count`
- `open_order_count`
- `completed_order_count`
- `artifact_paths`
- `research_only`
- `signal_allowed`
- `missing_inputs`
- `limitations`
- `no_signal_reasons`

### Snapshot View

- `snapshot_id`
- `planning_time`
- `future_reference_price`
- `traded_reference_price`
- `diff_points`
- `dte`
- `native_1sd`
- `native_2sd`
- `native_3sd`
- `reference_alignment`
- `long_plan.entry_level`
- `long_plan.target_level`
- `long_plan.stop_level`
- `long_plan.recovery_entry_level`
- `long_plan.recovery_target_level`
- `short_plan.*` (same fields)
- `missing_inputs`
- `limitations`

### Order View

- `order_id`
- `planning_time`
- `side`
- `entry_level`
- `target_level`
- `stop_level`
- `recovery_entry_level`
- `recovery_target_level`
- `status`
- `strict_triggered`
- `near_miss`
- `near_miss_distance_points`
- `near_miss_threshold_points`
- `closest_price_to_entry`
- `closest_time_to_entry`
- `trigger_time`
- `exit_time`
- `current_price`
- `current_pnl_points`
- `max_favorable_excursion_points`
- `max_adverse_excursion_points`
- `drawdown_points`
- `bars_covered_count`
- `limitations`
- `research_only`
- `signal_allowed`

## Display Rules

- `null` values render as `n/a` to avoid false assumptions.
- Long/short cards render only available fields.
- Near-miss chips render only where `near_miss` is true.
- Recovery rows are shown as normal statuses with dedicated counts.

