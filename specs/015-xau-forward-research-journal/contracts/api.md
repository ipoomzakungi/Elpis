# API Contracts: XAU Forward Research Journal

**Date**: 2026-05-14  
**Feature**: 015-xau-forward-research-journal

## Base URL

```text
http://localhost:8000/api/v1
```

## Authentication And Privacy

No authentication is required for v0 local research endpoints. These endpoints operate on saved local report ids and user-supplied research observations.

Endpoints must not accept or return cookies, tokens, authorization headers, browser profile paths, viewstate values, HAR content, screenshots, private full URLs, credentials, account/order/wallet values, broker fields, private endpoint content, endpoint replay payloads, paid-vendor secrets, or execution instructions.

These routes do not log into QuikStrike, attach to browsers, replay ASP.NET requests, bypass authentication, initiate extraction, initiate live/paper/shadow trading, or claim profitability, predictive power, safety, or live readiness.

## Endpoints

### 1. Create Journal Entry

Creates a local forward research journal entry from existing saved report ids.

**Endpoint**: `POST /api/v1/xau/forward-journal/entries`

**Request Body**:

```json
{
  "snapshot_time": "2026-05-14T03:08:04Z",
  "capture_session": "quikstrike-gold-am-session",
  "vol2vol_report_id": "quikstrike_20260513_101537",
  "matrix_report_id": "quikstrike_matrix_20260513_155058",
  "fusion_report_id": "xau_quikstrike_fusion_20260514_030803_real-local-fusion-smoke-fixed",
  "xau_vol_oi_report_id": "xau_vol_oi_20260514_030804_640930",
  "xau_reaction_report_id": "xau_reaction_20260514_030804_xau_vol_oi_20260514_030804_640930",
  "spot_price_at_snapshot": null,
  "futures_price_at_snapshot": 4707.2,
  "basis": null,
  "session_open_price": null,
  "event_news_flag": "none_known",
  "notes": [
    "Forward evidence snapshot created from local QuikStrike-derived reports."
  ],
  "persist_report": true,
  "research_only_acknowledged": true
}
```

**Response** (201 Created):

```json
{
  "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
  "status": "partial",
  "created_at": "2026-05-14T03:08:05Z",
  "updated_at": "2026-05-14T03:08:05Z",
  "snapshot": {
    "snapshot_time": "2026-05-14T03:08:04Z",
    "capture_session": "quikstrike-gold-am-session",
    "product": "Gold",
    "expiration": "2026-05-14",
    "expiration_code": "G2RK6",
    "spot_price_at_snapshot": null,
    "futures_price_at_snapshot": 4707.2,
    "basis": null,
    "session_open_price": null,
    "event_news_flag": "none_known",
    "missing_context": [
      "spot_price_at_snapshot",
      "basis",
      "session_open_price"
    ]
  },
  "source_reports": [
    {
      "source_type": "xau_quikstrike_fusion",
      "report_id": "xau_quikstrike_fusion_20260514_030803_real-local-fusion-smoke-fixed",
      "status": "partial",
      "product": "Gold",
      "warnings": [
        "Basis context is unavailable."
      ],
      "limitations": [
        "Fusion is local-only and research-only."
      ]
    }
  ],
  "top_oi_walls": [
    {
      "rank": 1,
      "strike": 4675.0,
      "expiration": "2026-05-14",
      "expiration_code": "G2RK6",
      "option_type": "mixed",
      "open_interest": 231.0,
      "wall_score": 0.1125
    }
  ],
  "top_oi_change_walls": [],
  "top_volume_walls": [],
  "reaction_summaries": [
    {
      "reaction_label": "NO_TRADE",
      "count": 72,
      "no_trade_reasons": [
        "Freshness state is UNKNOWN.",
        "Basis mapping is unavailable.",
        "Volatility regime context is unavailable.",
        "Opening-price regime context is unavailable."
      ]
    }
  ],
  "outcomes": [
    {
      "window": "30m",
      "status": "pending",
      "label": "pending",
      "notes": [
        "Outcome data has not been attached."
      ]
    }
  ],
  "artifacts": [
    {
      "artifact_type": "report_json",
      "path": "data/reports/xau_forward_journal/xau_forward_journal_20260514_030804_quikstrike-gold-am-session/report.json",
      "format": "json",
      "rows": 1
    }
  ],
  "warnings": [
    "Forward journal entries are research annotations only."
  ],
  "limitations": [
    "This journal builds forward evidence and is not a historical full-strategy backtest."
  ],
  "research_only_warnings": [
    "No live trading, paper trading, broker integration, order execution, strategy signal, profitability claim, predictive claim, safety claim, or live-readiness claim is included."
  ]
}
```

