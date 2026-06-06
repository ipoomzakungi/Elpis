# Python Fee Drag by Timeframe

Research-only diagnostic. No live trading, no paper trading, no broker integration, and no profitability claim.

Grid sensitivity warning preserved: lowering gridSdLen increased trade frequency and fee drag in the preview, so lower grids should not be accepted without filtered walk-forward evidence.

| symbol | interval | trades_per_day | commission_total | gross_pnl_before_cost | net_pnl_after_cost | fee_drag_ratio | recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GC=F | 15m | 0.5581 | 108 | 23.62 | -84.38 | 4.5724 | DO_NOT_LOWER_GRID |
| GC=F | 30m | 0.2857 | 27 | -77.44 | -104.44 | 0.3487 | DO_NOT_LOWER_GRID |
| GC=F | 1h | 0.4646 | 1800 | 1054.47 | -745.53 | 1.707 | DO_NOT_LOWER_GRID |
| GC=F | 4h | 0.0441 | 171 | 1111.65 | 940.65 | 0.1538 | TEST_GRID_WITH_FILTERS_ONLY |
| GC=F | 1d | 0.0302 | 265.5 | 1213.2 | 947.7 | 0.2188 | TEST_GRID_WITH_FILTERS_ONLY |
| GLD | 1d | 0.0246 | 34.75 | -346.91 | -381.66 | 0.1002 | TEST_GRID_WITH_FILTERS_ONLY |
