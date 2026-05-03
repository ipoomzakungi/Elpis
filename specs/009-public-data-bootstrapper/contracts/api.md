# API Contract: Public Data Bootstrapper

Base path: `/api/v1`

All endpoints are research-only. They must not accept private trading keys, broker credentials, wallet keys, order execution instructions, or paid provider credentials.

## Common Error Shape

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid public bootstrap request",
    "details": []
  }
}
```

Common error codes:

- `VALIDATION_ERROR`
- `UNSAFE_PATH`
- `UNSUPPORTED_CAPABILITY`
- `FORBIDDEN_SCOPE`
- `BOOTSTRAP_RUN_NOT_FOUND`
- `SOURCE_UNAVAILABLE`
- `REPORT_READ_ERROR`

## POST /api/v1/data-sources/bootstrap/public

Starts a public/no-key bootstrap run. The implementation may perform real public downloads only when explicitly invoked by the user; automated tests must use mocked providers.

### Request

```json
{
  "include_binance": true,
  "binance_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "optional_binance_symbols": [],
  "binance_timeframes": ["15m"],
  "include_binance_open_interest": true,
  "include_binance_funding": true,
  "include_yahoo": true,
  "yahoo_symbols": ["SPY", "QQQ", "GLD", "GC=F"],
  "yahoo_timeframes": ["1d"],
  "days": 90,
  "start_time": null,
  "end_time": null,
  "run_preflight_after": true,
  "include_xau_local_instructions": true,
  "research_only_acknowledged": true
}
```

### Response 201

```json
{
  "bootstrap_run_id": "bootstrap_20260503_120000",
  "status": "partial",
  "created_at": "2026-05-03T12:00:00Z",
  "completed_at": "2026-05-03T12:01:30Z",
  "downloaded_count": 2,
  "skipped_count": 1,
  "failed_count": 1,
  "asset_results": [
    {
      "provider": "binance_public",
      "symbol": "BTCUSDT",
      "timeframe": "15m",
      "status": "downloaded",
      "row_count": 8600,
      "start_timestamp": "2026-02-03T00:00:00Z",
      "end_timestamp": "2026-05-03T00:00:00Z",
      "raw_artifacts": [
        {
          "artifact_type": "raw_ohlcv",
          "provider": "binance_public",
          "path": "data/raw/binance/btcusdt_15m_ohlcv.parquet",
          "row_count": 8600,
          "start_timestamp": "2026-02-03T00:00:00Z",
          "end_timestamp": "2026-05-03T00:00:00Z",
          "limitations": []
        }
      ],
      "processed_feature_path": "data/processed/btcusdt_15m_features.parquet",
      "unsupported_capabilities": [],
      "warnings": [],
      "limitations": [
        "Binance public OI/funding history can be limited or shallow."
      ],
      "missing_data_actions": []
    },
    {
      "provider": "yahoo_finance",
      "symbol": "GLD",
      "timeframe": "1d",
      "status": "downloaded",
      "row_count": 90,
      "start_timestamp": "2026-02-03T00:00:00Z",
      "end_timestamp": "2026-05-03T00:00:00Z",
      "raw_artifacts": [],
      "processed_feature_path": "data/processed/gld_1d_features.parquet",
      "unsupported_capabilities": [
        "open_interest",
        "funding",
        "iv",
        "gold_options_oi",
        "futures_oi",
        "xauusd_spot_execution"
      ],
      "warnings": [],
      "limitations": [
        "Yahoo Finance is OHLCV-only and is not a source for OI, funding, IV, gold options OI, futures OI, or XAUUSD execution data."
      ],
      "missing_data_actions": []
    }
  ],
  "preflight_result": {
    "status": "partial",
    "crypto_results": [],
    "proxy_results": [],
    "xau_result": {
      "status": "blocked"
    }
  },
  "report_artifacts": [
    {
      "artifact_type": "bootstrap_report",
      "provider": "binance_public",
      "path": "data/reports/data_bootstrap/bootstrap_20260503_120000/summary.json",
      "row_count": 0,
      "start_timestamp": null,
      "end_timestamp": null,
      "limitations": []
    }
  ],
  "research_only_warnings": [
    "Public data bootstrap is research-only and does not enable live, paper, shadow, broker, wallet, or order execution workflows."
  ],
  "limitations": [
    "XAU options OI remains a local CSV/Parquet import workflow."
  ],
  "missing_data_actions": [
    "Provide a local XAU options OI CSV or Parquet file with date or timestamp, expiry, strike, option_type, and open_interest columns."
  ]
}
```

### Response 400

Returned when `research_only_acknowledged` is false, a requested field attempts forbidden execution scope, or requested symbols/timeframes are invalid.

## GET /api/v1/data-sources/bootstrap/runs

Lists saved public bootstrap runs.

### Response 200

```json
{
  "runs": [
    {
      "bootstrap_run_id": "bootstrap_20260503_120000",
      "status": "partial",
      "created_at": "2026-05-03T12:00:00Z",
      "completed_at": "2026-05-03T12:01:30Z",
      "downloaded_count": 2,
      "skipped_count": 1,
      "failed_count": 1,
      "artifact_root": "data/reports/data_bootstrap/bootstrap_20260503_120000",
      "research_only_warnings": [
        "Research-only bootstrap report; not a trading readiness claim."
      ]
    }
  ]
}
```

## GET /api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}

Reads a saved public bootstrap run.

### Response 200

Same shape as `POST /api/v1/data-sources/bootstrap/public` response.

### Response 404

```json
{
  "error": {
    "code": "BOOTSTRAP_RUN_NOT_FOUND",
    "message": "Bootstrap run not found: bootstrap_missing",
    "details": []
  }
}
```

## Dashboard Contract

The Data Sources dashboard consumes:

- `POST /api/v1/data-sources/bootstrap/public` to start a public bootstrap from default or user-selected options.
- `GET /api/v1/data-sources/bootstrap/runs` to populate the bootstrap run selector.
- `GET /api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}` to show run status, downloaded/skipped/failed assets, output paths, limitations, missing-data actions, and preflight readiness.

Dashboard copy must keep research-only disclaimers visible and must not include buy/sell signals, profitability claims, predictive claims, safety claims, or live-readiness wording.

## Security And Scope Requirements

- No endpoint accepts private trading keys, broker credentials, wallet/private keys, order execution fields, or paid vendor API keys.
- No response returns secret values, masked values, partial values, or hashes.
- Generated data/report paths are local references under ignored directories.
- Yahoo Finance is always represented as OHLCV-only.
- XAU options OI is represented as local CSV/Parquet import only.
