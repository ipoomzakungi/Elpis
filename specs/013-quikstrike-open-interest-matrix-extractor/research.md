# Research: QuikStrike Open Interest Matrix Extractor

**Date**: 2026-05-13
**Feature**: 013-quikstrike-open-interest-matrix-extractor

## Decision: Use sanitized HTML table snapshots as the primary source

**Rationale**: Private discovery found the Open Interest Matrix / Heatmap views expose useful HTML tables with strike rows, expiration columns, and call/put subcolumns for OI, OI Change, and Volume. This is the most direct structured surface after feature 012's Vol2Vol Highcharts extractor.

**Alternatives considered**:

- Highcharts memory extraction: not suitable for the matrix MVP because these target views are table based.
- Endpoint replay: rejected because it risks viewstate/session payload handling and violates the local-only boundary.
- Screenshot OCR: rejected because the table is machine-readable and OCR would add fragility and privacy risk.

## Decision: Keep this feature separate from `quikstrike`

**Rationale**: Feature 012 parses Highcharts chart objects. Matrix extraction requires table-specific header grouping, row/column span handling, blank-cell handling, and expiration-column mapping. A focused `quikstrike_matrix` package avoids overloading the chart parser with table assumptions.

**Alternatives considered**:

- Extend feature 012 modules directly: rejected because chart-series point mapping and matrix table parsing have different validation gates.
- Create a broad QuikStrike umbrella refactor: rejected because the user explicitly requested no architecture redesign.

## Decision: Support three MVP views only

**Rationale**: The discovered high-value matrix views are OI Matrix, OI Change Matrix, and Volume Matrix. Together they map cleanly to existing XAU Vol-OI fields: open interest, OI change, and volume.

**Alternatives considered**:

- Include Open Interest Profile, Settlements, Vol Tools, and This Week in Options now: rejected as broader scope. They are useful future context sources but not required for strike-by-expiration wall input.
- Include Most Active Strikes now: rejected because discovery did not confirm a stable ranked strike table in this pass.

## Decision: Treat blanks and unavailable cells as unavailable, never zero

**Rationale**: Matrix tables often use blanks or dashes for unavailable cells. Treating them as zero would materially change wall calculations and could create false OI/volume gaps.

**Alternatives considered**:

- Convert blanks to zero for easier aggregation: rejected because it hides missing data.
- Drop blank cells entirely without metadata: rejected because reports need missing-cell counts and warnings.

## Decision: Require strike and expiration mapping before conversion

**Rationale**: The XAU Vol-OI workflow needs strike-level and expiry-level rows. If either field cannot be determined, conversion must be blocked to avoid creating misleading downstream research input.

**Alternatives considered**:

- Allow conversion with missing expiration when only a table column index is known: rejected because multi-expiry matrix data would become ambiguous.
- Use one selected expiry from page context for all columns: rejected unless the table itself only has one clearly labeled expiration.

## Decision: Use optional local API/report endpoints for sanitized payloads only

**Rationale**: Local API endpoints make fixture smoke tests and dashboard inspection consistent with existing Elpis patterns. The routes should accept sanitized metadata/table snapshots and saved extraction ids only.

**Alternatives considered**:

- Browser automation endpoints: rejected because login/navigation remains user-controlled and no session material should be routed through the API.
- No API: possible, but the dashboard/status requirement is easier and more consistent with saved report endpoints.

## Decision: Add only a local browser adapter skeleton

**Rationale**: The current implementation slice should define safe boundaries for later local extraction without storing cookies, headers, viewstate, HAR files, screenshots, credentials, or private URLs. Full browser automation is not part of the planning target.

**Alternatives considered**:

- Full browser automation now: rejected because the feature should first prove sanitized table extraction and conversion using fixtures.
- Credential-based login automation: rejected by the privacy/security rules.

## Decision: Keep generated matrix artifacts in distinct ignored paths

**Rationale**: Matrix data is separate from feature 012 Vol2Vol artifacts and should be easy to inspect, guard, and clean independently.

**Alternatives considered**:

- Reuse `data/raw/quikstrike/`: rejected because row shapes and source surfaces differ.
- Commit sanitized examples from real QuikStrike tables: rejected because generated QuikStrike data must remain local and untracked.
