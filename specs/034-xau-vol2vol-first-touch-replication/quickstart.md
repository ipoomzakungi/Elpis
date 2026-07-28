# Quickstart: XAU Vol2Vol First-Touch Replication

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_xau_vol2vol_first_touch_study.py `
  --session-date-from 2026-05-31 `
  --session-date-to 2026-07-27
```

The command writes an immutable research run under:

`backend/data/reports/xau_first_touch_study/<run_id>/`

No command in this feature can submit or simulate a broker order.
