# Quickstart: XAU Dukascopy Price Capture And Plan Tracker

## Run With Existing Local Bars

```powershell
cd backend
python scripts/run_xau_plan_tracker.py `
  --session-date 2026-06-08 `
  --planning-time 10:10 `
  --planning-time 18:10 `
  --price-bars-path data/imports/xau_bars_20260608.csv `
  --entry-sd 2.0 `
  --target-sd 1.0 `
  --stop-sd 2.5 `
  --recovery-entry-sd 3.0 `
  --recovery-target-sd 2.0
```

## Run With Dukascopy CLI

```powershell
cd backend
python scripts/run_xau_plan_tracker.py `
  --session-date 2026-06-08 `
  --planning-time 10:10 `
  --planning-time 18:10 `
  --dukas-cli-path "PATH_TO_DUKAS_CLI" `
  --dukas-command-template "{cli} --symbol {symbol} --timeframe {timeframe} --from {start} --to {end} --output {output}"
```

## API

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/research/xau/plan-tracker/run `
  -ContentType "application/json" `
  -Body '{"session_date":"2026-06-08","planning_times":["10:10","18:10"],"price_bars_path":"data/imports/xau_bars_20260608.csv","research_only_acknowledged":true}'
```

## Expected Output

- Two snapshots for 10:10 and 18:10 when bars cover both references.
- Long and short simulated research orders.
- Current simulated PnL points and drawdown/MAE points when an order triggers.
- `research_only=true`
- `signal_allowed=false`

## Validation

```powershell
cd backend
python -m pytest tests/unit/test_xau_plan_tracker_dukas_cli.py -q
python -m pytest tests/unit/test_xau_plan_tracker_reference_price.py -q
python -m pytest tests/unit/test_xau_plan_tracker_order_tracker.py -q
python -m pytest tests/unit/test_xau_plan_tracker_service.py -q
python -m pytest tests/unit/test_xau_plan_tracker_api.py -q
python -m pytest tests/unit/test_run_xau_plan_tracker_script.py -q
python -c "from src.main import app; print('backend import ok')"
python scripts/run_xau_plan_tracker.py --help
```
