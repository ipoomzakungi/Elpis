# API Contracts: OI Regime Lab v0

**Date**: 2026-04-26
**Feature**: 001-oi-regime-lab

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

No authentication required for v0 (local research tool).

## Endpoints

### 1. Download Data

Initiates data download from Binance Futures.

**Endpoint**: `POST /api/v1/download`

**Request Body**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "15m",
  "days": 30
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |
| days | integer | No | 30 | Days of history to download |

**Response** (202 Accepted):
```json
{
  "status": "started",
  "task_id": "download_20260426_123456",
  "message": "Data download started"
}
```

**Error Responses**:
- 400 Bad Request: Invalid parameters
- 429 Too Many Requests: Rate limited by Binance
- 500 Internal Server Error: Download failed

---

### 2. Process Data

Triggers feature computation and regime classification.

**Endpoint**: `POST /api/v1/process`

**Request Body**:
```json
{
  "symbol": "BTCUSDT",
  "interval": "15m"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |

**Response** (202 Accepted):
```json
{
  "status": "started",
  "task_id": "process_20260426_123456",
  "message": "Data processing started"
}
```

**Error Responses**:
- 400 Bad Request: Invalid parameters
- 404 Not Found: No raw data found
- 500 Internal Server Error: Processing failed

---

### 3. Get OHLCV Data

Returns candlestick data.

**Endpoint**: `GET /api/v1/market-data/ohlcv`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |
| start_time | datetime | No | 7 days ago | Start time (ISO 8601) |
| end_time | datetime | No | now | End time (ISO 8601) |
| limit | integer | No | 1000 | Max records (1-5000) |

**Response** (200 OK):
```json
{
  "data": [
    {
      "timestamp": "2026-04-26T00:00:00Z",
      "open": 65000.50,
      "high": 65100.00,
      "low": 64900.25,
      "close": 65050.75,
      "volume": 1234.567,
      "quote_volume": 80234567.89,
      "trades": 5678,
      "taker_buy_volume": 617.283
    }
  ],
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "count": 1,
    "start_time": "2026-04-19T00:00:00Z",
    "end_time": "2026-04-26T00:00:00Z"
  }
}
```

---

### 4. Get Open Interest Data

Returns open interest data.

**Endpoint**: `GET /api/v1/market-data/open-interest`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |
| start_time | datetime | No | 7 days ago | Start time (ISO 8601) |
| end_time | datetime | No | now | End time (ISO 8601) |
| limit | integer | No | 1000 | Max records (1-5000) |

**Response** (200 OK):
```json
{
  "data": [
    {
      "timestamp": "2026-04-26T00:00:00Z",
      "symbol": "BTCUSDT",
      "open_interest": 12345.678,
      "open_interest_value": 802345678.90
    }
  ],
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "count": 1
  }
}
```

---

### 5. Get Funding Rate Data

Returns funding rate data.

**Endpoint**: `GET /api/v1/market-data/funding-rate`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| start_time | datetime | No | 7 days ago | Start time (ISO 8601) |
| end_time | datetime | No | now | End time (ISO 8601) |
| limit | integer | No | 1000 | Max records (1-5000) |

**Response** (200 OK):
```json
{
  "data": [
    {
      "timestamp": "2026-04-26T00:00:00Z",
      "symbol": "BTCUSDT",
      "funding_rate": 0.00010000,
      "mark_price": 65000.50
    }
  ],
  "meta": {
    "symbol": "BTCUSDT",
    "count": 1
  }
}
```

---

### 6. Get Features

Returns computed features.

**Endpoint**: `GET /api/v1/features`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |
| start_time | datetime | No | 7 days ago | Start time (ISO 8601) |
| end_time | datetime | No | now | End time (ISO 8601) |
| limit | integer | No | 1000 | Max records (1-5000) |

**Response** (200 OK):
```json
{
  "data": [
    {
      "timestamp": "2026-04-26T00:00:00Z",
      "open": 65000.50,
      "high": 65100.00,
      "low": 64900.25,
      "close": 65050.75,
      "volume": 1234.567,
      "atr": 150.25,
      "range_high": 65200.00,
      "range_low": 64800.00,
      "range_mid": 65000.00,
      "open_interest": 12345.678,
      "oi_change_pct": 2.5,
      "volume_ratio": 1.35,
      "funding_rate": 0.00010000,
      "funding_rate_change": 0.00005000,
      "funding_rate_cumsum": 0.00350000
    }
  ],
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "count": 1
  }
}
```

---

### 7. Get Regimes

Returns regime classifications.

**Endpoint**: `GET /api/v1/regimes`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |
| interval | string | No | "15m" | Timeframe |
| start_time | datetime | No | 7 days ago | Start time (ISO 8601) |
| end_time | datetime | No | now | End time (ISO 8601) |
| regime | string | No | all | Filter by regime type |
| limit | integer | No | 1000 | Max records (1-5000) |

**Response** (200 OK):
```json
{
  "data": [
    {
      "timestamp": "2026-04-26T00:00:00Z",
      "regime": "RANGE",
      "confidence": 0.85,
      "reason": "Price near range mid, low OI change, normal volume"
    }
  ],
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "15m",
    "count": 1,
    "regime_counts": {
      "RANGE": 500,
      "BREAKOUT_UP": 50,
      "BREAKOUT_DOWN": 45,
      "AVOID": 405
    }
  }
}
```

---

### 8. Get Data Quality

Returns data quality metrics.

**Endpoint**: `GET /api/v1/data-quality`

**Query Parameters**:
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| symbol | string | No | "BTCUSDT" | Trading pair |

**Response** (200 OK):
```json
{
  "ohlcv": {
    "data_type": "ohlcv",
    "total_records": 2880,
    "missing_timestamps": 5,
    "duplicate_timestamps": 0,
    "first_timestamp": "2026-03-27T00:00:00Z",
    "last_timestamp": "2026-04-26T00:00:00Z",
    "last_updated": "2026-04-26T12:30:00Z"
  },
  "open_interest": {
    "data_type": "open_interest",
    "total_records": 2875,
    "missing_timestamps": 10,
    "duplicate_timestamps": 0,
    "first_timestamp": "2026-03-27T00:00:00Z",
    "last_timestamp": "2026-04-26T00:00:00Z",
    "last_updated": "2026-04-26T12:30:00Z"
  },
  "funding_rate": {
    "data_type": "funding_rate",
    "total_records": 90,
    "missing_timestamps": 0,
    "duplicate_timestamps": 0,
    "first_timestamp": "2026-03-27T00:00:00Z",
    "last_timestamp": "2026-04-26T00:00:00Z",
    "last_updated": "2026-04-26T12:30:00Z"
  }
}
```

---

## Error Response Format

All error responses follow this format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": [
      {
        "field": "days",
        "message": "Must be between 1 and 365"
      }
    ]
  }
}
```

**Error Codes**:
| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_ERROR | 400 | Invalid request parameters |
| NOT_FOUND | 404 | Resource not found |
| RATE_LIMITED | 429 | Too many requests |
| INTERNAL_ERROR | 500 | Server error |
| DOWNLOAD_FAILED | 500 | Data download failed |
| PROCESSING_FAILED | 500 | Data processing failed |

---

## Rate Limits

- No rate limits for v0 (local research tool)
- Binance API rate limits apply (1200 requests/minute)

## Pagination

- Use `limit` and `offset` query parameters
- Default limit: 1000 records
- Maximum limit: 5000 records
- Use `start_time` and `end_time` for time-based filtering

## Data Format

- All timestamps in ISO 8601 format (UTC)
- All prices in USDT
- All volumes in base asset (BTC)
- All rates as decimals (0.0001 = 0.01%)
