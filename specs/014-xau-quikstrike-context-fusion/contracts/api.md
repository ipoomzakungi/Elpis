# API Contracts: XAU QuikStrike Context Fusion

**Date**: 2026-05-13  
**Feature**: 014-xau-quikstrike-context-fusion

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication And Privacy

No authentication is required for v0 local research endpoints. These endpoints operate on saved local QuikStrike Vol2Vol and Matrix reports plus optional user-supplied research context.

Endpoints must not accept or return cookies, tokens, authorization headers, browser profile paths, viewstate values, HAR content, screenshots, private full URLs, credentials, account/order/wallet values, broker fields, private endpoint content, endpoint replay payloads, paid-vendor secrets, or execution instructions.

These routes do not log into QuikStrike, attach to browsers, replay ASP.NET requests, bypass authentication, initiate extraction, or initiate live/paper/shadow trading.

## Endpoints

### 1. Create Fusion Report

Creates a local research fusion report from one saved Vol2Vol report and one saved Matrix report.

**Endpoint**: `POST /api/v1/xau/quikstrike-fusion/reports`

**Request Body**:

```json
{
  "vol2vol_report_id": "quikstrike_20260513_095411",
  "matrix_report_id": "quikstrike_matrix_20260513_155058",
  "xauusd_spot_reference": 4692.1,
  "gc_futures_reference": 4696.7,
  "session_open_price": null,
  "realized_volatility": null,
  "candle_context": [],
  "create_xau_vol_oi_report": true,
  "create_xau_reaction_report": true,
  "run_label": "local-fusion-smoke",
  "persist_report": true,
  "research_only_acknowledged": true
}
```

**Response** (201 Created):

```json
{
  "report_id": "xau_quikstrike_fusion_20260513_160000",
  "status": "partial",
  "created_at": "2026-05-13T16:00:00Z",
  "completed_at": "2026-05-13T16:00:02Z",
  "vol2vol_source": {
    "source_type": "vol2vol",
    "report_id": "quikstrike_20260513_095411",
    "status": "completed",
    "product": "Gold",
    "option_product_code": "OG|GC",
    "row_count": 910,
    "conversion_status": "completed",
    "warnings": [],
    "limitations": [
      "QuikStrike Vol2Vol extraction is local-only and research-only."
    ]
  },
  "matrix_source": {
    "source_type": "matrix",
    "report_id": "quikstrike_matrix_20260513_155058",
    "status": "completed",
    "product": "Gold",
    "option_product_code": "OG|GC",
    "row_count": 1860,
    "conversion_status": "completed",
    "warnings": [
      "Unavailable cells were preserved and not treated as zero."
    ],
    "limitations": [
      "QuikStrike Matrix extraction is local-only and research-only."
    ]
  },
  "coverage": {
    "matched_key_count": 120,
    "vol2vol_only_key_count": 62,
    "matrix_only_key_count": 245,
    "conflict_key_count": 0,
    "blocked_key_count": 0,
    "strike_count": 31,
    "expiration_count": 10,
    "option_type_count": 2,
    "value_type_count": 6
  },
  "context_summary": {
    "basis_status": "available",
    "iv_range_status": "partial",
    "open_regime_status": "unavailable",
    "candle_acceptance_status": "unavailable",
    "realized_volatility_status": "unavailable",
    "source_agreement_status": "available",
    "missing_context_count": 3
  },
  "basis_state": {
    "status": "available",
    "xauusd_spot_reference": 4692.1,
    "gc_futures_reference": 4696.7,
    "basis_points": 4.6,
    "calculation_note": "Spot-equivalent levels are research annotations only."
  },
  "fused_row_count": 427,
  "xau_vol_oi_input_row_count": 365,
  "downstream_result": {
    "xau_vol_oi_report_id": "xau_vol_oi_20260513_160001",
    "xau_reaction_report_id": "xau_reaction_20260513_160002_xau_vol_oi_20260513_160001",
    "xau_report_status": "partial",
    "reaction_report_status": "completed",
    "reaction_row_count": 215,
    "no_trade_count": 215,
    "all_reactions_no_trade": true,
    "notes": [
      "Reaction output remains conservative because open-regime and candle-acceptance context are unavailable."
    ]
  },
  "artifacts": [
    {
      "artifact_type": "report_json",
      "path": "data/reports/xau_quikstrike_fusion/xau_quikstrike_fusion_20260513_160000/report.json",
      "format": "json",
      "rows": 1
    },
    {
      "artifact_type": "fused_rows_json",
      "path": "data/reports/xau_quikstrike_fusion/xau_quikstrike_fusion_20260513_160000/fused_rows.json",
      "format": "json",
      "rows": 427
    }
  ],
  "warnings": [
    "Session open context is unavailable.",
    "Candle acceptance context is unavailable."
  ],
  "limitations": [
    "Fusion is local-only and research-only.",
    "Fusion does not create execution signals or claim predictive power."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, wallet handling, order execution, or strategy signal is included."
  ]
}
```

### 2. List Fusion Reports

**Endpoint**: `GET /api/v1/xau/quikstrike-fusion/reports`

**Response** (200 OK):

