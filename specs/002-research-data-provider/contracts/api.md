# API Contracts: Research Data Provider Layer

**Date**: 2026-04-26  
**Feature**: 002-research-data-provider

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research provider endpoints.

## Endpoints

### 1. List Providers

Returns capability metadata for all registered providers.

**Endpoint**: `GET /api/v1/providers`

**Response** (200 OK):

```json
{
  "providers": [
    {
      "provider": "binance",
      "display_name": "Binance USD-M Futures",
      "supports_ohlcv": true,
      "supports_open_interest": true,
      "supports_funding_rate": true,
      "requires_auth": false,
      "supported_timeframes": ["15m"],
      "default_symbol": "BTCUSDT",
      "limitations": [
        "Uses public Binance USD-M Futures market data only",
        "Binance official OI is acceptable for v0 prototype research but not enough for serious multi-year OI research"
      ]
    },
    {
      "provider": "yahoo_finance",
      "display_name": "Yahoo Finance",
      "supports_ohlcv": true,
      "supports_open_interest": false,
      "supports_funding_rate": false,
      "requires_auth": false,
      "supported_timeframes": ["1d", "1h"],
      "default_symbol": "SPY",
      "limitations": [
        "OHLCV-only research source",
        "Not a source for crypto open interest or funding"
      ]
    },
    {
      "provider": "local_file",
      "display_name": "Local File",
      "supports_ohlcv": true,
      "supports_open_interest": true,
      "supports_funding_rate": true,
      "requires_auth": false,
      "supported_timeframes": ["15m", "1h", "1d"],
      "default_symbol": null,
      "limitations": [
        "Capabilities depend on validated CSV or Parquet columns"
      ]
    }
  ]
}
```



### 2. Get Provider Details

Returns metadata for a single provider.

**Endpoint**: `GET /api/v1/providers/{provider_name}`

**Response** (200 OK):

```json
{
  "provider": "yahoo_finance",
  "display_name": "Yahoo Finance",
  "supports_ohlcv": true,
  "supports_open_interest": false,
  "supports_funding_rate": false,
  "requires_auth": false,
  "supported_timeframes": ["1d", "1h"],
  "default_symbol": "SPY",
  "limitations": [
    "OHLCV-only research source",
    "Not a source for crypto open interest or funding"
  ],
  "capabilities": [
    {
      "data_type": "ohlcv",
      "supported": true,
      "unsupported_reason": null
    },
    {
      "data_type": "open_interest",
      "supported": false,
      "unsupported_reason": "Yahoo Finance does not provide open interest for this research layer"
    },
    {
      "data_type": "funding_rate",
      "supported": false,
      "unsupported_reason": "Yahoo Finance does not provide funding rates"
    }
  ]
}
```

**Error Responses**:

- 404 Not Found: Unknown provider

```json
{
  "error": {
    "code": "PROVIDER_NOT_FOUND",
    "message": "Provider 'unknown' is not registered",
    "details": []
  }
}
```

### 3. Get Provider Symbols

Returns supported symbols for a provider.

**Endpoint**: `GET /api/v1/providers/{provider_name}/symbols`

**Response** (200 OK):

```json
{
  "provider": "yahoo_finance",
  "symbols": [
    {
      "symbol": "SPY",
      "display_name": "SPDR S&P 500 ETF Trust",
      "asset_class": "ETF",
      "supports_ohlcv": true,
      "supports_open_interest": false,
      "supports_funding_rate": false,
      "notes": ["OHLCV-only baseline research symbol"]
    },
    {
      "symbol": "GC=F",
      "display_name": "Gold Futures Proxy",
      "asset_class": "futures_proxy",
      "supports_ohlcv": true,
      "supports_open_interest": false,
      "supports_funding_rate": false,
      "notes": ["Yahoo Finance futures proxy OHLCV only"]
    }
  ]
}
```

### 4. Provider-Aware Download

Downloads or validates/imports research data through a selected provider.

**Endpoint**: `POST /api/v1/data/download`

**Request Body - Binance default flow**:

```json
{
  "provider": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "days": 30,
  "data_types": ["ohlcv", "open_interest", "funding_rate"]
}
```

**Response** (202 Accepted or 200 OK when synchronous):

