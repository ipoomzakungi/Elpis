# Data Model: Real Multi-Asset Research Report

**Date**: 2026-04-30  
**Feature**: 005-real-multi-asset-research-report

## Entities

### ResearchRunRequest

Represents one grouped multi-asset research request.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| assets | ResearchAssetConfig[] | Assets to evaluate | At least one enabled asset |
| default_asset_set | string/null | Optional preset such as `primary_crypto` or `crypto_plus_proxies` | Optional |
| base_assumptions | object | Shared backtest assumptions reused for each asset | Must preserve v0 no-leverage/no-execution rules |
| strategy_set | object | Strategy and baseline modes to compare | Must include at least one strategy or baseline |
| validation_config | object | Stress, sensitivity, walk-forward, coverage, and concentration settings | Uses existing validation bounds |
| report_format | enum | `json`, `markdown`, or `both` | Defaults to `both` |
| include_blocked_assets | boolean | Whether blocked assets appear in final report | Defaults to true |

### ResearchAssetConfig

Represents one configured asset.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol such as BTCUSDT, SPY, or GC=F | Required |
| provider | string | Provider name such as `binance`, `yahoo_finance`, or `local_file` | Required |
| asset_class | enum | `crypto`, `equity_proxy`, `gold_proxy`, `macro_proxy`, or `local_dataset` | Required |
| enabled | boolean | Whether the asset should be included | Defaults to true |
| timeframe | string | Feature timeframe | Required |
| feature_path | string/null | Optional explicit processed feature path | Must remain inside allowed local data paths |
| required_feature_groups | string[] | `ohlcv`, `regime`, `oi`, `funding`, `volume_confirmation` | Must be compatible with provider/source |
| display_name | string/null | Dashboard label | Optional |

### ResearchCapabilitySnapshot

Records source and dataset capability for one asset.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| provider | string | Provider name | Required |
| supports_ohlcv | boolean | Provider capability | Required |
| supports_open_interest | boolean | Provider capability | Required |
| supports_funding_rate | boolean | Provider capability | Required |
| detected_ohlcv | boolean | Processed file contains usable OHLCV columns | Required |
| detected_regime | boolean | Processed file contains regime/range columns | Required |
| detected_open_interest | boolean | Processed file contains OI columns | Required |
| detected_funding_rate | boolean | Processed file contains funding columns | Required |
| limitation_notes | string[] | Provider/source limitations | Optional |

### ResearchPreflightResult

Represents readiness for one asset before execution.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| provider | string | Provider name | Required |
| status | enum | `ready`, `missing_data`, `incomplete_features`, `unsupported_capability` | Required |
| feature_path | string | Expected or supplied feature file path | Required |
| row_count | integer/null | Processed row count when readable | Null when missing |
| first_timestamp | datetime/null | First feature timestamp | Null when missing |
| last_timestamp | datetime/null | Last feature timestamp | Null when missing |
| capability_snapshot | ResearchCapabilitySnapshot | Provider and dataset capabilities | Required |
| missing_columns | string[] | Required columns absent from file | Optional |
| instructions | string[] | Data preparation instructions | Required when blocked |
| warnings | string[] | Non-fatal limitations | Optional |

### ResearchAssetResult

Represents the final per-asset result in a grouped report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| provider | string | Provider name | Required |
| asset_class | enum | Configured asset class | Required |
| status | enum | `completed`, `blocked`, or `partial` | Required |
| classification | enum | `robust`, `fragile`, `missing_data`, `inconclusive`, `not_worth_continuing` | Required |
| preflight | ResearchPreflightResult | Preflight outcome | Required |
| validation_run_id | string/null | Linked single-asset validation run | Required when completed |
| data_identity | object | Source path, row count, date range, content hash | Required when completed |
| strategy_comparison | StrategyComparisonRow[] | Strategy/baseline comparison rows | Optional |
| stress_summary | StressSurvivalRow[] | Stress survival rows | Optional |
| walk_forward_summary | WalkForwardStabilityRow[] | Time-window stability rows | Optional |
| regime_coverage_summary | RegimeCoverageAssetRow[] | Regime coverage rows | Optional |
| concentration_summary | ConcentrationAssetRow[] | Concentration warning rows | Optional |
| warnings | string[] | Asset-specific warnings | Optional |
| limitations | string[] | Source or data limitations | Required |

