# Data Model: Real Data-Source Onboarding And First Evidence Run

## Enums

### DataSourceProviderType

| Value | Meaning |
|-------|---------|
| `binance_public` | Binance public market and public USD-M derivatives endpoints used for crypto research. |
| `yahoo_finance` | Yahoo Finance OHLCV/proxy provider. |
| `local_file` | Local CSV/Parquet imports. |
| `kaiko_optional` | Optional paid normalized crypto derivatives research provider. |
| `tardis_optional` | Optional paid native exchange archive/replay research provider. |
| `coinglass_optional` | Optional paid aggregate/dashboard overlay research provider. |
| `cryptoquant_optional` | Optional paid aggregate/on-chain/dashboard overlay research provider. |
| `cme_quikstrike_local_or_optional` | Local-first gold options OI import or optional configured CME/QuikStrike-style source. |
| `forbidden_private_trading` | Forbidden private trading, broker, wallet, or execution credential category. |

### DataSourceReadinessStatus

| Value | Meaning |
|-------|---------|
| `ready` | Source is usable for the requested research scope. |
| `configured` | Optional source appears configured, but no data fetch is performed by readiness checks. |
| `missing` | Required input is absent. |
| `unavailable_optional` | Optional source is not configured and does not block MVP. |
| `unsupported` | Requested capability is not supported by the provider. |
| `blocked` | Required source or local file blocks the requested workflow. |
| `forbidden` | Requested credential or behavior is outside v0 scope. |

### DataSourceTier

| Value | Meaning |
|-------|---------|
| `tier_0_public_local` | No-key public provider or local import path. |
| `tier_1_optional_paid_research` | Optional paid research data source. |
| `tier_2_forbidden_v0` | Forbidden private trading, broker, wallet, or execution source. |

### DataSourceWorkflowType

| Value | Meaning |
|-------|---------|
| `crypto_multi_asset` | Crypto processed-feature readiness for feature 005/007 workflows. |
| `proxy_ohlcv` | Yahoo/proxy OHLCV readiness for feature 005/007 workflows. |
| `xau_vol_oi` | Local XAU options OI readiness for feature 006/007 workflows. |
| `optional_vendor` | Optional paid research provider readiness. |
| `first_evidence_run` | Combined first-run evidence workflow. |

### FirstEvidenceRunStatus

| Value | Meaning |
|-------|---------|
| `completed` | First evidence workflow completed. |
| `partial` | At least one workflow completed and at least one workflow was blocked or skipped. |
| `blocked` | Required inputs blocked the run. |
| `failed` | Unexpected failure occurred. |

## Entities

### DataSourceCapability

Defines one provider row in the capability matrix.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `provider_type` | `DataSourceProviderType` | Yes | Canonical provider type. |
| `display_name` | string | Yes | Human-readable provider name. |
| `tier` | `DataSourceTier` | Yes | Public/local, optional paid, or forbidden. |
| `supports` | list[string] | Yes | Supported research data categories. |
| `unsupported` | list[string] | Yes | Unsupported categories that must be labeled. |
| `requires_key` | bool | Yes | True for optional paid provider sources. |
| `requires_local_file` | bool | Yes | True for local file/import based sources. |
| `is_optional` | bool | Yes | Optional providers do not block MVP when absent. |
| `limitations` | list[string] | Yes | Source limitations and research-only notes. |
| `forbidden_reason` | string or null | No | Populated for forbidden credential categories. |

### DataSourceProviderStatus

Reports readiness for one provider/source without exposing secret values.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `provider_type` | `DataSourceProviderType` | Yes | Source being inspected. |
| `status` | `DataSourceReadinessStatus` | Yes | Ready/configured/missing/optional/unsupported/forbidden. |
| `configured` | bool | Yes | True when source appears configured or public/local is available. |
| `env_var_name` | string or null | No | Name of allowlisted optional env var. No values are returned. |
| `secret_value_returned` | bool | Yes | Must always be false. |
| `capabilities` | `DataSourceCapability` | Yes | Capability row for the provider. |
| `warnings` | list[string] | Yes | Non-blocking warnings. |
| `limitations` | list[string] | Yes | Source limits. |
| `missing_actions` | list[`DataSourceMissingDataAction`] | Yes | Actions needed to configure or import data. |

### DataSourceMissingDataAction

Concrete action to unblock a workflow or optional provider.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `action_id` | string | Yes | Stable action id. |
| `workflow_type` | `DataSourceWorkflowType` | Yes | Workflow affected. |
| `provider_type` | `DataSourceProviderType` | Yes | Source related to the action. |
| `asset` | string or null | No | Asset symbol when relevant. |
| `severity` | string | Yes | `blocking`, `optional`, or `informational`. |
| `title` | string | Yes | Short action label. |
| `instructions` | list[string] | Yes | Concrete next steps. |
| `required_columns` | list[string] | No | Local file schema requirements. |
| `optional_columns` | list[string] | No | Local file optional schema columns. |
| `blocking` | bool | Yes | True when the run cannot proceed for that workflow. |

### DataSourceReadiness

