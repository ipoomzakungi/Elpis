# API Contracts: QuikStrike Open Interest Matrix Extractor

**Date**: 2026-05-13
**Feature**: 013-quikstrike-open-interest-matrix-extractor

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication And Privacy

No authentication is required for v0 local research endpoints. These endpoints must not accept or return cookies, tokens, authorization headers, browser profile paths, viewstate values, HAR content, screenshots, private full URLs, credentials, account/order/wallet values, broker fields, or paid-vendor secrets.

These routes operate on sanitized metadata/table payloads or saved local extraction reports only. They do not log into QuikStrike, replay endpoint requests, bypass access controls, or initiate live/paper/shadow trading.

## Endpoints

### 1. Create Matrix Extraction From Sanitized Payload

Creates a local research extraction report from sanitized visible metadata and sanitized HTML table snapshots.

**Endpoint**: `POST /api/v1/quikstrike-matrix/extractions/from-fixture`

**Request Body**:

```json
{
  "requested_views": [
    "open_interest_matrix",
    "oi_change_matrix",
    "volume_matrix"
  ],
  "metadata_by_view": {
    "open_interest_matrix": {
      "capture_timestamp": "2026-05-13T12:00:00Z",
      "product": "Gold",
      "option_product_code": "OG|GC",
      "futures_symbol": "GC",
      "source_menu": "OPEN INTEREST Matrix",
      "selected_view_type": "open_interest_matrix",
      "selected_view_label": "OI Matrix",
      "table_title": "Gold Open Interest Matrix",
      "raw_visible_text": "Gold (OG|GC) OPEN INTEREST OI Matrix",
      "warnings": [],
      "limitations": [
        "Local user-controlled QuikStrike table extraction only."
      ]
    }
  },
  "tables_by_view": {
    "open_interest_matrix": {
      "view_type": "open_interest_matrix",
      "caption": "Gold OI Matrix",
      "html_table": "<table><thead><tr><th>Strike</th><th colspan=\"2\">G2RK6 2 DTE</th></tr><tr><th></th><th>Call</th><th>Put</th></tr></thead><tbody><tr><th>4700</th><td>120</td><td>95</td></tr></tbody></table>",
      "header_rows": [],
      "body_rows": [],
      "metadata": {},
      "warnings": [],
      "limitations": []
    }
  },
  "run_label": "fixture-smoke",
  "persist_report": true,
  "research_only_acknowledged": true
}
```

**Response** (201 Created):

```json
{
  "extraction_id": "quikstrike_matrix_20260513_120000",
  "status": "completed",
  "created_at": "2026-05-13T12:00:00Z",
  "completed_at": "2026-05-13T12:00:01Z",
  "requested_views": [
    "open_interest_matrix"
  ],
  "completed_views": [
    "open_interest_matrix"
  ],
  "partial_views": [],
  "missing_views": [],
  "row_count": 2,
  "strike_count": 1,
  "expiration_count": 1,
  "unavailable_cell_count": 0,
  "mapping": {
    "status": "valid",
    "table_present": true,
    "strike_rows_found": 1,
    "expiration_columns_found": 1,
    "option_side_mapping": "call_put",
    "numeric_cell_count": 2,
    "unavailable_cell_count": 0,
    "duplicate_row_count": 0,
    "blocked_reasons": [],
    "warnings": [],
    "limitations": []
  },
  "conversion_eligible": true,
  "artifacts": [
    {
      "artifact_type": "raw_normalized_rows_json",
      "path": "data/raw/quikstrike_matrix/quikstrike_matrix_20260513_120000_normalized_rows.json",
      "format": "json",
      "rows": 2,
      "created_at": "2026-05-13T12:00:01Z",
      "limitations": [
        "Local user-controlled QuikStrike table extraction only."
      ]
    }
  ],
  "warnings": [],
  "limitations": [
    "QuikStrike Matrix extraction is local-only and research-only.",
    "This is not a CME API integration and does not bypass authentication."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, wallet handling, order execution, or strategy signal is included."
  ]
}
```

### 2. List Saved Matrix Extractions

**Endpoint**: `GET /api/v1/quikstrike-matrix/extractions`

**Response** (200 OK):

```json
{
  "extractions": [
    {
      "extraction_id": "quikstrike_matrix_20260513_120000",
      "status": "completed",
      "created_at": "2026-05-13T12:00:00Z",
      "completed_at": "2026-05-13T12:00:01Z",
      "requested_view_count": 3,
      "completed_view_count": 3,
      "missing_view_count": 0,
      "row_count": 420,
      "strike_count": 70,
      "expiration_count": 3,
      "unavailable_cell_count": 4,
      "conversion_eligible": true,
      "warning_count": 1,
      "limitation_count": 2
    }
  ]
}
```

