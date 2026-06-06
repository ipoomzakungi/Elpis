# Contract: XAU Daily Structural Map Report Artifacts

**Feature**: 019-xau-daily-structural-map-persistence-and-sample-run

This contract documents local artifact payloads. It is not a broker, alert, order, execution, or live-trading contract.

## Directory

```text
data/reports/xau_daily_structural_map/xau_daily_structural_map_2026-06-02_OG1M6/
```

## metadata.json

```json
{
  "map_id": "xau_daily_structural_map_2026-06-02_OG1M6",
  "source_kind": "operational",
  "session_date": "2026-06-02",
  "created_at": "2026-06-04T12:00:00Z",
  "source_report_ids": ["vol2vol_20260604", "xau_vol_oi_20260602"],
  "expected_range_source": "cme_native",
  "basis_mapping_available": true,
  "session_open_available": true,
  "wall_count": 1,
  "readiness": "structural_map_ready",
  "signal_allowed": false,
  "limitation_count": 0,
  "no_signal_reason_count": 1,
  "artifacts": []
}
```

## map.json

Contains the complete Feature 018 `XauDailyStructuralMap` payload and must load back into that schema.

## walls.json

Contains the map wall array. Nullable fields such as `oi_change` and `volume` remain JSON `null`.

## map.md

Contains a short research-only readout:

- map id
- session date
- readiness
- wall count
- expected-range source
- basis availability
- session-open availability
- no-signal reasons
- limitations
- artifact paths

## Contract Rules

- `signal_allowed` is always false.
- Missing basis, expected range, or session open must remain visible.
- Generated files stay under `data/reports/xau_daily_structural_map/`.
- Payloads must not include cookies, tokens, headers, HAR files, screenshots, credentials, private URLs, endpoint replay material, broker fields, wallet fields, order fields, or execution fields.