```json
{
  "status": "completed",
  "provider": "binance",
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "completed_data_types": ["ohlcv", "open_interest", "funding_rate"],
  "skipped_data_types": [],
  "artifacts": [
    {
      "data_type": "ohlcv",
      "path": "data/raw/btcusdt_15m_ohlcv.parquet",
      "rows": 2880,
      "provider": "binance",
      "symbol": "BTCUSDT",
      "timeframe": "15m",
      "first_timestamp": "2026-03-27T00:00:00Z",
      "last_timestamp": "2026-04-26T00:00:00Z"
    }
  ],
  "message": "Downloaded Binance research data",
  "warnings": []
}
```

**Request Body - Yahoo Finance OHLCV**:

```json
{
  "provider": "yahoo_finance",
  "symbol": "SPY",
  "timeframe": "1d",
  "days": 365,
  "data_types": ["ohlcv"]
}
```

**Request Body - Yahoo Finance unsupported capability**:

```json
{
  "provider": "yahoo_finance",
  "symbol": "SPY",
  "timeframe": "1d",
  "days": 365,
  "data_types": ["ohlcv", "open_interest", "funding_rate"]
}
```

**Response** (200 OK, partial with skipped unsupported capabilities):

```json
{
  "status": "partial",
  "provider": "yahoo_finance",
  "symbol": "SPY",
  "timeframe": "1d",
  "completed_data_types": ["ohlcv"],
  "skipped_data_types": [
    {
      "provider": "yahoo_finance",
      "data_type": "open_interest",
      "reason": "Yahoo Finance does not provide open interest for this research layer"
    },
    {
      "provider": "yahoo_finance",
      "data_type": "funding_rate",
      "reason": "Yahoo Finance does not provide funding rates"
    }
  ],
  "artifacts": [
    {
      "data_type": "ohlcv",
      "path": "data/raw/yahoo_finance_spy_1d_ohlcv.parquet",
      "rows": 252,
      "provider": "yahoo_finance",
      "symbol": "SPY",
      "timeframe": "1d",
      "first_timestamp": "2025-04-28T00:00:00Z",
      "last_timestamp": "2026-04-24T00:00:00Z"
    }
  ],
  "message": "Downloaded supported Yahoo Finance data; skipped unsupported capabilities",
  "warnings": []
}
```

**Request Body - Local file validation/import**:

```json
{
  "provider": "local_file",
  "symbol": "SAMPLE",
  "timeframe": "1d",
  "local_file_path": "data/imports/sample_ohlcv.csv",
  "data_types": ["ohlcv"]
}
```

**Local validation failure response** (400 Bad Request):

```json
{
  "error": {
    "code": "LOCAL_FILE_VALIDATION_FAILED",
    "message": "Local file is not valid OHLCV research data",
    "details": [
      {
        "field": "timestamp",
        "message": "Duplicate timestamps found: 2"
      },
      {
        "field": "close",
        "message": "Missing required values: 1"
      }
    ]
  }
}
```

### 5. Backward-Compatible Binance Download

Existing endpoint remains available and delegates internally to the provider-aware downloader.

**Endpoint**: `POST /api/v1/download`

**Request Body**:

```json
{
  "symbol": "BTCUSDT",
  "interval": "15m",
  "days": 30
}
```

**Response**: Existing response shape remains compatible with current frontend/tests.

```json
{
  "status": "completed",
  "task_id": "download_20260426_123456",
  "message": "Downloaded 30 days of BTCUSDT 15m data"
}
```

## Common Error Responses

### Unsupported Capability

Used when a request asks a provider for a data type that provider does not support and no partial download is appropriate.

```json
{
  "error": {
    "code": "UNSUPPORTED_CAPABILITY",
    "message": "Provider 'yahoo_finance' does not support funding_rate",
    "details": [
      {
        "provider": "yahoo_finance",
        "data_type": "funding_rate",
        "reason": "Yahoo Finance does not provide funding rates"
      }
    ]
  }
}
```

### Invalid Symbol or Timeframe

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Symbol 'ABC' is not supported by provider 'binance'",
    "details": []
  }
}
```

### Provider Upstream Failure

```json
{
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "Provider 'binance' is temporarily unavailable or rate-limited",
    "details": []
  }
}
```

