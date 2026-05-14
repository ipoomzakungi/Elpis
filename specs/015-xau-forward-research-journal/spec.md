# Feature Specification: XAU Forward Research Journal

**Feature Branch**: `015-xau-forward-research-journal`  
**Created**: 2026-05-14  
**Status**: Draft  
**Input**: User description: "Create feature 015-xau-forward-research-journal. Create a forward research journal for XAU QuikStrike snapshots that links QuikStrike Vol2Vol, QuikStrike Matrix, XAU QuikStrike Fusion, XAU Vol-OI, and XAU reaction reports to later outcome windows without claiming historical backtest validity or adding trading behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record A Research Snapshot (Priority: P1)

As an XAU researcher, I want to create a journal entry from the latest completed QuikStrike-derived reports so that each forward observation is preserved with the source reports, top walls, reaction context, missing context, and notes available at the time of capture.

**Why this priority**: This creates the evidence trail needed before any future evaluation can be honest. Without immutable forward snapshots, later outcome labels cannot be linked to what was actually known at capture time.

**Independent Test**: Can be tested by creating one journal entry from existing local report identifiers and verifying the entry records source references, snapshot metadata, walls, reactions, NO_TRADE reasons, missing context, and research-only limitations without requiring outcome candles.

**Acceptance Scenarios**:

1. **Given** completed local QuikStrike Vol2Vol, Matrix, fusion, XAU Vol-OI, and XAU reaction reports, **When** the researcher creates a journal entry, **Then** the system records a journal entry linked to those reports with snapshot time, capture session, product, expiration context, top wall summaries, reaction summaries, missing context, and notes.
2. **Given** optional spot, futures, session-open, or event-flag context is provided at snapshot time, **When** the entry is created, **Then** those fields are stored as snapshot context and omitted fields are clearly marked unavailable rather than fabricated.
3. **Given** a source report id is missing or incompatible, **When** the researcher attempts to create an entry, **Then** the system rejects or blocks the entry with a clear research-data validation reason.

---

### User Story 2 - Add Later Outcome Labels (Priority: P2)

As an XAU researcher, I want to update a journal entry with later price-outcome windows so that I can evaluate whether observed walls, NO_TRADE annotations, and reaction labels were followed by identifiable market behavior.

**Why this priority**: Forward evidence becomes useful only after later outcomes are linked to the original snapshot. This supports future research review without pretending a historical QuikStrike backtest exists.

**Independent Test**: Can be tested by updating an existing journal entry with synthetic outcome-window observations and verifying that each window records status, available price context, and an allowed outcome label.

**Acceptance Scenarios**:

1. **Given** a journal entry exists and later price observations are available for one or more outcome windows, **When** the researcher adds outcomes, **Then** each provided window is stored with its observation time, price context, label, and notes.
2. **Given** outcome price data is missing for a window, **When** outcomes are updated, **Then** that window remains pending or inconclusive and the system does not fabricate a label.
3. **Given** a NO_TRADE reaction was recorded at snapshot time, **When** later outcomes are added, **Then** the researcher can label whether the NO_TRADE state was later consistent, inconclusive, or not yet evaluated.

---

### User Story 3 - Inspect Forward Evidence (Priority: P3)

As an XAU researcher, I want to inspect journal entries and their outcome status from the existing XAU research dashboard so that I can review accumulated forward evidence, missing context, and limitations without opening raw files.

**Why this priority**: The journal needs a practical inspection surface to make forward evidence review repeatable and useful, but it depends on the ability to create and update entries first.

**Independent Test**: Can be tested by listing saved entries and opening one entry to verify its snapshot sources, top walls, reactions, NO_TRADE reasons, outcome statuses, labels, notes, and research-only disclaimer are visible.

**Acceptance Scenarios**:

1. **Given** one or more journal entries exist, **When** the researcher opens the XAU research dashboard, **Then** a Forward Journal section lists snapshots with their source report ids, outcome status, and key limitations.
2. **Given** a journal entry has outcome labels, **When** the researcher opens its detail view, **Then** the outcome windows and labels are visible alongside the original snapshot context.
3. **Given** an entry has missing context or pending outcomes, **When** it is inspected, **Then** the missing-data checklist and pending labels are visible and no strategy-performance claim is shown.

---

### Edge Cases

