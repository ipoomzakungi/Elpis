# API Contract: XAU Range Desk / Diff-SD Planner

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`
- `no_signal_reasons`
- `limitations`

## POST /api/v1/research/xau/range-desk/plan

Builds one research-only futures-to-traded Range Desk plan.

```json
{
  "traded_instrument": "XAUUSD",
  "futures_symbol": "GC",
  "future_reference_price": 4500.0,
  "traded_reference_price": 4470.0,
  "session_open_price": 4472.0,
  "levels": [
    {"label": "lower_1sd", "futures_level": 4490.0},
    {"label": "upper_1sd", "futures_level": 4510.0},
    {"label": "lower_2sd", "futures_level": 4470.0},
    {"label": "upper_2sd", "futures_level": 4520.0},
    {"label": "lower_3sd", "futures_level": 4450.0},
    {"label": "upper_3sd", "futures_level": 4530.0}
  ],
  "oi_walls": [
    {"wall_id": "wall_4520", "futures_level": 4520.0}
  ],
  "research_only_acknowledged": true
}
```

Response model: `XauRangeDeskPlan`.

Key response fields:

- `readiness`
- `basis_snapshot.diff_points`
- `basis_snapshot.traded_offset`
- `traded_levels`
- `mapped_oi_walls`
- `zones`
- `target_plans`
- `missing_inputs`
- `limitations`

## Forbidden Behavior

The API does not expose buy/sell signals, alerts, order instructions, position
sizing, PnL, broker access, paper trading, live trading, or automatic trade
placement.
