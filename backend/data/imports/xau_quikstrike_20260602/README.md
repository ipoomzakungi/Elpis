# XAU QuikStrike 2026-06-02 Local Import

Place the real local bundle files for the 2026-06-02 XAU/GC research run in this folder.

Expected files:

- `03_xau_quikstrike_fusion_fused_rows.json`
- `04_xau_vol_oi_report_report.json`
- `04_xau_vol_oi_report_walls.parquet`
- `04_xau_vol_oi_report_zones.parquet`

These are local research imports. Large JSON/Parquet bundle files should stay untracked; this folder's `.gitignore` keeps the data files out of git while preserving this README.

After copying the bundle, generate a map with:

```powershell
python backend/scripts/generate_xau_map_from_local_bundle.py `
  --input-dir backend/data/imports/xau_quikstrike_20260602 `
  --session-date 2026-06-02 `
  --expiration-code OG1M6 `
  --traded-instrument XAUUSD `
  --gc-reference-price 4549.2 `
  --traded-reference-price YOUR_XAU_PRICE `
  --session-open-price YOUR_SESSION_OPEN
```

The output remains a structural research map with `signal_allowed=false`; it is not a trading signal.
