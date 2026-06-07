# Quickstart: XAU Range Desk / Diff-SD Planner

## Scope

Feature 024A maps CME futures-side SD and OI levels to traded XAU/GO chart
levels. It does not calculate PnL, create alerts, size positions, place orders,
connect to brokers, or claim that a strategy works.

## API Usage

Start the backend from `backend/`:

```powershell
python -c "from src.main import app; print('backend import ok')"
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Run:

```powershell
$body = @{
  future_reference_price = 4500.0
  traded_reference_price = 4470.0
  levels = @(
    @{ label = "lower_1sd"; futures_level = 4490.0 },
    @{ label = "upper_1sd"; futures_level = 4510.0 },
    @{ label = "lower_2sd"; futures_level = 4470.0 },
    @{ label = "upper_2sd"; futures_level = 4520.0 },
    @{ label = "lower_3sd"; futures_level = 4450.0 },
    @{ label = "upper_3sd"; futures_level = 4530.0 }
  )
  oi_walls = @(
    @{ wall_id = "wall_4520"; futures_level = 4520.0 }
  )
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/research/xau/range-desk/plan `
  -ContentType "application/json" `
  -Body $body
```

Expected key result:

```text
diff_points = 30
traded_offset = -30
wall_4520 mapped_traded_level = 4490
signal_allowed = false
research_only = true
```

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_range_desk_planner.py tests/unit/test_xau_range_desk_api.py -q
python -m pytest tests/unit/test_xau_sd_oi_mean_reversion_candidate.py tests/unit/test_xau_daily_workbench_service.py tests/unit/test_xau_candidate_outcome_calculator.py -q
python -c "from src.main import app; print('backend import ok')"
python -m ruff check src/models/xau_range_desk.py src/xau_range_desk src/api/routes/xau_range_desk.py tests/unit/test_xau_range_desk_planner.py tests/unit/test_xau_range_desk_api.py src/main.py
```
