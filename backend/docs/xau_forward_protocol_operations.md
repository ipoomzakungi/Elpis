# XAU Forward Protocol v1 Operations

This workflow collects research evidence only. It never submits orders, sizes
positions, or emits live trade signals.

Protocol:

```text
xau_forward_research_protocol_v1
d24f343180682eddcd1a3cdf72f0e42d5c512b820951aeef5b5ff804c6710305
```

Do not edit protocol v1 after forward collection. Rule changes require v2.

Engine erratum `031M-forward-journal-execution-audit-fix` leaves the frozen
strategy rules unchanged while correcting execution accounting:

- entry and target/stop in the same M1 bar remain `same_bar_ambiguous` unless
  tick or sub-minute sequencing is available;
- F0 outcomes use `touch_entry`; F2 confirmations record the next executable
  bar but do not alter F0 outcomes;
- source alignment, XAU price age, and Vol2Vol snapshot age are persisted as
  separate fields;
- every prepare/monitor/finalize chain carries a `workflow_attempt_id`,
  `observation_mode`, `recorded_at`, `data_as_of`, and `engine_revision`.

Past sessions default to `retrospective_replay`. A same-day prepare defaults to
`true_forward` only when recorded from the planning time through 30 minutes
after it. Use `--observation-mode` explicitly when importing a historical
backtest or running a dry run. Monitor and finalize reuse the latest successful
prepare workflow for the same session and planning mode.

## Before 07:00 Bangkok

1. Start the user-controlled CDP browser with an authenticated Vol2Vol page.
2. Verify the Dukascopy XAUUSD data folder is current.
3. Keep generated data and journal files outside git.

### Vol2Vol daily browser unlock

Vol2Vol's free daily access is scoped to the browser profile that performed the
unlock. An unlock in the operator's normal Edge profile does not unlock the
separate CDP profile used by Elpis.

Observed flow on 2026-07-13:

1. Open `https://www.vol2vol.com/` in the Elpis CDP browser profile.
2. If the page shows the 24-hour unlock prompt, open it.
3. In the confirmation dialog, open the daily server-support link.
4. Close the external support tab and return to the original Vol2Vol tab.
5. Verify that the Range Desk and `/history` show current session data.
6. Run the collector while that same CDP browser profile remains open.

The page became available immediately after the support link was opened. This
is consistent with browser-scoped state that expires, but its exact server-side
implementation is intentionally treated as opaque. Do not copy, forge, replay,
or persist Vol2Vol cookies, Cloudflare state, tokens, or request headers. Use
the website's supported unlock flow in the same browser profile as the
collector.

The CDP profile can also become stale even when Edge still displays the page.
Observed symptoms include `ERR_CONNECTION_RESET`, an in-page `fetch()` failure,
or HTTP 403 from a previously working profile. Reuse the normal Elpis profile
while it works; when those symptoms persist, launch a fresh dated profile on a
new CDP port and complete the supported unlock again. A fresh profile is a
recovery measure, not a requirement to delete browser state every day. Edge's
native sync notice may cover the visible page, but it is browser chrome rather
than Vol2Vol content and does not prevent CDP from using the page.

Preserve the current session during the day so Vol2Vol retention cannot remove
it before the next collection. The file is intentionally marked incomplete and
the data-lake loader excludes it from backtests until a completed refresh
replaces it:

```powershell
python scripts/collect_vol2vol_browser_history.py `
  --all-available `
  --include-current-incomplete-session `
  --refresh `
  --cdp-url http://127.0.0.1:9222
```

Current and completion state is stored beside each daily payload in
`data/imports/vol2vol/daily/YYYY-MM-DD/collection_meta.json`. The retained
catalog is stored in `data/imports/vol2vol/catalog/available_sessions.json`.

`DATA_BLOCKED` is an Elpis safety state, not proof of an account or IP ban. It
means the collector did not obtain a valid Vol2Vol payload for the requested
session. Common causes include:

- the CDP browser is not running or port `9222` is unavailable;
- the CDP browser profile has not completed the daily unlock;
- Vol2Vol or Cloudflare rejected or reset the automated request;
- the returned payload is locked, malformed, stale, or for another session.

A visible unlocked page is not sufficient evidence that Elpis has collected
the data. Before preparing a plan, verify that this file exists and contains
the requested session date:

```text
data/imports/vol2vol/daily/YYYY-MM-DD/raw.json
```

If it is absent, remain `DATA_BLOCKED` and retry collection later. Do not run a
forward result from browser-visible data that was never persisted and
validated. An in-progress session may be used for a timestamp-safe prepare or
monitor step, but final outcomes must wait until the configured holding horizon
has ended and matching XAU bars are complete.

## Prepare Fixed Morning Plan

Run shortly after 07:00 Bangkok, once the 07:00 XAUUSD bar is available:

```powershell
python scripts/run_xau_forward_daily.py `
  --session-date 2026-07-13 `
  --stage prepare `
  --planning-mode fixed_morning `
  --collect-browser `
  --refresh-price
```

Expected successful state:

```text
PLAN_READY
```

Blocked states are explicit:

```text
DATA_BLOCKED
STALE_SOURCE
NO_VALID_SERIES
NO_PRE_07:00_SNAPSHOT
```

Do not bypass a blocked state by using a later snapshot as if it existed at
07:00.

## Rolling Research Checkpoints

Run at each configured 30-minute checkpoint:

```powershell
python scripts/run_xau_forward_daily.py `
  --session-date 2026-07-13 `
  --stage prepare `
  --planning-mode rolling_30m `
  --checkpoint 07:30
```

Use a new immutable plan record at every checkpoint. Fixed-morning and rolling
results remain separate.

## Monitor

Run during the session after refreshing the local Dukascopy data:

```powershell
python scripts/run_xau_forward_daily.py `
  --session-date 2026-07-13 `
  --stage monitor `
  --planning-mode fixed_morning `
  --refresh-price
```

The monitor appends observed touches and five-minute rejection confirmations.
F0 remains the baseline. F1 is context only; F2/F3 and BR are observational.

## Finalize

After the predefined intraday holding horizon has completed:

```powershell
python scripts/run_xau_forward_daily.py `
  --session-date 2026-07-13 `
  --stage finalize `
  --planning-mode fixed_morning `
  --refresh-price
```

Finalization appends A-D outcomes, MFE, MAE, and the frozen one-point baseline
cost assumption. Existing finalized rows are never rewritten. Corrections must
be appended as superseding records.

## Journal

Generated records are stored under:

```text
data/reports/xau_forward_protocol/v1/
```

Streams:

```text
plans.jsonl
opportunities.jsonl
confirmations.jsonl
outcomes.jsonl
daily_summary.jsonl
```

Review after ten new independent sessions or 15-20 new opportunities, not after
every outcome.
