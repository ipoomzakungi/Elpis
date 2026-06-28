# Data Model: XAU Walk-Forward Range Desk Research Runner

## Enums

- `XauWalkForwardReadiness`: `complete`, `partial`, `blocked`
- `XauWalkForwardScheduleTag`: `planning_1010`, `planning_1910`, `walk_forward`
- `XauWalkForwardPriceSource`: `manual`, `fixture`, `yahoo_research`, `unavailable`
- `XauWalkForwardSourceQuality`: `official`, `research_fallback`, `manual`, `fixture`, `unavailable`
- `XauWalkForwardSdSource`: `cme_native`, `derived_from_iv`, `manual_fix_range`, `fixture`, `unavailable`
- `XauResearchOrderSide`: `long_reversion`, `short_reversion`
- `XauResearchOrderStage`: `initial`, `recovery_1`, `recovery_2`
- `XauResearchRiskStatus`: `allowed`, `blocked`, `missing_config`
- `XauResearchOrderOutcomeStatus`: `planned`, `triggered`, `target_hit`, `stop_hit`, `expired`, `ambiguous`, `unavailable`

## Core Entities

- `XauWalkForwardScheduleConfig`
- `XauWalkForwardPriceSnapshot`
- `XauWalkForwardSdSnapshot`
- `XauResearchOrderPlanConfig`
- `XauResearchRiskConfig`
- `XauResearchOrderPlan`
- `XauResearchOrderOutcome`
- `XauWalkForwardSnapshotRecord`
- `XauWalkForwardRunRequest`
- `XauWalkForwardRunResult`

## State Rules

```text
diff_points = future_reference_price - traded_reference_price
traded_offset = traded_reference_price - future_reference_price
mapped_traded_level = futures_level + traded_offset

native range_bands.cme_numeric_sd present
  -> sd_source = cme_native

range_label only
  -> sd_source = unavailable
  -> limitation records that range labels are classification context only

recovery sizing missing point value
  -> risk_status = missing_config

computed recovery size > max_size
  -> risk_status = blocked
```

All persisted records remain `research_only=true` and `signal_allowed=false`.