Top-level readiness snapshot.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `generated_at` | datetime | Yes | Snapshot time. |
| `provider_statuses` | list[`DataSourceProviderStatus`] | Yes | Status per provider. |
| `capability_matrix` | list[`DataSourceCapability`] | Yes | Full matrix. |
| `public_sources_available` | bool | Yes | True when tier 0 sources are usable. |
| `optional_sources_missing` | list[`DataSourceProviderType`] | Yes | Optional paid providers absent. |
| `forbidden_sources_detected` | list[`DataSourceProviderType`] | Yes | Forbidden categories flagged. |
| `missing_data_actions` | list[`DataSourceMissingDataAction`] | Yes | Default missing-data checklist. |
| `research_only_warnings` | list[string] | Yes | No execution/no claims warnings. |

### DataSourcePreflightRequest

Request to check whether the first evidence run can proceed.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `crypto_assets` | list[string] | No | Defaults to BTCUSDT, ETHUSDT, SOLUSDT. |
| `optional_crypto_assets` | list[string] | No | Optional crypto symbols. |
| `crypto_timeframe` | string | No | Defaults to `15m`. |
| `proxy_assets` | list[string] | No | Defaults to SPY, QQQ, GLD, GC=F. |
| `proxy_timeframe` | string | No | Defaults to `1d`. |
| `processed_feature_root` | path or null | No | Optional override for processed features. |
| `xau_options_oi_file_path` | path or null | No | Local CSV/Parquet XAU options OI file. |
| `require_optional_vendors` | list[`DataSourceProviderType`] | No | Optional vendors the user wants to inspect. |
| `requested_capabilities` | list[string] | No | Extra capabilities to validate and label. |
| `research_only_acknowledged` | bool | Yes | Must be true for first-run preflight. |

Validation rules:

- `research_only_acknowledged` must be true.
- Parent directory traversal is rejected for local paths.
- Absolute XAU local paths must stay inside allowed data roots.
- Forbidden credential or execution capability requests are rejected or flagged.
- Yahoo capability requests for OI, funding, IV, gold options OI, futures OI, or XAUUSD execution are labeled unsupported.

### DataSourcePreflightResult

Grouped result for data-source preflight.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `status` | `FirstEvidenceRunStatus` | Yes | Completed/partial/blocked/failed readiness. |
| `readiness` | `DataSourceReadiness` | Yes | Provider readiness snapshot. |
| `crypto_results` | list[object] | Yes | Per crypto asset readiness. |
| `proxy_results` | list[object] | Yes | Per proxy asset readiness. |
| `xau_result` | object or null | No | XAU local file readiness. |
| `optional_vendor_results` | list[object] | Yes | Optional paid provider readiness. |
| `unsupported_capabilities` | list[string] | Yes | Explicit unsupported capability labels. |
| `missing_data_actions` | list[`DataSourceMissingDataAction`] | Yes | Combined missing-data checklist. |
| `warnings` | list[string] | Yes | Non-blocking warnings. |
| `limitations` | list[string] | Yes | Source limitations. |

### FirstEvidenceRunRequest

Request to start the first evidence workflow.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string or null | No | Optional display name. |
| `preflight` | `DataSourcePreflightRequest` | Yes | Source readiness config. |
| `use_existing_research_report_ids` | list[string] | No | Optional feature 005 report references. |
| `use_existing_xau_report_id` | string or null | No | Optional feature 006 XAU report reference. |
| `run_when_partial` | bool | No | Allows partial runs when some workflows are blocked. Defaults true. |
| `research_only_acknowledged` | bool | Yes | Must be true. |

### FirstEvidenceRunResult

Response from the first evidence workflow wrapper.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `first_run_id` | string | Yes | Wrapper id for the onboarding first-run request. |
| `status` | `FirstEvidenceRunStatus` | Yes | Completed/partial/blocked/failed. |
| `execution_run_id` | string or null | No | Linked feature 007 run id when created. |
| `evidence_report_path` | string or null | No | Existing ignored report path. |
| `linked_research_report_ids` | list[string] | Yes | Feature 005 report ids referenced or created. |
| `linked_xau_report_ids` | list[string] | Yes | Feature 006 report ids referenced or created. |
| `preflight_result` | `DataSourcePreflightResult` | Yes | Readiness snapshot used for the run. |
| `missing_data_actions` | list[`DataSourceMissingDataAction`] | Yes | Visible blocked and optional actions. |
| `research_only_warnings` | list[string] | Yes | No execution/no claims warnings. |
| `limitations` | list[string] | Yes | Source limitations. |
| `created_at` | datetime | Yes | Run creation time. |

## Relationships

- `DataSourceReadiness` contains many `DataSourceProviderStatus` rows.
- `DataSourceProviderStatus` references one `DataSourceCapability`.
- `DataSourcePreflightResult` contains one `DataSourceReadiness` snapshot and many `DataSourceMissingDataAction` rows.
- `FirstEvidenceRunResult` references one `DataSourcePreflightResult` and optionally one feature 007 `execution_run_id`.
- Feature 007 remains the source of truth for final evidence summaries.

## Invariants

- Secret values are never serialized in any model.
- Optional paid providers can be missing without failing the public/local MVP.
- Missing required local/processed data remains visible and is not silently omitted.
- Yahoo Finance remains OHLCV/proxy-only.
- Generated data and reports remain under ignored local data paths.
- All warnings and limitations use research-only language and avoid profitability, predictive power, safety, or live-readiness claims.
