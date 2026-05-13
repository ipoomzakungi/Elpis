# Quickstart: XAU QuikStrike Context Fusion

**Feature**: 014-xau-quikstrike-context-fusion  
**Date**: 2026-05-13

## Scope

This feature fuses saved QuikStrike Vol2Vol and QuikStrike Matrix reports into one local XAU research context. It does not extract from the browser, log into QuikStrike, replay endpoints, store credentials/session material, or create trading/execution behavior.

## Prerequisites

- A completed feature 012 Vol2Vol extraction report exists locally.
- A completed feature 013 Matrix extraction report exists locally.
- Generated QuikStrike and fusion artifacts remain under ignored local data/report paths.
- Optional context may be provided:
  - XAUUSD spot reference
  - GC futures reference
  - session open price
  - OHLC/candle reaction context
  - realized-volatility estimate

## Fixture Validation

Run backend validation from the backend directory:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_quikstrike_fusion_models.py -v
python -m pytest tests/unit/test_xau_quikstrike_fusion_loaders.py -v
python -m pytest tests/unit/test_xau_quikstrike_fusion_matching.py -v
python -m pytest tests/unit/test_xau_quikstrike_fusion_basis.py -v
python -m pytest tests/unit/test_xau_quikstrike_fusion_fusion.py -v
python -m pytest tests/unit/test_xau_quikstrike_fusion_report_store.py -v
python -m pytest tests/integration/test_xau_quikstrike_fusion_flow.py -v
python -m pytest tests/contract/test_xau_quikstrike_fusion_api_contracts.py -v
python -m pytest tests/ -q
```

Expected results:

- Synthetic Vol2Vol and Matrix report fixtures load.
- Match keys are created by strike, expiration/expiration code, option type, and value type.
- Source agreement and disagreement are preserved.
- Missing basis, IV/range, open, candle, and realized-volatility context is visible.
- Fused XAU Vol-OI compatible rows are produced only when mapping is reliable.
- Unsafe mapping blocks or marks conversion partial.

## API Smoke

Start the backend:

```powershell
cd backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Create a fusion report using saved local report ids:

```powershell
$body = @{
  vol2vol_report_id = "quikstrike_20260513_095411"
  matrix_report_id = "quikstrike_matrix_20260513_155058"
  xauusd_spot_reference = 4692.1
  gc_futures_reference = 4696.7
  session_open_price = $null
  realized_volatility = $null
  candle_context = @()
  create_xau_vol_oi_report = $true
  create_xau_reaction_report = $true
  run_label = "fusion-smoke"
  persist_report = $true
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/xau/quikstrike-fusion/reports" `
  -ContentType "application/json" `
  -Body $body
```

Confirm the response includes:

- `report_id`
- selected Vol2Vol report id
- selected Matrix report id
- fused row count
- strike and expiry coverage
- source agreement/disagreement
- basis status
- IV/range status
- open/candle context status
- missing context checklist
- generated artifact paths
- linked XAU Vol-OI report id when requested and eligible
- linked XAU reaction report id when requested and eligible
- research-only warnings

Read saved outputs:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/quikstrike-fusion/reports"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/quikstrike-fusion/reports/{report_id}"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/quikstrike-fusion/reports/{report_id}/rows"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context"
```

Expected error checks:

- Unknown fusion report id returns structured `NOT_FOUND`.
- Unknown source report id returns structured `SOURCE_NOT_FOUND`.
- Incompatible source product returns structured `INCOMPATIBLE_SOURCE_REPORTS`.
- Requests with secret/session-like fields are rejected.
- Requests without `research_only_acknowledged=true` are rejected.

## Dashboard Smoke

Start the frontend:

```powershell
cd frontend
npm install
npm run build
npm run dev -- --hostname localhost --port 3000
```

Open:

```text
http://localhost:3000/xau-vol-oi
```

Confirm the QuikStrike Fusion panel shows:

- selected Vol2Vol report id
- selected Matrix report id
- fused row count
- strike coverage
- expiry coverage
- source agreement/disagreement
- basis status
- IV/range status
- open-regime status
- candle-acceptance status
- missing context checklist
- generated fused artifact paths
- linked XAU Vol-OI report id if created
- linked XAU reaction report id if created
- whether all reaction rows are `NO_TRADE`
- local-only and research-only disclaimer

## Artifact Guard

Run from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status --short
```

Expected results:

- Artifact guard passes.
- Generated fusion reports, XAU reports, and QuikStrike-derived data remain ignored and untracked.
- No `.env`, credentials, cookies, headers, HAR, screenshots, viewstate, private URLs, or endpoint replay payloads are staged.

## Forbidden-Scope Review

Before completing implementation, scan changed files and confirm no:

- live trading
- paper trading
- shadow trading
- private trading keys
- broker integration
- real execution
- wallet/private-key handling
- endpoint replay
- credential/session storage
- cookies/tokens/HAR/screenshots/viewstate/private URL storage
- browser RPA
- OCR
- paid vendors
- Rust
- ClickHouse
- PostgreSQL
- Kafka / Redpanda / NATS
- Kubernetes
- ML model training
- buy/sell execution signals
- profitability, predictive, safety, or live-readiness claims

## Operational Notes

- Missing spot/futures basis should keep futures-strike levels and mark basis unavailable.
- Missing IV/range, realized volatility, session open, or candle context should keep downstream reaction output conservative.
- If all XAU reaction rows remain `NO_TRADE`, the fusion report should explain which context items are missing or conflicting.
- Fusion should not fabricate basis, IV, range, spot, open, candle, or realized-volatility data.
