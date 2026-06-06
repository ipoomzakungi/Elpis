# Python Walk-Forward by Timeframe

Research-only diagnostic. No live trading, no paper trading, no broker integration, and no profitability claim.

Filter policy is selected on the train window only, then frozen for the test window. Minimum frozen-policy test trades default to 30.

Research walk-forward passing splits: 0 of 7.

| symbol | interval | split_id | selected_filter_policy | train_net_pnl | test_net_pnl | test_trade_count | test_profit_factor | sample_size_warning | walk_forward_pass | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GC=F | 15m | 1 | COMBINED_CONSERVATIVE | -1.88 | -15.94 | 1 | 0 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 30m | 1 | RAW | -22.97 | -81.47 | 3 | 0.1136 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 1 | COMBINED_CONSERVATIVE | -107.39 | -29.33 | 14 | 0.6145 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 2 | COMBINED_CONSERVATIVE | -136.72 | -21.38 | 13 | 0.6719 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1h | 3 | COMBINED_CONSERVATIVE | -158.1 | -46.25 | 21 | 0.6141 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 4h | 1 | OPEN_DISTANCE_FILTER | 868.01 | 166.57 | 13 | 1.9299 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
| GC=F | 1d | 1 | FEE_HURDLE_FILTER | 698.58 | 325.97 | 21 | 1.9342 | SAMPLE_SIZE_WARNING: fewer than 30 frozen-policy test trades | False | INSUFFICIENT_TEST_TRADES_LT_30 |
