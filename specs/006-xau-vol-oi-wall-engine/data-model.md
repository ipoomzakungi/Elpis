# Data Model: XAU Vol-OI Wall Engine

**Date**: 2026-05-01  
**Feature**: 006-xau-vol-oi-wall-engine

## Entities

### XauVolOiReportRequest

Represents one XAU wall analysis request.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| options_oi_file_path | string | Local CSV/Parquet source file | Required, safe local research path |
| session_date | date/null | Selected report date/session | Optional; derived from file when absent |
| spot_reference | XauReferencePrice/null | XAUUSD spot or proxy reference | Required unless source rows include valid spot price |
| futures_reference | XauReferencePrice/null | Gold futures reference | Required unless source rows include valid futures price |
| manual_basis | decimal/null | Explicit basis override | Optional; must be labeled manual |
| volatility_snapshot | XauVolatilitySnapshot/null | IV/realized/manual range inputs | Optional |
| include_2sd_range | boolean | Whether to compute 2SD stress range when possible | Defaults false |
| min_wall_score | decimal | Minimum score for top wall display | >= 0 |
| report_format | enum | `json`, `markdown`, or `both` | Defaults `both` |

### XauReferencePrice

Represents a spot, proxy, or futures price reference.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| source | string | Source label such as XAUUSD spot, GC=F, GLD, manual | Required |
| symbol | string | Reference symbol | Required |
| price | decimal | Reference price | > 0 |
| timestamp | datetime/null | Reference timestamp | Optional |
| reference_type | enum | `spot`, `proxy`, `futures`, or `manual` | Required |
| freshness_status | enum | `fresh`, `stale`, `unknown` | Required |
| notes | string[] | Source limitations | Optional |

### XauBasisSnapshot

Records basis calculation and mapping readiness.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| basis | decimal/null | Futures price minus spot/proxy price | Null when unavailable |
| basis_source | enum | `computed`, `manual`, or `unavailable` | Required |
| futures_reference | XauReferencePrice/null | Futures reference used | Optional |
| spot_reference | XauReferencePrice/null | Spot/proxy reference used | Optional |
| timestamp_alignment_status | enum | `aligned`, `mismatched`, `unknown` | Required |
| mapping_available | boolean | Whether spot-equivalent mapping can run | Required |
| notes | string[] | Basis warnings and limitations | Optional |

### XauOptionsOiRow

Normalized options OI source row.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| source_row_id | string | Stable row identifier | Required |
| timestamp | datetime | Source date/session timestamp | Required |
| expiry | date | Option expiry | Required |
| days_to_expiry | integer | Days from session to expiry | >= 0 |
| strike | decimal | Futures/options strike | > 0 |
| option_type | enum | `call`, `put`, or `unknown` | Required |
| open_interest | decimal | Strike open interest | >= 0 |
| oi_change | decimal/null | Recent OI change | Optional |
| volume | decimal/null | Intraday volume | Optional |
| implied_volatility | decimal/null | IV as normalized annualized decimal | Optional |
| underlying_futures_price | decimal/null | Futures reference in source row | Optional |
| xauusd_spot_price | decimal/null | Spot reference in source row | Optional |
| delta | decimal/null | Optional option delta | Optional |
| gamma | decimal/null | Optional option gamma | Optional |
| validation_notes | string[] | Row-level warnings | Optional |

### XauVolatilitySnapshot

Represents available range inputs.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| implied_volatility | decimal/null | IV normalized as annualized decimal | Optional |
| realized_volatility | decimal/null | Realized volatility estimate | Optional |
| manual_expected_move | decimal/null | Manually imported expected move | Optional |
| source | enum | `iv`, `realized_volatility`, `manual`, or `unavailable` | Required |
| days_to_expiry | integer/null | Days used for annualized move | Required for IV/realized ranges |
| notes | string[] | Volatility source limitations | Optional |

### XauExpectedRange

Represents expected move and range outputs.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| source | enum | `iv`, `realized_volatility`, `manual`, or `unavailable` | Required |
| reference_price | decimal/null | Price used for range center | Optional |
| expected_move | decimal/null | 1SD expected move | Null when unavailable |
| lower_1sd | decimal/null | Lower 1SD bound | Null when unavailable |
| upper_1sd | decimal/null | Upper 1SD bound | Null when unavailable |
| lower_2sd | decimal/null | Optional lower 2SD bound | Optional |
| upper_2sd | decimal/null | Optional upper 2SD bound | Optional |
| days_to_expiry | integer/null | Expiry horizon | Optional |
| unavailable_reason | string/null | Reason range cannot be computed | Required when unavailable |
| notes | string[] | Range interpretation notes | Optional |

### XauOiWall