- A journal entry is requested before one or more required source reports exist.
- Source reports are present but refer to incompatible products, expirations, or capture sessions.
- A source report is partial or contains missing-context warnings.
- Snapshot context is missing spot, futures, session-open, event flag, or basis values.
- Outcome data is submitted for only some windows.
- Outcome data conflicts with an already recorded outcome label.
- Outcome windows are updated out of order.
- Later price data is missing, stale, or insufficient to assign a label.
- Notes include forbidden execution, profitability, prediction, safety, or live-readiness wording.
- Generated journal artifacts exist locally but must remain ignored and untracked.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a researcher to create a local research journal entry from existing QuikStrike Vol2Vol, QuikStrike Matrix, XAU QuikStrike Fusion, XAU Vol-OI, and XAU reaction report identifiers.
- **FR-002**: Each journal entry MUST include a unique journal id, snapshot time, capture session, source report identifiers, product, expiration context, optional spot and futures prices, optional session-open price, optional event or news flag, and user notes.
- **FR-003**: Each journal entry MUST summarize top open-interest walls, top open-interest-change walls, top volume walls, reaction labels, NO_TRADE reasons, missing-context checklist items, and bounded risk annotations if present.
- **FR-004**: The system MUST preserve source-report provenance so a researcher can trace each journal entry back to the reports used at snapshot time.
- **FR-005**: The system MUST validate that required source reports exist and are compatible enough to journal together, including product compatibility and usable XAU report linkage.
- **FR-006**: The system MUST mark unavailable optional snapshot inputs as missing or unavailable and MUST NOT fabricate spot, futures, basis, session-open, event, candle, volatility, or outcome values.
- **FR-007**: The system MUST support outcome windows for 30 minutes, 1 hour, 4 hours, session close, and next day.
- **FR-008**: The system MUST support outcome labels: wall_held, wall_rejected, wall_accepted_break, moved_to_next_wall, reversed_before_target, stayed_inside_range, no_trade_was_correct, and inconclusive.
- **FR-009**: The system MUST allow later outcome updates without changing the original snapshot observations.
- **FR-010**: If later price data is missing or insufficient for a window, the system MUST keep that window pending or inconclusive and MUST NOT infer a label.
- **FR-011**: The system MUST identify when an outcome update conflicts with an existing outcome and require the conflict to be explicit in the journal entry notes.
- **FR-012**: The system MUST expose saved journal entries for listing, detail inspection, and outcome updates through local research interfaces.
- **FR-013**: The dashboard MUST show a Forward Journal section with snapshot list, top walls or zones, reaction labels, NO_TRADE reasons, outcome status, outcome labels, notes, and a research-only disclaimer.
- **FR-014**: Journal entries and generated journal reports MUST remain local research artifacts and MUST be stored only under ignored local artifact paths.
- **FR-015**: The system MUST reject or flag secret/session-like fields and MUST NOT store cookies, tokens, headers, HAR files, screenshots, viewstate, private URLs, credentials, or endpoint replay material.
- **FR-016**: The system MUST NOT create trading signals, order instructions, position instructions, profitability claims, predictive claims, safety claims, or live-readiness claims.
- **FR-017**: The system MUST make missing historical QuikStrike coverage explicit so researchers understand the journal is forward evidence collection, not a historical full-strategy backtest.

### Key Entities *(include if feature involves data)*

- **Forward Journal Entry**: A local research snapshot linking source report ids, capture metadata, product and expiration context, top wall summaries, reactions, missing context, risk annotations if any, notes, and outcome status.
- **Source Report Reference**: A reference to an existing local report used to create the journal entry, including report id, source type, status, product context, and limitations.
- **Snapshot Context**: Optional market context known at capture time, including spot price, futures price, basis, session open, event flag, and notes.
- **Wall Summary**: A compact representation of top open-interest, open-interest-change, or volume levels captured at snapshot time.
- **Reaction Summary**: A compact representation of reaction labels, NO_TRADE reasons, and bounded risk annotations from the XAU reaction report.
- **Outcome Window**: A later observation window such as 30 minutes, 1 hour, 4 hours, session close, or next day, with status, price context, label, and notes.
- **Outcome Label**: A controlled research label describing observed behavior after the snapshot without implying tradability or profitability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can create a journal entry from a complete set of existing source report identifiers in under 2 minutes.
- **SC-002**: 100% of created journal entries retain source report identifiers and original snapshot time.
- **SC-003**: 100% of entries with missing optional context show explicit missing-context fields rather than blank or fabricated values.
- **SC-004**: A researcher can update at least one outcome window for an existing entry and retrieve the updated label and notes.
- **SC-005**: Entries with unavailable outcome price data remain pending or inconclusive in 100% of validation cases.
- **SC-006**: The dashboard inspection flow shows journal snapshots, outcome status, and research limitations for at least one saved entry.
- **SC-007**: Automated validation confirms no generated journal data, reports, secrets, session material, or private URLs are tracked.
- **SC-008**: Review of journal output finds zero profitability, predictive-power, safety, live-readiness, or execution-signal claims.

## Assumptions

- The journal starts with forward evidence collection because complete historical QuikStrike strike-level snapshots are not available locally.
- Existing QuikStrike Vol2Vol, Matrix, fusion, XAU Vol-OI, and XAU reaction reports are produced by completed features before journal entries are created.
- Outcome candles or price observations may be supplied later from existing approved research data sources or local files; missing observations remain pending.
- The first version focuses on XAU/Gold QuikStrike research snapshots only.
- The journal is local-only and research-only; it is not a paper trading, live trading, or execution readiness workflow.
