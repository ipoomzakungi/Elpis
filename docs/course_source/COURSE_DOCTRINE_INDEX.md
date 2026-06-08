# Course Doctrine Index

This index locks the local course-source files that should guide future XAU/CME Vol2Vol/OI work in Elpis. It is a compact project map, not a copy of the source contents.

## Primary Sources

1. `oi_options_deep_distilled_source_pack_v2.md`
2. `CME_Vol2Vol_OI_Dense_Knowledge_Source_Pack_v2.md`
3. `Distrilled-IV.txt`
4. `Option-CME-ไม่ตรงกับราคาทองที่เทรดจริง.txt`

## Doctrine Rules

- OI is a structural map, not a direct buy/sell signal.
- High call OI or high put OI alone must not produce direction.
- IV and SD bands describe expected movement and risk boundaries, not guaranteed reversals or hard walls.
- OI change and intraday volume/flow are activation and freshness context.
- CME GC strikes and SD bands must be mapped to the traded instrument with basis/price drift before XAU/GO interpretation.
- Opening-price behavior matters: session open relative to walls and SD bands is required context.
- Candle acceptance or rejection is required before later reaction classification.
- Missing basis, missing expected range, missing open context, stale data, or missing candle context means `NO_TRADE`, `WAIT`, or `signal_allowed=false`.
- Signal logic must be traceable to these source files and must not be inferred from generic trading intuition when it conflicts with them.

## Current Project Translation

- Feature 017 preserves CME expected-range parity and blocks range-label-only numeric SD fabrication.
- Feature 018 creates a daily structural map with readiness and no-signal reasons.
- Feature 019 persists structural maps as local research artifacts.
- Feature 020A reads local bundle-shaped XAU artifacts and persists a structural map.
- Feature 021 creates research-only 2SD-3SD SD/OI candidate labels while keeping
  `signal_allowed=false` and `research_only=true`.
- Feature 022 connects the local XAU/CME components into a research-only daily
  workbench with provider statuses, basis snapshots, candidate sidecars, CLI,
  and API inspection while keeping `signal_allowed=false`.
- Feature 023 attaches local price-bar forward outcome labels to saved
  candidates for 30m, 1h, 4h, session-close, and next-day windows while keeping
  `signal_allowed=false`, `research_only=true`, and no PnL/execution behavior.
- Feature 024A maps CME futures-side SD and OI levels to traded XAU/GO/CFD
  planning levels with Diff/Basis while staying research-only.
- Feature 024B audits saved local artifacts for source-backed OI, volume,
  volatility, DTE, native SD, delta, gamma, and GEX prerequisites.
- Feature 025 creates research-only walk-forward Range Desk snapshots and
  simulated order/outcome records from source-backed native SD and mapped Diff
  context while keeping `signal_allowed=false`.

## Forbidden For Current Phase

- OI-only buy/sell output.
- `range_label` converted into fake numeric SD.
- CME strikes placed on XAU/GO charts without basis mapping.
- Live trading, broker execution, alerts, PnL, or strategy automation.
- 2SD/3.5SD entry-stop automation, PnL, alerts, execution, or strategy claims
  before outcome evidence is aggregated and validated.
- Recovery sizing treated as live position management or martingale behavior
  before research limits and outcome evidence are validated.

## Current Next Milestone

Feature 024 should compute reaction states automatically:

```text
confirmation_state
iv_state
flow_state
```

It must remain research-only and must not add live signals, orders, alerts, PnL,
paper trading, or execution behavior.
