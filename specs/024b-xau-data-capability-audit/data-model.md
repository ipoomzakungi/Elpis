# Data Model: XAU Data Capability Audit

## Enums

### XauDataCapabilityAuditReadiness

- `complete`
- `partial`
- `blocked`

### XauDataCapabilityStatus

- `available`
- `partial`
- `unavailable`
- `blocked`

### XauDataCapabilityName

- `has_oi`
- `has_oi_change`
- `has_intraday_volume`
- `has_vol`
- `has_vol_chg`
- `has_future_chg`
- `has_dte`
- `has_future_reference`
- `has_native_sd`
- `has_delta`
- `has_gamma`
- `has_delta_ranges`
- `has_sd_ranges`
- `has_gex_possible`

### XauDataCapabilitySourceType

- `vol2vol`
- `matrix`
- `fusion`
- `xau_vol_oi`

## Entities

### XauDataCapabilityAuditRequest

- `reports_dir`
- `vol2vol_report_ids`
- `matrix_report_ids`
- `fusion_report_ids`
- `xau_vol_oi_report_ids`
- `max_reports_per_source`
- `research_only_acknowledged`

Validation:

- Report ID lists are normalized and deduplicated.
- `max_reports_per_source` is between 1 and 20.
- Research-only acknowledgement is required.

### XauDataCapabilitySourceSummary

- `source_type`
- `report_id`
- `status`
- `row_count`
- `artifact_paths`
- `limitations`

### XauDataCapabilityEvidence

- `source_type`
- `report_id`
- `field_names`
- `row_count`
- `non_null_count`
- `sample_values`

### XauDataCapabilityResult

- `capability`
- `status`
- `source_count`
- `row_count`
- `non_null_count`
- `evidence`
- `limitations`

### XauDataCapabilityAuditResult

- `audit_id`
- `created_at`
- `readiness`
- `source_reports`
- `capabilities`
- `missing_capabilities`
- `blocked_capabilities`
- `limitations`
- `no_signal_reasons`
- `research_only`
- `signal_allowed`

Validation:

- `signal_allowed` must be false.
- `research_only` must be true.
- No-signal reasons are required.

## Source Mapping Rules

```text
Vol2Vol value_type=open_interest
  -> has_oi

Vol2Vol value_type=oi_change
  -> has_oi_change

Vol2Vol value_type=intraday_volume
  -> has_intraday_volume

Vol2Vol vol_settle
  -> has_vol

Vol2Vol dte
  -> has_dte

Vol2Vol future_reference_price
  -> has_future_reference

Vol2Vol range_label/sigma_label or range_bands.cme_numeric_sd
  -> has_sd_ranges / has_native_sd

Matrix value_type=open_interest
  -> has_oi

Matrix value_type=oi_change
  -> has_oi_change

Matrix value_type=volume
  -> has_intraday_volume as partial

Matrix dte and future_reference_price
  -> has_dte / has_future_reference

Fusion expected_range_snapshot cme_numeric_*sd
  -> has_native_sd

Fusion expected_range_snapshot vol_settle/report_level_iv
  -> has_vol

XAU Vol-OI source rows open_interest, oi_change, implied_volatility,
days_to_expiry, underlying_futures_price, delta, gamma
  -> matching capabilities

XAU Vol-OI source rows volume
  -> has_intraday_volume as partial

gamma available + OI available
  -> has_gex_possible available

gamma missing or OI missing
  -> has_gex_possible blocked
```
