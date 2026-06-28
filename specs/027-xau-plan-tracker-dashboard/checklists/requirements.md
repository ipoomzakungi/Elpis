# Requirements Checklist: XAU Plan Tracker Dashboard

- [X] Frontend route `/xau-plan-tracker` exists.
- [X] Loads latest run and run/snapshot/order bundle on mount.
- [X] Supports loading a specific run_id.
- [X] Displays run summary, planning snapshots, and mapped long/short levels.
- [X] Displays order outcomes, status, PnL, drawdown, and near-miss diagnostics.
- [X] Displays research-only signals (`signal_allowed=false`, `research_only=true`).
- [X] Handles empty API state with guidance instead of hard error.
- [X] Adds nav entry from global header.
- [X] Does not add live trading controls or execution actions.
