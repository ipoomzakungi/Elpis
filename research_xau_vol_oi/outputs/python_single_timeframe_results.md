# Python Single-Timeframe Results

Research-only diagnostic. No live trading, no paper trading, no broker integration, and no profitability claim.

Each row is a separate symbol/interval. No mixed-timeframe strategy score is calculated.

| symbol | interval | rows | trade_count | net_pnl_after_cost | profit_factor | max_drawdown | commission_paid | timeframe_label | sample_size_warning | proxy_warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GC=F | 15m | 712 | 24 | -84.38 | 0.6 | 98.44 | 108 | NEGATIVE | SAMPLE_SIZE_WARNING: fewer than 30 trades |  |
| GC=F | 30m | 230 | 6 | -104.44 | 0.3333 | 129.51 | 27 | NEGATIVE | SAMPLE_SIZE_WARNING: fewer than 30 trades |  |
| GC=F | 1h | 11594 | 400 | -745.53 | 0.6255 | 754.48 | 1800 | NEGATIVE |  |  |
| GC=F | 4h | 852 | 38 | 940.65 | 2.8916 | 45.09 | 171 | PROMISING_DIAGNOSTIC |  |  |
| GC=F | 1d | 1381 | 59 | 947.7 | 2.0423 | 54.43 | 265.5 | PROMISING_DIAGNOSTIC |  |  |
| GLD | 1d | 3901 | 139 | -381.66 | 0.7121 | 408 | 34.75 | PROXY_ONLY |  | PROXY_ONLY: GLD is not treated as XAU/GC. |
| XAUUSD=X | 1d | 2 | 0 | 0 | INF | 0 | 0 | INSUFFICIENT_DATA | INSUFFICIENT_DATA: only 2 rows available. |  |
