# API Contract: Real Research Execution Runbook

## Scope

This contract defines research-only FastAPI endpoints for creating, listing, and reading research execution runs and their evidence reports. Endpoints must not create live, paper, shadow, broker, or execution behavior.

Base path: `/api/v1/research/execution-runs`

## Common Error Shape

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Research execution run not found",
    "details": {
      "execution_run_id": "rex_20260501_000001"
    }
  }
}
```

Common codes:

- `NOT_FOUND`
- `INVALID_CONFIG`
- `UNSUPPORTED_CAPABILITY`
- `UNSAFE_PATH`
- `MISSING_DATA`
- `REPORT_READ_ERROR`

## POST /api/v1/research/execution-runs

Create a research execution run. The implementation may reference existing feature 005/006 report IDs or run existing workflows when ready inputs are available.

### Request

```json
{
  "name": "May 2026 crypto proxy XAU evidence run",
  "research_only_acknowledged": true,
  "crypto": {
    "enabled": true,
    "primary_assets": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "optional_assets": [],
    "timeframe": "15m",
    "required_feature_groups": [
      "ohlcv",
      "regime",
      "open_interest",
      "funding",
      "volume_confirmation"
    ],
    "existing_research_run_id": null
  },
  "proxy": {
    "enabled": true,
    "assets": ["SPY", "GC=F"],
    "provider": "yahoo_finance",
    "timeframe": "1d",
    "required_feature_groups": ["ohlcv"],
    "existing_research_run_id": null
  },
  "xau": {
    "enabled": true,
    "options_oi_file_path": "data/local/xau/options_oi.csv",
    "existing_xau_report_id": null,
    "include_2sd_range": true
  }
}
```

### Response 201

```json
{
  "execution_run_id": "rex_20260501_000001",
  "status": "partial",
  "decision": "refine",
  "completed_workflow_count": 1,
  "blocked_workflow_count": 1,
  "partial_workflow_count": 1,
  "failed_workflow_count": 0,
  "workflow_results": [
    {
      "workflow_type": "crypto_multi_asset",
      "status": "partial",
      "decision": "refine",
      "decision_reason": "BTCUSDT completed while ETHUSDT and SOLUSDT require processed features.",
      "report_ids": ["research_20260501_000001"],
      "missing_data_actions": [
        "Download and process 15m features for ETHUSDT before rerunning this workflow."
      ],
      "warnings": [
        "Research evidence only; this is not a live trading approval."
      ],
      "limitations": []
    }
  ],
  "missing_data_count": 1,
  "research_only_warnings": [
    "Evidence labels are research decisions only and do not claim profitability, predictive power, safety, or live readiness."
  ],
  "artifact_paths": {
    "metadata": "data/reports/research_execution/rex_20260501_000001/metadata.json",
    "evidence": "data/reports/research_execution/rex_20260501_000001/evidence.json",
    "markdown": "data/reports/research_execution/rex_20260501_000001/evidence.md",
    "missing_data": "data/reports/research_execution/rex_20260501_000001/missing_data.json"
  }
}
```

## GET /api/v1/research/execution-runs

List saved execution runs.

### Response 200

```json
{
  "runs": [
    {
      "execution_run_id": "rex_20260501_000001",
      "name": "May 2026 crypto proxy XAU evidence run",
      "status": "partial",
      "decision": "refine",
      "completed_workflow_count": 1,
      "blocked_workflow_count": 1,
      "partial_workflow_count": 1,
      "failed_workflow_count": 0,
      "created_at": "2026-05-01T12:00:00Z",
      "artifact_root": "data/reports/research_execution/rex_20260501_000001"
    }
  ]
}
```

## GET /api/v1/research/execution-runs/{execution_run_id}

Read a persisted execution run with normalized config, workflow results, and artifact references.

### Response 200

```json
{
  "execution_run_id": "rex_20260501_000001",
  "name": "May 2026 crypto proxy XAU evidence run",
  "status": "partial",
  "decision": "refine",
  "normalized_config": {},
  "preflight_results": [],
  "evidence_summary": {},
  "artifact_paths": {}
}
```

## GET /api/v1/research/execution-runs/{execution_run_id}/evidence

Read the final evidence summary.

### Response 200

```json
{
  "execution_run_id": "rex_20260501_000001",
  "status": "partial",
  "decision": "refine",
  "workflow_results": [],
  "crypto_summary": null,
  "proxy_summary": null,
  "xau_summary": null,
  "missing_data_checklist": [],
  "limitations": [],
  "research_only_warnings": [
    "Research evidence only; not a profitability, prediction, safety, or live-readiness claim."
  ],
  "created_at": "2026-05-01T12:00:00Z"
}
```

## GET /api/v1/research/execution-runs/{execution_run_id}/missing-data

Read missing-data actions for an execution run.

### Response 200

```json
{
  "execution_run_id": "rex_20260501_000001",
  "missing_data_checklist": [
    {
      "workflow_type": "crypto_multi_asset",
      "asset": "ETHUSDT",
      "severity": "blocking",
      "instruction": "Download and process ETHUSDT 15m features before rerunning.",
      "required_inputs": ["ohlcv", "regime", "open_interest", "funding"]
    },
    {
      "workflow_type": "xau_vol_oi",
      "asset": "XAU",
      "severity": "blocking",
      "instruction": "Import a local CSV or Parquet file with date, expiry, strike, option_type, and open_interest columns.",
      "required_inputs": ["gold options OI by strike and expiry"]
    }
  ]
}
```

## Dashboard Contract

The Evidence dashboard consumes:

- `GET /api/v1/research/execution-runs` for selector options.
- `GET /api/v1/research/execution-runs/{execution_run_id}` for metadata, linked report IDs, and workflow status cards.
- `GET /api/v1/research/execution-runs/{execution_run_id}/evidence` for decision table and evidence summaries.
- `GET /api/v1/research/execution-runs/{execution_run_id}/missing-data` for missing-data checklist.

Dashboard copy must keep research-only disclaimers visible and avoid buy/sell, profitability, predictive, safety, and live-readiness wording.
