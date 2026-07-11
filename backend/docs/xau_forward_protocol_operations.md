# XAU Forward Protocol v1 Operations

This workflow collects research evidence only. It never submits orders, sizes
positions, or emits live trade signals.

Protocol:

```text
xau_forward_research_protocol_v1
d24f343180682eddcd1a3cdf72f0e42d5c512b820951aeef5b5ff804c6710305
```

Do not edit protocol v1 after forward collection. Rule changes require v2.

## Before 07:00 Bangkok

1. Start the user-controlled CDP browser with an authenticated Vol2Vol page.
2. Verify the Dukascopy XAUUSD data folder is current.
3. Keep generated data and journal files outside git.

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
