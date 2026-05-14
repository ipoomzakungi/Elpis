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

Generated reports are written only under ignored local data paths such as:

```text
backend/data/reports/quikstrike/
backend/data/reports/quikstrike_matrix/
backend/data/reports/xau_quikstrike_fusion/
backend/data/reports/xau_vol_oi/
backend/data/reports/xau_reaction/
backend/data/reports/xau_forward_journal/
```

## Optional Context

Only pass market references when you already have them from a separate trusted
research source. Missing context is preserved as missing.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1 `
  -XauUsdSpotReference 2400.5 `
  -GcFuturesReference 2407.2 `
  -SessionOpenPrice 2395.0
```

## Windows Task Scheduler

Use Task Scheduler only as a reminder/launcher. The task should run while the
user is logged on because manual QuikStrike login is still required.

Suggested task settings:

- Program: `powershell.exe`
- Arguments:
  `-ExecutionPolicy Bypass -File "C:\Users\punnawat_s\Guthib\Elpis\scripts\run_daily_xau_quikstrike_snapshot.ps1"`
- Start in: `C:\Users\punnawat_s\Guthib\Elpis`
- Security option: `Run only when user is logged on`

Do not store QuikStrike usernames, passwords, cookies, headers, tokens, HAR
files, screenshots, viewstate values, or private URLs in Task Scheduler,
PowerShell scripts, `.env` files, or repository files.

## Validation

After a run:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status --short --ignored
```