### StrategyComparisonRow

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| provider | string | Provider name | Required |
| mode | string | Strategy or baseline mode | Required |
| category | enum | `strategy` or `baseline` | Required |
| total_return_pct | decimal/null | Per-mode return under assumptions | Null when undefined |
| max_drawdown_pct | decimal/null | Per-mode drawdown | Null when undefined |
| number_of_trades | integer | Trade count | >= 0 |
| profit_factor | decimal/null | Profit factor | Optional |
| win_rate | decimal/null | Win rate | Optional |
| notes | string[] | Undefined/no-trade notes | Optional |

### StressSurvivalRow

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| mode | string | Strategy/baseline mode | Required |
| profile | string | Cost profile | Required |
| outcome | string | Stress outcome | Required |
| survived | boolean/null | Whether result remained favorable under higher costs | Null when not evaluable |
| notes | string[] | Assumptions and warnings | Optional |

### WalkForwardStabilityRow

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| split_id | string | Chronological split id | Required |
| status | string | Evaluated or insufficient | Required |
| row_count | integer | Feature rows in split | >= 0 |
| trade_count | integer | Trades in split | >= 0 |
| stable | boolean/null | Stability flag for evaluated split | Null when insufficient |
| notes | string[] | Split notes | Optional |

### RegimeCoverageAssetRow

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| regime | string | Regime label | Required |
| bar_count | integer | Bars in regime | >= 0 |
| trade_count | integer | Trades in regime | >= 0 |
| return_pct | decimal/null | Return by regime | Optional |
| notes | string[] | Missing/unknown regime notes | Optional |

### ConcentrationAssetRow

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| symbol | string | Asset symbol | Required |
| top_1_profit_contribution_pct | decimal/null | Share from top trade | Optional |
| top_5_profit_contribution_pct | decimal/null | Share from top five trades | Optional |
| top_10_profit_contribution_pct | decimal/null | Share from top ten trades | Optional |
| max_consecutive_losses | integer | Loss streak | >= 0 |
| drawdown_recovery_status | string | Recovery status | Required |
| warning_level | enum | `none`, `watch`, `high` | Required |
| notes | string[] | Concentration warnings | Optional |

### ResearchRun

Grouped persisted report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| research_run_id | string | Filesystem-safe grouped report id | Required, unique |
| status | enum | `completed`, `partial`, or `failed` | Required |
| created_at | datetime | Creation timestamp | Required |
| completed_at | datetime/null | Completion timestamp | Required when completed/partial |
| request | ResearchRunRequest | Normalized config | Required |
| assets | ResearchAssetResult[] | One row per configured asset | Required |
| completed_count | integer | Completed assets | >= 0 |
| blocked_count | integer | Blocked assets | >= 0 |
| warnings | string[] | Report-level warnings | Optional |
| limitations | string[] | Research-only and source limitations | Required |
| artifacts | ReportArtifact[] | Generated grouped artifacts | Required |

## Relationships

```text
ResearchRunRequest (1) -> (many) ResearchAssetConfig
ResearchAssetConfig (1) -> (1) ResearchPreflightResult
ResearchPreflightResult (1) -> (1) ResearchCapabilitySnapshot
ResearchRun (1) -> (many) ResearchAssetResult
ResearchAssetResult (0..1) -> (1) ValidationRun
ResearchAssetResult (1) -> (many) StrategyComparisonRow
ResearchAssetResult (1) -> (many) StressSurvivalRow
ResearchAssetResult (1) -> (many) WalkForwardStabilityRow
ResearchAssetResult (1) -> (many) RegimeCoverageAssetRow
ResearchAssetResult (1) -> (0..1) ConcentrationAssetRow
ResearchRun (1) -> (many) ReportArtifact
```

## Validation Rules

- A research run must include at least one enabled asset.
- An enabled asset must specify symbol, provider, asset class, and timeframe.
- Processed feature paths must resolve inside local data directories or be rejected.
- Missing processed features must produce instructions, not synthetic fallback.
- Binance crypto assets may request OHLCV, OI, funding, regime, and volume-confirmation feature groups.
- Yahoo Finance assets may request OHLCV and price/regime-derived feature groups only; OI and funding must be reported unsupported.
- Local-file assets derive capability from validated columns and must not infer missing OI/funding.
- Gold proxy assets must carry source-limitation text explaining GC=F/GLD are OHLCV proxies only.
- Asset classification must be evidence-based and must not claim profitability, predictive power, safety, or live readiness.
- Generated artifacts must remain under `data/reports` and ignored by version control.
