# Quickstart: XAU Plan Tracker Dashboard

## Backend Run (required source data)

```powershell
cd backend
python scripts/run_xau_plan_tracker.py `
  --session-date 2026-06-08 `
  --planning-time 10:10 `
  --planning-time 18:10 `
  --price-bars-path data/imports/binance_spot_xautusdt_20260608_1m.csv `
  --stop-sd 0.5 `
  --recovery-multiplier 3 `
  --near-miss-threshold-points 0.3
```

## Frontend

```powershell
cd frontend
npm run dev
```

Open:

```
http://localhost:3000/xau-plan-tracker
```

## What to expect

- Latest run summary card with session, date, readiness, and counts.
- Two snapshot cards (10:10 and 18:10) with long/short plan levels.
- Orders table with status, triggers, current PnL points, drawdown, strict/near-miss flags.
- Source-quality panel with missing inputs, limitations, and no-signal reasons.
- Clear `research_only`/`signal_allowed` warning.

## API sanity check (optional)

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8000/api/v1/research/xau/plan-tracker/latest
```
