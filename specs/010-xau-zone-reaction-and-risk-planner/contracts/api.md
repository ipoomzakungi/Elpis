# API Contracts: XAU Zone Reaction and Risk Planner

**Date**: 2026-05-12  
**Feature**: 010-xau-zone-reaction-and-risk-planner

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication

No authentication is required for v0 local research endpoints. Endpoints must not require or accept private exchange keys, broker credentials, wallet credentials, paper trading credentials, live trading permissions, or execution credentials.

## Endpoints

### 1. Create XAU Reaction Report

Creates a deterministic research-only reaction report from an existing feature 006 XAU Vol-OI report.

**Endpoint**: `POST /api/v1/xau/reaction-reports`

**Request Body**:

```json
{
  "source_report_id": "xau_vol_oi_20260430_160000",
  "current_price": 2405.0,
  "current_timestamp": "2026-04-30T16:15:00Z",
  "freshness_input": {
    "intraday_timestamp": "2026-04-30T16:10:00Z",
    "current_timestamp": "2026-04-30T16:15:00Z",
    "total_intraday_contracts": 12500,
    "min_contract_threshold": 1000,
    "max_allowed_age_minutes": 30,
    "session_flag": "regular"
  },
  "vol_regime_input": {
    "implied_volatility": 0.16,
    "realized_volatility": 0.11,
    "price": 2405.0,
    "iv_lower": 2378.0,
    "iv_upper": 2428.0,
    "rv_lower": 2388.0,
    "rv_upper": 2420.0
  },
  "open_regime_input": {
    "session_open": 2398.0,
    "current_price": 2405.0,
    "initial_move_direction": "up",
    "crossed_open_after_initial_move": false,
    "acceptance_beyond_open": false
  },
  "acceptance_inputs": [
    {
      "wall_id": "20260430_20260507_2400_call",
      "wall_level": 2393.0,
      "high": 2410.0,
      "low": 2390.0,
      "close": 2405.0,
      "next_bar_open": 2406.0,
      "buffer_points": 2.0
    }
  ],
  "event_risk_state": "unknown",
  "max_total_risk_per_idea": 0.01,
  "max_recovery_legs": 1,
  "minimum_rr": 1.5,
  "wall_buffer_points": 2.0,
  "report_format": "both",
  "research_only_acknowledged": true
}
```

**Response** (200 OK):

```json
{
  "report_id": "xau_reaction_20260430_161500",
  "source_report_id": "xau_vol_oi_20260430_160000",
  "status": "completed",
  "created_at": "2026-04-30T16:15:02Z",
  "session_date": "2026-04-30",
  "source_wall_count": 6,
  "source_zone_count": 5,
  "reaction_count": 6,
  "no_trade_count": 1,
  "risk_plan_count": 5,
  "freshness_state": {
    "state": "VALID",
    "age_minutes": 5,
    "confidence_impact": "none",
    "no_trade_reason": null,
    "notes": ["Intraday options snapshot is within the allowed age and contract threshold."]
  },
  "vol_regime_state": {
    "realized_volatility": 0.11,
    "vrp": 0.05,
    "vrp_regime": "iv_premium",
    "iv_edge_state": "inside",
    "rv_extension_state": "inside",
    "confidence_impact": "reduce",
    "notes": ["IV is above RV; simple mean-reversion confidence is reduced unless candle rejection confirms."]
  },
  "open_regime_state": {
    "open_side": "above_open",
    "open_distance_points": 7.0,
    "open_flip_state": "no_flip",
    "open_as_support_or_resistance": "support_test",
    "notes": ["Current price is above the session open."]
  },
  "warnings": [
    "XAU reaction outputs are research annotations only and are not buy/sell signals or execution instructions."
  ],
  "limitations": [
    "Source XAU Vol-OI report data must be independently verified for completeness."
  ],
  "artifacts": []
}
```

### 2. List XAU Reaction Reports

**Endpoint**: `GET /api/v1/xau/reaction-reports`

**Response** (200 OK):

