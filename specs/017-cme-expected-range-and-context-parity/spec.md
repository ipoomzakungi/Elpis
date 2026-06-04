# Feature Specification: CME Expected Range And Context Parity

**Feature Branch**: `017-cme-expected-range-and-context-parity`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: "Create feature 017-cme-expected-range-and-context-parity. Promote the current CME/XAU pipeline from wall map only to daily structural map ready by persisting missing CME expected-range and context fields through extraction, fusion, XAU Vol-OI report, and forward journal. Keep it research-only and do not create trading signals."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture Expected Range Context (Priority: P1)

As an XAU researcher, I want CME expected-range context to be preserved with the same point-in-time metadata as the existing QuikStrike rows so that I can distinguish exact CME-native numeric ranges from local IV-derived fallback ranges.

**Why this priority**: The current wall map can show OI structure, but it cannot prove Vol2Vol expected-range parity without numeric SD bands, report-level IV, fractional DTE, release status, and source timing.

**Independent Test**: Can be tested with synthetic expected-range inputs where native numeric bands are present, missing, or reduced to only range labels.

**Acceptance Scenarios**:

1. **Given** CME-native numeric 1SD, 2SD, and 3SD bands are available, **When** expected range context is captured, **Then** the result records CME-native source, numeric distances, upper/lower bands, reference futures price, report-level IV, fractional DTE, release timestamp, and source status.
2. **Given** CME-native numeric bands are missing but reference futures price, report-level IV, and fractional DTE are available, **When** expected range context is built, **Then** the result is labeled as IV-derived and includes a limitation explaining the fallback.
3. **Given** only a Vol2Vol range label exists, **When** expected range context is built, **Then** no numeric SD band is fabricated and the limitation states that range labels are not numeric SD values.

---

### User Story 2 - Propagate Parity Context (Priority: P2)

As an XAU researcher, I want expected range, source status, official release timing, basis availability, and fractional DTE to be carried through fusion and XAU Vol-OI reports so that downstream daily structural maps can rely on one auditable context bundle.

**Why this priority**: Feature 014 fusion and Feature 006 XAU Vol-OI already connect walls, basis, range, and reaction context. Feature 017 must fill the specific P0 parity gaps without creating a parallel strategy engine.

**Independent Test**: Can be tested by attaching an expected-range snapshot to a synthetic fusion/XAU report and verifying that the context remains available without changing wall scoring behavior.

**Acceptance Scenarios**:

1. **Given** a fusion report has an expected-range snapshot, **When** the report is serialized or inspected, **Then** report-level IV, numeric SD fields, fractional DTE, source status, and official release timestamp remain available.
2. **Given** basis inputs are missing, **When** expected-range context is present, **Then** spot-equivalent levels remain unavailable and the basis limitation remains visible.
3. **Given** blank or null Matrix cells are present, **When** context is propagated, **Then** blank/null cells remain blank/null and are not converted to zero.

---

### User Story 3 - Prepare Manual CME Field Discovery (Priority: P3)

As an XAU researcher, I want a narrow manual-discovery checklist for CME/QuikStrike page fields so that future page exploration captures only sanitized expected-range values and never session material.

**Why this priority**: Some CME fields may require visual/manual inspection. The project needs a precise discovery target before any browser interaction.

**Independent Test**: Can be tested by reviewing the discovery checklist and verifying that it names only permitted visible fields and excludes cookies, tokens, headers, HAR data, screenshots, private URLs, and credentials.

**Acceptance Scenarios**:

1. **Given** a manual CME page review is performed later, **When** visible fields are recorded, **Then** the checklist captures only sanitized field names, source view names, capture timestamps, and structured values.
2. **Given** the page exposes only labels and not numeric bands, **When** the result is documented, **Then** numeric expected-range status remains unavailable or partial.

### Edge Cases