### 2. List Journal Entries

**Endpoint**: `GET /api/v1/xau/forward-journal/entries`

**Response** (200 OK):

```json
{
  "entries": [
    {
      "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
      "status": "partial",
      "snapshot_time": "2026-05-14T03:08:04Z",
      "capture_session": "quikstrike-gold-am-session",
      "product": "Gold",
      "expiration": "2026-05-14",
      "expiration_code": "G2RK6",
      "fusion_report_id": "xau_quikstrike_fusion_20260514_030803_real-local-fusion-smoke-fixed",
      "xau_vol_oi_report_id": "xau_vol_oi_20260514_030804_640930",
      "xau_reaction_report_id": "xau_reaction_20260514_030804_xau_vol_oi_20260514_030804_640930",
      "outcome_status": "pending",
      "completed_outcome_count": 0,
      "pending_outcome_count": 5,
      "no_trade_count": 72,
      "warning_count": 1
    }
  ]
}
```

### 3. Get Journal Entry Detail

**Endpoint**: `GET /api/v1/xau/forward-journal/entries/{journal_id}`

Returns the saved journal entry including source report references, snapshot context, top wall summaries, reaction summaries, missing context, outcomes, notes, warnings, limitations, research-only text, and artifact paths.

### 4. Update Outcomes

**Endpoint**: `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes`

**Request Body**:

```json
{
  "outcomes": [
    {
      "window": "30m",
      "label": "stayed_inside_range",
      "observation_start": "2026-05-14T03:08:04Z",
      "observation_end": "2026-05-14T03:38:04Z",
      "open": 4707.2,
      "high": 4712.0,
      "low": 4701.5,
      "close": 4706.0,
      "reference_wall_id": "2026-05-14_4675_mixed",
      "reference_wall_level": 4675.0,
      "next_wall_reference": null,
      "notes": [
        "Synthetic validation example; not a strategy result."
      ]
    }
  ],
  "update_note": "Attach first outcome observation.",
  "research_only_acknowledged": true
}
```

**Response** (200 OK):

```json
{
  "journal_id": "xau_forward_journal_20260514_030804_quikstrike-gold-am-session",
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
      "notes": [
        "Synthetic validation example; not a strategy result."
      ]
    }
  ],
  "updated_at": "2026-05-14T03:40:00Z",
  "warnings": [],
  "limitations": [
    "Outcome labels are forward research annotations only."
  ]
}
```

### 5. Get Outcomes

**Endpoint**: `GET /api/v1/xau/forward-journal/entries/{journal_id}/outcomes`

Returns all outcome windows for the selected entry, including pending windows.

## Common Error Responses

### Missing Journal Entry

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "XAU forward journal entry 'unknown' was not found",
    "details": []
  }
}
```

### Missing Source Report

```json
{
  "error": {
    "code": "SOURCE_REPORT_NOT_FOUND",
    "message": "One or more selected source reports were not found",
    "details": [
      {
        "field": "fusion_report_id",
        "message": "Fusion report 'missing' was not found"
      }
    ]
  }
}
```

### Invalid Outcome Update

```json
{
  "error": {
    "code": "INVALID_OUTCOME_UPDATE",
    "message": "Outcome update is invalid",
    "details": [
      {
        "field": "outcomes[0].window",
        "message": "Unsupported outcome window"
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
        "message": "Provide an update note explaining why the label changed"
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
    "message": "XAU forward journal request is invalid",
    "details": [
      {
        "field": "payload",
        "message": "Request must not include cookies, tokens, headers, viewstate, HAR, screenshots, credentials, private full URLs, endpoint replay fields, broker fields, wallet fields, order fields, or execution fields."
      }
    ]
  }
}
```

## Contract Rules

- Responses must include local-only and research-only limitations.
- Snapshot source report ids and original snapshot time must remain visible.
- Outcome updates must not mutate original snapshot observations.
- Missing OHLC data must leave outcome windows pending or inconclusive.
- Generated paths must point under ignored local artifact roots.
- Endpoints must not accept or expose session material, endpoint replay material, credentials, private URLs, execution fields, or unsupported performance claims.
