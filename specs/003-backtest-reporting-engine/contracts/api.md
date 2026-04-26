# API Contracts: Backtest and Reporting Engine

**Date**: 2026-04-27  
**Feature**: 003-backtest-reporting-engine

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research backtest endpoints.

## Endpoints

### 1. Run Backtest

Starts a local synchronous v0 research backtest and writes report artifacts under `data/reports/{run_id}/`.

**Endpoint**: `POST /api/v1/backtests/run`

**Request Body**:

```json
{
  "symbol": "BTCUSDT",
  "provider": "binance",
  "timeframe": "15m",
  "feature_path": null,
  "initial_equity": 10000,
  "assumptions": {
    "fee_rate": 0.0004,
    "slippage_rate": 0.0002,
    "risk_per_trade": 0.01,
    "max_positions": 1,
    "allow_short": true,
    "allow_compounding": false,
    "leverage": 1,
    "ambiguous_intrabar_policy": "stop_first"
  },
  "strategies": [
    {
      "mode": "grid_range",
      "enabled": true,
      "allow_short": true,
      "entry_threshold": 0.15,
      "atr_buffer": 1.0,
      "take_profit": { "mode": "range_mid" }
    },
    {
      "mode": "breakout",
      "enabled": true,
      "allow_short": true,
      "atr_buffer": 1.0,
      "risk_reward_multiple": 2.0
    }
  ],
  "baselines": ["buy_hold", "price_breakout"],
  "report_format": "both"
}
```

**Response** (200 OK):

```json
{
  "run_id": "bt_20260427_153000_btcusdt_15m",
  "status": "completed",
  "created_at": "2026-04-27T15:30:00Z",
  "completed_at": "2026-04-27T15:30:02Z",
  "symbol": "BTCUSDT",
  "provider": "binance",
  "timeframe": "15m",
  "metrics": {
    "total_return_pct": 1.2,
    "max_drawdown_pct": -0.8,
    "profit_factor": 1.15,
    "win_rate": 0.52,
    "number_of_trades": 25,
    "expectancy": 4.5
  },
  "artifacts": [
    {
      "artifact_type": "metadata",
      "path": "data/reports/bt_20260427_153000_btcusdt_15m/metadata.json",
      "format": "json"
    },
    {
      "artifact_type": "trades",
      "path": "data/reports/bt_20260427_153000_btcusdt_15m/trades.parquet",
      "format": "parquet",
      "rows": 25
    }
  ],
  "warnings": [
    "Backtest is historical simulation only and does not imply profitability or live-trading readiness"
  ]
}
```

### 2. List Backtests

Lists saved run metadata from `data/reports`.

**Endpoint**: `GET /api/v1/backtests`

**Response** (200 OK):

```json
{
  "runs": [
    {
      "run_id": "bt_20260427_153000_btcusdt_15m",
      "status": "completed",
      "created_at": "2026-04-27T15:30:00Z",
      "symbol": "BTCUSDT",
      "provider": "binance",
      "timeframe": "15m",
      "strategy_modes": ["grid_range", "breakout"],
      "baseline_modes": ["buy_hold", "price_breakout"],
      "total_return_pct": 1.2,
      "max_drawdown_pct": -0.8
    }
  ]
}
```

### 3. Get Backtest Run

Returns run detail and artifact references.

**Endpoint**: `GET /api/v1/backtests/{run_id}`

**Response** (200 OK):

```json
{
  "run_id": "bt_20260427_153000_btcusdt_15m",
  "status": "completed",
  "created_at": "2026-04-27T15:30:00Z",
  "completed_at": "2026-04-27T15:30:02Z",
  "symbol": "BTCUSDT",
  "provider": "binance",
  "timeframe": "15m",
  "feature_path": "data/processed/btcusdt_15m_features.parquet",
  "config": {},
  "artifacts": [],
  "warnings": []
}
```

### 4. Get Backtest Trades

Returns trade log rows.

**Endpoint**: `GET /api/v1/backtests/{run_id}/trades?limit=500&offset=0`

**Response** (200 OK):

```json
{
  "data": [
    {
      "trade_id": "T000001",
      "run_id": "bt_20260427_153000_btcusdt_15m",
      "strategy_mode": "grid_range",
      "provider": "binance",
      "symbol": "BTCUSDT",
      "timeframe": "15m",
      "side": "long",
      "regime_at_signal": "RANGE",
      "signal_timestamp": "2026-04-24T00:00:00Z",
      "entry_timestamp": "2026-04-24T00:15:00Z",
      "entry_price": 65000.0,
      "exit_timestamp": "2026-04-24T04:00:00Z",
      "exit_price": 65500.0,
      "exit_reason": "take_profit",
      "quantity": 0.01,
      "notional": 650.0,
      "gross_pnl": 5.0,
      "fees": 0.52,
      "slippage": 0.26,
      "net_pnl": 4.22,
      "return_pct": 0.00649,
      "holding_bars": 15
    }
  ],
  "meta": { "count": 1, "limit": 500, "offset": 0 }
}
```

### 5. Get Backtest Metrics

Returns summary metrics, grouped returns, and comparison data.

**Endpoint**: `GET /api/v1/backtests/{run_id}/metrics`

**Response** (200 OK):

```json
{
  "run_id": "bt_20260427_153000_btcusdt_15m",
  "summary": {
    "total_return": 0.012,
    "total_return_pct": 1.2,
    "max_drawdown": -0.008,
    "max_drawdown_pct": -0.8,
    "profit_factor": 1.15,
    "win_rate": 0.52,
    "average_win": 10.5,
    "average_loss": -8.8,
    "expectancy": 4.5,
    "number_of_trades": 25,
    "average_holding_bars": 12.4,
    "max_consecutive_losses": 4
  },
  "return_by_regime": [],
  "return_by_strategy_mode": [],
  "return_by_symbol_provider": [],
  "baseline_comparison": [],
  "notes": []
}
```

### 6. Get Backtest Equity

Returns equity and drawdown curve points.

**Endpoint**: `GET /api/v1/backtests/{run_id}/equity`

**Response** (200 OK):

```json
{
  "run_id": "bt_20260427_153000_btcusdt_15m",
  "data": [
    {
      "timestamp": "2026-04-24T00:00:00Z",
      "strategy_mode": "grid_range",
      "equity": 10000.0,
      "drawdown": 0.0,
      "drawdown_pct": 0.0,
      "realized_pnl": 0.0,
      "open_position": false
    }
  ],
  "meta": { "count": 1 }
}
```

## Common Error Responses

### Missing Processed Features

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Processed features not found for BTCUSDT 15m",
    "details": [
      { "field": "feature_path", "message": "data/processed/btcusdt_15m_features.parquet does not exist" }
    ]
  }
}
```

### Invalid Backtest Configuration

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid backtest configuration",
    "details": [
      { "field": "assumptions.fee_rate", "message": "fee_rate must be greater than or equal to 0" },
      { "field": "assumptions.leverage", "message": "leverage above 1 is not allowed in v0" }
    ]
  }
}
```

### Missing Report Artifact

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Backtest run 'unknown' was not found",
    "details": []
  }
}
```