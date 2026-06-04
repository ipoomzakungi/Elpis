# Data Model: XAU Daily Structural Map Persistence And Sample Run

**Date**: 2026-06-04
**Feature**: 019-xau-daily-structural-map-persistence-and-sample-run

## Enums

### XauDailyStructuralMapArtifactType

- `metadata`
- `map_json`
- `map_markdown`
- `walls_json`

### XauDailyStructuralMapArtifactFormat

- `json`
- `markdown`

## Entities

### XauDailyStructuralMapArtifact

Fields:

- `artifact_type`
- `path`
- `format`
- `rows`

Validation:

- `path` must remain under `data/reports/xau_daily_structural_map/` or equivalent backend-local report root.

### XauDailyStructuralMapReportMetadata

Fields:

- `map_id`
- `source_kind`
- `session_date`
- `created_at`
- `source_report_ids`
- `expected_range_source`
- `basis_mapping_available`
- `session_open_available`
- `wall_count`
- `readiness`
- `signal_allowed`
- `limitation_count`
- `no_signal_reason_count`
- `artifacts`

Validation:

- `signal_allowed` must be false.
- Source report ids are normalized and deduplicated.

### XauDailyStructuralMapReportResult

Fields:

- `metadata`
- `daily_map`
- `artifacts`

Validation:

- Metadata map id must equal the daily map id.
- Artifact paths must be unique.

## Artifact Layout

```text
data/reports/xau_daily_structural_map/{map_id}/
|-- metadata.json
|-- map.json
|-- map.md
`-- walls.json
```

## State Rules

```text
persist map
  -> metadata.json summarizes map and artifacts
  -> map.json is canonical round-trip source
  -> walls.json preserves wall nulls
  -> map.md remains research-only

missing context
  -> saved as-is
  -> no-signal reasons stay visible
```
