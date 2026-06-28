# Quickstart: XAU Walk-Forward Range Desk Research Runner

## Backend Import Check

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
```

## Focused Tests

```powershell
cd backend
python -m pytest tests/unit/test_xau_walk_forward_schedule.py -q
python -m pytest tests/unit/test_xau_walk_forward_sd_source.py -q
python -m pytest tests/unit/test_xau_walk_forward_order_planner.py -q
python -m pytest tests/unit/test_xau_walk_forward_simulated_order_engine.py -q
python -m pytest tests/unit/test_xau_walk_forward_report_store.py -q
python -m pytest tests/unit/test_xau_walk_forward_api.py -q
python -m pytest tests/unit/test_run_xau_walk_forward_research_script.py -q
```

## CLI Smoke

```powershell
cd backend
python scripts/run_xau_walk_forward_research.py `
  --session-date 2026-06-08 `
  --mode planning-only `
  --cme-source fixture `
  --price-source manual `
  --future-reference-price 4500 `
  --traded-reference-price 4470
```

Expected:

- A run ID is printed.
- Artifacts are written under `data/reports/xau_walk_forward/{run_id}`.
- `signal_allowed=false`.

## API Smoke

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/research/xau/walk-forward/run `
  -ContentType "application/json" `
  -Body '{"session_date":"2026-06-08","cme_source":"fixture","price_source":"manual","future_reference_price":4500,"traded_reference_price":4470,"research_only_acknowledged":true}'
```

## Guardrail Review

Confirm no live trading, paper trading, broker integration, real orders, alerts, real PnL, position management, or profitability claims were added.
