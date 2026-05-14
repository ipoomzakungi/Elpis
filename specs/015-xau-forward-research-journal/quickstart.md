# Quickstart: XAU Forward Research Journal

**Feature**: 015-xau-forward-research-journal  
**Date**: 2026-05-14

## Scope

This feature records forward XAU/Gold research snapshots from existing local report ids and later attaches outcome-window labels. It does not extract from QuikStrike, log into QuikStrike, replay endpoints, store credentials/session material, create trading behavior, or claim profitability, predictive power, safety, or live readiness.

## Prerequisites

- Completed local reports exist from:
  - Feature 012 QuikStrike Vol2Vol extraction
  - Feature 013 QuikStrike Matrix extraction
  - Feature 014 XAU QuikStrike Fusion
  - Feature 006 XAU Vol-OI Wall Engine
  - Feature 010 XAU Reaction and Risk Planner
- Generated reports remain under ignored local data/report paths.
- Optional snapshot context may be provided:
  - XAUUSD spot price at snapshot
  - GC futures price at snapshot
  - basis
  - session open price
  - event/news flag
  - notes
- Outcome OHLC observations may be attached later. Missing observations remain pending.

## Fixture Validation

Run backend validation from the backend directory:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_forward_journal_models.py -v
python -m pytest tests/unit/test_xau_forward_journal_entry_builder.py -v
python -m pytest tests/unit/test_xau_forward_journal_outcome.py -v
python -m pytest tests/unit/test_xau_forward_journal_report_store.py -v
python -m pytest tests/integration/test_xau_forward_journal_flow.py -v
python -m pytest tests/contract/test_xau_forward_journal_api_contracts.py -v
python -m pytest tests/ -q
```

Expected results:

- Synthetic source report fixtures create a journal entry.
- Source ids, snapshot time, top walls, reactions, NO_TRADE reasons, and missing context are preserved.
- Outcome windows default to `pending`.
- Outcome updates preserve the original snapshot.
- Missing OHLC data remains pending or inconclusive.
- Secret/session/execution fields are rejected.

## API Smoke

Start the backend:

```powershell
cd backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Create a journal entry using saved local report ids:

```powershell
$body = @{
  snapshot_time = "2026-05-14T03:08:04Z"
  capture_session = "quikstrike-gold-am-session"
  vol2vol_report_id = "quikstrike_20260513_101537"
  matrix_report_id = "quikstrike_matrix_20260513_155058"
  fusion_report_id = "xau_quikstrike_fusion_20260514_030803_real-local-fusion-smoke-fixed"
  xau_vol_oi_report_id = "xau_vol_oi_20260514_030804_640930"
  xau_reaction_report_id = "xau_reaction_20260514_030804_xau_vol_oi_20260514_030804_640930"
  spot_price_at_snapshot = $null
  futures_price_at_snapshot = 4707.2
  basis = $null
  session_open_price = $null
  event_news_flag = "none_known"
  notes = @("Forward evidence snapshot created from local reports.")
  persist_report = $true
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries" `
  -ContentType "application/json" `
  -Body $body
```

Confirm the response includes:

- `journal_id`
- snapshot time and capture session
- linked Vol2Vol, Matrix, Fusion, XAU Vol-OI, and XAU reaction report ids
- top OI wall summaries
- reaction labels and NO_TRADE reasons
- missing context checklist
- pending outcome windows
- generated artifact paths
- research-only warnings

Read saved outputs:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/{journal_id}"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/{journal_id}/outcomes"
```

Update one outcome window:

```powershell
$outcomeBody = @{
  outcomes = @(
    @{
      window = "30m"
      label = "stayed_inside_range"
      observation_start = "2026-05-14T03:08:04Z"
      observation_end = "2026-05-14T03:38:04Z"
      open = 4707.2
      high = 4712.0
      low = 4701.5
      close = 4706.0
      reference_wall_id = "2026-05-14_4675_mixed"
      reference_wall_level = 4675.0
      next_wall_reference = $null
      notes = @("Synthetic validation observation; not a strategy result.")
    }
  )
  update_note = "Attach first outcome observation."
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/{journal_id}/outcomes" `
  -ContentType "application/json" `
  -Body $outcomeBody
```

Expected error checks:

- Unknown journal id returns structured `NOT_FOUND`.
- Unknown source report id returns structured `SOURCE_REPORT_NOT_FOUND`.
- Unsupported outcome window returns structured `INVALID_OUTCOME_UPDATE`.
- Changing a non-pending label without an update note returns structured `OUTCOME_CONFLICT`.
- Requests with secret/session/execution material are rejected.
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

Confirm the Forward Journal section shows:

- saved journal entry selector/list
- snapshot time and capture session
- linked source report ids
- top walls/zones
- reaction labels and NO_TRADE reasons
- missing context checklist
- outcome-window status and labels
- notes and artifact paths
- local-only and research-only disclaimer

## Artifact Guard

Run from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status --short --ignored
```

Expected results:

- Artifact guard passes.
- Generated journal reports remain ignored and untracked.
- No `.env`, credentials, cookies, headers, HAR, screenshots, viewstate, private URLs, endpoint replay payloads, or generated reports are staged.

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

- This journal builds forward evidence from capture time onward.
- It is not a historical QuikStrike strike-level OI backtest.
- NO_TRADE decisions can be reviewed later, but labels remain research annotations.
- Missing outcome data remains pending or inconclusive.
