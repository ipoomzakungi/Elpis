# Data Model: XAU Dukascopy Price Capture And Plan Tracker

## Enums

- `XauDukasCaptureStatus`: `completed`, `partial`, `unavailable`, `failed`
- `XauTrackedOrderStatus`: `planned`, `triggered`, `target_hit`, `stop_hit`, `recovery_triggered`, `recovery_target_hit`, `expired`, `open`, `ambiguous`, `unavailable`
- `XauPlanTrackerReadiness`: `complete`, `partial`, `blocked`
- `XauReferenceAlignmentStatus`: `exact`, `within_tolerance`, `stale`, `unavailable`

## Entities

### XauDukasCliCaptureRequest

Symbol, timeframe, start/end time, timezone, CLI path, command template, output directory, timeout, and research acknowledgement.

### XauDukasPriceBar

Normalized traded-side XAUUSD OHLCV bar with source `dukascopy_cli` and source quality `research_price_feed`.

### XauDukasCaptureResult

Capture ID, status, bar count, bars path, latest price, limitations, and research-only guardrails.

### XauPlanTrackerRequest

Session date, planning times, CME source, price source, local bars path or Dukascopy CLI config, SD plan parameters, run-until time, output root, and research acknowledgement.

### XauResearchPlanTrackerSnapshot

Planning time, future reference, traded reference, Diff, DTE, native SD values, long/short plan levels, missing inputs, limitations, and guardrails.

### XauResearchTrackedOrder

Order ID, planning time, side, entry/target/stop/recovery levels, simulated status, trigger/exit time, current price, current simulated PnL points, MFE, MAE/drawdown, bar coverage, limitations, and guardrails.

### XauPlanTrackerRunResult

Run ID, session date, snapshot/order counts, artifact paths, readiness, missing inputs, limitations, and guardrails.

## Validation Rules

- `signal_allowed` is always false.
- `research_only` is always true.
- Missing price bars never become zero prices.
- No broker order IDs or account fields exist.
- `range_label` is never converted into numeric SD.
