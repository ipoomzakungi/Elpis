# Feature Specification: QuikStrike Open Interest Matrix Extractor

**Feature Branch**: `codex/013-quikstrike-open-interest-matrix-extractor`  
**Created**: 2026-05-13  
**Status**: Draft  
**Input**: User description: "Create feature 013-quikstrike-open-interest-matrix-extractor."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Gold Open Interest Matrix Tables Locally (Priority: P1)

As an Elpis researcher with an authenticated local QuikStrike browser session, I want to extract structured Gold Open Interest Matrix rows after I manually log in and select Gold, so that I can use the matrix tables as local XAU options research input without storing credentials or session material.

**Why this priority**: This is the core value of the feature. The discovered Open Interest Matrix surface provides strike-by-expiration table data that can complement the completed Vol2Vol extraction and existing XAU Vol-OI research workflow.

**Independent Test**: Can be tested with synthetic HTML table fixtures for the supported matrix views and a local browser-shape validation run that proves only sanitized table data is captured.

**Acceptance Scenarios**:

1. **Given** a user-controlled authenticated QuikStrike browser session on the Open Interest Matrix surface with `Metals -> Precious Metals -> Gold (OG|GC)` selected, **When** the researcher starts extraction for the OI Matrix view, **Then** the system captures normalized rows with strike, expiration, option side, value, value type, and source limitations.
2. **Given** synthetic matrix table fixtures for OI, OI Change, and Volume, **When** the extractor processes the fixtures, **Then** it produces normalized rows for all supported views and records row counts, strike counts, expiry counts, and missing-cell warnings.
3. **Given** a page that is not logged in, not on the supported Open Interest Matrix surface, or not showing Gold, **When** the researcher starts extraction, **Then** the system returns a local readiness error and does not attempt credential reuse, endpoint replay, or private session capture.

---

### User Story 2 - Validate Table Mapping Before Conversion (Priority: P2)

As an Elpis researcher, I want matrix table structure to be validated before any conversion into XAU Vol-OI input, so that ambiguous rows, missing expirations, or missing strikes are not silently treated as usable strike-level options data.

**Why this priority**: Matrix tables can change labels, combine option sides, or contain blank cells. The feature must fail closed when core research fields cannot be determined.

**Independent Test**: Can be tested with table fixtures containing valid rows, blank cells, missing strikes, missing expiration headers, call/put columns, combined columns, and non-numeric values.

**Acceptance Scenarios**:

1. **Given** a matrix table with strike rows, expiration columns, and call/put subcolumns, **When** validation runs, **Then** the system confirms the table is structured enough for normalized research rows.
2. **Given** a matrix table with blank cells, **When** validation runs, **Then** the blanks are marked unavailable and are not treated as zero unless the table explicitly marks them as zero.
3. **Given** a matrix table where strike or expiration cannot be determined, **When** conversion is requested, **Then** conversion is blocked and the report explains the missing mapping.

---

### User Story 3 - Convert Valid Matrix Rows Into XAU Vol-OI Input (Priority: P3)

As an Elpis researcher, I want validated matrix rows to convert into the existing XAU Vol-OI local input shape, so that Open Interest Matrix data can feed the completed wall engine and reaction planner without duplicating wall scoring logic.

**Why this priority**: Conversion makes the extraction useful in the existing Elpis research chain while preserving the boundary between source extraction and downstream wall analysis.

**Independent Test**: Can be tested by converting complete synthetic OI, OI Change, and Volume matrix rows into XAU Vol-OI compatible rows and verifying that unsafe or incomplete rows are rejected.

**Acceptance Scenarios**:

1. **Given** validated OI Matrix rows, **When** conversion runs, **Then** the converted rows populate open interest fields and preserve strike, expiration, option side, source menu, and limitations.
2. **Given** validated OI Change Matrix rows, **When** conversion runs, **Then** the converted rows populate OI change fields and preserve missing-cell warnings.
3. **Given** validated Volume Matrix rows, **When** conversion runs, **Then** the converted rows populate volume fields and clearly label the value as matrix volume research data.

---

