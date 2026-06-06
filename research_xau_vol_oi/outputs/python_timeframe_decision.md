# Python Timeframe Decision

Research-only diagnostic. No live trading, no paper trading, no broker integration, and no profitability claim.

Final labels: DO_NOT_USE_RAW_SIGNALS, WATCH_4H_FILTERED_CANDIDATE, WATCH_1D_RESEARCH_ONLY, AVOID_LOW_TIMEFRAME_RAW, NEEDS_WALK_FORWARD_PASS, NEEDS_MORE_FORWARD_EVIDENCE, NOT_READY_FOR_MONEY.

Decision: avoid raw low timeframe signals, watch GC=F 4h only as a filtered research candidate, keep 1d research-only, and keep all outputs NOT_READY_FOR_MONEY.

| symbol | interval | timeframe_label | recommended_label | walk_forward_pass | money_readiness | required_next_step |
| --- | --- | --- | --- | --- | --- | --- |
| GC=F | 15m | NEGATIVE | AVOID_LOW_TIMEFRAME_RAW | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 30m | NEGATIVE | AVOID_LOW_TIMEFRAME_RAW | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 1h | NEGATIVE | AVOID_LOW_TIMEFRAME_RAW | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 4h | PROMISING_DIAGNOSTIC | WATCH_4H_FILTERED_CANDIDATE | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GC=F | 1d | PROMISING_DIAGNOSTIC | WATCH_1D_RESEARCH_ONLY | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| GLD | 1d | PROXY_ONLY | PROXY_ONLY_NOT_A_DECISION_TIMEFRAME | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
| XAUUSD=X | 1d | INSUFFICIENT_DATA | INSUFFICIENT_DATA | False | NOT_READY_FOR_MONEY | NEEDS_WALK_FORWARD_PASS |
