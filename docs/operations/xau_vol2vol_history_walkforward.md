# XAU Vol2Vol History Walk-Forward

This module prepares research-only evidence from Vol2Vol history data before any
shadow signal engine exists.

It is not an XAUUSD candle downloader and it is not a live/paper trading module.
All outputs keep `signal_allowed=false` and `research_only=true`.

## Purpose

Use Vol2Vol public/local history payloads to normalize:

- intraday volume snapshots
- open-interest snapshots
- monthly open-interest snapshots
- futures current price and range context when present
- strike rows with call, put, total, vol settle, and changes

Then, when separately supplied traded-side XAUUSD/CFD bars are available, run
points-only SD mean-reversion walk-forward tests.

## Sources

Supported source modes:

- `local_file`
- `local_folder`
- `http_endpoint`
- `latest_existing`
- `unavailable`

HTTP source templates are configurable and use no cookies, credentials, or auth
bypass. Examples:

```text
https://www.vol2vol.com/api/vol2vol-history?sessionDate={session_date}
https://www.vol2vol.com/api/monthly-oi?targetMonth={target_month}
```

Raw HTTP responses are cached under:

```text
backend/data/imports/vol2vol_history/{session_date}/raw.json
```

## Diff Mapping

Vol2Vol/CME levels are futures-side structure. CFD/XAUUSD levels require Diff:

```text
diff = future_price - cfd_price
cfd_level = future_level - diff
```

If Diff/Basis is missing, plan readiness is blocked. The module must not coerce
missing values to zero.

## Wormhole

Wormhole means low-activity strike space:

```text
total <= threshold
```

It is context only:

- target vacuum may mean lower friction toward target
- stop vacuum may mean continuation risk beyond stop
- it is not directional by itself

## Simulation

Default plan grid:

- entries: 2SD and 3SD
- TP: half-SD, one-SD, fixed 12.5, fixed 25
- SL: next half-SD, next SD, 3.5SD

The simulator waits for price to touch the entry level, then checks target and
stop using local OHLC bars. If target and stop are both inside the same candle,
the default status is `ambiguous`.

No lot sizing, spread, slippage, commission, PnL, recovery, order IDs, or broker
state is included.

## Example

```powershell
cd backend

python scripts/run_xau_vol2vol_history_walkforward.py `
  --session-date-from 2026-06-25 `
  --session-date-to 2026-07-08 `
  --history-source-mode local_folder `
  --history-folder data/imports/vol2vol `
  --price-bars-path data/imports/xauusd_1m_20260625_20260708.csv `
  --entry-sd two_sd `
  --entry-sd three_sd `
  --tp-mode half_sd `
  --tp-mode one_sd `
  --tp-mode fixed_12_5 `
  --tp-mode fixed_25 `
  --timezone Asia/Bangkok
```

For Vol2Vol data preparation only, omit `--price-bars-path`. The run will still
write normalized history and plan artifacts, but walk-forward outcomes will be
empty and the report will explain that simulation was skipped.

## Outputs

```text
backend/data/reports/xau_vol2vol_history_walkforward/{run_id}/
  raw_manifest.json
  normalized_history.json
  normalized_history.csv
  plans.json
  outcomes.json
  stats.json
  ai_walkforward_pack.md
  ai_walkforward_pack.json
  metadata.json
```

Use `ai_walkforward_pack.md` and `stats.json` as the handoff files for review.

## Next Feature

After enough days are tested and reviewed, the next feature can be:

```text
032-xau-shadow-signal-decision-engine
```

That later module should consume evidence from this feature. It should not be
built before the walk-forward results are available.
