# Feature Specification: XAU Real Structural Map From Bundle

**Feature Branch**: `020a-xau-real-structural-map-from-bundle`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: "Create Feature 020A: xau-real-structural-map-from-bundle. Build an adapter/service that reads existing saved XAU QuikStrike/XAU Vol-OI bundle artifacts and generates a persisted XauDailyStructuralMap using the Feature 019 report store. Keep it research-only."

## User Scenarios & Testing

### User Story 1 - Generate One Local Bundle Map (Priority: P1)

As an XAU researcher, I want to point the system at saved QuikStrike/XAU Vol-OI report artifacts so that a real local bundle can produce the same persisted daily structural-map artifacts that Feature 019 created from synthetic inputs.

**Why this priority**: Feature 019 proves persistence only with synthetic context. Forward outcomes should attach to a map generated from saved local bundle data, not a fabricated sample.

**Independent Test**: Use temporary bundle-shaped fixtures containing report JSON, wall rows, expected range, basis inputs, and session open, then verify the persisted map is ready and round-trips through `map.json`.

**Acceptance Scenarios**:

1. Given report JSON, wall rows, Feature 017 expected range, basis, and session open are available, when the adapter runs, then `metadata.json`, `map.json`, `map.md`, and `walls.json` are written and the map readiness is `structural_map_ready`.
2. Given a complete bundle map is written, when `map.json` is read, then it validates back into `XauDailyStructuralMap`.
3. Given the map is complete, when the payload is inspected, then `signal_allowed` remains false.

### User Story 2 - Preserve Missing Context Without Fabrication (Priority: P2)

As an XAU researcher, I want missing basis, expected range, range-label-only context, and null wall fields to survive bundle generation so that the map shows uncertainty instead of inventing values.

**Why this priority**: Feature 017 and Feature 018 require range labels, per-strike IV, missing basis, and blank cells to remain explicit blockers or limitations.

**Independent Test**: Run the adapter with missing basis, missing expected range, range-label-only report context, and null OI-change or volume fields.

**Acceptance Scenarios**:

1. Given basis inputs are unavailable, when the adapter runs, then spot-equivalent wall levels stay null and no-signal reasons include basis unavailable.
2. Given expected range fields are unavailable, when the adapter runs, then SD fields stay null and no-signal reasons include expected range unavailable.
3. Given only `range_label` exists, when the adapter runs, then no numeric SD bands are created.
4. Given wall OI-change or volume fields are null, missing, or blank, when the adapter writes `walls.json`, then they remain null and are not converted to zero.

### User Story 3 - Fall Back From Missing Parquet Walls (Priority: P3)

As an XAU researcher, I want the adapter to load parquet wall rows when available and fall back to embedded report JSON walls when parquet is absent so that local bundle differences do not block map creation.

**Why this priority**: Saved bundles may contain `04_xau_vol_oi_report_walls.parquet`, embedded wall rows, or no wall rows yet. All cases should produce auditable map artifacts with limitations.

**Independent Test**: Run with missing parquet and embedded walls, then with no wall rows, and verify persistence still occurs.

## Edge Cases

- `walls_path` is provided but does not exist.
- Report JSON is a composed wrapper with `report`, `walls`, `basis_snapshot`, and `expected_range` keys.
- Report JSON is a direct model-like payload.
- Wall rows omit `total_expiry_open_interest`, `oi_share`, `expiry_weight`, or `freshness_factor`.
- Manual basis is supplied without enough reference prices.
- Reference-price basis is supplied but one reference is missing.
- `range_label` exists without numeric SD-band fields.
- Per-strike IV exists without report-level IV or fractional DTE.
- No wall rows are available.
- Output map id collides with an existing report directory.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a bundle adapter function that accepts local paths for XAU Vol-OI report JSON, optional wall rows, optional fused rows, basis inputs, session open, output root, and overwrite policy.
- **FR-002**: The adapter MUST support report JSON shaped as either the direct XAU Vol-OI report payload or a composed wrapper containing a nested `report` payload.
- **FR-003**: The adapter MUST load wall rows from parquet when an existing `walls_path` is provided.
- **FR-004**: If parquet wall rows are unavailable, the adapter MUST fall back to embedded wall rows in the report JSON when present.
- **FR-005**: If no wall rows are available, the adapter MUST still persist a map with `wall_count = 0` and a visible limitation.
- **FR-006**: Manual basis MUST take precedence over computed basis.
- **FR-007**: If manual basis is absent but GC and traded reference prices are present, the adapter MUST compute basis through existing basis logic.
- **FR-008**: If basis cannot be resolved, the adapter MUST preserve unavailable mapping and MUST NOT fake spot-equivalent levels.
- **FR-009**: The adapter MUST use Feature 017 expected-range snapshot fields when present.
- **FR-010**: The adapter MUST NOT convert `range_label` into numeric SD fields.
- **FR-011**: The adapter MUST NOT promote per-strike IV into report-level expected range unless the Feature 017 builder has all valid report-level inputs.
- **FR-012**: The adapter MUST preserve nullable `oi_change` and `volume` values in persisted walls.
- **FR-013**: The adapter MUST persist maps using the Feature 019 structural-map report store and write `metadata.json`, `map.json`, `map.md`, and `walls.json`.
- **FR-014**: Persisted metadata MUST use an allowed source kind and include limitations stating that local imported options data must be independently verified.
- **FR-015**: `signal_allowed` MUST remain false in every output.
- **FR-016**: The feature MUST NOT implement forward outcome labels, reaction classifiers, strategy entries, 2SD entries, 3.5SD stops, PnL, alerts, execution, broker integration, private keys, ML, or backtests.

### Key Entities

- **Bundle Adapter Request**: Function arguments describing local report paths, reference prices, basis, session open, output root, and overwrite policy.
- **Bundle Report Payload**: The direct or wrapped XAU Vol-OI report JSON containing expected range, limitations, and optional wall rows.
- **Bundle Wall Row**: One wall row loaded from parquet or embedded JSON and normalized into `XauOiWall` plus nullable OI-change and volume maps.
- **Persisted Structural Map Result**: The Feature 019 report result returned after writing local artifacts.

## Success Criteria

- **SC-001**: Full-context bundle tests write all required artifacts, produce `structural_map_ready`, map wall spot levels, and round-trip `map.json`.
- **SC-002**: Missing-basis tests keep spot-equivalent levels null and preserve the basis-unavailable no-signal reason.
- **SC-003**: Missing-expected-range tests keep SD fields null and preserve the expected-range-unavailable no-signal reason.
- **SC-004**: Range-label-only tests create no numeric SD fields.
- **SC-005**: Null OI-change and volume remain JSON `null` in `walls.json`.
- **SC-006**: Missing parquet fallback works with embedded walls, and no-wall bundles persist with `wall_count = 0` plus limitations.
- **SC-007**: Review of code, docs, and output finds zero buy/sell, alert, execution, profitability, predictive-proof, safety, or live-readiness claims.

## Assumptions

- Exact 2026-06-02 bundle files may not exist in the tracked repo; tests may use temporary bundle-shaped fixtures.
- Feature 019 report store remains the canonical writer for structural-map artifacts.
- Feature 018 builder remains the source of readiness and no-signal semantics.
- Local imported options data may be incomplete or unaudited and must carry limitations.
