# Quickstart: XAU Daily Research Workbench

## Scope

Feature 022 runs a local research-only XAU workbench. It can load a local bundle or use the latest existing structural map, run Feature 021 candidates, and persist local artifacts. It does not trade, alert, size positions, calculate PnL, or connect to brokers.

## Python Usage

Run from `backend/`:

```powershell
@'
from datetime import date
from pathlib import Path

from src.models.xau_daily_workbench import XauDailyWorkbenchRunRequest
from src.xau_daily_workbench.service import run_xau_daily_research_workbench

result = run_xau_daily_research_workbench(
    XauDailyWorkbenchRunRequest(
        session_date=date(2026, 6, 2),
        expiration_code="OG1M6",
        traded_instrument="XAUUSD",
        cme_source="local_bundle",
        input_dir=Path("data/imports/xau_quikstrike_20260602"),
        gc_reference_price=4549.2,
        traded_reference_price=4536.7,
        session_open_price=4538.0,
        confirmation_state="rejection",
        iv_state="stable",
        flow_state="not_breakout_confirmed",
        run_candidates=True,
        research_only_acknowledged=True,
    )
)
print(result.run_id)
print(result.map_id)
print(result.candidate_set_id)
print(result.readiness)
'@ | python -
```

PowerShell can also use the existing Feature 020A script to create a map first, then run the workbench with `cme_source=latest_existing`.

## API Usage

Start the backend from `backend/`:

```powershell
python -c "from src.main import app; print('backend import ok')"
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Run:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/api/v1/research/xau/workbench/run `
  -ContentType "application/json" `
  -Body '{
    "session_date": "2026-06-02",
    "expiration_code": "OG1M6",
    "traded_instrument": "XAUUSD",
    "cme_source": "local_bundle",
    "input_dir": "backend/data/imports/xau_quikstrike_20260602",
    "gc_reference_price": 4549.2,
    "traded_reference_price": 4536.7,
    "session_open_price": 4538.0,
    "confirmation_state": "rejection",
    "iv_state": "stable",
    "flow_state": "not_breakout_confirmed",
    "run_candidates": true,
    "research_only_acknowledged": true
  }'
```

## CLI Usage

Run from `backend/`:

```powershell
python scripts/run_xau_daily_research_workbench.py `
  --session-date 2026-06-02 `
  --expiration-code OG1M6 `
  --traded-instrument XAUUSD `
  --cme-source local_bundle `
  --input-dir data/imports/xau_quikstrike_20260602 `
  --gc-reference-price 4549.2 `
  --traded-reference-price 4536.7 `
  --session-open-price 4538.0 `
  --confirmation-state rejection `
  --iv-state stable `
  --flow-state not_breakout_confirmed
```

The command prints JSON with:

- `status`
- `run_id`
- `map_id`
- `candidate_set_id`
- `readiness`
- artifact paths
- `no_signal_reasons`
- `missing_inputs`
- `signal_allowed=false`
- `research_only=true`

Read latest:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/workbench/latest
```

Read a run:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/workbench/runs/{run_id}
```

Read map:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/workbench/maps/{map_id}
```

Read candidates:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/workbench/candidates/{map_id}
```

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_daily_workbench_service.py tests/contract/test_xau_daily_workbench_api_contracts.py -q
python -m pytest tests/unit/test_xau_daily_workbench_providers.py tests/unit/test_xau_daily_workbench_candidate_store.py -q
python -m pytest tests/unit/test_xau_daily_workbench_api.py tests/unit/test_run_xau_daily_research_workbench_script.py -q
python -m pytest tests/unit/test_xau_daily_structural_map_bundle_adapter.py tests/unit/test_xau_sd_oi_mean_reversion_candidate.py -q
python -c "from src.main import app; print('backend import ok')"
python scripts/run_xau_daily_research_workbench.py --help
python -m ruff check src/models/xau_daily_workbench.py src/xau_daily_workbench src/api/routes/xau_daily_workbench.py scripts/run_xau_daily_research_workbench.py tests/unit/test_xau_daily_workbench_service.py tests/unit/test_xau_daily_workbench_providers.py tests/unit/test_xau_daily_workbench_candidate_store.py tests/unit/test_xau_daily_workbench_api.py tests/unit/test_run_xau_daily_research_workbench_script.py tests/contract/test_xau_daily_workbench_api_contracts.py
```
