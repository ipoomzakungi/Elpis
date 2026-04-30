# API Contracts: Real Multi-Asset Research Report

**Date**: 2026-04-30  
**Feature**: 005-real-multi-asset-research-report

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research endpoints. Endpoints must not require private exchange keys, broker credentials, wallet credentials, paper trading credentials, or live trading permissions.

## Endpoints

### 1. Run Multi-Asset Research Report

Runs a synchronous local grouped research report. Generated artifacts are saved under `data/reports/{research_run_id}/`.

**Endpoint**: `POST /api/v1/research/runs`

**Request Body**:

```json
{
  "assets": [
    {
      "symbol": "BTCUSDT",
      "provider": "binance",
      "asset_class": "crypto",
      "timeframe": "15m",
      "enabled": true,
      "required_feature_groups": ["ohlcv", "regime", "oi", "funding", "volume_confirmation"]
    },
    {
      "symbol": "SPY",
      "provider": "yahoo_finance",
      "asset_class": "equity_proxy",
      "timeframe": "1d",
      "enabled": true,
      "required_feature_groups": ["ohlcv", "regime"]
    }
  ],
  "base_assumptions": {
    "initial_equity": 10000,
    "fee_rate": 0.0004,
    "slippage_rate": 0.0002,
    "risk_per_trade": 0.01,
    "allow_short": true
  },
  "strategy_set": {
    "include_grid_range": true,
    "include_breakout": true,
    "baselines": ["buy_hold", "price_breakout", "no_trade"]
  },
  "validation_config": {
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
    }
  },
  "report_format": "both"
}
```

**Response** (200 OK):

```json
{
  "research_run_id": "research_20260430_120000_multi_asset",
  "status": "partial",
  "created_at": "2026-04-30T12:00:00Z",
  "completed_at": "2026-04-30T12:02:15Z",
  "completed_count": 1,
  "blocked_count": 1,
  "assets": [
    {
      "symbol": "BTCUSDT",
      "provider": "binance",
      "asset_class": "crypto",
      "status": "completed",
      "classification": "fragile",
      "validation_run_id": "val_20260430_120010_btcusdt_15m",
      "capabilities": {
        "supports_ohlcv": true,
        "supports_open_interest": true,
        "supports_funding_rate": true,
        "detected_ohlcv": true,
        "detected_open_interest": true,
        "detected_funding_rate": true
      },
      "warnings": [
        "Historical simulation outputs only; not profitability evidence or live-readiness evidence."
      ]
    },
    {
      "symbol": "SPY",
      "provider": "yahoo_finance",
      "asset_class": "equity_proxy",
      "status": "blocked",
      "classification": "missing_data",
      "validation_run_id": null,
      "missing_data_instructions": [
        "Download SPY OHLCV data from the provider layer.",
        "Run feature processing for SPY 1d before starting multi-asset research."
      ],
      "warnings": [
        "Yahoo Finance assets are OHLCV-only in v0; OI and funding are not supported."
      ]
    }
  ],
  "warnings": [
    "Grouped report is a research comparison only and does not imply profitability, predictive power, safety, or live readiness."
  ],
  "artifacts": []
}
```

### 2. List Research Reports

**Endpoint**: `GET /api/v1/research/runs`

**Response** (200 OK):

```json
{
  "runs": [
    {
      "research_run_id": "research_20260430_120000_multi_asset",
      "status": "partial",
      "created_at": "2026-04-30T12:00:00Z",
      "completed_count": 1,
      "blocked_count": 1,
      "asset_count": 2,
      "warnings": []
    }
  ]
}
```

### 3. Get Research Report

**Endpoint**: `GET /api/v1/research/runs/{research_run_id}`

Returns full grouped research report metadata, asset summaries, warnings, limitations, and artifact references.

### 4. Get Asset Summary

**Endpoint**: `GET /api/v1/research/runs/{research_run_id}/assets`

Returns one row per configured asset, including status, capability badges, classification, row count, date range, missing-data instructions, warnings, and limitations.

### 5. Get Strategy/Baseline Comparison

**Endpoint**: `GET /api/v1/research/runs/{research_run_id}/comparison`

Returns per-asset and per-mode strategy/baseline comparison rows.

### 6. Get Validation Aggregation

**Endpoint**: `GET /api/v1/research/runs/{research_run_id}/validation`

Returns grouped stress, sensitivity, walk-forward, regime coverage, and concentration summary sections.

## Common Error Responses

### Invalid Research Configuration

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid research configuration",
    "details": [
      {
        "field": "assets",
        "message": "At least one enabled asset is required."
      }
    ]
  }
}
```

### Unsupported Capability Request

```json
{
  "error": {
    "code": "UNSUPPORTED_CAPABILITY",
    "message": "Requested OI/funding research is not supported for yahoo_finance asset SPY",
    "details": [
      {
        "field": "assets.1.required_feature_groups",
        "message": "Yahoo Finance assets are OHLCV-only in v0."
      }
    ]
  }
}
```

### Missing Research Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Research run 'unknown' was not found",
    "details": []
  }
}
```

## Research-Only Contract Rules

- Responses must not include profitability claims, predictive claims, safety claims, or live-readiness claims.
- Missing assets must be represented as blocked report rows rather than silently omitted.
- Synthetic data must not be substituted for real processed features in a real-data research run.
- Generated report paths must point under `data/reports`.
