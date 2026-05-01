# Data Model: Real Research Execution Runbook

## Overview

Feature 007 adds models that describe a research execution request, workflow preflight results, linked report outcomes, evidence decisions, and persisted evidence summaries. Models are Pydantic schemas in `backend/src/models/research_execution.py`.

## Enums

### ResearchExecutionWorkflowStatus

Allowed values:

- `completed`
- `partial`
- `blocked`
- `skipped`
- `failed`

### ResearchEvidenceDecision

Allowed values:

- `continue`
- `refine`
- `reject`
- `data_blocked`
- `inconclusive`

Each label is a research triage decision only. It is not a trading approval.

### ResearchExecutionWorkflowType

Allowed values:

- `crypto_multi_asset`
- `proxy_ohlcv`
- `xau_vol_oi`
- `evidence_summary`

## Entity: ResearchExecutionRunRequest

Fields:

- `name`: Optional human-readable run name.
- `description`: Optional research note.
- `crypto`: Optional `CryptoResearchWorkflowConfig`.
- `proxy`: Optional `ProxyResearchWorkflowConfig`.
- `xau`: Optional `XauVolOiWorkflowConfig`.
- `evidence_options`: Optional dictionary of evidence aggregation settings.
- `reference_report_ids`: Optional list of existing report IDs to link.
- `research_only_acknowledged`: Boolean that must be true.

Validation rules:

- At least one workflow config must be enabled.
- Unknown or execution-oriented fields such as order size, broker, account, leverage execution, API key, wallet, or private key are rejected.
- Synthetic data flags are allowed only in automated tests and must not be used for final real-data execution runs.

## Entity: ResearchExecutionWorkflowConfig

Common fields:

- `enabled`: Boolean.
- `workflow_type`: `ResearchExecutionWorkflowType`.
- `required_capabilities`: List of capability strings.
- `existing_report_id`: Optional report ID to reference instead of rerunning.
- `notes`: Optional workflow note.

Validation rules:

- Disabled workflows become `skipped`, not failed.
- Existing report IDs must be read through their owning report store.

## Entity: CryptoResearchWorkflowConfig

Fields:

- `enabled`: Boolean.
- `primary_assets`: List of crypto symbols, defaulting to BTCUSDT, ETHUSDT, SOLUSDT.
- `optional_assets`: List of optional crypto symbols.
- `timeframe`: Timeframe string.
- `processed_feature_root`: Optional local processed data root.
- `required_feature_groups`: List such as `ohlcv`, `regime`, `open_interest`, `funding`, `volume_confirmation`.
- `existing_research_run_id`: Optional feature 005 report ID.

Validation rules:

- Symbols are normalized to uppercase.
- Crypto workflows may require OI and funding, but missing columns must produce blocked or partial evidence rather than silent omission.

## Entity: ProxyResearchWorkflowConfig

Fields:

- `enabled`: Boolean.
- `assets`: List such as SPY, QQQ, GLD, GC=F, BTC-USD.
- `provider`: Provider name, normally `yahoo_finance` or `local_file`.
- `timeframe`: Timeframe string.
- `processed_feature_root`: Optional local processed data root.
- `required_feature_groups`: List, normally `ohlcv`.
- `existing_research_run_id`: Optional feature 005 report ID.

Validation rules:

- Yahoo/proxy assets are OHLCV-only unless local processed columns support more.
- Requests for OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data are labeled unsupported.

## Entity: XauVolOiWorkflowConfig

Fields:

- `enabled`: Boolean.
- `options_oi_file_path`: Optional local CSV or Parquet path.
- `existing_xau_report_id`: Optional feature 006 report ID.
- `spot_reference`: Optional spot reference payload.
- `futures_reference`: Optional futures reference payload.
- `manual_basis`: Optional manual basis value.
- `volatility_snapshot`: Optional IV or realized volatility input.
- `include_2sd_range`: Boolean.

Validation rules:

