## Data Model: XAU Plan Tracker Stats

- `XauPlanTrackerStatsRequest`
  - `session_date_from`, `session_date_to`
  - `planning_times`
  - `sides`
  - `statuses`
  - `include_unavailable_orders`
  - `max_runs`

- `XauPlanTrackerStatsRunSummary`
  - `run_id`, `session_date`
  - counts: snapshot_count, order_count, status_counts, side_counts, planning_time_counts
  - counts of near-miss and strict-triggered plans
  - average current PnL/drawdown

- `XauPlanTrackerDteStats`
  - sample_count/min/max/average

- `XauPlanTrackerStatsResult`
  - aggregate totals, run-level counts
  - global status/side/planning-time counts
  - recovery count, near miss count, strict trigger count
  - aggregate PnL/DD/min/max metrics
  - run summaries
  - `research_only=true`, `signal_allowed=false`