### User Story 4 - Inspect Matrix Extraction Status (Priority: P4)

As an Elpis researcher, I want the dashboard or data-source inspection surface to show matrix extraction status, coverage, warnings, conversion status, and generated local paths, so that I can decide whether the extracted table data is complete enough for downstream XAU research.

**Why this priority**: Visibility is needed for operational use, but it depends on extraction, validation, and conversion behavior being safe first.

**Independent Test**: Can be tested by loading saved extraction reports and confirming the inspection surface shows coverage and blockers for complete and partial matrix extractions.

**Acceptance Scenarios**:

1. **Given** a completed matrix extraction report, **When** the researcher opens the inspection surface, **Then** row count, strike count, expiry count, view coverage, conversion status, and generated local paths are visible.
2. **Given** a partial matrix extraction report, **When** the researcher opens the inspection surface, **Then** missing views, missing cells, mapping blockers, and conversion warnings are visible.
3. **Given** any matrix extraction status is displayed, **When** the researcher reviews it, **Then** the surface clearly states that the workflow is local-only and research-only.

### Edge Cases

- The user is not logged in, the session expires, or the browser redirects to a disclaimer or login screen.
- The selected page is not the Open Interest Matrix surface or the selected product is not `Gold (OG|GC)`.
- The Open Interest Matrix view is visible but has no data rows for the selected date or expiry set.
- Strike rows contain labels, separators, totals, subtotals, or non-numeric text that should not become strike rows.
- Expiration headers contain futures symbol, price, date, DTE, or combined labels in different visible formats.
- The table provides combined values but no call/put separation.
- The table provides call/put separation but one side has missing or blank cells.
- OI Change values are negative, parenthesized, signed, comma-formatted, or blank.
- Volume and OI cells contain zeros, blanks, dashes, or unavailable markers that must be distinguished.
- Duplicate strike, expiration, option side, and value type rows appear across repeated table sections.
- The table layout changes and the extractor cannot confidently identify strike rows or expiration columns.
- Any candidate input contains cookies, tokens, headers, viewstate values, HAR-like content, screenshots, private full URLs, credentials, or other session material.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a local-only QuikStrike Open Interest Matrix extraction workflow that assumes the user manually logs in and manually navigates to the supported Gold matrix surface.
- **FR-002**: The system MUST reject or pause extraction when the active browser context is not authenticated, not on the supported Open Interest Matrix surface, or not showing `Metals -> Precious Metals -> Gold (OG|GC)`.
- **FR-003**: The system MUST support these matrix view types: `open_interest_matrix`, `oi_change_matrix`, and `volume_matrix`.
- **FR-004**: The system MUST extract only sanitized table research data and MUST NOT persist cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, credential material, or endpoint replay payloads.
- **FR-005**: Each normalized matrix row MUST include capture timestamp, product, option product code, futures symbol when available, source menu, view type, strike, expiration, DTE when available, option type, value, value type, table row label, table column label, extraction warnings, and extraction limitations.
- **FR-006**: The system MUST validate table presence, strike-row presence, expiration-column presence, and numeric value parsing before producing a completed extraction status.
- **FR-007**: The system MUST validate call/put separation when the table provides option-side subcolumns and MUST preserve `combined` as the option type only when the table explicitly provides combined values.
- **FR-008**: The system MUST mark blank, dash, and unavailable cells as unavailable and MUST NOT treat them as zero unless the visible table value is explicitly zero.
- **FR-009**: The system MUST preserve negative and signed OI Change values when the table provides them.
- **FR-010**: The system MUST record view coverage, row count, strike count, expiry count, missing-cell count, and duplicate-row warnings for every extraction report.
- **FR-011**: The system MUST block XAU Vol-OI conversion when strike or expiration cannot be determined for required rows.
- **FR-012**: The system MUST support XAU Vol-OI compatible conversion where OI Matrix maps to open interest, OI Change Matrix maps to OI change, and Volume Matrix maps to volume.
- **FR-013**: The system MUST preserve source menu, view type, option side, expiration metadata, missing-cell warnings, and source limitations in converted rows.
- **FR-014**: The system MUST NOT duplicate existing XAU Vol-OI wall scoring logic.
- **FR-015**: The system MUST save allowed normalized rows under ignored `data/raw/quikstrike_matrix/`, optional processed rows under ignored `data/processed/quikstrike_matrix/`, and extraction reports under ignored `data/reports/quikstrike_matrix/`.
- **FR-016**: The system MUST expose matrix extraction status, row count, strike count, expiry count, view coverage, missing-cell warnings, conversion status, generated local paths, and research-only disclaimers through an inspection surface.
- **FR-017**: The system MUST keep all generated matrix raw, processed, and report files ignored and untracked by default.
- **FR-018**: The system MUST remain research-only and MUST NOT add live trading, paper trading, shadow trading, private trading keys, broker integration, real execution, wallet/private-key handling, paid vendor integration, endpoint replay, credential reuse, cookie/session/token storage, HAR capture, screenshot OCR, browser automation beyond local user-controlled extraction, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- **FR-019**: The system MUST NOT emit buy/sell execution signals or claim profitability, predictive power, safety, or live readiness from extracted matrix data.

