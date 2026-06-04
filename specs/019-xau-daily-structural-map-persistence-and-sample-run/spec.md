# Feature Specification: XAU Daily Structural Map Persistence And Sample Run

**Feature Branch**: `019-xau-daily-structural-map-persistence-and-sample-run`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: "Create Feature 019: xau-daily-structural-map-persistence-and-sample-run. Persist the Feature 018 daily structural map as a reproducible research artifact and add a small sample-run path for the 2026-06-02 XAU QuikStrike bundle. Keep it research-only and do not create signals or backtests."

## User Scenarios & Testing

### User Story 1 - Persist One Structural Map (Priority: P1)

As an XAU researcher, I want to save a daily structural map to local artifacts so that the exact expected range, basis mapping, wall rows, readiness state, and no-signal reasons can be reviewed later without rebuilding from memory.

**Why this priority**: Feature 018 builds the map in memory. Later forward outcomes need a stable `map_id` and artifact path before labels can be attached honestly.

**Independent Test**: Persist a synthetic full-context map and verify `metadata.json`, `map.json`, `map.md`, and `walls.json` are written under the ignored structural-map report path.

**Acceptance Scenarios**:

1. Given expected range, basis, session open, and walls are available, when the map is persisted, then metadata, map JSON, markdown, and wall artifacts are written with readiness `structural_map_ready`.
2. Given the saved map is reloaded from `map.json`, when it is validated, then it round-trips into `XauDailyStructuralMap`.
3. Given a complete map is saved, when metadata is inspected, then `signal_allowed` remains false.

### User Story 2 - Preserve Partial Maps As Artifacts (Priority: P2)

As an XAU researcher, I want maps with missing basis, missing expected range, or missing session open to still be saved so that missing context remains explicit rather than blocking evidence collection.

**Why this priority**: Partial maps are useful evidence, but only if nulls and missing reasons are preserved.

**Independent Test**: Persist maps with missing basis, missing expected range, and missing session open, then verify null fields and no-signal reasons survive in saved JSON.

**Acceptance Scenarios**:

1. Given basis is unavailable, when the map is saved, then spot-equivalent wall levels remain null and metadata records partial or blocked readiness.
2. Given expected range is unavailable, when the map is saved, then SD fields remain null and no-signal reasons include "Expected range unavailable."
3. Given session open is unavailable, when the map is saved, then readiness remains partial and no-signal reasons include "Session open unavailable."
4. Given optional OI change or volume is null, when walls are saved, then null remains null rather than zero.

### User Story 3 - Generate A Local Sample Run (Priority: P3)

As an XAU researcher, I want a testable helper that produces and persists one sample structural-map report from supplied expected-range, wall, basis, and session-open inputs so that a 2026-06-02 map can be generated without live CME access.

**Why this priority**: A sample-run path proves the map can become a reproducible artifact while avoiding browser/session material and before adding forward outcomes.

**Independent Test**: Call the sample-run helper with synthetic 2026-06-02 context and verify the returned map id, readiness, wall count, and artifact paths.

### Edge Cases

- Report id already exists.
- Report id or artifact filename contains path traversal.
- Basis is missing, blocked, or conflicting.
- Expected range snapshot is missing or unavailable.
- Session open is missing.
- Wall OI change or volume is null.
- Generated report artifacts exist locally but must remain ignored and untracked.
- Requests include buy/sell entries, alerts, execution, broker data, private keys, endpoint replay, ML, strategy backtests, profitability, prediction, safety, or live-readiness claims.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST persist a Feature 018 `XauDailyStructuralMap` under `data/reports/xau_daily_structural_map/{map_id}/`.
- **FR-002**: The persisted artifacts MUST include `metadata.json`, `map.json`, `map.md`, and `walls.json`.
- **FR-003**: Metadata MUST include map id, session date, created timestamp, source report ids used, expected-range source, basis mapping availability, session-open availability, wall count, readiness, `signal_allowed = false`, and limitation count.
- **FR-004**: `map.json` MUST round-trip into `XauDailyStructuralMap`.
- **FR-005**: `walls.json` MUST preserve nullable wall fields such as OI change and volume without converting null to zero.
- **FR-006**: Missing basis MUST keep spot-equivalent levels null and preserve the basis-unavailable no-signal reason.
- **FR-007**: Missing expected range MUST keep SD fields null and preserve the expected-range-unavailable no-signal reason.
- **FR-008**: Missing session open MUST preserve partial readiness and the session-open-unavailable no-signal reason.
- **FR-009**: The sample-run helper MUST build a map from supplied expected-range snapshot, walls, basis context or manual basis, optional session open, and output directory.
- **FR-010**: The sample-run helper MUST return artifact paths, map id, readiness, and wall count.
- **FR-011**: Report ids and artifact paths MUST stay under the structural-map report root and reject traversal.
- **FR-012**: The feature MUST NOT implement buy/sell signals, alerts, broker execution, auto trading, ML, strategy backtests, 2SD candidate classifiers, 3.5SD stops, PnL, order instructions, or position instructions.
- **FR-013**: The feature MUST NOT store cookies, headers, tokens, HAR files, screenshots, private URLs, credentials, broker data, wallet keys, or execution material.

### Key Entities

- **Structural Map Report Metadata**: A compact summary of the persisted map and source readiness.
- **Structural Map Artifact**: A local generated file reference under the ignored report path.
- **Structural Map Report Result**: The saved map plus metadata and artifact paths.
- **Sample Run Request**: Supplied session date, expiration, expected range, walls, basis context, session open, and output location.

## Success Criteria

- **SC-001**: A full-context map writes all required artifacts and reloads from `map.json`.
- **SC-002**: Missing-basis, missing-range, and missing-session-open maps are saved with nulls and no-signal reasons preserved.
- **SC-003**: Null OI-change and volume values remain null in saved wall artifacts in 100% of validation cases.
- **SC-004**: A sample-run helper produces a saved structural-map report for a 2026-06-02 synthetic input set without live CME access.
- **SC-005**: Generated artifacts are path-safe and remain under `data/reports/xau_daily_structural_map/`.
- **SC-006**: Review of output finds zero buy/sell, alert, execution, profitability, predictive-proof, safety, or live-readiness claims.

## Assumptions

- Feature 018 map builder remains the source of map readiness and no-signal semantics.
- The first sample run uses supplied local or synthetic inputs; it does not fetch CME, broker, or browser data.
- Generated reports are local research artifacts and are not committed.
- Forward outcomes require this stable map artifact and are deferred to a later feature.
