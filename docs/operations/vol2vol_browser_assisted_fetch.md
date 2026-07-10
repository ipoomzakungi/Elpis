# Vol2Vol Browser-Assisted Fetch

Direct CLI HTTP requests to Vol2Vol may fail even when the same page works in a
normal browser. The browser can carry Cloudflare/session state and Next.js RSC
request context that a plain Python or PowerShell request does not have.

This is not treated as a reason to hard-code cookies.

## Rules

Do not store or commit:

- cookies
- `cf_clearance`
- CSRF tokens
- request headers
- browser session material
- private URLs or replayable session artifacts

Implemented flow:

1. The user opens Vol2Vol in their own browser session.
2. A user-controlled browser tool requests the same public JSON endpoint.
3. The tool saves only the JSON response body under `backend/data/imports/vol2vol`.
4. The research pipeline reads that local JSON later.

The saved file should follow the data-lake layout:

```text
backend/data/imports/vol2vol/daily/YYYY-MM-DD/raw.json
backend/data/imports/vol2vol/monthly/YYYY-MM/raw.json
```

## Why This Exists

Vol2Vol structure data is useful for research preparation:

- range snapshots
- strike activity
- open interest
- intraday volume
- monthly OI confluence

It is not a buy/sell signal and does not replace traded-side XAUUSD/GO candles.

## Collector

Start a visible Chrome or Edge instance with local CDP enabled and a dedicated,
local-only profile. Complete any browser challenge manually, then leave the
Vol2Vol history page open.

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:LOCALAPPDATA\Elpis\vol2vol-browser-profile" `
  https://www.vol2vol.com/history
```

Run the collector from `backend`:

```powershell
python scripts/collect_vol2vol_browser_history.py `
  --cdp-url http://127.0.0.1:9222 `
  --base-url https://www.vol2vol.com `
  --all-available `
  --output-root data/imports/vol2vol `
  --min-delay-seconds 1.5
```

The collector:

- discovers the server-advertised session catalog;
- excludes the current incomplete session by default;
- rejects HTTP 200 responses whose returned `sessionDate` does not match the request;
- skips an existing valid matching file unless `--refresh` is supplied;
- writes only response JSON and sanitized collection metadata;
- uses atomic daily-file replacement and bounded retries.

Implementation:

```text
backend/src/xau_vol2vol_history_walkforward/browser_collector.py
backend/src/xau_vol2vol_history_walkforward/collection_manifest.py
backend/scripts/collect_vol2vol_browser_history.py
```

If the browser is absent, the CDP port is unavailable, the challenge is not
cleared, or the session expires, collection fails closed and records no browser
credentials. Close the dedicated browser and remove
`%LOCALAPPDATA%\Elpis\vol2vol-browser-profile` to remove its local state. A new
profile or a cleared challenge rotates that state; it must never be copied into
the repository.