Represents a basis-adjusted wall level.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| wall_id | string | Stable wall id | Required |
| expiry | date | Source expiry | Required |
| strike | decimal | Original futures strike | > 0 |
| spot_equivalent_level | decimal/null | Basis-adjusted level | Null when basis unavailable |
| basis | decimal/null | Basis used for mapping | Optional |
| option_type | enum | `call`, `put`, `mixed`, or `unknown` | Required |
| open_interest | decimal | Wall OI | >= 0 |
| total_expiry_open_interest | decimal | Expiry/window total OI | > 0 |
| oi_share | decimal | Strike OI divided by total OI | 0 to 1 |
| expiry_weight | decimal | Near-expiry weight | >= 0 |
| freshness_factor | decimal | Activity freshness score | >= 0 |
| wall_score | decimal | Transparent score | >= 0 |
| freshness_status | enum | `confirmed`, `neutral`, `stale`, or `unavailable` | Required |
| notes | string[] | Score and source notes | Optional |
| limitations | string[] | Missing data limitations | Optional |

### XauZone

Represents a classified research zone.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| zone_id | string | Stable zone id | Required |
| zone_type | enum | `support_candidate`, `resistance_candidate`, `pin_risk_zone`, `squeeze_risk_zone`, `breakout_candidate`, `reversal_candidate`, or `no_trade_zone` | Required |
| level | decimal/null | Central zone level | Optional |
| lower_bound | decimal/null | Lower bound when zone has range | Optional |
| upper_bound | decimal/null | Upper bound when zone has range | Optional |
| linked_wall_ids | string[] | Wall ids supporting the zone | Optional |
| wall_score | decimal/null | Representative wall score | Optional |
| pin_risk_score | decimal/null | Pin-risk score | Optional |
| squeeze_risk_score | decimal/null | Squeeze-risk score | Optional |
| confidence | enum | `high`, `medium`, `low`, or `unavailable` | Required |
| no_trade_warning | boolean | Whether zone should be treated as no-trade due to evidence quality | Required |
| notes | string[] | Classification explanation | Required |
| limitations | string[] | Source or data limitations | Optional |

### XauVolOiReport

Persisted report.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| report_id | string | Filesystem-safe report id | Required, unique |
| status | enum | `completed`, `partial`, or `blocked` | Required |
| created_at | datetime | Creation timestamp | Required |
| session_date | date/null | Analysis session | Optional |
| request | XauVolOiReportRequest | Normalized request | Required |
| basis_snapshot | XauBasisSnapshot | Basis result | Required |
| expected_range | XauExpectedRange | Range result | Required |
| source_row_count | integer | Imported row count | >= 0 |
| accepted_row_count | integer | Valid row count | >= 0 |
| rejected_row_count | integer | Invalid row count | >= 0 |
| walls | XauOiWall[] | Wall table | Optional |
| zones | XauZone[] | Zone table | Optional |
| warnings | string[] | Report warnings | Optional |
| limitations | string[] | Research-only and source limitations | Required |
| artifacts | ReportArtifact[] | Generated files | Required |

### XauVolOiReportSummary

List row for saved reports.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| report_id | string | Report identifier | Required |
| status | enum | `completed`, `partial`, or `blocked` | Required |
| created_at | datetime | Creation timestamp | Required |
| session_date | date/null | Analysis session | Optional |
| source_row_count | integer | Imported rows | >= 0 |
| wall_count | integer | Persisted wall rows | >= 0 |
| zone_count | integer | Persisted zone rows | >= 0 |
| warning_count | integer | Warning count | >= 0 |

## Relationships

```text
XauVolOiReportRequest (1) -> (0..many) XauOptionsOiRow
XauVolOiReportRequest (1) -> (0..1) XauBasisSnapshot
XauBasisSnapshot (1) -> (many) XauOiWall
XauVolatilitySnapshot (1) -> (0..1) XauExpectedRange
XauOiWall (many) -> (many) XauZone
XauVolOiReport (1) -> (many) XauOiWall
XauVolOiReport (1) -> (many) XauZone
XauVolOiReport (1) -> (many) ReportArtifact
```

## Validation Rules

- Local options OI files must contain date or timestamp, expiry, strike, option_type, and open_interest.
- Optional columns are accepted only when parseable: oi_change, volume, implied_volatility, underlying_futures_price, xauusd_spot_price, delta, gamma.
- Option type values normalize to call, put, or unknown; invalid values produce validation notes.
- Strike and open interest must be numeric; negative open interest is invalid.
- Expiry must parse to a date and must not be before the selected session without a warning or rejection.
- A basis snapshot is mapping-available only when manual basis exists or both futures and spot/proxy references are valid.
- IV-based range is unavailable when IV or days-to-expiry is missing.
- Yahoo Finance and proxy references cannot satisfy options OI or IV requirements.
- Generated reports and imported datasets must remain ignored and untracked.
- Reports must not claim profitability, predictive power, safety, or live readiness.
