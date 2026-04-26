# Data Model: Backtest and Reporting Engine

**Date**: 2026-04-27  
**Feature**: 003-backtest-reporting-engine

## Entities

### BacktestRun

Represents one reproducible historical simulation and its saved report artifacts.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| run_id | string | Stable run identifier used in file paths and API routes | Required, unique, filesystem-safe |
| status | enum | `completed`, `failed`, or `partial` | Required |
| created_at | datetime | Run creation timestamp | Required |
| completed_at | datetime/null | Run completion timestamp | Required on completed runs |
| symbol | string | Research symbol | Required |
| provider | string/null | Source provider when known | Optional for older artifacts |
| timeframe | string | Feature timeframe | Required |
| feature_path | string | Processed feature input path | Required |
| config | BacktestConfig | Saved reproducible configuration | Required |
| artifacts | ReportArtifact[] | Saved metadata, trades, equity, metrics, and report files | Required |
| warnings | string[] | Non-fatal assumptions or limitations | Optional |

### BacktestConfig

Saved configuration for reproducing a backtest run.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Symbol to load from processed features | Required, defaults to BTCUSDT |
| provider | string/null | Provider label where available | Optional |
| timeframe | string | Feature timeframe | Required, defaults to 15m |
| feature_path | string/null | Override path for synthetic or imported tests | Optional local path only |
| initial_equity | decimal | Starting simulated equity | > 0 |
| assumptions | BacktestAssumptions | Fee, slippage, sizing, and execution assumptions | Required |
| strategies | StrategyConfig[] | Regime-aware strategies to run | At least one strategy or baseline required |
| baselines | BaselineMode[] | Baseline comparison modes | Optional but recommended |
| report_format | enum | `json`, `markdown`, or `both` | Required |

### BacktestAssumptions

Captures simulation assumptions used by all strategies in a run.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| fee_rate | decimal | Fee applied per entry/exit notional | >= 0 and bounded |
| slippage_rate | decimal | Slippage applied to entry/exit prices | >= 0 and bounded |
| risk_per_trade | decimal | Fixed fractional risk per trade | > 0 and bounded |
| max_positions | integer | Max simultaneous positions | Must be 1 in v0 |
| allow_short | boolean | Whether short positions are permitted | Required |
| allow_compounding | boolean | Whether sizing uses current equity | Defaults false |
| leverage | decimal | Simulated leverage | Must be 1 in v0 |
| ambiguous_intrabar_policy | enum | Same-bar stop/TP policy | `stop_first` in v0 |

### StrategyConfig

Configures one strategy mode.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| mode | enum | `grid_range`, `breakout`, `buy_hold`, `price_breakout`, `no_trade` | Required |
| enabled | boolean | Whether this mode runs | Required |
| allow_short | boolean/null | Strategy-level short override | Optional, cannot exceed run assumption |
| entry_threshold | decimal/null | Distance/threshold for range or breakout entry | Strategy-specific |
| atr_buffer | decimal/null | ATR buffer for stops | >= 0 where used |
| take_profit | object/null | TP mode and value | Strategy-specific |
| risk_reward_multiple | decimal/null | Breakout TP R multiple | > 0 where used |

### StrategySignal

Internal signal produced from one feature row.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| signal_id | string | Stable signal identifier | Required |
| strategy_mode | enum | Strategy producing the signal | Required |
| signal_timestamp | datetime | Timestamp of signal bar | Required |
| side | enum | `long` or `short` | Required |
| entry_bar_index | integer | Index of next bar open for entry | Must exist |
| stop_loss | decimal | Proposed stop price | Required |
| take_profit | decimal/null | Proposed take-profit price | Optional |
| regime | string/null | Regime at signal | Optional |
| reason | string | Human-readable signal reason | Required |

### Position

Represents the one active simulated position in v0.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| position_id | string | Stable identifier | Required |
| strategy_mode | enum | Owning strategy mode | Required |
| side | enum | `long` or `short` | Required |
| entry_timestamp | datetime | Entry timestamp | Required |
| entry_price | decimal | Slippage-adjusted entry price | > 0 |
| quantity | decimal | Position quantity | > 0 |
| notional | decimal | Entry notional | > 0 |
| stop_loss | decimal | Stop price | Required |
| take_profit | decimal/null | Take-profit price | Optional |
| entry_fee | decimal | Entry fee | >= 0 |

### TradeRecord

