# API Contract: Real Data-Source Onboarding And First Evidence Run

Base path: `/api/v1`

All responses use the existing structured error envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": []
  }
}
```

## GET /api/v1/data-sources/readiness

Returns current provider readiness and optional key presence without returning secret values.

### Response 200

```json
{
  "generated_at": "2026-05-02T10:00:00Z",
  "public_sources_available": true,
  "optional_sources_missing": [
    "kaiko_optional",
    "tardis_optional",
    "coinglass_optional",
    "cryptoquant_optional"
  ],
  "forbidden_sources_detected": [],
  "research_only_warnings": [
    "Data-source onboarding is research-only and does not enable live, paper, shadow, broker, wallet, or order execution workflows."
  ],
  "provider_statuses": [
    {
      "provider_type": "binance_public",
      "status": "ready",
      "configured": true,
      "env_var_name": null,
      "secret_value_returned": false,
      "capabilities": {
        "provider_type": "binance_public",
        "display_name": "Binance Public",
        "tier": "tier_0_public_local",
        "supports": ["crypto_ohlcv", "limited_public_open_interest", "public_funding"],
        "unsupported": ["private_account_data", "execution"],
        "requires_key": false,
        "requires_local_file": false,
        "is_optional": false,
        "limitations": [
          "Official historical OI can be limited; deeper history may require vendor data."
        ],
        "forbidden_reason": null
      },
      "warnings": [],
      "limitations": [
        "Public endpoints only; no private account or order endpoints."
      ],
      "missing_actions": []
    },
    {
      "provider_type": "kaiko_optional",
      "status": "unavailable_optional",
      "configured": false,
      "env_var_name": "KAIKO_API_KEY",
      "secret_value_returned": false,
      "capabilities": {
        "provider_type": "kaiko_optional",
        "display_name": "Kaiko",
        "tier": "tier_1_optional_paid_research",
        "supports": ["normalized_crypto_derivatives", "open_interest_research"],
        "unsupported": ["execution", "private_account_data"],
        "requires_key": true,
        "requires_local_file": false,
        "is_optional": true,
        "limitations": [
          "Optional paid research source; absent key does not block MVP."
        ],
        "forbidden_reason": null
      },
      "warnings": [],
      "limitations": [],
      "missing_actions": [
        {
          "action_id": "configure-kaiko-optional",
          "workflow_type": "optional_vendor",
          "provider_type": "kaiko_optional",
          "asset": null,
          "severity": "optional",
          "title": "Configure Kaiko research key if available",
          "instructions": [
            "Set KAIKO_API_KEY in a local .env file if this paid research source is available.",
            "Do not commit .env files or secret values."
          ],
          "required_columns": [],
          "optional_columns": [],
          "blocking": false
        }
      ]
    }
  ],
  "capability_matrix": [],
  "missing_data_actions": []
}
```

## GET /api/v1/data-sources/capabilities

Returns the capability matrix only.

### Response 200

```json
{
  "capabilities": [
    {
      "provider_type": "yahoo_finance",
      "display_name": "Yahoo Finance",
      "tier": "tier_0_public_local",
      "supports": ["ohlcv_proxy"],
      "unsupported": [
        "crypto_open_interest",
        "funding",
        "gold_options_oi",
        "futures_oi",
        "implied_volatility",
        "xauusd_spot_execution"
      ],
      "requires_key": false,
      "requires_local_file": false,
      "is_optional": false,
      "limitations": [
        "Yahoo Finance is OHLCV/proxy-only for this research platform."
      ],
      "forbidden_reason": null
    }
  ]
}
```

## GET /api/v1/data-sources/missing-data

Returns default missing-data instructions for crypto, proxy, XAU, and optional vendors.

### Response 200

```json
{
  "actions": [
    {
      "action_id": "crypto-btcusdt-15m-processed-features",
      "workflow_type": "crypto_multi_asset",
      "provider_type": "binance_public",
      "asset": "BTCUSDT",
      "severity": "blocking",
      "title": "Create BTCUSDT processed features",
      "instructions": [
        "Download BTCUSDT 15m public Binance research data.",
        "Run feature processing to create processed features before evidence execution."
      ],
      "required_columns": [],
      "optional_columns": [],
      "blocking": true
    },
    {
      "action_id": "xau-local-options-schema",
      "workflow_type": "xau_vol_oi",
      "provider_type": "local_file",
      "asset": "XAU",
      "severity": "blocking",
      "title": "Provide local XAU options OI file",
      "instructions": [
        "Import a local CSV or Parquet gold options OI file.",
        "Yahoo GC=F and GLD are OHLCV proxies only and are not gold options OI sources."
      ],
      "required_columns": ["date_or_timestamp", "expiry", "strike", "option_type", "open_interest"],
      "optional_columns": [
        "oi_change",
        "volume",
        "implied_volatility",
        "underlying_futures_price",
        "xauusd_spot_price",
        "delta",
        "gamma"
      ],
      "blocking": true
    }
  ]
}
```

## POST /api/v1/data-sources/preflight

Checks whether requested sources are ready for a first evidence run. It must not download external data.

### Request

```json
{
  "crypto_assets": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "optional_crypto_assets": ["BNBUSDT"],
  "crypto_timeframe": "15m",
  "proxy_assets": ["SPY", "QQQ", "GLD", "GC=F"],
  "proxy_timeframe": "1d",
  "processed_feature_root": null,
  "xau_options_oi_file_path": "data/raw/xau/options_oi_sample.csv",
  "require_optional_vendors": ["kaiko_optional", "tardis_optional"],
  "requested_capabilities": ["ohlcv", "open_interest", "funding", "iv"],
  "research_only_acknowledged": true
}
```

### Response 200

```json
{
  "status": "partial",
  "readiness": {
    "generated_at": "2026-05-02T10:00:00Z",
    "public_sources_available": true,
    "optional_sources_missing": ["kaiko_optional", "tardis_optional"],
    "forbidden_sources_detected": [],
    "research_only_warnings": [
      "Preflight is research-only and does not run external downloads or execution."
    ],
    "provider_statuses": [],
    "capability_matrix": [],
    "missing_data_actions": []
  },
  "crypto_results": [
    {
      "asset": "BTCUSDT",
      "provider_type": "binance_public",
      "status": "ready",
      "feature_path": "data/processed/BTCUSDT_15m_features.parquet",
      "row_count": 5000,
      "missing_data_actions": [],
      "limitations": [
        "Binance public OI history can be limited."
      ]
    }
  ],
  "proxy_results": [
    {
      "asset": "GLD",
      "provider_type": "yahoo_finance",
      "status": "ready",
      "unsupported_capabilities": ["open_interest", "funding", "iv"],
      "limitations": [
        "GLD is an OHLCV proxy only and is not gold options OI, futures OI, IV, or XAUUSD execution data."
      ]
    }
  ],
  "xau_result": {
    "asset": "XAU",
    "provider_type": "local_file",
    "status": "blocked",
    "missing_data_actions": [
      {
        "action_id": "xau-local-options-schema",
        "workflow_type": "xau_vol_oi",
        "provider_type": "local_file",
        "asset": "XAU",
        "severity": "blocking",
        "title": "Provide local XAU options OI file",
        "instructions": [
          "Required columns: date or timestamp, expiry, strike, option_type, and open_interest."
        ],
        "required_columns": ["date_or_timestamp", "expiry", "strike", "option_type", "open_interest"],
        "optional_columns": [],
        "blocking": true
      }
    ]
  },
  "optional_vendor_results": [],
  "unsupported_capabilities": ["open_interest", "funding", "iv"],
  "missing_data_actions": [],
  "warnings": [],
  "limitations": [
    "Synthetic data is allowed only in tests and smoke validation, not final real research runs."
  ]
}
```

### Response 400

Returned when `research_only_acknowledged` is false, a forbidden credential category is requested, or a local path is unsafe.

## POST /api/v1/evidence/first-run

Starts the first evidence workflow after preflight. It delegates to feature 007 and does not create strategy logic.

### Request

```json
{
  "name": "First real evidence run",
  "preflight": {
    "crypto_assets": ["BTCUSDT"],
    "crypto_timeframe": "15m",
    "proxy_assets": ["SPY", "GLD"],
    "proxy_timeframe": "1d",
    "xau_options_oi_file_path": "data/raw/xau/options_oi_sample.csv",
    "research_only_acknowledged": true
  },
  "use_existing_research_report_ids": [],
  "use_existing_xau_report_id": null,
  "run_when_partial": true,
  "research_only_acknowledged": true
}
```

### Response 201

```json
{
  "first_run_id": "first_evidence_20260502_100000",
  "status": "partial",
  "execution_run_id": "research_execution_20260502_100000",
  "evidence_report_path": "data/reports/research_execution/research_execution_20260502_100000/evidence.json",
  "linked_research_report_ids": [],
  "linked_xau_report_ids": [],
  "preflight_result": {
    "status": "partial",
    "crypto_results": [],
    "proxy_results": [],
    "optional_vendor_results": [],
    "unsupported_capabilities": [],
    "missing_data_actions": [],
    "warnings": [],
    "limitations": []
  },
  "missing_data_actions": [],
  "research_only_warnings": [
    "First evidence run is research-only and is not live, paper, shadow, broker, or execution ready."
  ],
  "limitations": [
    "Optional paid provider absence is reported but does not block the public/local MVP."
  ],
  "created_at": "2026-05-02T10:00:00Z"
}
```

### Response 400

Returned for invalid config, unsafe local paths, or missing acknowledgement.

## GET /api/v1/evidence/first-run/{run_id}

Reads a persisted first-run wrapper result or linked feature 007 evidence reference.

### Response 200

Same shape as `FirstEvidenceRunResult`.

### Response 404

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "First evidence run not found: first_evidence_missing",
    "details": []
  }
}
```

## Security And Scope Requirements

- API responses must never include secret values, partial values, hashes, request-provided key values, or env var values.
- Optional provider key status must be `configured` or `missing` only.
- The API must not expose endpoints for live trading, paper trading, broker integration, real order execution, or private wallet/key handling.
- Yahoo Finance must always remain OHLCV/proxy-only in response labels.
- Generated data and report paths are local references under ignored directories and are not committed.
