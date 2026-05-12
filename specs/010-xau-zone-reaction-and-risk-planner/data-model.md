# Data Model: XAU Zone Reaction and Risk Planner

**Date**: 2026-05-12  
**Feature**: 010-xau-zone-reaction-and-risk-planner

## Entities

### XauReactionReportRequest

Represents one request to create a reaction report from an existing XAU Vol-OI report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| source_report_id | string | Existing feature 006 XAU Vol-OI report id | Required, filesystem-safe id |
| current_price | decimal/null | Current XAU reference price for distance and open context | Required for full classification; missing can force no-trade |
| current_timestamp | datetime/null | Timestamp used for freshness and session checks | Required for fresh intraday classification |
| freshness_input | XauIntradayFreshnessInput/null | Intraday options freshness context | Optional; missing becomes unknown |
| vol_regime_input | XauVolRegimeInput/null | IV/RV/range context | Optional; missing becomes unknown |
| open_regime_input | XauOpenRegimeInput/null | Session-open context | Optional; missing becomes unknown |
| acceptance_inputs | XauAcceptanceInput[] | Per-wall or per-zone candle reaction inputs | Optional; missing weakens or blocks confirmation |
| event_risk_state | enum/null | Optional event-risk state | `clear`, `elevated`, `blocked`, or `unknown` |
| max_total_risk_per_idea | decimal/null | Research risk cap for planning annotations | Optional; required for risk plan output |
| max_recovery_legs | integer | Maximum bounded recovery legs | >= 0; default 0 |
| minimum_rr | decimal/null | Minimum reward/risk requirement | Optional; if unmet plan is blocked or noted |
| wall_buffer_points | decimal | Default wall buffer for acceptance and stops | >= 0 |
| report_format | enum | `json`, `markdown`, or `both` | Defaults `both` |
| research_only_acknowledged | boolean | Confirms user understands research-only scope | Must be true |

### XauIntradayFreshnessInput

Inputs for intraday OI freshness classification.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| intraday_timestamp | datetime/null | Timestamp of intraday OI/options snapshot | Optional; missing -> `UNKNOWN` |
| current_timestamp | datetime/null | Current/report timestamp | Optional; missing -> `UNKNOWN` |
| total_intraday_contracts | decimal/null | Total contracts observed in the intraday snapshot | Optional; <= 0 or missing -> `UNKNOWN` or `THIN` |
| min_contract_threshold | decimal | Minimum contracts for usable flow | > 0 |
| max_allowed_age_minutes | integer | Maximum snapshot age | > 0 |
| session_flag | string/null | Optional session label from source data | Optional |

### XauFreshnessState

Output of the freshness classifier.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| state | enum | `VALID`, `THIN`, `STALE`, `PRIOR_DAY`, or `UNKNOWN` | Required |
| age_minutes | decimal/null | Snapshot age in minutes | Null when unavailable |
| confidence_impact | enum | `none`, `reduce`, or `block` | Required |
| no_trade_reason | string/null | Reason when freshness blocks a candidate | Required when impact is block |
| notes | string[] | Freshness explanation | Optional |

### XauVolRegimeInput

Inputs for IV/RV/VRP and range-position evaluation.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| implied_volatility | decimal/null | Annualized IV as decimal | Optional; > 0 when provided |
| realized_volatility | decimal/null | Annualized RV as decimal | Optional; > 0 when provided |
| price | decimal/null | Current/reference price | Optional; > 0 when provided |
| iv_lower | decimal/null | Lower IV expected range edge | Optional |
| iv_upper | decimal/null | Upper IV expected range edge | Optional |
| rv_lower | decimal/null | Lower RV range edge | Optional |
| rv_upper | decimal/null | Upper RV range edge | Optional |
| price_series | decimal[] | Optional price series for realized volatility calculation | Optional; at least 2 values when used |
| annualization_periods | integer/null | Periods used to annualize realized volatility | Required when calculating RV from series |

### XauVolRegimeState

Volatility-context output.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| realized_volatility | decimal/null | Supplied or calculated RV | Null when unavailable |
| vrp | decimal/null | IV minus RV | Null unless both IV and RV exist |
| vrp_regime | enum | `iv_premium`, `balanced`, `rv_premium`, or `unknown` | Required |
| iv_edge_state | enum | `inside`, `at_edge`, `beyond_edge`, or `unknown` | Required |
| rv_extension_state | enum | `inside`, `extended`, `beyond_range`, or `unknown` | Required |
| confidence_impact | enum | `none`, `reduce`, `stress_warning`, or `unknown` | Required |
| notes | string[] | Volatility interpretation notes | Optional |

