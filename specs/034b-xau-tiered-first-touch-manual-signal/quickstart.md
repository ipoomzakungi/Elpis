# Quickstart: XAU Tiered First-Touch Manual Signal

Historical matrix and current plan:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_xau_tiered_manual_signal.py `
  --session-date-from 2026-05-31 `
  --session-date-to 2026-07-27 `
  --as-of-date 2026-07-28
```

API:

```text
GET  /api/v1/research/xau/manual-signals/latest
POST /api/v1/research/xau/manual-signals/{signal_id}/acknowledge
```

All outputs are alerts and research records only. No order is submitted.

Daily refresh and run:

```powershell
cd backend
.\scripts\run_daily_xau_tiered_manual_signal.ps1 `
  -SessionDate 2026-07-28 `
  -CdpUrl http://127.0.0.1:9222
```

The Vol2Vol collector requires an already authenticated Chrome instance exposing
the configured CDP URL. The Dukascopy fetch uses an exclusive end date internally.

Optional broker quote CSV:

```csv
timestamp,symbol,bid,ask
2026-07-28T08:00:30+07:00,XAUUSD,4100.10,4100.40
```

Without a synchronized valid broker quote, an eligible setup remains a
`REFERENCE_ALERT`, not an exact broker entry.
