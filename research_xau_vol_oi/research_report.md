# XAU Vol-OI Research Report

Research-only diagnostic. No live trading, no paper trading, no broker integration, and no profitability claim.

## Single-Timeframe Python Results

| symbol | interval | rows | trade_count | net_pnl_after_cost | timeframe_label |
| --- | --- | --- | --- | --- | --- |
| GC=F | 15m | 712 | 24 | -84.38 | NEGATIVE |
| GC=F | 30m | 230 | 6 | -104.44 | NEGATIVE |
| GC=F | 1h | 11594 | 400 | -745.53 | NEGATIVE |
| GC=F | 4h | 852 | 38 | 940.65 | PROMISING_DIAGNOSTIC |
| GC=F | 1d | 1381 | 59 | 947.7 | PROMISING_DIAGNOSTIC |
| GLD | 1d | 3901 | 139 | -381.66 | PROXY_ONLY |
| XAUUSD=X | 1d | 2 | 0 | 0 | INSUFFICIENT_DATA |

## Walk-Forward by Timeframe

| symbol | interval | split_id | selected_filter_policy | test_net_pnl | test_trade_count | walk_forward_pass | reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GC=F | 15m | 1 | COMBINED_CONSERVATIVE | -15.94 | 1 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 30m | 1 | RAW | -81.47 | 3 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 1 | COMBINED_CONSERVATIVE | -29.33 | 14 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 2 | COMBINED_CONSERVATIVE | -21.38 | 13 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 3 | COMBINED_CONSERVATIVE | -46.25 | 21 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 4h | 1 | OPEN_DISTANCE_FILTER | 166.57 | 13 | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1d | 1 | FEE_HURDLE_FILTER | 325.97 | 21 | False | INSUFFICIENT_TEST_TRADES_LT_30 |

## 4h Candidate Deep Dive

GC=F 4h remains a filtered research watch candidate, not a validated money strategy. Net after cost is 940.65, while the top three winners account for 66.91% of net. Combined conservative filtering keeps 17 trades.

## Fee Drag by Timeframe

| symbol | interval | trades_per_day | fee_drag_ratio | recommendation |
| --- | --- | --- | --- | --- |
| GC=F | 15m | 0.5581 | 4.5724 | DO_NOT_LOWER_GRID |
| GC=F | 30m | 0.2857 | 0.3487 | DO_NOT_LOWER_GRID |
| GC=F | 1h | 0.4646 | 1.707 | DO_NOT_LOWER_GRID |
| GC=F | 4h | 0.0441 | 0.1538 | TEST_GRID_WITH_FILTERS_ONLY |
| GC=F | 1d | 0.0302 | 0.2188 | TEST_GRID_WITH_FILTERS_ONLY |
| GLD | 1d | 0.0246 | 0.1002 | TEST_GRID_WITH_FILTERS_ONLY |

## Timeframe Decision

| symbol | interval | recommended_label | money_readiness | required_next_step |
| --- | --- | --- | --- | --- |
| GC=F | 15m | AVOID_LOW_TIMEFRAME_RAW | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 30m | AVOID_LOW_TIMEFRAME_RAW | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 1h | AVOID_LOW_TIMEFRAME_RAW | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 4h | WATCH_4H_FILTERED_CANDIDATE | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 1d | WATCH_1D_RESEARCH_ONLY | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GLD | 1d | PROXY_ONLY_NOT_A_DECISION_TIMEFRAME | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| XAUUSD=X | 1d | INSUFFICIENT_DATA | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