- CME-native numeric SD bands are partially available, such as 1SD only or upper/lower bands without numeric distance values.
- Report-level IV is missing while per-strike IV or `vol_settle` exists.
- Fractional DTE is present in source rows but rounded or dropped in downstream report output.
- Official release timestamp or source status is unknown.
- Capture timestamp exists but the simulated backtest clock is earlier than the release timestamp.
- Native CME numeric bands conflict with locally derived IV bands.
- Basis inputs are absent, stale, or conflicting.
- Matrix cells are blank or unavailable.
- Manual discovery notes contain session, credential, private URL, endpoint replay, browser, broker, order, wallet, or execution material.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST represent a CME expected-range snapshot with source report id, source view, capture timestamp, official release timestamp, source status, product, option product code, futures symbol, expiration, reference futures price, report-level IV, `vol_settle`, fractional DTE, numeric SD bands, range source, extraction quality, and limitations.
- **FR-002**: The system MUST label native CME numeric SD-band context as `cme_native` when numeric 1SD, 2SD, 3SD, and upper/lower bands are available.
- **FR-003**: The system MUST label IV-derived expected range context as `derived_from_iv` when native numeric bands are unavailable but reference futures price, report-level IV, and fractional DTE are available.
- **FR-004**: IV-derived fallback MUST compute 1SD as reference futures price times report-level IV times the square root of fractional DTE divided by 365 unless a later project convention explicitly replaces that formula.
- **FR-005**: The system MUST NOT treat `range_label` as numeric SD input and MUST NOT create numeric upper/lower bands from a range label alone.
- **FR-006**: The system MUST keep per-strike `vol_settle` separate from report-level IV and MUST NOT silently promote per-strike IV into the report-level SD anchor.
- **FR-007**: The system MUST preserve fractional DTE rather than relying only on rounded integer days when computing or reporting expected ranges.
- **FR-008**: The system MUST carry expected-range snapshot context through fusion and XAU Vol-OI report shapes without changing existing wall scoring behavior.
- **FR-009**: The system MUST preserve basis availability and must not compute spot-equivalent levels when basis inputs are missing.
- **FR-010**: The system MUST preserve blank/null Matrix cells and MUST NOT coerce blank, unavailable, invalid, or missing cells to zero.
- **FR-011**: The system MUST update field inventory coverage so report-level IV, numeric SD bands, fractional DTE, source status, and official release timestamp are available when an expected-range snapshot is present.
- **FR-012**: The system MUST provide tests for CME-native range, IV-derived fallback, range-label-only blocking, missing basis, blank Matrix cells, and inventory integration.
- **FR-013**: The system MUST document manual CME page discovery targets for ATM/report-level IV, expected move, SD bands, delta ranges, source view, future reference price, DTE, expiration, and capture timestamp.
- **FR-014**: The system MUST store only sanitized visible text or structured extracted values during manual discovery and MUST NOT store cookies, tokens, headers, HAR files, screenshots, credentials, private URLs, endpoint replay material, broker data, wallet data, or execution data.
- **FR-015**: The system MUST remain research-only and MUST NOT create live trading, paper trading, shadow trading, alerts, broker integration, private keys, real execution, order instructions, position management, Rust execution, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- **FR-016**: The system MUST NOT present expected-range context as profitability evidence, predictive proof, safety evidence, live-readiness evidence, or an instruction to act in the market.

### Key Entities *(include if feature involves data)*

- **CME Expected Range Snapshot**: Point-in-time expected-range context from a CME/QuikStrike source or a conservative IV fallback.
- **Expected Range Source**: Controlled source label such as `cme_native`, `derived_from_iv`, or `unavailable`.
- **Source Timing State**: Capture timestamp, official release timestamp, and source status needed for no-lookahead review.
- **Numeric SD Bands**: 1SD, 2SD, and 3SD numeric distances plus upper/lower reference bands.
- **Expected Range Limitation**: Explanation for fallback, partial, unavailable, range-label-only, or per-strike-IV-only context.
- **Manual Field Discovery Checklist**: Narrow list of permitted visible CME page fields to inspect later.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of native numeric SD-band test cases preserve source, numeric distances, and upper/lower bands without fallback limitations.
- **SC-002**: 100% of IV-derived fallback test cases compute 1SD, 2SD, and 3SD from reference futures price, report-level IV, and fractional DTE with an explicit fallback limitation.
- **SC-003**: 100% of range-label-only test cases leave numeric SD fields unavailable and include a limitation explaining that labels are not numeric ranges.
- **SC-004**: 100% of missing-basis test cases leave spot-equivalent levels unavailable.
- **SC-005**: 100% of blank Matrix cell test cases preserve null numeric values instead of zero.
- **SC-006**: The field inventory shows report-level IV, numeric CME SD bands, fractional DTE, source status, and official release timestamp as available when expected-range snapshot fields are present.
- **SC-007**: Review of Feature 017 docs and output finds zero live execution, order, broker, profitability, predictive-proof, safety, or live-readiness claims.

## Assumptions

- CME-native numeric SD bands are authoritative when captured as visible numeric values.
- IV-derived bands are a fallback and must remain labeled as fallback context.
- The current annualization convention for this feature is calendar DTE divided by 365.
- Existing QuikStrike Vol2Vol, Matrix, fusion, XAU Vol-OI, reaction, and forward journal features remain the source chain.
- Manual CME field discovery may require a later authenticated local browser session and is not required for this code-only slice.
