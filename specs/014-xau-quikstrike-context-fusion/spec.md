# Feature Specification: XAU QuikStrike Context Fusion

**Feature Branch**: `014-xau-quikstrike-context-fusion`  
**Created**: 2026-05-13  
**Status**: Draft  
**Input**: User description: "Create feature 014-xau-quikstrike-context-fusion."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fuse Vol2Vol and Matrix Context (Priority: P1)

As an Elpis researcher, I want to combine an existing QuikStrike Vol2Vol extraction report with an existing QuikStrike Matrix extraction report, so that XAU research can inspect a single enriched options context instead of treating current-expiry Vol2Vol data and cross-expiry matrix data as separate artifacts.

**Why this priority**: This is the core value of the feature. The completed Vol2Vol and Matrix extractors each provide useful but incomplete context; fusion makes their combined coverage usable by the existing XAU research chain.

**Independent Test**: Can be tested with one synthetic Vol2Vol report and one synthetic Matrix report where rows join by strike, expiration, option side, and value type, producing fused rows with preserved provenance and coverage counts.

**Acceptance Scenarios**:

1. **Given** a completed Vol2Vol report and a completed Matrix report for Gold options, **When** the researcher creates a fusion report, **Then** the system produces fused rows that preserve each source value and identify whether the row came from Vol2Vol, Matrix, or both.
2. **Given** both reports provide the same field for the same strike, expiration, option side, and value type, **When** fusion runs, **Then** the system keeps both source values and marks agreement or disagreement instead of silently overwriting either value.
3. **Given** one report provides a field that the other report lacks, **When** fusion runs, **Then** the system keeps the available source value and records that source coverage is partial.

---

### User Story 2 - Explain Missing XAU Reaction Context (Priority: P2)

As an Elpis researcher, I want the fused context to explain missing basis, volatility range, session open, and candle reaction inputs, so that I understand why the XAU reaction planner remains in NO_TRADE or low-confidence states.

**Why this priority**: The latest operational workflow produced usable XAU walls and zones but all reaction rows remained NO_TRADE because confirmation context was missing. The fusion report must make these blockers explicit.

**Independent Test**: Can be tested with fused source rows and intentionally missing spot/futures basis, range, open, and candle inputs, verifying that the report produces a structured missing-context checklist and does not fabricate missing values.

**Acceptance Scenarios**:

1. **Given** fused QuikStrike rows without spot or futures basis references, **When** the fusion report is created, **Then** basis status is marked unavailable and futures-strike levels are preserved without invented spot-equivalent levels.
2. **Given** fused rows without usable IV/range context, **When** the report is reviewed, **Then** IV/range status is marked unavailable or partial and the report explains the effect on reaction confidence.
3. **Given** session open and candle acceptance context are missing, **When** an XAU reaction report is created from the fused context, **Then** missing context is carried forward and NO_TRADE or low-confidence annotations are preserved.

---

### User Story 3 - Produce XAU Vol-OI Compatible Fused Input (Priority: P3)

As an Elpis researcher, I want validated fused rows to produce an XAU Vol-OI compatible local input, so that the existing XAU wall engine can use the richer QuikStrike context without duplicating wall scoring logic.

**Why this priority**: The existing wall engine and reaction planner are already implemented and validated. Fusion should enrich their inputs and metadata rather than create a parallel scoring system.

**Independent Test**: Can be tested by converting a valid synthetic fusion report into XAU Vol-OI compatible rows and verifying that Matrix OI/OI Change/Volume and Vol2Vol range/context values are preserved with source limitations.

**Acceptance Scenarios**:

1. **Given** fused rows with valid strikes, expirations, option sides, and open interest values, **When** conversion runs, **Then** the system creates XAU Vol-OI compatible rows with provenance and source limitations preserved.
2. **Given** spot and futures references are provided, **When** conversion runs, **Then** the system computes spot-equivalent strike levels and records the basis status used for the transformation.
3. **Given** spot or futures reference is missing, **When** conversion runs, **Then** the system keeps futures-strike levels only and records that basis-adjusted spot levels are unavailable.

---

### User Story 4 - Inspect Fusion and Downstream Outcomes (Priority: P4)

As an Elpis researcher, I want the dashboard or local report inspection surface to show selected source reports, fused coverage, agreement warnings, missing context, and downstream XAU outcomes, so that I can decide what data is still needed before interpreting reaction labels.

