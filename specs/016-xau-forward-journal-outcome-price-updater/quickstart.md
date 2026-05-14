# Quickstart: XAU Forward Journal Outcome Price Updater

**Feature**: 016-xau-forward-journal-outcome-price-updater
**Date**: 2026-05-14

## Scope

This feature updates saved XAU Forward Journal outcome windows from approved OHLC candle data. It computes observed price metrics only when candles cover the required windows, keeps missing windows pending, marks partial windows inconclusive, labels proxy sources, and preserves original snapshot evidence.

It does not extract from QuikStrike, log into QuikStrike, replay endpoints, store credentials/session material, use paid vendors, create trading behavior, or claim profitability, predictive power, safety, or live readiness.

## Prerequisites

- Feature 015 XAU Forward Research Journal is implemented.
- At least one saved journal entry exists under ignored `data/reports/xau_forward_journal/` or `backend/data/reports/xau_forward_journal/`.
- A local OHLC CSV/Parquet file or existing public OHLC output is available.
- The OHLC file contains timestamp, open, high, low, and close values.
- Generated reports remain ignored and untracked.

## Fixture Validation

Run backend validation from the backend directory:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_xau_forward_journal_price_data.py -v
python -m pytest tests/unit/test_xau_forward_journal_price_outcome.py -v
python -m pytest tests/unit/test_xau_forward_journal_report_store.py -v
python -m pytest tests/integration/test_xau_forward_journal_price_update_flow.py -v
python -m pytest tests/contract/test_xau_forward_journal_api_contracts.py -v
python -m pytest tests/ -q
```

Expected results:

- Synthetic OHLC schema validation accepts valid CSV/Parquet rows.
- Invalid high/low/open/close rows are rejected.
- Window calculation derives `30m`, `1h`, `4h`, `session_close`, and `next_day`.
- Complete candles produce computed high, low, close, and range.
- Missing candles keep windows pending.
- Partial candles mark windows inconclusive.
- Proxy sources produce visible limitation labels.
- Snapshot fields remain immutable after update.

## API Smoke

Start the backend:

```powershell
cd backend
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Use a saved journal id from feature 015:

```powershell
$journalId = "xau_forward_journal_20260514_030804_quikstrike-gold-am-session"
```

Check price coverage without mutating outcomes:

```powershell
$query = @{
  source_label = "yahoo_gc_f_proxy"
  source_symbol = "GC=F"
  ohlc_path = "data/raw/yahoo/gc=f_1d_ohlcv.parquet"
  timestamp_column = "timestamp"
  open_column = "open"
  high_column = "high"
  low_column = "low"
  close_column = "close"
  timezone = "UTC"
  research_only_acknowledged = "true"
}

$coverageUri = "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/$journalId/price-coverage?" + (
  ($query.GetEnumerator() | ForEach-Object {
    [System.Uri]::EscapeDataString($_.Key) + "=" + [System.Uri]::EscapeDataString([string]$_.Value)
  }) -join "&"
)

Invoke-RestMethod $coverageUri
```

Confirm the response includes:

- source label and source symbol
- per-window coverage status
- complete, partial, and missing window lists
- missing candle checklist
- proxy limitation notes
- research-only warnings

Update outcomes from price data:

```powershell
$body = @{
  source_label = "yahoo_gc_f_proxy"
  source_symbol = "GC=F"
  ohlc_path = "data/raw/yahoo/gc=f_1d_ohlcv.parquet"
  timestamp_column = "timestamp"
  open_column = "open"
  high_column = "high"
  low_column = "low"
  close_column = "close"
  timezone = "UTC"
  update_note = "Attach local OHLC validation outcomes."
  persist_report = $true
  research_only_acknowledged = $true
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/$journalId/outcomes/from-price-data" `
  -ContentType "application/json" `
  -Body $body
```

Confirm the response includes:

- update report id
- updated outcomes
- computed high, low, close, range for complete windows
- direction when snapshot price is available
- pending windows for missing candles
- inconclusive windows for partial candles
- source coverage summary
- generated artifact paths under `data/reports/xau_forward_journal/`

Read the updated entry and outcomes:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/$journalId"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/xau/forward-journal/entries/$journalId/outcomes"
```

Expected error checks:

- Unknown journal id returns structured `NOT_FOUND`.
- Unsupported source label returns structured `INVALID_PRICE_SOURCE`.
- Missing OHLC file returns structured `PRICE_DATA_NOT_FOUND`.
- Bad OHLC schema returns structured `INVALID_OHLC_SCHEMA`.
- Changing an existing non-pending outcome without an update note returns structured `OUTCOME_CONFLICT`.
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
- price data source and source symbol
- coverage status for outcome windows
- missing windows and missing candle checklist
- updated outcome labels and pending/inconclusive states
- computed high, low, close, range, and direction when present
- proxy limitation notes
- artifact paths
- local-only and research-only disclaimer

## Artifact Guard

Run from repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status --short --ignored
```

Expected results:

- Artifact guard passes.
- Generated price update reports remain ignored and untracked.
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

- This updater attaches later observed candle outcomes to an existing forward snapshot.
- It is not a historical QuikStrike strike-level OI backtest.
- Proxy OHLC sources are useful research references but are not true XAUUSD spot unless explicitly labeled as `true_xauusd_spot`.
- Missing candles remain pending.
- Partial candles remain inconclusive.