Finalized simulated trade row.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| trade_id | string | Stable trade identifier | Required |
| run_id | string | Owning run | Required |
| strategy_mode | enum | Strategy or baseline mode | Required |
| provider | string/null | Provider where known | Optional |
| symbol | string | Symbol | Required |
| timeframe | string | Timeframe | Required |
| side | enum | `long` or `short` | Required |
| regime_at_signal | string/null | Regime at signal | Optional |
| signal_timestamp | datetime | Signal bar timestamp | Required |
| entry_timestamp | datetime | Entry timestamp | Required |
| entry_price | decimal | Slippage-adjusted entry | > 0 |
| exit_timestamp | datetime | Exit timestamp | Required |
| exit_price | decimal | Slippage-adjusted exit | > 0 |
| exit_reason | enum | `take_profit`, `stop_loss`, `end_of_data`, `invalidated` | Required |
| quantity | decimal | Simulated quantity | > 0 |
| notional | decimal | Entry notional | > 0 |
| gross_pnl | decimal | PnL before fees/slippage accounting | Required |
| fees | decimal | Total fees | >= 0 |
| slippage | decimal | Slippage cost estimate | >= 0 |
| net_pnl | decimal | PnL after costs | Required |
| return_pct | decimal | Trade return percentage | Required |
| holding_bars | integer | Bars held | >= 0 |

### EquityPoint

Timestamped equity and drawdown observation.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| timestamp | datetime | Bar timestamp | Required |
| strategy_mode | enum | Strategy/baseline mode | Required |
| equity | decimal | Simulated equity | >= 0 |
| drawdown | decimal | Drawdown fraction | <= 0 or 0 |
| drawdown_pct | decimal | Drawdown percentage | <= 0 or 0 |
| realized_pnl | decimal | Cumulative realized PnL | Required |
| open_position | boolean | Whether a position is open | Required |

### MetricsSummary

Aggregated backtest metrics.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| total_return | decimal | Total return fraction | Required |
| total_return_pct | decimal | Total return percentage | Required |
| max_drawdown | decimal | Worst drawdown fraction | Required |
| max_drawdown_pct | decimal | Worst drawdown percentage | Required |
| profit_factor | decimal/null | Gross wins divided by gross losses | Null when undefined |
| win_rate | decimal/null | Winning trade fraction | Null when no trades |
| average_win | decimal/null | Mean winning trade PnL | Null when no winners |
| average_loss | decimal/null | Mean losing trade PnL | Null when no losers |
| expectancy | decimal/null | Mean expected PnL per trade | Null when no trades |
| number_of_trades | integer | Trade count | >= 0 |
| average_holding_bars | decimal/null | Mean holding bars | Null when no trades |
| max_consecutive_losses | integer | Worst loss streak | >= 0 |
| return_by_regime | object | Grouped return/trade stats by regime | Required |
| return_by_strategy_mode | object | Grouped return/trade stats by mode | Required |
| return_by_symbol_provider | object | Grouped return where metadata exists | Required, can be empty |
| notes | string[] | Undefined metric or limitation notes | Optional |

### ReportArtifact

Saved artifact reference.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| artifact_type | enum | `metadata`, `config`, `trades`, `equity`, `metrics`, `report_json`, `report_markdown` | Required |
| path | string | Project-relative path under `data/reports` | Required |
| format | enum | `json`, `parquet`, `markdown` | Required |
| rows | integer/null | Row count for table artifacts | Optional |
| created_at | datetime | Artifact write time | Required |
| content_hash | string/null | Optional reproducibility hash | Optional |

## Relationships

```text
BacktestRun (1) -> (1) BacktestConfig
BacktestRun (1) -> (many) StrategyModeResult
StrategyModeResult (1) -> (many) TradeRecord
StrategyModeResult (1) -> (many) EquityPoint
StrategyModeResult (1) -> (1) MetricsSummary
BacktestRun (1) -> (many) ReportArtifact
BacktestConfig (1) -> (many) StrategyConfig
ProcessedFeatureDataset (1) -> (many) BacktestRun
```

## Required Feature Columns

Minimum shared columns: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `atr`, `range_high`, `range_low`, `range_mid`.

Regime-aware strategies additionally require `regime`. OI-aware comparisons may use `open_interest`, `oi_change_pct`, `funding_rate`, and related fields when available, but v0 backtests must not fail only because optional derivative fields are absent unless the selected strategy explicitly requires them.

## State Transitions

### Backtest Run

```text
[Requested]
  -> [Config Validated]
  -> [Features Loaded]
  -> [Feature Columns Validated]
  -> [Strategies Simulated]
  -> [Artifacts Written]
  -> [Completed]

[Config Validated] -> [Rejected]
[Features Loaded] -> [Rejected]
[Artifacts Written] -> [Failed]
```

### Position

```text
[No Position]
  -> [Signal Generated]
  -> [Enter Next Bar Open]
  -> [Open]
  -> [Exit by Stop/TP/End]
  -> [Trade Recorded]
  -> [No Position]
```

## Validation Rules

- Missing processed feature data returns a structured not-found response.
- Fee and slippage rates must be non-negative and bounded to prevent accidental unrealistic configs.
- Risk per trade must be positive and bounded.
- v0 rejects leverage above 1 and max positions above 1.
- Config models forbid unexpected fields so live-trading concepts cannot silently enter saved configs.
- Strategy modes validate their required columns before simulation.
- Final-bar signals with no next bar open are skipped and recorded in run warnings.
- Generated artifacts must remain under `data/reports/{run_id}/`.