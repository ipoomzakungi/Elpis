# Data Model: XAU Real Structural Map From Bundle

**Date**: 2026-06-04
**Feature**: 020a-xau-real-structural-map-from-bundle

## Adapter Function

```python
generate_xau_daily_structural_map_from_bundle(
    *,
    map_id: str,
    session_date: date,
    xau_vol_oi_report_path: Path,
    walls_path: Path | None = None,
    fused_rows_path: Path | None = None,
    traded_instrument: str,
    traded_reference_price: float | None,
    gc_reference_price: float | None,
    manual_basis: float | None,
    session_open_price: float | None,
    session_open_source: str | None,
    output_root: Path | None = None,
    overwrite_allowed: bool = False,
) -> XauDailyStructuralMapReportResult
```

## Inputs

### Bundle Report Payload

Supported forms:

- direct XAU Vol-OI report payload
- composed report JSON with nested `report`

Relevant fields:

- `report_id`
- `source_kind`
- `session_date`
- `expected_range_snapshot`
- `expected_range`
- `basis_snapshot`
- `walls`
- `limitations`

### Bundle Wall Row

Accepted fields:

- `wall_id`
- `expiry`
- `expiration_code`
- `strike`
- `option_type` or `wall_type`
- `open_interest`
- `total_expiry_open_interest`
- `oi_share`
- `expiry_weight`
- `freshness_factor`
- `wall_score`
- `freshness_status` or `freshness_state`
- `oi_change`
- `volume`
- `notes`
- `limitations`

When total expiry OI or share is missing, the adapter calculates a conservative row-total denominator from loaded wall rows only. This does not create OI-change or volume values.

## Output

The adapter returns the existing Feature 019 result:

- `metadata`
- `daily_map`
- `artifacts`

Artifacts:

```text
data/reports/xau_daily_structural_map/{map_id}/
|-- metadata.json
|-- map.json
|-- map.md
`-- walls.json
```

## State Rules

```text
manual basis present
  -> manual basis wins

manual basis missing and both references present
  -> compute basis

missing basis
  -> spot-equivalent levels null

expected-range snapshot present
  -> use snapshot

range_label only
  -> unavailable expected-range snapshot with limitation

missing wall parquet
  -> fallback to embedded report walls

no wall rows
  -> persist map with wall_count = 0 and limitation
```
