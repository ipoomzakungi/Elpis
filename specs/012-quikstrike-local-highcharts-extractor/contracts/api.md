# API Contracts: QuikStrike Local Highcharts Extractor

**Date**: 2026-05-13
**Feature**: 012-quikstrike-local-highcharts-extractor

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication And Privacy

No authentication is required for v0 local research endpoints. These endpoints must not accept or return cookies, tokens, authorization headers, browser profile paths, viewstate values, HAR content, screenshots, private full URLs, credentials, account/order/wallet values, broker fields, or paid-vendor secrets.

These routes operate on sanitized DOM and Highcharts payloads or saved local extraction reports only. They do not log into QuikStrike, replay ASP.NET postbacks, bypass access controls, or initiate live/paper/shadow trading.

## Endpoints

### 1. Create QuikStrike Extraction From Sanitized Payload

Creates a local research extraction report from sanitized DOM metadata and sanitized Highcharts chart objects.

**Endpoint**: `POST /api/v1/quikstrike/extractions`

**Request Body**:

```json
{
  "requested_views": [
    "intraday_volume",
    "eod_volume",
    "open_interest",
    "oi_change",
    "churn"
  ],
  "dom_metadata_by_view": {
    "open_interest": {
      "product": "Gold",
      "option_product_code": "OG|GC",
      "futures_symbol": "GC",
      "expiration": "2026-05-15",
      "dte": 2.59,
      "future_reference_price": 4722.6,
      "source_view": "QUIKOPTIONS VOL2VOL",
      "selected_view_type": "open_interest",
      "surface": "QUIKOPTIONS VOL2VOL",
      "raw_header_text": "Gold (OG|GC) OG3K6 (2.59 DTE) vs 4722.6 - Open Interest",
      "raw_selector_text": "Metals Precious Metals Gold (OG|GC) OG3K6 15 May 2026",
      "warnings": [],
      "limitations": [
        "Local user-controlled QuikStrike browser extraction only."
      ]
    }
  },
  "highcharts_by_view": {
    "open_interest": {
      "chart_title": "OG3K6 Open Interest",
      "view_type": "open_interest",
      "series": [
        {
          "series_name": "Put",
          "series_type": "put",
          "point_count": 2,
          "points": [
            {
              "series_type": "put",
              "x": 4700,
              "y": 120,
              "name": "4700",
              "category": "4700",
              "strike_id": "strike-4700",
              "range_label": null,
              "sigma_label": null,
              "metadata_keys": ["StrikeId"]
            }
          ],
          "warnings": [],
          "limitations": []
        },
        {
          "series_name": "Call",
          "series_type": "call",
          "point_count": 2,
          "points": [
            {
              "series_type": "call",
              "x": 4700,
              "y": 95,
              "name": "4700",
              "category": "4700",
              "strike_id": "strike-4700",
              "range_label": null,
              "sigma_label": null,
              "metadata_keys": ["StrikeId"]
            }
          ],
          "warnings": [],
          "limitations": []
        }
      ],
      "chart_warnings": [],
      "chart_limitations": []
    }
  },
  "run_label": "fixture-smoke",
  "report_format": "both",
  "research_only_acknowledged": true
}
```

**Response** (201 Created):

```json
{
  "extraction_id": "quikstrike_20260513_120000",
  "status": "completed",
  "created_at": "2026-05-13T12:00:00Z",
  "completed_at": "2026-05-13T12:00:01Z",
  "requested_views": ["open_interest"],
  "completed_views": ["open_interest"],
  "partial_views": [],
  "missing_views": [],
  "row_count": 4,
  "put_row_count": 2,
  "call_row_count": 2,
  "strike_mapping": {
    "confidence": "high",
    "method": "x_name_category_strike_id_match",
    "matched_point_count": 4,
    "unmatched_point_count": 0,
    "conflict_count": 0,
    "evidence": ["x/name/category alignment", "StrikeId present"],
    "warnings": [],
    "limitations": []
  },
  "conversion_eligible": true,
  "artifacts": [
    {
      "artifact_type": "raw_normalized_rows_parquet",
      "path": "data/raw/quikstrike/quikstrike_20260513_120000_normalized_rows.parquet",
      "format": "parquet",
      "rows": 4,
      "created_at": "2026-05-13T12:00:01Z",
      "limitations": [
        "Local user-controlled QuikStrike browser extraction only."
      ]
    }
  ],
  "warnings": [],
  "limitations": [
    "QuikStrike extraction is local-only and research-only.",
    "This is not a CME API integration and does not bypass authentication."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, wallet handling, order execution, or strategy signal is included."
  ]
}
```

