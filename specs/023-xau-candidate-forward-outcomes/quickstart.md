# Quickstart: XAU Candidate Forward Outcomes

## Scope

Feature 023 attaches forward outcome evidence to saved XAU SD/OI research candidates. It does not calculate PnL, create alerts, size positions, place orders, connect to brokers, or claim that a strategy works.

## CLI Usage

Run from `backend/`:

```powershell
python scripts/run_xau_candidate_forward_outcomes.py `
  --candidate-set-path data/reports/xau_daily_structural_map/{map_id}/candidates.json `
  --price-bars-path data/imports/xau_price_bars.csv `
  --window 30m `
  --window 1h `
  --window 4h `
  --window session_close `
  --window next_day
```

The command prints JSON with:

- `outcome_run_id`
- `candidate_count`
- `outcome_count`
- `unavailable_count`
- `artifact_paths`
- `signal_allowed=false`
- `research_only=true`

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
  -Uri http://localhost:8000/api/v1/research/xau/candidate-outcomes/run `
  -ContentType "application/json" `
  -Body '{
    "candidate_set_path": "backend/data/reports/xau_daily_structural_map/{map_id}/candidates.json",
    "price_bars_path": "backend/data/imports/xau_price_bars.csv",
    "windows": ["30m", "1h"],
    "research_only_acknowledged": true
  }'
```

Read latest:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/candidate-outcomes/latest
```

Read by id:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/research/xau/candidate-outcomes/{outcome_run_id}
```

## Focused Validation

Run from `backend/`:

```powershell
python -m pytest tests/unit/test_xau_sd_oi_mean_reversion_candidate.py -q
python -m pytest tests/unit/test_xau_daily_workbench_service.py -q
python -m pytest tests/unit/test_xau_candidate_outcome_models.py -q
python -m pytest tests/unit/test_xau_candidate_outcome_calculator.py -q
python -m pytest tests/unit/test_xau_candidate_outcome_store.py -q
python -m pytest tests/unit/test_xau_candidate_outcome_api.py -q
python -m pytest tests/unit/test_run_xau_candidate_forward_outcomes_script.py -q
python -c "from src.main import app; print('backend import ok')"
python scripts/run_xau_candidate_forward_outcomes.py --help
python -m ruff check src/models/xau_candidate_outcome.py src/xau_candidate_outcomes src/api/routes/xau_candidate_outcomes.py scripts/run_xau_candidate_forward_outcomes.py tests/unit/test_xau_candidate_outcome_models.py tests/unit/test_xau_candidate_outcome_calculator.py tests/unit/test_xau_candidate_outcome_store.py tests/unit/test_xau_candidate_outcome_api.py tests/unit/test_run_xau_candidate_forward_outcomes_script.py
```
