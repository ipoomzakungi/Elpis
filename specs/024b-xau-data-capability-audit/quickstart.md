# Quickstart: XAU Data Capability Audit

## Backend Import Check

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
```

Expected:

```text
backend import ok
```

## Focused Tests

```powershell
cd backend
python -m pytest tests/unit/test_xau_data_capability_audit.py -q
```

Expected:

```text
3 passed
```

## Local API Smoke

Start the backend:

```powershell
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Run the audit:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/research/xau/data-capability-audit/run `
  -ContentType "application/json" `
  -Body '{"max_reports_per_source":1,"research_only_acknowledged":true}'
```

Expected:

- Response includes `research_only=true`.
- Response includes `signal_allowed=false`.
- Response includes capability rows for OI, OI change, volume, volatility, DTE, SD, delta, gamma, and GEX possibility.
- Missing capabilities are marked unavailable or blocked with limitations.

## Guardrail Review

Confirm no live trading, paper trading, broker integration, private keys, order
routing, alerts, PnL, position sizing, ML training, buy/sell live signal, or
execution behavior was added.