```json
{
  "reports": [
    {
      "report_id": "xau_quikstrike_fusion_20260513_160000",
      "status": "partial",
      "created_at": "2026-05-13T16:00:00Z",
      "vol2vol_report_id": "quikstrike_20260513_095411",
      "matrix_report_id": "quikstrike_matrix_20260513_155058",
      "fused_row_count": 427,
      "strike_count": 31,
      "expiration_count": 10,
      "basis_status": "available",
      "iv_range_status": "partial",
      "open_regime_status": "unavailable",
      "candle_acceptance_status": "unavailable",
      "xau_vol_oi_report_id": "xau_vol_oi_20260513_160001",
      "xau_reaction_report_id": "xau_reaction_20260513_160002_xau_vol_oi_20260513_160001",
      "all_reactions_no_trade": true,
      "warning_count": 2
    }
  ]
}
```

### 3. Get Fusion Report Detail

**Endpoint**: `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}`

Returns saved report metadata, source report refs, coverage, basis/context summaries, warnings, limitations, research-only text, linked downstream report ids, and artifact paths.

### 4. Get Fused Rows

**Endpoint**: `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}/rows`

**Response** (200 OK):

```json
{
  "report_id": "xau_quikstrike_fusion_20260513_160000",
  "rows": [
    {
      "fusion_row_id": "xau_quikstrike_fusion_20260513_160000:G2RK6:4700:call:open_interest",
      "match_key": {
        "strike": 4700,
        "expiration": "2026-05-15",
        "expiration_code": "G2RK6",
        "expiration_key": "2026-05-15",
        "option_type": "call",
        "value_type": "open_interest"
      },
      "source_type": "fused",
      "match_status": "matched",
      "agreement_status": "agreement",
      "vol2vol_value": {
        "source_type": "vol2vol",
        "source_report_id": "quikstrike_20260513_095411",
        "source_row_id": "vol2vol-row-1",
        "value": 120,
        "value_type": "open_interest",
        "source_view": "open_interest"
      },
      "matrix_value": {
        "source_type": "matrix",
        "source_report_id": "quikstrike_matrix_20260513_155058",
        "source_row_id": "matrix-row-1",
        "value": 120,
        "value_type": "open_interest",
        "source_view": "open_interest_matrix"
      },
      "basis_points": 4.6,
      "spot_equivalent_level": 4695.4,
      "source_agreement_notes": [
        "Comparable open interest values agree."
      ],
      "missing_context_notes": [],
      "warnings": [],
      "limitations": [
        "Fused row is a research annotation only."
      ]
    }
  ]
}
```

### 5. Get Missing Context

**Endpoint**: `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context`

**Response** (200 OK):

```json
{
  "report_id": "xau_quikstrike_fusion_20260513_160000",
  "missing_context": [
    {
      "context_key": "session_open",
      "status": "unavailable",
      "severity": "warning",
      "message": "Session open price was not provided; open-regime context remains unavailable.",
      "blocks_conversion": false,
      "blocks_reaction_confidence": true,
      "source_refs": []
    },
    {
      "context_key": "candle_acceptance",
      "status": "unavailable",
      "severity": "warning",
      "message": "Candle acceptance/rejection context was not provided; reaction output should remain conservative.",
      "blocks_conversion": false,
      "blocks_reaction_confidence": true,
      "source_refs": []
    }
  ]
}
```

## Common Error Responses

### Missing Fusion Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "XAU QuikStrike fusion report 'unknown' was not found",
    "details": []
  }
}
```

### Missing Source Report

```json
{
  "error": {
    "code": "SOURCE_NOT_FOUND",
    "message": "Selected QuikStrike source report was not found",
    "details": [
      {
        "field": "vol2vol_report_id",
        "message": "Vol2Vol report 'missing' was not found"
      }
    ]
  }
}
```

### Incompatible Source Reports

```json
{
  "error": {
    "code": "INCOMPATIBLE_SOURCE_REPORTS",
    "message": "Selected QuikStrike reports cannot be fused",
    "details": [
      {
        "field": "matrix_report_id",
        "message": "Matrix report product is not Gold/OG/GC"
      }
    ]
  }
}
```

### Invalid Or Secret-Bearing Request

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "XAU QuikStrike fusion request is invalid",
    "details": [
      {
        "field": "research_only_acknowledged",
        "message": "research_only_acknowledged must be true"
      },
      {
        "field": "payload",
        "message": "Request must not include cookies, tokens, headers, viewstate, HAR, screenshots, credentials, private full URLs, endpoint replay fields, or execution fields."
      }
    ]
  }
}
```

## Contract Rules

- Endpoints must not accept or expose cookies, tokens, headers, viewstate values, HAR content, screenshots, credentials, account/order/wallet fields, broker fields, private endpoint content, private full URLs, endpoint replay material, or paid-vendor secrets.
- Endpoints must not log into QuikStrike, connect to browsers, replay QuikStrike endpoint calls, or bypass authentication.
- Responses must include local-only and research-only limitations.
- Source values from Vol2Vol and Matrix must remain separately visible when both exist.
- Fusion must be blocked or partial when strike, expiration, option side, or value mapping is not reliable.
- Missing basis, IV/range, open, candle, and realized-volatility context must be explicit.
- Generated paths must point under ignored local artifact roots.
- Responses must not include live trading, paper trading, shadow trading, broker integration, real execution, wallet/private-key handling, profitability claims, predictive claims, safety claims, live-readiness claims, or buy/sell execution signals.
