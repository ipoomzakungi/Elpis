# API Contracts: Free Public Derivatives Data Expansion

**Date**: 2026-05-12  
**Feature**: 011-free-public-derivatives-data-expansion

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research endpoints. The feature must not require or accept private Deribit keys, broker credentials, wallet credentials, paid vendor credentials, paper trading credentials, live trading permissions, or execution credentials.

## Endpoints

### 1. Create Free Derivatives Bootstrap Run

Creates a research-only bootstrap run for CFTC COT, GVZ, and/or Deribit public options data.

**Endpoint**: `POST /api/v1/data-sources/bootstrap/free-derivatives`

**Request Body**:

```json
{
  "include_cftc": true,
  "include_gvz": true,
  "include_deribit": true,
  "cftc": {
    "years": [2025, 2026],
    "categories": ["futures_only", "futures_and_options_combined"],
    "market_filters": ["gold", "comex"],
    "source_urls": [],
    "local_fixture_paths": []
  },
  "gvz": {
    "series_id": "GVZCLS",
    "start_date": "2025-01-01",
    "end_date": "2026-05-12",
    "source_url": null,
    "local_fixture_path": null
  },
  "deribit": {
    "underlyings": ["BTC", "ETH", "SOL"],
    "include_expired": false,
    "snapshot_timestamp": "2026-05-12T10:00:00Z",
    "fixture_instruments_path": null,
    "fixture_summary_path": null
  },
  "run_label": "free-derivatives-smoke",
  "report_format": "both",
  "research_only_acknowledged": true
}
```

**Response** (201 Created):

```json
{
  "run_id": "free_derivatives_20260512_100000",
  "status": "partial",
  "created_at": "2026-05-12T10:00:00Z",
  "completed_at": "2026-05-12T10:00:08Z",
  "source_results": [
    {
      "source": "cftc_cot",
      "status": "completed",
      "requested_items": ["2025:futures_only", "2025:futures_and_options_combined"],
      "completed_items": ["2025:futures_only", "2025:futures_and_options_combined"],
      "skipped_items": [],
      "failed_items": [],
      "row_count": 104,
      "instrument_count": 0,
      "coverage_start": "2025-01-07",
      "coverage_end": "2026-05-05",
      "snapshot_timestamp": null,
      "artifacts": [
        {
          "artifact_type": "processed_cftc",
          "source": "cftc_cot",
          "path": "data/processed/cftc/gold_positioning_summary.parquet",
          "format": "parquet",
          "rows": 104,
          "created_at": "2026-05-12T10:00:08Z",
          "limitations": [
            "Weekly broad positioning context only; not strike-level options open interest and not intraday wall data."
          ]
        }
      ],
      "warnings": [],
      "limitations": [
        "Weekly broad positioning context only; not strike-level options open interest and not intraday wall data."
      ],
      "missing_data_actions": []
    }
  ],
  "artifacts": [
    {
      "artifact_type": "run_json",
      "source": "cftc_cot",
      "path": "data/reports/free_derivatives/free_derivatives_20260512_100000/report.json",
      "format": "json",
      "rows": null,
      "created_at": "2026-05-12T10:00:08Z",
      "limitations": []
    }
  ],
  "warnings": [
    "Free derivatives bootstrap is research-only and uses public/no-key or local fixture inputs only."
  ],
  "limitations": [
    "CFTC COT, GVZ, and Deribit public options do not replace local XAU strike-level options OI."
  ],
  "missing_data_actions": [],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, wallet handling, paid vendors, or execution behavior is included."
  ]
}
```

### 2. List Free Derivatives Bootstrap Runs

**Endpoint**: `GET /api/v1/data-sources/bootstrap/free-derivatives/runs`

**Response** (200 OK):

```json
{
  "runs": [
    {
      "run_id": "free_derivatives_20260512_100000",
      "status": "partial",
      "created_at": "2026-05-12T10:00:00Z",
      "completed_at": "2026-05-12T10:00:08Z",
      "completed_source_count": 2,
      "partial_source_count": 1,
      "failed_source_count": 0,
      "artifact_count": 9,
      "warning_count": 1,
      "limitation_count": 3
    }
  ]
}
```

### 3. Get Free Derivatives Bootstrap Run

**Endpoint**: `GET /api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}`

Returns the saved run detail, source results, artifact paths, warnings, limitations, missing-data actions, and research-only warnings.

### 4. Data-Source Readiness Extension

**Endpoint**: `GET /api/v1/data-sources/readiness`

The existing response must include provider statuses for:

- `cftc_cot`
- `gvz`
- `deribit_public_options`

Each status must show configured/available/missing state, capabilities, limitations, missing actions, and no secret values.

### 5. Data-Source Capability Extension

**Endpoint**: `GET /api/v1/data-sources/capabilities`

The existing capability matrix must include:

```json
{
  "provider_type": "cftc_cot",
  "display_name": "CFTC COT Gold Positioning",
  "tier": "tier_0_public_local",
  "supports": ["weekly_gold_positioning", "futures_only_cot", "futures_and_options_combined_cot"],
  "unsupported": ["strike_level_options_oi", "intraday_wall_data", "execution"],
  "requires_key": false,
  "requires_local_file": false,
  "is_optional": false,
  "limitations": [
    "Weekly broad positioning context only; not strike-level options open interest and not intraday wall data."
  ],
  "forbidden_reason": null
}
```

Analogous rows must exist for `gvz` and `deribit_public_options`.

### 6. Missing-Data Extension

**Endpoint**: `GET /api/v1/data-sources/missing-data`

The existing response must include actions for:

- CFTC public download unavailable or local fixture needed
- GVZ public download unavailable or local CSV needed
- Deribit public options unavailable or unsupported underlying
- XAU local options OI still required for strike-level XAU wall reports

## Common Error Responses

### Missing Run

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Free derivatives run 'unknown' was not found",
    "details": []
  }
}
```

### Invalid Request

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Free derivatives bootstrap request is invalid",
    "details": [
      {
        "field": "research_only_acknowledged",
        "message": "research_only_acknowledged must be true"
      }
    ]
  }
}
```

### Blocked Source

```json
{
  "error": {
    "code": "MISSING_DATA",
    "message": "Free derivatives bootstrap cannot run any enabled source",
    "details": [
      {
        "field": "cftc.local_fixture_paths",
        "message": "No CFTC public source or local fixture is available for the requested year."
      }
    ]
  }
}
```

## Contract Rules

- Responses must not include private keys, masked key values, partial key values, secret hashes, account ids, order ids, wallet values, broker credentials, or paid vendor credentials.
- Responses must not include live trading, paper trading, shadow trading, broker integration, real execution, wallet/private-key handling, profitability claims, predictive claims, safety claims, or live-readiness claims.
- CFTC outputs must be labeled weekly broad positioning only.
- GVZ outputs must be labeled as GLD-options-derived proxy volatility only.
- Deribit outputs must be labeled crypto options only.
- Generated raw, processed, and report paths must point under ignored `data/` roots.
- Partial source results must remain visible when another source succeeds.
