# Quickstart: XAU Zone Reaction and Risk Planner

**Date**: 2026-05-12  
**Feature**: 010-xau-zone-reaction-and-risk-planner

This quickstart describes the expected validation path after implementation. The feature is research-only and must not rely on live trading, paper trading, shadow trading, broker credentials, private keys, wallet handling, real execution, or buy/sell execution signals.

## 1. Verify Existing Checks

From `backend/`:

```powershell
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q
```

From `frontend/`:

```powershell
npm install
npm run build
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## 2. Prepare Or Create A Source XAU Vol-OI Report

Use an existing feature 006 report or create one with the XAU Vol-OI quickstart:

```text
specs/006-xau-vol-oi-wall-engine/quickstart.md
```

The source report must provide:

- report id
- basis snapshot
- expected range
- wall rows
- zone rows
- research-only limitations

Generated source reports remain under ignored `data/reports/xau_vol_oi/` paths and must not be committed.

## 3. Start Backend

From `backend/`:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## 4. Run An XAU Reaction Report

Submit a reaction report request using the source report id from step 2:

```powershell
$body = @{
  source_report_id = "xau_vol_oi_20260430_160000"
  current_price = 2405.0
  current_timestamp = "2026-04-30T16:15:00Z"
  freshness_input = @{
    intraday_timestamp = "2026-04-30T16:10:00Z"
    current_timestamp = "2026-04-30T16:15:00Z"
    total_intraday_contracts = 12500
    min_contract_threshold = 1000
    max_allowed_age_minutes = 30
    session_flag = "regular"
  }
  vol_regime_input = @{
    implied_volatility = 0.16
    realized_volatility = 0.11
    price = 2405.0
    iv_lower = 2378.0
    iv_upper = 2428.0
    rv_lower = 2388.0
    rv_upper = 2420.0
  }
  open_regime_input = @{
    session_open = 2398.0
    current_price = 2405.0
    initial_move_direction = "up"
    crossed_open_after_initial_move = $false
    acceptance_beyond_open = $false
  }
  acceptance_inputs = @(
    @{
      wall_id = "20260430_20260507_2400_call"
      wall_level = 2393.0
      high = 2410.0
      low = 2390.0
      close = 2405.0
      next_bar_open = 2406.0
      buffer_points = 2.0
    }
  )
  event_risk_state = "unknown"
  max_total_risk_per_idea = 0.01
  max_recovery_legs = 1
  minimum_rr = 1.5
  wall_buffer_points = 2.0
  report_format = "both"
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 20

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/xau/reaction-reports" `
  -ContentType "application/json" `
  -Body $body
```

Expected behavior:

- The response includes `report_id`, `source_report_id`, report-level freshness, volatility, and open context.
- Reaction rows are classified only as `REVERSAL_CANDIDATE`, `BREAKOUT_CANDIDATE`, `PIN_MAGNET`, `SQUEEZE_RISK`, `VACUUM_TO_NEXT_WALL`, or `NO_TRADE`.
- Stale, thin, prior-day, unknown-basis, or conflicting scenarios produce `NO_TRADE` or explicit confidence reduction notes.
- `NO_TRADE` rows have no entry plan.
- Risk plans are capped and research-only.
- Responses do not contain buy/sell execution signals or live-readiness claims.

## 5. Inspect Saved Reaction Reports

List reports:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/reaction-reports"
```

Read report:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/reaction-reports/{report_id}"
```

Read sections:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/xau/reaction-reports/{report_id}/reactions"
Invoke-RestMethod "http://localhost:8000/api/v1/xau/reaction-reports/{report_id}/risk-plan"
```

Generated reaction artifacts should appear under:

```text
data/reports/xau_reaction/{report_id}/
```

They must remain ignored by git.

## 6. Start Dashboard

From `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000/xau-vol-oi
```

Verify the page shows reaction-report inspection:

- freshness badge
- IV/RV/VRP panel
- session open panel
- acceptance/rejection state
- reaction label table
- bounded risk planner table
- no-trade reasons
- research-only disclaimer

## 7. Focused Test Commands

From `backend/`:

```powershell
python -m pytest tests/unit/test_xau_reaction_freshness.py -v
python -m pytest tests/unit/test_xau_reaction_vol_regime.py -v
python -m pytest tests/unit/test_xau_reaction_open_regime.py -v
python -m pytest tests/unit/test_xau_reaction_acceptance.py -v
python -m pytest tests/unit/test_xau_reaction_classifier.py -v
python -m pytest tests/unit/test_xau_reaction_risk_plan.py -v
python -m pytest tests/integration/test_xau_reaction_flow.py -v
python -m pytest tests/contract/test_xau_reaction_api_contracts.py -v
python -m pytest tests/ -q
```

From `frontend/`:

```powershell
npm run build
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## 8. Forbidden Scope Review

Before marking implementation complete:

```powershell
rg -n -i "live trading|paper trading|shadow trading|private key|api_key|broker|order execution|wallet|rust|clickhouse|postgres|kafka|kubernetes|sklearn|tensorflow|torch|buy signal|sell signal|profitable|predicts|safe to trade|live ready" backend/src frontend/src backend/pyproject.toml frontend/package.json .github/workflows/validation.yml
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected result:

- Any matches are guardrail/disclaimer text only.
- No live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell execution signal behavior, or prohibited claims were introduced.
- No generated reaction reports or local research data are tracked.
