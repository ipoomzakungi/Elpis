# API Contracts: XAU Forward Journal Outcome Price Updater

**Date**: 2026-05-14
**Feature**: 016-xau-forward-journal-outcome-price-updater

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication And Privacy

No authentication is required for v0 local research endpoints. These endpoints operate on saved local journal entries and approved local/public OHLC research outputs.

Endpoints must not accept or return cookies, tokens, authorization headers, browser profile paths, viewstate values, HAR content, screenshots, private full URLs, credentials, account/order/wallet values, broker fields, private endpoint content, endpoint replay payloads, paid-vendor secrets, or execution instructions.

These routes do not log into QuikStrike, attach to browsers, replay ASP.NET requests, bypass authentication, initiate extraction, initiate live/paper/shadow trading, or claim profitability, predictive power, safety, or live readiness.

## Endpoints

### 1. Update Outcomes From Price Data

Updates outcome windows for a saved XAU Forward Journal entry from local/public OHLC candle data.

**Endpoint**: `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data`

**Request Body**:

```json
{
  "source_label": "yahoo_gc_f_proxy",
  "source_symbol": "GC=F",
  "ohlc_path": "data/raw/yahoo/gc=f_1d_ohlcv.parquet",
  "timestamp_column": "timestamp",
  "open_column": "open",
  "high_column": "high",
  "low_column": "low",
  "close_column": "close",
  "timezone": "UTC",
  "update_note": "Attach synthetic OHLC validation outcomes.",
  "persist_report": true,
  "research_only_acknowledged": true
}
```

**Response** (200 OK):

```json
{
  "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
  "update_report": {
    "update_id": "price_update_20260514_040000",
    "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
    "created_at": "2026-05-14T04:00:00Z",
    "source": {
      "source_label": "yahoo_gc_f_proxy",
      "source_symbol": "GC=F",
      "source_path": "data/raw/yahoo/gc=f_1d_ohlcv.parquet",
      "format": "parquet",
      "row_count": 12,
      "first_timestamp": "2026-05-14T03:08:04Z",
      "last_timestamp": "2026-05-15T03:08:04Z",
      "warnings": [],
      "limitations": [
        "Yahoo GC=F is a futures proxy OHLCV source and is not true XAUUSD spot."
      ]
    },
    "missing_candle_checklist": [
      {
        "window": "session_close",
        "required_start": "2026-05-14T03:08:04Z",
        "required_end": "2026-05-14T21:00:00Z",
        "status": "partial",
        "message": "Candles overlap the window but do not fully cover the required interval.",
        "action": "Import or generate candles that cover the full session_close window."
      }
    ],
    "proxy_limitations": [
      "Yahoo GC=F is a futures proxy OHLCV source and is not true XAUUSD spot."
    ]
  },
  "coverage": {
    "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
    "snapshot_time": "2026-05-14T03:08:04Z",
    "complete_windows": ["30m", "1h", "4h"],
    "partial_windows": ["session_close"],
    "missing_windows": ["next_day"],
    "windows": [
      {
        "window": "30m",
        "status": "complete",
        "required_start": "2026-05-14T03:08:04Z",
        "required_end": "2026-05-14T03:38:04Z",
        "observed_start": "2026-05-14T03:08:04Z",
        "observed_end": "2026-05-14T03:38:04Z",
        "candle_count": 31,
        "gap_count": 0,
        "missing_reason": null,
        "partial_reason": null,
        "source_label": "yahoo_gc_f_proxy",
        "source_symbol": "GC=F",
        "limitations": []
      }
    ]
  },
  "outcomes": [
    {
      "window": "30m",
      "status": "completed",
      "label": "stayed_inside_range",
      "observation_start": "2026-05-14T03:08:04Z",
      "observation_end": "2026-05-14T03:38:04Z",
      "open": 4707.2,
      "high": 4712.0,
      "low": 4701.5,
      "close": 4706.0,
      "range": 10.5,
      "direction": "down_from_snapshot",
      "price_source_label": "yahoo_gc_f_proxy",
      "price_source_symbol": "GC=F",
      "coverage_status": "complete",
      "coverage_reason": null,
      "price_update_id": "price_update_20260514_040000",
      "notes": [
        {
          "text": "Outcome metrics were computed from local research OHLC candles.",
          "source": "price_update"
        }
      ],
      "limitations": [
        "Outcome labels are forward research annotations only."
      ],
      "updated_at": "2026-05-14T04:00:00Z"
    }
  ],
  "artifacts": [
    {
      "artifact_type": "price_update_report_json",
      "path": "data/reports/xau_forward_journal/xau_forward_journal_20260514_030804_quikstrike-gold-am-session/price_updates/price_update_20260514_040000_report.json",
      "format": "json",
      "rows": 1
    }
  ],
  "warnings": [],
  "limitations": [
    "Outcome updates are local-only forward research annotations."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, order execution, strategy signal, profitability claim, predictive claim, safety claim, or live-readiness claim is included."
  ]
}
```

### 2. Get Price Coverage

Returns per-window candle coverage for a saved XAU Forward Journal entry without mutating outcomes.

**Endpoint**: `GET /api/v1/xau/forward-journal/entries/{journal_id}/price-coverage`

**Query Parameters**:

