# API Contracts: XAU Vol-OI Wall Engine

**Date**: 2026-05-01  
**Feature**: 006-xau-vol-oi-wall-engine

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research endpoints. Endpoints must not require private exchange keys, broker credentials, wallet credentials, paper trading credentials, or live trading permissions.

## Endpoints

### 1. Run XAU Vol-OI Report

Runs a synchronous local research report from a local gold options OI dataset and reference prices.

**Endpoint**: `POST /api/v1/xau/vol-oi/reports`

**Request Body**:

```json
{
  "options_oi_file_path": "data/raw/xau/sample_gold_options_oi.csv",
  "session_date": "2026-04-30",
  "spot_reference": {
    "source": "manual",
    "symbol": "XAUUSD",
    "price": 2403.0,
    "timestamp": "2026-04-30T16:00:00Z",
    "reference_type": "spot"
  },
  "futures_reference": {
    "source": "manual",
    "symbol": "GC",
    "price": 2410.0,
    "timestamp": "2026-04-30T16:00:00Z",
    "reference_type": "futures"
  },
  "manual_basis": null,
  "volatility_snapshot": {
    "implied_volatility": 0.16,
    "realized_volatility": null,
    "manual_expected_move": null,
    "source": "iv",
    "days_to_expiry": 7
  },
  "include_2sd_range": true,
  "min_wall_score": 0.0,
  "report_format": "both"
}
```

**Response** (200 OK):

```json
{
  "report_id": "xau_vol_oi_20260430_160000",
  "status": "completed",
  "created_at": "2026-04-30T16:00:02Z",
  "session_date": "2026-04-30",
  "basis_snapshot": {
    "basis": 7.0,
    "basis_source": "computed",
    "mapping_available": true,
    "timestamp_alignment_status": "aligned",
    "notes": []
  },
  "expected_range": {
    "source": "iv",
    "reference_price": 2403.0,
    "expected_move": 25.2,
    "lower_1sd": 2377.8,
    "upper_1sd": 2428.2,
    "lower_2sd": 2352.6,
    "upper_2sd": 2453.4,
    "unavailable_reason": null,
    "notes": ["IV-based expected range; not a prediction or trade signal."]
  },
  "source_row_count": 12,
  "accepted_row_count": 12,
  "rejected_row_count": 0,
  "wall_count": 6,
  "zone_count": 5,
  "warnings": [
    "XAU Vol-OI zones are research annotations only and do not imply profitability, predictive power, safety, or live readiness."
  ],
  "limitations": [
    "Local imported options data must be independently verified for completeness and licensing."
  ],
  "artifacts": []
}
```

### 2. List XAU Vol-OI Reports

**Endpoint**: `GET /api/v1/xau/vol-oi/reports`

**Response** (200 OK):

```json
{
  "reports": [
    {
      "report_id": "xau_vol_oi_20260430_160000",
      "status": "completed",
      "created_at": "2026-04-30T16:00:02Z",
      "session_date": "2026-04-30",
      "source_row_count": 12,
      "wall_count": 6,
      "zone_count": 5,
      "warning_count": 1
    }
  ]
}
```

### 3. Get XAU Vol-OI Report

**Endpoint**: `GET /api/v1/xau/vol-oi/reports/{report_id}`

Returns persisted report metadata, request, basis snapshot, expected range, warnings, limitations, and artifact references.

### 4. Get XAU Wall Table

**Endpoint**: `GET /api/v1/xau/vol-oi/reports/{report_id}/walls`

**Response** (200 OK):

```json
{
  "report_id": "xau_vol_oi_20260430_160000",
  "data": [
    {
      "wall_id": "20260430_20260507_2400_call",
      "expiry": "2026-05-07",
      "strike": 2400.0,
      "spot_equivalent_level": 2393.0,
      "basis": 7.0,
      "option_type": "call",
      "open_interest": 12500.0,
      "total_expiry_open_interest": 50000.0,
      "oi_share": 0.25,
      "expiry_weight": 0.8,
      "freshness_factor": 1.1,
      "wall_score": 0.22,
      "freshness_status": "confirmed",
      "notes": ["Recent volume confirms activity at this strike."],
      "limitations": []
    }
  ]
}
```

### 5. Get XAU Zone Table

**Endpoint**: `GET /api/v1/xau/vol-oi/reports/{report_id}/zones`

**Response** (200 OK):

```json
{
  "report_id": "xau_vol_oi_20260430_160000",
  "data": [
    {
      "zone_id": "pin_2393_20260507",
      "zone_type": "pin_risk_zone",
      "level": 2393.0,
      "lower_bound": 2388.0,
      "upper_bound": 2398.0,
      "linked_wall_ids": ["20260430_20260507_2400_call"],
      "wall_score": 0.22,
      "pin_risk_score": 0.67,
      "squeeze_risk_score": 0.2,
      "confidence": "medium",
      "no_trade_warning": false,
      "notes": ["Near-expiry wall is close to the spot-equivalent reference."],
      "limitations": ["Zone is a research annotation, not a trade signal."]
    }
  ]
}
```

## Common Error Responses

### Missing Required Columns

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Gold options OI file is missing required columns",
    "details": [
      {
        "field": "options_oi_file_path",
        "message": "Missing columns: expiry, open_interest"
      }
    ]
  }
}
```

### Missing Basis Inputs

```json
{
  "error": {
    "code": "MISSING_DATA",
    "message": "Spot-equivalent mapping requires a manual basis or both futures and spot references",
    "details": [
      {
        "field": "basis",
        "message": "Provide futures_reference and spot_reference, or provide manual_basis."
      }
    ]
  }
}
```

### Missing Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "XAU Vol-OI report 'unknown' was not found",
    "details": []
  }
}
```

## Research-Only Contract Rules

- Responses must not include profitability claims, predictive claims, safety claims, or live-readiness claims.
- XAU wall and zone outputs are research annotations only.
- Yahoo Finance GC=F and GLD references must be labeled as OHLCV proxies only.
- Generated report paths must point under `data/reports`.
- Local imported datasets and generated report artifacts must remain ignored by version control.