**Why this priority**: Operational visibility is needed after the core fusion and conversion behavior is safe, especially because this feature is meant to explain why reaction output may still be NO_TRADE.

**Independent Test**: Can be tested by loading saved fusion reports with complete, partial, and blocked contexts and verifying that coverage, warnings, missing context, generated paths, and downstream report references are visible.

**Acceptance Scenarios**:

1. **Given** a saved fusion report, **When** the researcher opens the inspection surface, **Then** the selected Vol2Vol report id, selected Matrix report id, fused row count, strike and expiry coverage, basis status, IV/range status, open/candle status, and missing context checklist are visible.
2. **Given** a fusion report with source disagreements, **When** the researcher reviews the report, **Then** agreement and disagreement details are visible without implying one source is automatically correct.
3. **Given** a downstream XAU reaction report exists, **When** the researcher reviews the fusion status, **Then** the report indicates whether all reactions are NO_TRADE and explains the missing or conflicting context that caused that outcome.

### Edge Cases

- The requested Vol2Vol or Matrix report id does not exist or points to an incomplete extraction.
- The two reports cover different products, unsupported products, or different QuikStrike surfaces.
- Expiration codes, calendar dates, or DTE values disagree between source reports.
- Strike values differ due to formatting, decimal precision, or futures-versus-spot representation.
- Option side is missing, combined, or inconsistent between sources.
- Both sources provide values for the same field but the values disagree beyond a visible tolerance.
- Matrix data covers multiple expiries while Vol2Vol data covers only one current expiry.
- Vol2Vol provides range or volatility-style context for one expiry while Matrix provides OI structure for many expiries.
- Basis references are missing, stale, or internally inconsistent.
- Realized-volatility, session open, or candle reaction context is missing or unavailable.
- A source report contains warnings that should block or downgrade downstream conversion.
- A fusion report is created from local generated artifacts that remain ignored and untracked.
- Any input or candidate report contains cookies, tokens, headers, viewstate values, HAR-like content, screenshots, private full URLs, credentials, or other session material.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST create a local research-only fusion report from one existing QuikStrike Vol2Vol extraction report and one existing QuikStrike Matrix extraction report.
- **FR-002**: The system MUST require both source reports to represent Gold options research data before producing a completed fusion report.
- **FR-003**: The system MUST join source rows by strike, expiration or expiration code, option type, and value type where those fields are available.
- **FR-004**: The system MUST preserve row-level provenance for Vol2Vol-only, Matrix-only, and fused rows.
- **FR-005**: The system MUST keep both source values when both reports provide the same field and MUST mark agreement, disagreement, or unavailable comparison state.
- **FR-006**: The system MUST use Matrix data as the primary cross-expiry source for open interest, OI change, and volume structure while preserving Matrix source limitations.
- **FR-007**: The system MUST use Vol2Vol data as the primary current-expiry source for range, volatility-style context, churn, and view-specific context where available while preserving Vol2Vol source limitations.
- **FR-008**: The system MUST NOT silently overwrite one source with another when source values conflict or overlap.
- **FR-009**: The system MUST compute spot-equivalent strike levels only when sufficient spot and futures reference inputs are provided.
- **FR-010**: The system MUST mark basis status as unavailable when spot or futures reference inputs are missing and MUST preserve futures-strike levels without fabricating basis-adjusted levels.
- **FR-011**: The system MUST report IV/range status as available, partial, or unavailable based only on source context actually present in the input reports.
- **FR-012**: The system MUST report open-regime status and candle-acceptance status as available, partial, or unavailable based only on optional user-provided context.
- **FR-013**: The system MUST produce a structured missing-context checklist covering basis, IV/range, realized volatility, session open, candle acceptance, source report quality, and source agreement.
- **FR-014**: The system MUST produce XAU Vol-OI compatible fused input when required strike, expiration, option side, and value fields are valid.
- **FR-015**: The system MUST block or mark conversion partial when required join keys or source values cannot be mapped confidently.
- **FR-016**: The system MUST support creating an optional XAU Vol-OI report from valid fused input without duplicating existing wall scoring logic.
- **FR-017**: The system MUST support creating an optional XAU reaction report from a valid XAU Vol-OI report and the available fused context.
- **FR-018**: The system MUST preserve NO_TRADE outcomes or low-confidence annotations when basis, IV/range, open-regime, candle-acceptance, or other required confirmation context is missing.
- **FR-019**: The system MUST expose fusion report creation, listing, detail, fused rows, and missing-context inspection through local research interfaces.
- **FR-020**: The system MUST show selected Vol2Vol report id, selected Matrix report id, fused row count, strike and expiry coverage, basis status, IV/range status, open/candle status, source agreement, missing context, downstream report references, and research-only warnings in an inspection surface.
- **FR-021**: The system MUST save only allowed fusion rows, conversion rows, metadata, and reports under ignored local artifact paths.
- **FR-022**: The system MUST NOT persist cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, credentials, endpoint replay payloads, or any browser/session material.
- **FR-023**: The system MUST remain research-only and MUST NOT add live trading, paper trading, shadow trading, private trading keys, broker integration, real execution, wallet/private-key handling, paid vendor integration, endpoint replay, credential/session storage, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- **FR-024**: The system MUST NOT emit buy/sell execution signals or claim profitability, predictive power, safety, or live readiness from fused QuikStrike context.