### XauOpenRegimeInput

Inputs for session-open regime evaluation.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| session_open | decimal/null | Session opening price | Required for known open state |
| current_price | decimal/null | Current/reference price | Required for known open state |
| initial_move_direction | enum/null | `up`, `down`, `flat`, or `unknown` | Optional |
| crossed_open_after_initial_move | boolean/null | Whether price crossed open after initial move | Optional |
| acceptance_beyond_open | boolean/null | Whether price held beyond open after crossing | Optional |

### XauOpenRegimeState

Opening price context output.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| open_side | enum | `above_open`, `below_open`, `at_open`, or `unknown` | Required |
| open_distance_points | decimal/null | Absolute price distance from open | Null when unavailable |
| open_flip_state | enum | `no_flip`, `crossed_without_acceptance`, `accepted_flip`, or `unknown` | Required |
| open_as_support_or_resistance | enum | `support_test`, `resistance_test`, `boundary`, or `unknown` | Required |
| notes | string[] | Open-anchor interpretation notes | Optional |

### XauAcceptanceInput

Inputs for wall acceptance/rejection classification.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| wall_id | string/null | Source wall id | Required when applying to a wall row |
| zone_id | string/null | Source zone id | Optional |
| wall_level | decimal | Wall or zone level being tested | Required |
| high | decimal | Candle high | Required |
| low | decimal | Candle low | Required |
| close | decimal | Candle close | Required |
| next_bar_open | decimal/null | Next bar open or hold proxy | Optional |
| buffer_points | decimal | Wall buffer in points | >= 0 |

### XauAcceptanceState

Candle reaction output.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| wall_id | string/null | Source wall id | Optional |
| zone_id | string/null | Source zone id | Optional |
| accepted_beyond_wall | boolean | Close beyond wall buffer | Required |
| wick_rejection | boolean | Wick through wall without acceptance | Required |
| failed_breakout | boolean | Break attempt failed to hold | Required |
| confirmed_breakout | boolean | Close plus next-bar hold beyond wall | Required |
| direction | enum | `above`, `below`, or `unknown` | Required |
| notes | string[] | Candle-state explanation | Optional |

### XauReactionLabel

Enum for the six required reaction labels.

| Value | Meaning |
|-------|---------|
| `REVERSAL_CANDIDATE` | Rejection at a significant wall with stretched context and usable data |
| `BREAKOUT_CANDIDATE` | Acceptance beyond a wall with supportive context |
| `PIN_MAGNET` | Near-expiry high OI near spot inside expected range |
| `SQUEEZE_RISK` | Accepted stress through a wall with IV/flow expansion evidence |
| `VACUUM_TO_NEXT_WALL` | Low-OI gap context toward a distant next wall |
| `NO_TRADE` | Data quality, missing context, conflict, or blocked setup |

### XauReactionRow

One classified reaction row.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| reaction_id | string | Stable row id | Required |
| source_report_id | string | Feature 006 report id | Required |
| wall_id | string/null | Linked source wall | Optional |
| zone_id | string/null | Linked source zone | Optional |
| reaction_label | XauReactionLabel | Required reaction label | Required |
| confidence_label | enum | `high`, `medium`, `low`, `blocked`, or `unknown` | Required |
| explanation_notes | string[] | Reasons for classification | Required |
| no_trade_reasons | string[] | Reasons candidate is blocked | Required when label is `NO_TRADE` |
| invalidation_level | decimal/null | Research invalidation reference | Null when unavailable |
| target_level_1 | decimal/null | First target/reference level | Null when unavailable |
| target_level_2 | decimal/null | Second target/reference level | Null when unavailable |
| next_wall_reference | string/null | Linked next wall id or level note | Optional |
| freshness_state | XauFreshnessState | Freshness context used | Required |
| vol_regime_state | XauVolRegimeState | Volatility context used | Required |
| open_regime_state | XauOpenRegimeState | Open context used | Required |
| acceptance_state | XauAcceptanceState/null | Candle context used | Optional |
| research_only_warning | string | Required warning text | Required |

### XauRiskPlan

