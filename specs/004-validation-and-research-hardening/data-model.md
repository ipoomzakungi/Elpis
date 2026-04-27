# Data Model: Validation and Research Hardening

**Date**: 2026-04-27  
**Feature**: 004-validation-and-research-hardening

## Entities

### ValidationRun

Represents one generated research hardening report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| validation_run_id | string | Stable filesystem-safe identifier | Required, unique |
| source_backtest_config | BacktestRunRequest | Base backtest configuration used for validation | Required |
| created_at | datetime | Creation timestamp | Required |
| completed_at | datetime/null | Completion timestamp | Required on completed run |
| status | enum | `completed`, `failed`, or `partial` | Required |
| data_identity | object | Source dataset path, provider, symbol, timeframe, hash, row count, date range | Required |
| mode_metrics | ModeMetrics[] | Per-strategy and per-baseline metrics | Required |
| stress_results | StressResult[] | Results by fee/slippage profile | Optional, default empty |
| sensitivity_results | ParameterSensitivityResult[] | Bounded parameter-grid rows | Optional, default empty |
| walk_forward_results | WalkForwardResult[] | Chronological split rows | Optional, default empty |
| regime_coverage | RegimeCoverageReport | Regime counts and regime performance | Optional when regimes unavailable |
| concentration_report | TradeConcentrationReport | Trade concentration and drawdown recovery | Optional when no trades |
| warnings | string[] | Non-fatal assumptions, cap events, limitations | Optional |
| artifacts | ReportArtifact[] | Saved validation report artifacts | Required |

### CapitalSizingConfig

Captures passive and active sizing assumptions.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| buy_hold_capital_fraction | decimal | Starting equity fraction used by buy-and-hold | > 0 and <= 1, default 1 |
| buy_hold_sizing_mode | enum | `capital_fraction` or explicit `risk_fractional` | Required |
| active_risk_per_trade | decimal | Existing active strategy fixed fractional risk | > 0 and <= 1 |
| leverage | decimal | Simulated leverage assumption | Must be 1 in v0 |
| notional_cap_enabled | boolean | Whether no-leverage cap is enforced | Must be true in v0 |

### NotionalCapEvent

Records one no-leverage cap event.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| trade_id | string/null | Trade linked to the cap event when available | Optional |
| strategy_mode | enum | Mode whose position was capped | Required |
| requested_notional | decimal | Notional before cap | > 0 |
| capped_notional | decimal | Notional after cap | > 0 and <= available equity |
| available_equity | decimal | Equity used for cap decision | > 0 |
| reason | string | Human-readable cap reason | Required |

### EquityObservation

Extends the existing equity point for open-position visibility.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Bar timestamp | Required |
| strategy_mode | enum | Strategy or baseline mode | Required |
| realized_equity | decimal | Equity from closed trades only | >= 0 |
| unrealized_pnl | decimal/null | Mark-to-market open-position PnL using close price | Null if unavailable |
| total_equity | decimal | Realized plus unrealized equity where available | >= 0 |
| drawdown | decimal | Drawdown fraction based on total equity when available | <= 0 or 0 |
| drawdown_pct | decimal | Drawdown percentage | <= 0 or 0 |
| open_position | boolean | Whether a position is open | Required |
| equity_basis | enum | `total_mark_to_market` or `realized_only` | Required |

### ModeMetrics

Canonical metric row for one independent strategy or baseline mode.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| strategy_mode | enum | Mode name | Required |
| category | enum | `strategy` or `baseline` | Required |
| total_return_pct | decimal | Return for this independent mode | Required |
| max_drawdown_pct | decimal | Drawdown for this independent mode | Required |
| number_of_trades | integer | Trade count | >= 0 |
| profit_factor | decimal/null | Null when undefined | Optional |
| win_rate | decimal/null | Null when no trades | Optional |
| expectancy | decimal/null | Null when no trades | Optional |
| equity_basis | enum | Basis used for drawdown and equity | Required |
| notes | string[] | Undefined metrics, no-trade notes, cap notes | Optional |

### CostStressProfile

Named transaction cost assumption set.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | enum | `normal`, `high_fee`, `high_slippage`, `worst_reasonable_cost` | Required |
| fee_rate | decimal | Fee assumption | >= 0 and bounded |
| slippage_rate | decimal | Slippage assumption | >= 0 and bounded |
| description | string | Profile explanation | Required |

### StressResult