### Key Entities *(include if feature involves data)*

- **QuikStrike Fusion Request**: A local research request selecting one Vol2Vol report, one Matrix report, and optional spot, futures, session open, candle, and realized-volatility context.
- **Fused QuikStrike Row**: A normalized research row combining Vol2Vol and Matrix context for a strike, expiration, option side, and value type while preserving source values and provenance.
- **Source Agreement Result**: The comparison state for overlapping source fields, including agreement, disagreement, unavailable comparison, and explanation notes.
- **Basis Context**: Optional spot and futures reference information used to determine whether spot-equivalent strike levels can be computed.
- **Range and Volatility Context**: Available, partial, or unavailable range/volatility-style evidence derived from Vol2Vol and optional realized-volatility inputs.
- **Reaction Confirmation Context**: Optional session open and candle acceptance/rejection context used to explain downstream reaction confidence or NO_TRADE states.
- **Missing Context Checklist**: A structured list of unavailable, partial, conflicting, or stale inputs that limit wall interpretation and reaction classification.
- **Fused XAU Vol-OI Input**: A converted local dataset that the existing XAU Vol-OI workflow can consume, with source limitations and provenance retained.
- **Fusion Report**: A local research report summarizing source reports, fused coverage, agreement warnings, missing context, conversion status, downstream report references, and artifact paths.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A synthetic Vol2Vol report and a synthetic Matrix report can be fused into rows with correct strike, expiration, option side, value type, provenance, and source agreement state.
- **SC-002**: Source overlap tests preserve both source values and identify agreement or disagreement in 100% of tested overlapping-field cases.
- **SC-003**: Missing basis tests mark basis unavailable and preserve futures-strike levels without computing spot-equivalent levels in 100% of missing-reference cases.
- **SC-004**: Missing IV/range, open-regime, and candle-context tests produce a structured missing-context checklist and preserve NO_TRADE or low-confidence downstream behavior.
- **SC-005**: Valid fused rows convert into XAU Vol-OI compatible research input with Matrix OI/OI Change/Volume and Vol2Vol context preserved.
- **SC-006**: Conversion is blocked or marked partial in 100% of tested cases where strike, expiration, option side, or value mapping is not confident.
- **SC-007**: A downstream XAU reaction run from incomplete confirmation context clearly explains whether reaction rows remain NO_TRADE and why.
- **SC-008**: Secret/session persistence checks confirm that no cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, credentials, or endpoint replay payloads are written by the fusion workflow.
- **SC-009**: Generated fusion rows, converted inputs, metadata, and reports are written only to ignored local artifact paths and are not staged by default.
- **SC-010**: The inspection surface shows selected source report ids, fused row count, strike and expiry coverage, source agreement, missing context, downstream report references, limitations, and research-only warnings for completed and partial fusion reports.

## Assumptions

- The source QuikStrike Vol2Vol and Matrix extraction reports already exist locally and were produced by completed local-only extractors.
- The supported product for this feature is Gold options research data from QuikStrike-derived local reports.
- Matrix data is broader across expiries, while Vol2Vol data is richer for the selected/current expiry and may contain range or volatility-style context.
- Optional spot, futures, session open, candle, and realized-volatility inputs may be absent; absence should reduce confidence or preserve NO_TRADE outcomes rather than trigger fabricated values.
- Existing XAU Vol-OI wall scoring and XAU reaction/risk planner behavior remain downstream consumers; this feature enriches local context and does not create a parallel strategy engine.
- Generated fusion artifacts are local research artifacts and must remain ignored and untracked.
