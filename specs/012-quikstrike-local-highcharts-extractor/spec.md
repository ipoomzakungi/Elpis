# Feature Specification: QuikStrike Local Highcharts Extractor

**Feature Branch**: `012-quikstrike-local-highcharts-extractor`
**Created**: 2026-05-13
**Status**: Draft
**Input**: User description: "Add a local QuikStrike Highcharts extractor for XAU options research."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Gold Vol2Vol Chart Rows Locally (Priority: P1)

As an Elpis researcher with an authenticated QuikStrike browser session, I want to extract structured Gold options rows from the QuikStrike `QUIKOPTIONS VOL2VOL` chart after I manually log in and choose Gold, so that I can use the data as local research input without storing credentials or private session material.

**Why this priority**: This is the core value of the feature: turning the discovered browser-memory chart data into normalized local research rows while preserving the user's authentication boundary.

**Independent Test**: Can be tested with synthetic chart fixtures and a local browser-shape validation run that proves rows are extracted for the supported Gold Vol2Vol views without saving cookies, tokens, headers, viewstate values, HAR files, screenshots, or private full URLs.

**Acceptance Scenarios**:

1. **Given** a user-controlled authenticated QuikStrike browser session on `QUIKOPTIONS VOL2VOL` with `Metals -> Precious Metals -> Gold (OG|GC)` selected, **When** the researcher starts extraction, **Then** the system captures normalized rows for the selected supported views and records only allowed research data fields.
2. **Given** synthetic chart fixture data with Put, Call, Vol Settle, and Ranges series, **When** the extractor processes the fixture, **Then** it produces rows with product, option code, expiration, DTE, future reference price, view type, strike, strike id, option type, value, value type, and limitation notes.
3. **Given** a page that is not logged in or is not on the supported Gold Vol2Vol surface, **When** the researcher starts extraction, **Then** the system returns a local readiness error explaining the manual steps needed and does not attempt credential reuse or endpoint replay.

---

### User Story 2 - Validate Strike Mapping Before Research Use (Priority: P2)

As an Elpis researcher, I want strike mapping confidence to be checked before extracted QuikStrike rows are converted into XAU Vol-OI input, so that uncertain chart coordinates are not silently treated as reliable strike-level options data.

**Why this priority**: The discovery found strike-like chart coordinates and `StrikeId` metadata, but the feature must prevent downstream XAU wall analysis from using rows when strike mapping is ambiguous.

**Independent Test**: Can be tested with fixture cases where chart coordinates, strike ids, visible labels, or tooltip-derived labels agree, partially agree, or conflict.

**Acceptance Scenarios**:

1. **Given** extracted rows with chart x-values, `StrikeId` metadata, and matching visible or tooltip labels, **When** validation runs, **Then** the extraction is marked as confident enough for conversion.
2. **Given** extracted rows where strike-like x-values cannot be matched to visible labels, tooltip text, or strike metadata, **When** validation runs, **Then** the extraction is marked partial and conversion to XAU Vol-OI input is blocked.
3. **Given** extracted rows with separated Put and Call series, **When** validation runs, **Then** the system confirms option-side separation before allowing any compatible output.

---

### User Story 3 - Convert Validated Rows Into XAU Vol-OI Local Input (Priority: P3)

As an Elpis researcher, I want validated normalized QuikStrike rows to be converted into the existing XAU Vol-OI local input shape, so that the completed XAU Vol-OI Wall Engine and XAU Reaction Planner can inspect data from the local QuikStrike workflow without duplicating wall scoring logic.

**Why this priority**: Conversion makes the extracted data usable in the existing research stack, but it must depend on the extraction and validation steps being safe and complete.

**Independent Test**: Can be tested by converting a complete synthetic extraction into XAU Vol-OI compatible rows and verifying that incomplete or uncertain extraction results are rejected.

**Acceptance Scenarios**:

