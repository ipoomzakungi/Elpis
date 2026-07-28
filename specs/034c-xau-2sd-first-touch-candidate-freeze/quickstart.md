# Quickstart: XAU 2SD First-Touch Candidate Freeze

Coverage audit and retained candidate report:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_xau_ft2_candidate.py `
  --session-date-from 2026-05-31 `
  --session-date-to 2026-07-27 `
  --as-of-date 2026-07-28
```

Daily collection and plan:

```powershell
cd backend
.\scripts\run_daily_xau_ft2_candidate.ps1 -SessionDate 2026-07-28
```

The daily collector requires authenticated Chrome remote debugging on the
configured CDP URL. Missing CDP, exact-date Vol2Vol, XAUUSD, or mapping data
fails closed. No command submits an order.

API:

```text
GET  /api/v1/research/xau/ft2-candidate/latest
POST /api/v1/research/xau/ft2-candidate/{alert_id}/acknowledge
```

Credential storage, rotation, broker-quote timing, and local journal paths are
documented in `docs/operations/xau_ft2_candidate.md`.