```text
source_label=yahoo_gc_f_proxy
source_symbol=GC%3DF
ohlc_path=data/raw/yahoo/gc=f_1d_ohlcv.parquet
timestamp_column=timestamp
open_column=open
high_column=high
low_column=low
close_column=close
timezone=UTC
research_only_acknowledged=true
```

**Response** (200 OK):

```json
{
  "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
  "coverage": {
    "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
    "snapshot_time": "2026-05-14T03:08:04Z",
    "source": {
      "source_label": "yahoo_gc_f_proxy",
      "source_symbol": "GC=F",
      "source_path": "data/raw/yahoo/gc=f_1d_ohlcv.parquet",
      "format": "parquet",
      "row_count": 12,
      "first_timestamp": "2026-05-14T03:08:04Z",
      "last_timestamp": "2026-05-15T03:08:04Z",
      "warnings": [],
      "limitations": [
        "Yahoo GC=F is a futures proxy OHLCV source and is not true XAUUSD spot."
      ]
    },
    "windows": [
      {
        "window": "30m",
        "status": "complete",
        "required_start": "2026-05-14T03:08:04Z",
        "required_end": "2026-05-14T03:38:04Z",
        "observed_start": "2026-05-14T03:08:04Z",
        "observed_end": "2026-05-14T03:38:04Z",
        "candle_count": 31,
        "gap_count": 0,
        "missing_reason": null,
        "partial_reason": null,
        "source_label": "yahoo_gc_f_proxy",
        "source_symbol": "GC=F",
        "limitations": []
      },
      {
        "window": "next_day",
        "status": "missing",
        "required_start": "2026-05-14T03:08:04Z",
        "required_end": "2026-05-15T03:08:04Z",
        "observed_start": null,
        "observed_end": null,
        "candle_count": 0,
        "gap_count": 0,
        "missing_reason": "No usable candles overlap the required next_day window.",
        "partial_reason": null,
        "source_label": "yahoo_gc_f_proxy",
        "source_symbol": "GC=F",
        "limitations": []
      }
    ],
    "complete_windows": ["30m", "1h", "4h"],
    "partial_windows": ["session_close"],
    "missing_windows": ["next_day"],
    "missing_candle_checklist": [
      {
        "window": "next_day",
        "required_start": "2026-05-14T03:08:04Z",
        "required_end": "2026-05-15T03:08:04Z",
        "status": "missing",
        "message": "No usable candles overlap the required next_day window.",
        "action": "Import or generate candles that cover the next_day window."
      }
    ],
    "proxy_limitations": [
      "Yahoo GC=F is a futures proxy OHLCV source and is not true XAUUSD spot."
    ],
    "warnings": [],
    "limitations": [
      "Coverage status is a data availability check, not a trading signal."
    ],
    "research_only_warnings": [
      "Price coverage is local-only research metadata."
    ]
  },
  "warnings": [],
  "limitations": [
    "Coverage checks do not update journal outcomes."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, order execution, strategy signal, profitability claim, predictive claim, safety claim, or live-readiness claim is included."
  ]
}
```

## Common Error Responses

### Missing Journal Entry

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "XAU forward journal entry 'unknown' was not found",
    "details": [
      {
        "field": "journal_id",
        "message": "unknown"
      }
    ]
  }
}
```

### Invalid Price Source

```json
{
  "error": {
    "code": "INVALID_PRICE_SOURCE",
    "message": "Price data source is invalid",
    "details": [
      {
        "field": "source_label",
        "message": "Unsupported price source label"
      }
    ]
  }
}
```

### Missing OHLC File

```json
{
  "error": {
    "code": "PRICE_DATA_NOT_FOUND",
    "message": "OHLC price data file was not found",
    "details": [
      {
        "field": "ohlc_path",
        "message": "data/raw/yahoo/gc=f_1d_ohlcv.parquet"
      }
    ]
  }
}
```

### Invalid OHLC Schema

```json
{
  "error": {
    "code": "INVALID_OHLC_SCHEMA",
    "message": "OHLC candle data is invalid",
    "details": [
      {
        "field": "high",
        "message": "High must be greater than or equal to open, low, and close"
      }
    ]
  }
}
```

### Conflicting Outcome Update

```json
{
  "error": {
    "code": "OUTCOME_CONFLICT",
    "message": "Existing non-pending outcome label requires an explicit update note",
    "details": [
      {
        "field": "update_note",
        "message": "Provide an update note explaining why the price-derived outcome changed"
      }
    ]
  }
}
```

### Secret Or Execution Material

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "XAU forward journal price update request is invalid",
    "details": [
      {
        "field": "payload",
        "message": "Request must not include cookies, tokens, headers, viewstate, HAR, screenshots, credentials, private full URLs, endpoint replay fields, broker fields, wallet fields, order fields, execution fields, paid-vendor secrets, or unsupported performance claims."
      }
    ]
  }
}
```

## Contract Rules

- Responses must include local-only and research-only limitations.
- Every response must include one required price source label.
- Proxy source labels must include proxy limitation notes.
- Coverage responses must include all five required windows.
- Outcome updates must not mutate original snapshot observations, source reports, walls, reactions, missing context, or original notes.
- Missing candles must leave outcome windows pending.
- Partial candles must mark outcome windows inconclusive.
- Generated paths must point under ignored local `data/reports/xau_forward_journal/` artifact roots.
- Endpoints must not accept or expose session material, endpoint replay material, credentials, private URLs, execution fields, paid-vendor secrets, or unsupported strategy claims.