### Key Entities *(include if feature involves data)*

- **QuikStrike Matrix Extraction Session**: A local research run against the user's current authenticated browser context. Tracks capture timestamp, selected product, selected matrix views, readiness state, warnings, limitations, and generated artifact paths without storing session secrets.
- **QuikStrike Matrix View Snapshot**: The sanitized table context for one supported matrix view. Includes source menu, view type, table labels, row and column coverage, value type, warnings, and limitations.
- **QuikStrike Matrix Cell Row**: One normalized research row derived from a matrix cell. Includes strike, expiration, optional DTE, option type, value, value type, table row label, table column label, and missing-cell state.
- **Matrix Mapping Validation Result**: The confidence assessment for table presence, strike mapping, expiration mapping, option-side mapping, numeric parsing, missing cells, and duplicate handling. Determines whether conversion is allowed or blocked.
- **XAU Vol-OI Matrix Conversion Output**: A local input-compatible dataset derived from validated matrix rows for the existing XAU Vol-OI workflow, with source limitations and matrix metadata preserved.
- **Matrix Extraction Report**: A local research report summarizing extraction status, view coverage, row counts, strike and expiry counts, missing cells, warnings, limitations, conversion eligibility, and generated paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Synthetic HTML table fixtures for OI Matrix, OI Change Matrix, and Volume Matrix each produce normalized rows with 100% of required fields present where fixture data provides them.
- **SC-002**: Validation fixtures confirm that missing strikes, missing expirations, unsupported table layouts, and non-numeric required values block conversion in 100% of tested cases.
- **SC-003**: Blank, dash, and unavailable cells are preserved as unavailable and are never converted to zero in 100% of missing-cell test cases.
- **SC-004**: Valid synthetic matrix rows convert into XAU Vol-OI compatible research rows with correct open interest, OI change, and volume field mapping.
- **SC-005**: Secret/session persistence checks confirm that no cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, credentials, or endpoint replay payloads are written by the extractor.
- **SC-006**: Generated raw rows, processed rows, and extraction reports are written only to ignored local artifact paths and are not staged by default.
- **SC-007**: The inspection surface shows extraction status, row count, strike count, expiry count, view coverage, missing-cell warnings, conversion status, generated local paths, limitations, and a research-only disclaimer for completed and partial reports.

## Assumptions

- The user has legitimate QuikStrike access and performs all login and product navigation manually in a local browser session.
- The supported product for this feature is `Metals -> Precious Metals -> Gold (OG|GC)`.
- The initial supported matrix views are Open Interest OI Matrix, OI Change Matrix, and Volume Matrix; other discovered menus are future scope.
- The Volume Matrix is treated as volume-style research input and must be labeled with source limitations.
- Missing cells mean unavailable, not zero, unless the table visibly contains an explicit numeric zero.
- Existing XAU Vol-OI and XAU reaction features remain downstream consumers; this feature provides validated local input and inspection metadata only.
- If the QuikStrike table structure changes, the extractor should fail closed with actionable warnings instead of producing low-confidence research input.