```json
{
  "reports": [
    {
      "report_id": "xau_reaction_20260430_161500",
      "source_report_id": "xau_vol_oi_20260430_160000",
      "status": "completed",
      "created_at": "2026-04-30T16:15:02Z",
      "session_date": "2026-04-30",
      "reaction_count": 6,
      "no_trade_count": 1,
      "risk_plan_count": 5,
      "warning_count": 1
    }
  ]
}
```

### 3. Get XAU Reaction Report

**Endpoint**: `GET /api/v1/xau/reaction-reports/{report_id}`

Returns persisted report metadata, source report id, report-level freshness, volatility, open context, warnings, limitations, reaction rows, risk plans, and artifact references.

### 4. Get Reaction Rows

**Endpoint**: `GET /api/v1/xau/reaction-reports/{report_id}/reactions`

**Response** (200 OK):

```json
{
  "report_id": "xau_reaction_20260430_161500",
  "data": [
    {
      "reaction_id": "reaction_20260430_20260507_2400_call",
      "source_report_id": "xau_vol_oi_20260430_160000",
      "wall_id": "20260430_20260507_2400_call",
      "zone_id": "pin_2393_20260507",
      "reaction_label": "REVERSAL_CANDIDATE",
      "confidence_label": "medium",
      "explanation_notes": [
        "High-score wall rejected within the configured buffer.",
        "Price is stretched near the expected range edge."
      ],
      "no_trade_reasons": [],
      "invalidation_level": 2390.0,
      "target_level_1": 2405.0,
      "target_level_2": 2420.0,
      "next_wall_reference": "20260430_20260507_2425_call",
      "research_only_warning": "Research annotation only; not a buy/sell signal."
    }
  ]
}
```

### 5. Get Risk Plan Rows

**Endpoint**: `GET /api/v1/xau/reaction-reports/{report_id}/risk-plan`

**Response** (200 OK):

```json
{
  "report_id": "xau_reaction_20260430_161500",
  "data": [
    {
      "plan_id": "risk_reaction_20260430_20260507_2400_call",
      "reaction_id": "reaction_20260430_20260507_2400_call",
      "reaction_label": "REVERSAL_CANDIDATE",
      "entry_condition_text": "Research-only condition: wait for rejection state to remain valid before considering the scenario in analysis.",
      "invalidation_level": 2390.0,
      "stop_buffer_points": 2.0,
      "target_1": 2405.0,
      "target_2": 2420.0,
      "max_total_risk_per_idea": 0.01,
      "max_recovery_legs": 1,
      "minimum_rr": 1.5,
      "rr_state": "meets_minimum",
      "cancel_conditions": [
        "Freshness becomes stale or prior-day.",
        "Candle acceptance invalidates the rejection state."
      ],
      "risk_notes": [
        "Research annotation only; not execution-ready.",
        "Recovery legs are capped and unlimited averaging is not allowed."
      ]
    }
  ]
}
```

## Common Error Responses

### Missing Source XAU Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Source XAU Vol-OI report 'unknown' was not found",
    "details": []
  }
}
```

### Invalid Reaction Request

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "XAU reaction request is invalid",
    "details": [
      {
        "field": "research_only_acknowledged",
        "message": "research_only_acknowledged must be true"
      }
    ]
  }
}
```

### Blocked Reaction Report

```json
{
  "error": {
    "code": "MISSING_DATA",
    "message": "XAU reaction report cannot be created from the source report",
    "details": [
      {
        "field": "source_report_id",
        "message": "Source report has no usable wall rows."
      }
    ]
  }
}
```

### Missing Reaction Report

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "XAU reaction report 'unknown' was not found",
    "details": []
  }
}
```

## Research-Only Contract Rules

- Responses must not include buy/sell execution signals, order instructions, broker instructions, profitability claims, predictive claims, safety claims, or live-readiness claims.
- `NO_TRADE` rows must not include entry plans.
- Risk plans are bounded research annotations only.
- Generated report paths must point under `data/reports/xau_reaction/`.
- Source XAU Vol-OI report ids must remain traceable in every reaction report.