### 2. List Saved Extractions

**Endpoint**: `GET /api/v1/quikstrike/extractions`

**Response** (200 OK):

```json
{
  "extractions": [
    {
      "extraction_id": "quikstrike_20260513_120000",
      "status": "completed",
      "created_at": "2026-05-13T12:00:00Z",
      "completed_at": "2026-05-13T12:00:01Z",
      "requested_view_count": 5,
      "completed_view_count": 5,
      "missing_view_count": 0,
      "row_count": 640,
      "strike_mapping_confidence": "high",
      "conversion_eligible": true,
      "warning_count": 0,
      "limitation_count": 2
    }
  ]
}
```

### 3. Get Extraction Detail

**Endpoint**: `GET /api/v1/quikstrike/extractions/{extraction_id}`

Returns saved extraction metadata, view summaries, warnings, limitations, research-only text, artifact paths, strike mapping confidence, and conversion eligibility.

### 4. Get Normalized Rows

**Endpoint**: `GET /api/v1/quikstrike/extractions/{extraction_id}/rows`

**Response** (200 OK):

```json
{
  "extraction_id": "quikstrike_20260513_120000",
  "rows": [
    {
      "row_id": "quikstrike_20260513_120000:open_interest:4700:put",
      "capture_timestamp": "2026-05-13T12:00:00Z",
      "product": "Gold",
      "option_product_code": "OG|GC",
      "futures_symbol": "GC",
      "expiration": "2026-05-15",
      "dte": 2.59,
      "future_reference_price": 4722.6,
      "view_type": "open_interest",
      "strike": 4700,
      "strike_id": "strike-4700",
      "option_type": "put",
      "value": 120,
      "value_type": "open_interest",
      "vol_settle": 26.7,
      "range_label": null,
      "sigma_label": null,
      "source_view": "QUIKOPTIONS VOL2VOL",
      "strike_mapping_confidence": "high",
      "extraction_warnings": [],
      "extraction_limitations": [
        "Local user-controlled QuikStrike browser extraction only."
      ]
    }
  ]
}
```

### 5. Convert Extraction To XAU Vol-OI Input

**Endpoint**: `POST /api/v1/quikstrike/extractions/{extraction_id}/convert-xau-vol-oi`

**Response** (200 OK):

```json
{
  "conversion_id": "quikstrike_20260513_120000_xau_vol_oi",
  "extraction_id": "quikstrike_20260513_120000",
  "status": "completed",
  "row_count": 256,
  "output_artifacts": [
    {
      "artifact_type": "processed_xau_vol_oi_parquet",
      "path": "data/processed/quikstrike/quikstrike_20260513_120000_xau_vol_oi_input.parquet",
      "format": "parquet",
      "rows": 256,
      "created_at": "2026-05-13T12:00:02Z",
      "limitations": [
        "Converted from local QuikStrike chart extraction; source limitations preserved."
      ]
    }
  ],
  "blocked_reasons": [],
  "warnings": [],
  "limitations": [
    "Conversion prepares local XAU Vol-OI input only and does not run wall scoring."
  ]
}
```

## Common Error Responses

### Missing Extraction

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "QuikStrike extraction 'unknown' was not found",
    "details": []
  }
}
```

### Invalid Or Secret-Bearing Request

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "QuikStrike extraction request is invalid",
    "details": [
      {
        "field": "research_only_acknowledged",
        "message": "research_only_acknowledged must be true"
      },
      {
        "field": "payload",
        "message": "Request must not include cookies, tokens, headers, viewstate, HAR, screenshots, credentials, or private full URLs."
      }
    ]
  }
}
```

### Conversion Blocked

```json
{
  "error": {
    "code": "CONVERSION_BLOCKED",
    "message": "QuikStrike extraction is not eligible for XAU Vol-OI conversion",
    "details": [
      {
        "field": "strike_mapping",
        "message": "Strike mapping confidence is partial."
      }
    ]
  }
}
```

## Contract Rules

- Endpoints must not accept or expose cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, account/order/wallet fields, broker fields, private endpoint content, or private full URLs.
- Endpoints must not log into QuikStrike or replay ASP.NET POSTs.
- Responses must include local-only and research-only limitations.
- Conversion must be blocked unless strike mapping confidence is high and required fields are present.
- Generated paths must point under ignored `data/raw/quikstrike/`, `data/processed/quikstrike/`, or `data/reports/quikstrike/`.
- Responses must not include live trading, paper trading, shadow trading, broker integration, real execution, wallet/private-key handling, profitability claims, predictive claims, safety claims, or live-readiness claims.