Bounded research risk-plan annotation.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| plan_id | string | Stable plan id | Required |
| reaction_id | string | Linked reaction row | Required |
| reaction_label | XauReactionLabel | Reaction label being planned | Must not be `NO_TRADE` for active plan fields |
| entry_condition_text | string/null | Conditional research-only entry condition | Null for `NO_TRADE` |
| invalidation_level | decimal/null | Invalidation reference | Required for non-`NO_TRADE` plans unless unavailable reason exists |
| stop_buffer_points | decimal/null | Stop buffer annotation | >= 0 when provided |
| target_1 | decimal/null | First target/reference | Optional |
| target_2 | decimal/null | Second target/reference | Optional |
| max_total_risk_per_idea | decimal/null | Configured risk cap | Optional but must be noted when absent |
| max_recovery_legs | integer | Maximum bounded recovery legs | >= 0 |
| minimum_rr | decimal/null | Minimum reward/risk requirement | Optional |
| rr_state | enum | `meets_minimum`, `below_minimum`, `unavailable`, or `not_applicable` | Required |
| cancel_conditions | string[] | Conditions that cancel the research plan | Required for non-`NO_TRADE` plans |
| risk_notes | string[] | Research-only, cap, and limitation notes | Required |

### XauReactionReport

Persisted reaction report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| report_id | string | Reaction report id | Required, unique, filesystem-safe |
| source_report_id | string | Feature 006 source report id | Required |
| status | enum | `completed`, `partial`, or `blocked` | Required |
| created_at | datetime | Report creation timestamp | Required |
| session_date | date/null | Source/session date | Optional |
| request | XauReactionReportRequest | Normalized request | Required |
| source_wall_count | integer | Count of source walls evaluated | >= 0 |
| source_zone_count | integer | Count of source zones evaluated | >= 0 |
| reaction_count | integer | Count of reaction rows | >= 0 |
| no_trade_count | integer | Count of `NO_TRADE` rows | >= 0 |
| risk_plan_count | integer | Count of risk plans | >= 0 |
| freshness_state | XauFreshnessState | Report-level freshness summary | Required |
| vol_regime_state | XauVolRegimeState | Report-level volatility summary | Required |
| open_regime_state | XauOpenRegimeState | Report-level open summary | Required |
| reactions | XauReactionRow[] | Reaction table | Required |
| risk_plans | XauRiskPlan[] | Risk-plan table | Required |
| warnings | string[] | Research-only and data-quality warnings | Required |
| limitations | string[] | Source and feature limitations | Required |
| artifacts | ReportArtifact[] | Generated file references | Required |

### XauReactionReportSummary

List row for saved reaction reports.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| report_id | string | Reaction report id | Required |
| source_report_id | string | Source XAU Vol-OI report id | Required |
| status | enum | `completed`, `partial`, or `blocked` | Required |
| created_at | datetime | Report creation timestamp | Required |
| session_date | date/null | Session date | Optional |
| reaction_count | integer | Reaction row count | >= 0 |
| no_trade_count | integer | No-trade row count | >= 0 |
| risk_plan_count | integer | Risk-plan row count | >= 0 |
| warning_count | integer | Warning count | >= 0 |

## Relationships

```text
XauReactionReportRequest (1) -> (1) XauVolOiReport from feature 006
XauVolOiReport (1) -> (many) XauReactionRow
XauReactionRow (0..1) -> (1) XauRiskPlan
XauReactionRow (many) -> (0..many) XauOiWall references
XauReactionRow (many) -> (0..many) XauZone references
XauReactionReport (1) -> (many) ReportArtifact
```

## State Rules

- A reaction report is `blocked` when the source report is missing, invalid, has no usable walls/zones, basis is unavailable and required, or research-only acknowledgement is false.
- A reaction report is `partial` when some rows classify but others are `NO_TRADE` due to missing context, stale/thin data, unavailable targets, or incomplete risk inputs.
- A reaction report is `completed` when all eligible rows are evaluated and persisted, even if some rows are correctly labeled `NO_TRADE`.
- A `NO_TRADE` reaction must not have an active risk plan.
- Every risk plan must reference exactly one non-`NO_TRADE` reaction.
- Every generated artifact path must be under ignored report roots.

## Validation Rules

- `source_report_id` and `report_id` must be filesystem-safe and must not allow path traversal.
- `research_only_acknowledged` must be true for report creation.
- Freshness state must be `UNKNOWN` when required timestamp or contract inputs are absent.
- Prior-day freshness must not be upgraded to valid by high contract count.
- IV and RV must be positive when supplied.
- VRP is null unless both IV and RV are available.
- Open flip cannot be `accepted_flip` unless acceptance beyond the open is true.
- Confirmed breakout requires close beyond the wall buffer and next-bar hold evidence.
- Wick-only penetration cannot be confirmed breakout.
- Risk plans cannot contain martingale, unlimited averaging, live-readiness, order, broker, or execution-ready wording.
- Reports and dashboard responses must not claim profitability, predictive power, safety, or live readiness.
