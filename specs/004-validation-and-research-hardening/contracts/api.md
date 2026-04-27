# API Contracts: Validation and Research Hardening

**Date**: 2026-04-27  
**Feature**: 004-validation-and-research-hardening

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research validation endpoints. Endpoints must not require private exchange keys or broker credentials.

## Endpoints

### 1. Run Validation Report

Runs a synchronous local research hardening report and writes generated artifacts under `data/reports/{validation_run_id}/`.

**Endpoint**: `POST /api/v1/backtests/validation/run`

**Request Body**:

```json
{
  "base_config": {
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
      {"mode": "grid_range", "enabled": true, "entry_threshold": 0.15, "atr_buffer": 1.0},
      {"mode": "breakout", "enabled": true, "atr_buffer": 1.0, "risk_reward_multiple": 2.0}
    ],
    "baselines": ["buy_hold", "price_breakout"],
    "report_format": "both"
  },
  "capital_sizing": {
    "buy_hold_capital_fraction": 1.0,
    "buy_hold_sizing_mode": "capital_fraction"
  },
  "stress_profiles": ["normal", "high_fee", "high_slippage", "worst_reasonable_cost"],
  "sensitivity_grid": {
    "grid_entry_threshold": [0.1, 0.15, 0.2],
    "atr_stop_buffer": [0.75, 1.0, 1.25],
    "breakout_risk_reward_multiple": [1.5, 2.0, 2.5],
    "fee_slippage_profile": ["normal", "high_fee"]
  },
  "walk_forward": {
    "split_count": 3,
    "minimum_rows_per_split": 20
  },
  "include_real_data_check": true
}
```

**Response** (200 OK):

```json
{
  "validation_run_id": "val_20260427_160000_btcusdt_15m",
  "status": "completed",
  "created_at": "2026-04-27T16:00:00Z",
  "completed_at": "2026-04-27T16:00:20Z",
  "symbol": "BTCUSDT",
  "provider": "binance",
  "timeframe": "15m",
  "data_identity": {
    "feature_path": "data/processed/btcusdt_15m_features.parquet",
    "row_count": 2880,
    "first_timestamp": "2026-03-28T00:00:00Z",
    "last_timestamp": "2026-04-27T00:00:00Z",
    "content_hash": "sha256..."
  },
  "mode_metrics": [],
  "stress_results": [],
  "sensitivity_results": [],
  "walk_forward_results": [],
  "regime_coverage": {},
  "concentration_report": {},
  "warnings": [
    "Historical simulation outputs only; not profitability evidence or live-trading readiness."
  ],
  "artifacts": []
}
```

### 2. List Validation Reports

**Endpoint**: `GET /api/v1/backtests/validation`

**Response** (200 OK):

```json
{
  "runs": [
    {
      "validation_run_id": "val_20260427_160000_btcusdt_15m",
      "status": "completed",
      "created_at": "2026-04-27T16:00:00Z",
      "symbol": "BTCUSDT",
      "provider": "binance",
      "timeframe": "15m",
      "mode_count": 4,
      "stress_profile_count": 4,
      "walk_forward_split_count": 3,
      "warnings": []
    }
  ]
}

```

### 3. Get Validation Report

**Endpoint**: `GET /api/v1/backtests/validation/{validation_run_id}`

Returns full validation metadata and report sections.

### 4. Get Stress Results

**Endpoint**: `GET /api/v1/backtests/validation/{validation_run_id}/stress`

Returns rows grouped by stress profile and strategy/baseline mode.

### 5. Get Sensitivity Results

**Endpoint**: `GET /api/v1/backtests/validation/{validation_run_id}/sensitivity`

Returns bounded parameter-grid rows with fragility flags.

### 6. Get Walk-Forward Results

**Endpoint**: `GET /api/v1/backtests/validation/{validation_run_id}/walk-forward`

Returns chronological split rows with per-mode metrics or insufficiency notes.

### 7. Get Concentration and Coverage Results

**Endpoint**: `GET /api/v1/backtests/validation/{validation_run_id}/concentration`

Returns regime coverage and trade concentration sections.

## Common Error Responses

### Missing Processed Features

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Processed features not found for BTCUSDT 15m",
    "details": [
      {
        "field": "feature_path",
        "message": "Run the existing data download and feature processing flow before real-data validation: POST /api/v1/download then POST /api/v1/process."
      }
    ]
  }
}
```

### Invalid Validation Configuration

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid validation configuration",
    "details": [
      {"field": "capital_sizing.buy_hold_capital_fraction", "message": "must be greater than 0 and no more than 1"},
      {"field": "sensitivity_grid", "message": "parameter grid exceeds local validation limit"}
    ]
  }
}
```

### Missing Validation Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Validation run 'unknown' was not found",
    "details": []
  }
}
```