1. **Given** validated extracted rows covering supported view types with confident strike mapping, **When** the converter runs, **Then** intraday volume and EOD volume become volume-style fields, OI becomes open interest, OI Change becomes OI change, and Churn becomes churn or freshness context.
2. **Given** extracted rows missing required fields or marked as partial, **When** the converter runs, **Then** no XAU Vol-OI input file is produced and the report explains the blocker.
3. **Given** conversion succeeds, **When** the researcher reviews the output, **Then** the source limitations remain visible and the existing XAU Vol-OI wall scoring logic is not duplicated.

---

### User Story 4 - Inspect Local Extraction Status (Priority: P4)

As an Elpis researcher, I want the dashboard or data-source status view to show local QuikStrike extraction readiness, coverage, row counts, warnings, and generated local paths, so that I can see what was captured and what is missing before running downstream XAU research.

**Why this priority**: The extractor needs an inspection surface, but dashboard visibility is secondary to safe extraction, validation, and conversion.

**Independent Test**: Can be tested by loading a saved extraction report and confirming the UI shows readiness, supported view coverage, row counts, strike confidence, missing-view warnings, local file paths, and a research-only disclaimer.

**Acceptance Scenarios**:

1. **Given** a completed extraction report, **When** the researcher opens the inspection surface, **Then** the system shows view coverage for intraday volume, EOD volume, open interest, OI change, and churn.
2. **Given** a partial extraction report, **When** the researcher opens the inspection surface, **Then** missing views, strike mapping uncertainty, and conversion blockers are visible.
3. **Given** any extraction status is shown, **When** the researcher reviews it, **Then** the view clearly states that the workflow is local-only and research-only.

### Edge Cases

- The user is not logged in, the browser session has expired, or the page redirects to login.
- The browser is open but not on `QUIKOPTIONS VOL2VOL`.
- The selected product is not `Gold (OG|GC)`.
- One or more supported views produce no chart rows.
- Put/Call series are missing, merged, renamed, or not separable.
- Vol Settle or Ranges series are missing while Put/Call values exist.
- DTE, expiration, or future reference price cannot be parsed from visible page context.
- Strike mapping is only partially supported by chart coordinates and metadata.
- The page structure changes and the extractor can no longer identify supported view coverage.
- Any candidate data includes secret/session-like fields, private URLs, viewstate values, headers, cookies, screenshots, or HAR-style content.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a local-only QuikStrike extraction workflow that assumes the user manually logs in and manually navigates to the supported Gold Vol2Vol surface.
- **FR-002**: The system MUST reject or pause extraction when the active browser context is not authenticated, not on `QUIKOPTIONS VOL2VOL`, or not showing `Metals -> Precious Metals -> Gold (OG|GC)`.
- **FR-003**: The system MUST support these view types: `intraday_volume`, `eod_volume`, `open_interest`, `oi_change`, and `churn`.
- **FR-004**: The system MUST extract only normalized chart research rows and MUST NOT persist cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, or credential material.
- **FR-005**: Each normalized row MUST include capture timestamp, product, option product code, expiration, DTE, future reference price, view type, strike, strike id, option type, value, value type, source view, extraction warnings, and extraction limitations when available.
- **FR-006**: The system MUST include Vol Settle values, range labels, and sigma labels when available from the supported chart context.
- **FR-007**: The system MUST validate that each requested supported view produces rows or record a missing-view warning.
- **FR-008**: The system MUST validate Put/Call separation before any conversion into XAU Vol-OI compatible input.
- **FR-009**: The system MUST validate strike mapping by comparing chart x-values, strike metadata, visible labels, or tooltip-derived labels where possible.
- **FR-010**: The system MUST mark extraction as partial when strike mapping cannot be confidently validated.
- **FR-011**: The system MUST block conversion into XAU Vol-OI compatible input when extraction is partial, missing required fields, or has uncertain strike mapping.
- **FR-012**: The system MUST save allowed raw normalized rows under ignored local QuikStrike raw data paths, optional processed rows under ignored local processed paths, and extraction reports under ignored local report paths.
- **FR-013**: The system MUST provide an XAU Vol-OI converter that maps intraday volume and EOD volume into volume-style fields, OI into open interest, OI Change into OI change, and Churn into churn or freshness context.
- **FR-014**: The system MUST preserve QuikStrike source limitation notes in extracted rows, reports, converted rows, and inspection surfaces.
- **FR-015**: The system MUST NOT duplicate existing XAU Vol-OI wall scoring logic.
- **FR-016**: The system MUST expose local extraction readiness, last extraction status, view coverage, row counts, missing-view warnings, strike mapping confidence, generated local paths, and research-only disclaimers through an inspection surface.
- **FR-017**: The system MUST keep all generated QuikStrike raw, processed, and report files ignored and untracked by default.
- **FR-018**: The system MUST remain research-only and MUST NOT add live trading, paper trading, shadow trading, private trading keys, broker integration, real order execution, wallet/private-key handling, paid vendor integration, endpoint replay of ASP.NET POSTs, credential reuse, screenshot OCR, HAR capture, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.

