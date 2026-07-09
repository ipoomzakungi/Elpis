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

Acceptable future flow:

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

## Current Status

The code currently includes only a safe persistence stub:

```text
backend/src/xau_vol2vol_history_walkforward/browser_assisted_fetch.py
```

Full browser automation should be added only if it can save sanitized response
bodies without persisting cookies, headers, or session tokens.
