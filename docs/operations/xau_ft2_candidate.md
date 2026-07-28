# XAU FT2 Raw Candidate Operations

## Scope

`FT2_RAW_V1` is a research-only literal-2SD first-touch candidate. It never
submits orders, sizes positions, averages, recovers, or uses martingale.

OI, IV, volume, and rejection are context only. They do not gate the primary
raw first-touch alert.

## Daily Run

From `backend`:

```powershell
.\scripts\run_daily_xau_ft2_candidate.ps1 -SessionDate 2026-07-28
```

The runner:

1. Reuses CDP on `127.0.0.1:9222` or starts the existing dedicated Edge profile.
2. Fetches the exact-date Vol2Vol payload.
3. Refreshes Dukascopy XAUUSD M1 data.
4. Runs the strict-DTE audit and frozen candidate workflow.
5. Appends immutable candidate records.

Starting a new browser profile may require the user to complete Vol2Vol's
supported browser authentication before rerunning collection. Authentication
failure records no payload and creates no plan.

## Local Storage

Research data:

```text
data/imports/vol2vol/daily/YYYY-MM-DD/raw.json
data/imports/vol2vol/daily/YYYY-MM-DD/collection_meta.json
data/imports/xau/dukascopy/xauusd/m1/YYYY-MM.csv
```

Immutable candidate journals:

```text
data/reports/xau_ft2_candidate/v1/plans.jsonl
data/reports/xau_ft2_candidate/v1/alerts.jsonl
data/reports/xau_ft2_candidate/v1/acknowledgements.jsonl
data/reports/xau_ft2_candidate/v1/events.jsonl
data/reports/xau_ft2_candidate/v1/outcomes.jsonl
data/reports/xau_ft2_candidate/v1/daily_summaries.jsonl
```

These data and report paths are local and excluded from git.

## API

```text
GET  /api/v1/research/xau/ft2-candidate/latest
POST /api/v1/research/xau/ft2-candidate/{alert_id}/acknowledge
```

Acknowledgement does not close a candidate and does not submit an order.

## Broker Quote

Optional CSV:

```csv
timestamp,symbol,bid,ask
2026-07-28T08:00:30+07:00,XAUUSD,4100.10,4100.40
```

A provisional translated alert requires:

- quote age no greater than 60 seconds;
- touch-to-alert delay no greater than 120 seconds;
- touch-to-quote gap no greater than 120 seconds;
- spread no greater than 2.5 points;
- a synchronized retained Dukascopy reference.

Otherwise, the output remains a `REFERENCE_ALERT`.

## Credential Boundary

No credential, cookie, header, token, private URL, or browser replay material is
written to the repository, logs, reports, or research files.

The dedicated browser profile is local:

```text
%LOCALAPPDATA%\Elpis\quikstrike-browser-profile
```

To remove or rotate browser state:

1. Close the dedicated Edge window.
2. Remove that local profile directory.
3. Start the browser again with `scripts/start_vol2vol_cdp_browser.ps1`.
4. Complete supported browser authentication again.

Missing or expired browser credentials fail closed: no Vol2Vol payload, no
frozen plan, and no alert.
