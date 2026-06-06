# Daily XAU QuikStrike Snapshot

This workflow is local-only and research-only. It does not automate QuikStrike
login, replay endpoints, store credentials, store cookies, capture HAR files,
save screenshots, persist viewstate values, or write private full URLs.

## Manual Run

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1
```

The script opens Edge with a local CDP port and a non-sync local profile:

```text
--remote-debugging-port=9222
--user-data-dir="$env:LOCALAPPDATA\Elpis\quikstrike-browser-profile"
--disable-sync
```

Manual steps remain required:

1. Log in to QuikStrike in the opened browser.
2. Open Gold `(OG|GC)` on `QUIKOPTIONS VOL2VOL`.
3. Press Enter in the script window to capture Vol2Vol.
4. Open Gold `(OG|GC)` under `OPEN INTEREST` Matrix.
5. Select `OI Matrix`, `OI Change Matrix`, and `Volume Matrix` as the script waits.

## Fast Session Reuse

For faster repeated captures, start the dedicated browser session once:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_quikstrike_session.ps1
```

Log in in that browser and keep it open. Then run snapshots against the same
local CDP session:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1 -Fast
```

The runner now polls every 0.5 seconds by default and leaves the QuikStrike browser
open for session reuse unless `-CloseBrowser` is explicitly passed. `-Fast`
additionally caps the default wait window at 180 seconds. If the QuikStrike
session expires, log in again in the same browser and rerun.

This browser-based runner still does not read or store QuikStrike email,
password, cookies, headers, tokens, HAR files, viewstate, or request payloads.
The fast path reuses the browser session instead of exporting credentials.

To try normal browser auto-login first, fill the ignored root `.env` file:

```env
QUIKSTRIKE_API_USERNAME=your-email
QUIKSTRIKE_API_PASSWORD=your-password
```

Then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_quikstrike_session.ps1 -AutoLogin
```

This opens the same visible browser path and fills ordinary login fields when
they are present. If `.env` is blank, the browser remains open so you can use
Edge's saved-password flow or reset the QuikStrike password manually.

The repository now has a separate approved exception for a future read-only
QuikStrike/CME API ingestion feature. That exception allows local-only runtime
credentials only when they stay outside tracked files, preferably in the OS
credential store, and are never written to logs, diagnostics, reports, network
artifacts, screenshots, or git. Reversible encoding is treated as secret
material, not protection.

Generated reports are written only under ignored local data paths such as:

```text
backend/data/reports/quikstrike/
backend/data/reports/quikstrike_matrix/
backend/data/reports/xau_quikstrike_fusion/
backend/data/reports/xau_vol_oi/
backend/data/reports/xau_reaction/
backend/data/reports/xau_forward_journal/
```

The Matrix step captures the Heatmap `OI`, `OI Change`, and `Volume` views into
the normalized Matrix/XAU Vol-OI pipeline. It also writes supplemental sanitized
side-nav tables for:

- `History > Settlements`
- `Futures > Volume & OI`

Those supplemental views are saved next to the Matrix report as:

```text
backend/data/reports/quikstrike_matrix/{matrix_report_id}/supplemental_views.json
```

They are not converted into XAU Vol-OI rows yet because their layouts differ
from the Heatmap strike/expiration table parser. To skip them:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1 `
  -SkipMatrixSupplementalViews
```

## Optional Browser Network Diagnostics

To investigate whether the browser is using API-like resources, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1 `
  -NetworkDiagnostics
```

This writes a sanitized JSON report under:

```text
backend/data/reports/quikstrike_network_diag/
```

The diagnostic records browser Performance Resource Timing metadata only:
host, redacted path, query key names, resource type, status when exposed by the
browser, and timing/size fields. It does not store headers, cookies, request
bodies, response bodies, HAR files, full URLs, query values, screenshots,
viewstate, or replayable session material.

Use the `network_diagnostics_api_only_assessment` field as a feasibility hint,
not as proof. API-only capture is supported only if a documented public API can
provide the same Vol2Vol and Matrix fields without private session replay.

## Experimental API Login Probe

The repository has an approved local-only exception for testing read-only
QuikStrike/CME API ingestion credentials. The first step is a sanitized HTTP
login probe:

```powershell
cd backend
$env:QUIKSTRIKE_API_USERNAME = "your-email"
$env:QUIKSTRIKE_API_PASSWORD = "your-password"
python scripts/quikstrike_api_probe.py
Remove-Item Env:\QUIKSTRIKE_API_USERNAME
Remove-Item Env:\QUIKSTRIKE_API_PASSWORD
```

The probe attempts form-based HTTP login and writes only sanitized metadata under:

```text
backend/data/reports/quikstrike_api_probe/
```

It does not persist cookies, headers, credentials, request bodies, response
bodies, viewstate values, full URLs, HAR files, screenshots, or replay payloads.
The report can prove whether the authenticated page is reachable without a
browser. It does not yet prove that Vol2Vol or Matrix data can be extracted via
a stable API call.

## Optional Context

Only pass market references when you already have them from a separate trusted
research source. Missing context is preserved as missing.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1 `
  -XauUsdSpotReference 2400.5 `
  -GcFuturesReference 2407.2 `
  -SessionOpenPrice 2395.0
```

## Validation

After a run:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status --short --ignored
```