- The local file path must remain under allowed local research paths.
- Missing local OI files produce local import instructions with required schema.
- Yahoo GC=F and GLD are not valid sources for gold options OI, futures OI, IV, or XAUUSD spot execution data.

## Entity: ResearchExecutionPreflightResult

Fields:

- `workflow_type`: Workflow type.
- `status`: Workflow status.
- `asset`: Optional asset symbol.
- `source_identity`: Provider/source description.
- `ready`: Boolean.
- `row_count`: Optional integer.
- `date_start`: Optional ISO date/time.
- `date_end`: Optional ISO date/time.
- `missing_data_actions`: List of actionable instructions.
- `unsupported_capabilities`: List of unsupported capability labels.
- `warnings`: List of warnings.
- `limitations`: List of source limitations.

Validation rules:

- Blocked results must include at least one missing-data action or validation error.
- Unsupported capabilities must stay visible in the final evidence report.

## Entity: ResearchExecutionWorkflowResult

Fields:

- `workflow_type`: Workflow type.
- `status`: Workflow status.
- `decision`: Research decision label.
- `decision_reason`: Human-readable evidence reason.
- `report_ids`: List of linked report IDs.
- `asset_results`: List of per-asset or per-source summaries.
- `warnings`: List of warnings.
- `limitations`: List of limitations.
- `missing_data_actions`: List of missing-data actions.

Validation rules:

- Every workflow result has exactly one decision label.
- Completed or partial workflow results should include report references where available.

## Entity: ResearchEvidenceSummary

Fields:

- `execution_run_id`: Stable run ID.
- `status`: Overall workflow status.
- `decision`: Overall research decision label.
- `workflow_results`: List of `ResearchExecutionWorkflowResult`.
- `crypto_summary`: Optional crypto evidence section.
- `proxy_summary`: Optional proxy OHLCV evidence section.
- `xau_summary`: Optional XAU Vol-OI evidence section.
- `missing_data_checklist`: List of missing-data actions.
- `limitations`: List of limitations.
- `research_only_warnings`: List of warnings.
- `created_at`: ISO timestamp.

Validation rules:

- Overall `data_blocked` if all enabled workflows are blocked.
- Overall `partial` status if at least one workflow completes and one workflow is blocked, skipped, or failed.
- Summary copy must not include profitability, predictive, safety, live-readiness, or buy/sell claims.

## Entity: ResearchExecutionRun

Fields:

- `execution_run_id`: Stable ID.
- `name`: Optional name.
- `normalized_config`: Request after normalization.
- `preflight_results`: List of `ResearchExecutionPreflightResult`.
- `evidence_summary`: `ResearchEvidenceSummary`.
- `artifact_paths`: Paths for metadata JSON, evidence JSON, evidence Markdown, and missing-data checklist.
- `created_at`: ISO timestamp.
- `updated_at`: ISO timestamp.

Validation rules:

- Artifact paths must be under `data/reports/research_execution/`.
- Generated artifacts must not be staged or committed.

## Entity: ResearchExecutionRunSummary

Fields:

- `execution_run_id`: Stable ID.
- `name`: Optional name.
- `status`: Overall status.
- `decision`: Overall decision.
- `completed_workflow_count`: Integer.
- `blocked_workflow_count`: Integer.
- `partial_workflow_count`: Integer.
- `failed_workflow_count`: Integer.
- `created_at`: ISO timestamp.
- `artifact_root`: Local report directory.

## Relationships

- `ResearchExecutionRunRequest` normalizes into one or more workflow configs.
- Workflow configs produce `ResearchExecutionPreflightResult` rows.
- Ready workflows reference or create feature 005 and feature 006 report IDs.
- `ResearchExecutionWorkflowResult` rows aggregate those report artifacts.
- `ResearchEvidenceSummary` groups all workflow results and decisions.
- `ResearchExecutionRun` persists config, metadata, evidence, and missing-data artifacts.
