# XAU Intraday Options Research Lab

Feature 032 is a retrospective, research-only harness for testing whether Vol2Vol IV,
open interest, and intraday option volume add information beyond XAUUSD price and
standard-deviation levels.

It does not modify the forward journal or protocol v1, submit orders, select a best
strategy, or produce signal-enabled output.

## Run

From `backend`:

```powershell
python scripts/run_xau_options_research_lab.py `
  --session-date-from 2026-05-31 `
  --session-date-to 2026-07-16
```

The CLI uses completed Vol2Vol sessions and matching Dukascopy XAUUSD bars. It builds
fixed-morning and rolling-30-minute checkpoints, deduplicates related events into
excursion episodes, and keeps the chronological 70/30 development/holdout split.

## Experiments

The tracked registry is `config/xau_options_research_experiments_v1.json`:

- `MR0`: price-only mean reversion control
- `MR1`: IV-conditioned mean reversion
- `MR2`: OI-wall mean reversion
- `MR3`: OI, IV, and flow-conditioned mean reversion
- `BO0`: price-only breakout control
- `BO1`: options-confirmed breakout
- `PIN0`: OI magnet/pinning study

Experiment hashes prevent rules from being changed silently after results are seen.
Missing option features remain null and do not become zero.

## Interpretation

Snapshots and checkpoints are not independent observations. Excursion episodes are
deduplicated, and the session is the bootstrap and holdout unit. Cost copies do not
increase sample counts. A result remains `insufficient_sample` unless sample,
integrity, bootstrap, holdout, incremental-value, and negative-control gates pass.

Generated reports are written under:

```text
data/reports/xau_options_research/<run_id>/
```

Generated market data and reports are intentionally excluded from git. Share
`review_handoff.md` with the JSON artifacts it references for external review.