One validation result for a mode under a cost profile.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| profile | CostStressProfile | Profile used | Required |
| strategy_mode | enum | Mode evaluated | Required |
| category | enum | `strategy` or `baseline` | Required |
| metrics | ModeMetrics | Per-mode result under profile | Required |
| outcome | enum | `remained_positive`, `turned_negative`, `no_trades`, `not_evaluable` | Required |
| notes | string[] | Warnings or assumptions | Optional |

### ParameterSensitivityResult

One bounded parameter-grid result row.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| parameter_set_id | string | Stable row identifier | Required |
| grid_entry_threshold | decimal/null | Grid threshold value when applicable | Optional |
| atr_stop_buffer | decimal/null | ATR stop buffer value when applicable | Optional |
| breakout_risk_reward_multiple | decimal/null | Breakout R multiple when applicable | Optional |
| stress_profile_name | string | Fee/slippage profile name | Required |
| strategy_mode | enum | Mode evaluated | Required |
| metrics | ModeMetrics | Result for this parameter row | Required |
| fragility_flag | boolean | True when performance depends on isolated setting | Required |
| notes | string[] | Explanatory notes | Optional |

### WalkForwardResult

One chronological validation split.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| split_id | string | Stable split identifier | Required |
| start_timestamp | datetime | First bar in split | Required |
| end_timestamp | datetime | Last bar in split | Required |
| row_count | integer | Feature rows in split | >= 0 |
| status | enum | `evaluated` or `insufficient_data` | Required |
| mode_metrics | ModeMetrics[] | Per-mode metrics for the split | Optional when insufficient |
| notes | string[] | Insufficiency or limitation notes | Optional |

### RegimeCoverageReport

Summarizes feature and trade coverage by regime.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| bar_counts | object | Counts for RANGE, BREAKOUT_UP, BREAKOUT_DOWN, AVOID, unknown | Required when regimes exist |
| trades_per_regime | object | Trade counts by regime | Required when trades exist |
| return_by_regime | object | Return summary by regime | Required when trades exist |
| coverage_notes | string[] | Missing or malformed regime notes | Optional |

### TradeConcentrationReport

Summarizes dependence on outlier trades and drawdown recovery.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| top_1_profit_contribution_pct | decimal/null | Profit share from best trade | Null when unavailable |
| top_5_profit_contribution_pct | decimal/null | Profit share from best five trades | Null when unavailable |
| top_10_profit_contribution_pct | decimal/null | Profit share from best ten trades | Null when unavailable |
| best_trades | TradeRecord[] | Up to 10 best trades | Optional |
| worst_trades | TradeRecord[] | Up to 10 worst trades | Optional |
| max_consecutive_losses | integer | Worst loss streak | >= 0 |
| drawdown_recovery_bars | integer/null | Bars to recover from worst drawdown | Null when unavailable |
| drawdown_recovery_status | enum | `recovered`, `not_recovered`, `not_applicable` | Required |
| notes | string[] | Concentration and recovery notes | Optional |

## Relationships

```text
ValidationRun (1) -> (1) BacktestRunRequest
ValidationRun (1) -> (many) ModeMetrics
ValidationRun (1) -> (many) StressResult
ValidationRun (1) -> (many) ParameterSensitivityResult
ValidationRun (1) -> (many) WalkForwardResult
ValidationRun (1) -> (1) RegimeCoverageReport
ValidationRun (1) -> (1) TradeConcentrationReport
ValidationRun (1) -> (many) ReportArtifact
BacktestRunRequest (1) -> (1) CapitalSizingConfig
TradeRecord (0..1) -> (0..1) NotionalCapEvent
```

## Validation Rules

- Buy-and-hold capital fraction must be greater than 0 and no more than 1.
- Buy-and-hold defaults to capital-fraction sizing and must be visibly separated from active strategies.
- Active fixed fractional sizing must cap notional to available equity when leverage is 1.
- Cap events must be recorded whenever requested notional exceeds available equity.
- Stress profile names must be unique within a validation run.
- Parameter grids must be bounded to avoid local runaway validation runs.
- Walk-forward splits must be chronological and non-overlapping unless a rolling-window option is explicitly configured in a later feature.
- Walk-forward splits with insufficient rows are reported as insufficient rather than silently dropped.
- Regime coverage must tolerate missing or unknown regimes with notes.
- Concentration metrics must handle fewer than 10 trades without failing.
- Real-data validation must not silently substitute synthetic data when processed features are missing.
- Generated validation artifacts must remain under `data/reports` and ignored by git.