### 3. Get Matrix Extraction Detail

**Endpoint**: `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}`

Returns saved extraction metadata, view summaries, warnings, limitations, research-only text, artifact paths, mapping status, and conversion eligibility.

### 4. Get Normalized Matrix Rows

**Endpoint**: `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/rows`

**Response** (200 OK):

```json
{
  "extraction_id": "quikstrike_matrix_20260513_120000",
  "rows": [
    {
      "row_id": "quikstrike_matrix_20260513_120000:open_interest_matrix:G2RK6:4700:call",
      "capture_timestamp": "2026-05-13T12:00:00Z",
      "product": "Gold",
      "option_product_code": "OG|GC",
      "futures_symbol": "GC",
      "source_menu": "OPEN INTEREST Matrix",
      "view_type": "open_interest_matrix",
      "strike": 4700,
      "expiration": "G2RK6",
      "dte": 2,
      "future_reference_price": 4722.6,
      "option_type": "call",
      "value": 120,
      "value_type": "open_interest",
      "cell_state": "available",
      "table_row_label": "4700",
      "table_column_label": "G2RK6 Call",
      "extraction_warnings": [],
      "extraction_limitations": [
        "Local user-controlled QuikStrike table extraction only."
      ]
    }
  ]
}
```

### 5. Get XAU Vol-OI Conversion Rows

**Endpoint**: `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/conversion`

**Response** (200 OK):

```json
{
  "extraction_id": "quikstrike_matrix_20260513_120000",
  "conversion_result": {
    "conversion_id": "quikstrike_matrix_20260513_120000_xau_vol_oi",
    "extraction_id": "quikstrike_matrix_20260513_120000",
    "status": "completed",
    "row_count": 140,
    "output_artifacts": [
      {
        "artifact_type": "processed_xau_vol_oi_csv",
        "path": "data/processed/quikstrike_matrix/quikstrike_matrix_20260513_120000_xau_vol_oi_input.csv",
        "format": "csv",
        "rows": 140,
        "created_at": "2026-05-13T12:00:02Z",
        "limitations": [
          "Converted from local QuikStrike Matrix table extraction; source limitations preserved."
        ]
      }
    ],
    "blocked_reasons": [],
    "warnings": [
      "Unavailable cells were omitted and not treated as zero."
    ],
    "limitations": [
      "Conversion prepares local XAU Vol-OI input only and does not run wall scoring."
    ]
  },
  "rows": []
}
```

## Common Error Responses

### Missing Extraction

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "QuikStrike Matrix extraction 'unknown' was not found",
    "details": []
  }
}
```

### Invalid Or Secret-Bearing Request

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "QuikStrike Matrix extraction request is invalid",
    "details": [
      {
        "field": "research_only_acknowledged",
        "message": "research_only_acknowledged must be true"
      },
      {
        "field": "payload",
        "message": "Request must not include cookies, tokens, headers, viewstate, HAR, screenshots, credentials, private full URLs, or endpoint replay fields."
      }
    ]
  }
}
```

### Blocked Conversion Status

```json
{
  "extraction_id": "quikstrike_matrix_20260513_120000",
  "conversion_result": {
    "conversion_id": "quikstrike_matrix_20260513_120000_xau_vol_oi",
    "extraction_id": "quikstrike_matrix_20260513_120000",
    "status": "blocked",
    "row_count": 0,
    "output_artifacts": [],
    "blocked_reasons": [
      "Expiration column mapping is blocked."
    ],
    "warnings": [],
    "limitations": [
      "Conversion prepares local XAU Vol-OI research input only and does not run wall scoring."
    ]
  },
  "rows": []
}
```

## Contract Rules

- Endpoints must not accept or expose cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, account/order/wallet fields, broker fields, private endpoint content, or private full URLs.
- Endpoints must not log into QuikStrike or replay endpoint calls.
- Responses must include local-only and research-only limitations.
- Conversion must be blocked unless strike and expiration mapping are valid and required fields are present.
- Generated paths must point under ignored `data/raw/quikstrike_matrix/`, `data/processed/quikstrike_matrix/`, or `data/reports/quikstrike_matrix/`.
- Responses must not include live trading, paper trading, shadow trading, broker integration, real execution, wallet/private-key handling, profitability claims, predictive claims, safety claims, or live-readiness claims.