### Key Entities *(include if feature involves data)*

- **QuikStrike Extraction Session**: A local research run against the user's current authenticated browser context. Tracks capture timestamp, supported view coverage, readiness state, warnings, limitations, and generated local artifact paths without storing session secrets.
- **QuikStrike View Snapshot**: The extracted chart context for one supported view. Includes product, option product code, expiration, DTE, future reference price, view type, row counts, series coverage, and extraction warnings.
- **QuikStrike Option Row**: One normalized Put or Call chart data row for a strike-like level. Includes strike, strike id, option type, value, value type, source view, optional vol settle or range context, and limitations.
- **Strike Mapping Validation Result**: The confidence assessment for mapping chart coordinates and metadata to actual strikes. Determines whether downstream conversion is allowed, partial, or blocked.
- **XAU Vol-OI Conversion Output**: A local input-compatible dataset derived from validated QuikStrike rows for the existing XAU Vol-OI workflow, with source limitations preserved.
- **Extraction Report**: A local research report summarizing extraction status, view coverage, row counts, warnings, limitations, conversion eligibility, and generated paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Synthetic Highcharts-style fixtures for all five supported views produce normalized QuikStrike rows with 100% of required fields present where fixture data provides them.
- **SC-002**: At least one validation case for each supported view confirms non-empty row output, Put/Call separation, DTE extraction, future reference price extraction, and value type assignment.
- **SC-003**: 100% of uncertain strike mapping fixtures are marked partial and blocked from automatic XAU Vol-OI conversion.
- **SC-004**: 100% of complete and confidently mapped fixture rows can be converted into XAU Vol-OI compatible local input without duplicating wall scoring behavior.
- **SC-005**: Secret/session persistence checks confirm that no cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, or credential material are written by the extractor.
- **SC-006**: Generated raw rows, processed rows, and extraction reports are written only to ignored local artifact paths and are not staged by default.
- **SC-007**: The inspection surface shows extraction readiness, last status, five-view coverage, row counts, strike mapping confidence, local paths, limitations, and a research-only disclaimer for completed and partial extraction reports.

## Assumptions

- The user has legitimate QuikStrike access and performs all login and product navigation manually in a local browser session.
- The supported QuikStrike target for this feature is limited to `QUIKOPTIONS VOL2VOL` and `Gold (OG|GC)`.
- This feature treats QuikStrike as a local browser research source, not as a public API or paid-vendor integration.
- Real browser extraction validation may inspect shape and allowed fields without persisting private session material or chart payloads outside ignored local artifacts.
- Existing XAU Vol-OI and XAU reaction features remain the downstream consumers; this feature only provides validated local input and inspection metadata.
- If QuikStrike page structure changes, the extractor should fail closed with actionable warnings instead of producing low-confidence research input.
