# Feature Specification: XAU Forward Journal Outcome Price Updater

**Feature Branch**: `016-xau-forward-journal-outcome-price-updater`
**Created**: 2026-05-14
**Status**: Draft
**Input**: User description: "Add XAU forward journal outcome price updater. Update Forward Journal outcome windows using local or public OHLC candle data for relevant time ranges. Keep the feature research-only, preserve immutable snapshot data, label proxy sources clearly, never fabricate missing candles, provide update and coverage interfaces, extend the XAU Vol-OI Forward Journal panel, and validate with unit, integration, API contract, frontend, and artifact-guard checks."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Update Outcomes From Price Data (Priority: P1)

As an XAU researcher, I want to update a saved Forward Journal entry from approved OHLC candle data so that pending outcome windows can be filled with observed high, low, close, range, and direction where the data actually covers the required period.

**Why this priority**: This is the core research value. Forward Journal entries already preserve the snapshot, but the later outcome windows remain pending until candle data is attached conservatively.

**Independent Test**: Can be tested by loading one synthetic journal entry with pending windows, applying synthetic complete OHLC candles for one or more windows, and verifying the updated outcomes include computed price metrics while the original snapshot data remains unchanged.

**Acceptance Scenarios**:

1. **Given** a journal entry with pending 30m, 1h, 4h, session_close, and next_day windows and complete OHLC candles covering the 30m and 1h windows, **When** the researcher updates outcomes from price data, **Then** those covered windows record high, low, close, range, source label, coverage status, update report reference, and direction if a snapshot price is available.
2. **Given** a journal entry with a snapshot price, **When** a covered outcome window closes above, below, or equal to that snapshot price, **Then** the outcome records the corresponding observed direction without presenting it as a prediction, trading signal, profitability result, safety result, or live-readiness claim.
3. **Given** a journal entry without a snapshot price, **When** complete candles are available, **Then** the outcome records high, low, close, and range while direction remains unavailable with a clear limitation note.

---

### User Story 2 - Review Price Coverage Before Or After Update (Priority: P2)

As an XAU researcher, I want to inspect whether available candles cover each outcome window so that I can see which windows are complete, partial, missing, or proxy-limited before trusting an outcome update.

**Why this priority**: Research notes are only useful when source coverage and limitations are explicit. Missing or partial data must not be hidden behind completed labels.

**Independent Test**: Can be tested by requesting coverage for a journal entry against a synthetic candle dataset with complete, partial, and missing windows and verifying the coverage summary and missing-candle checklist.

**Acceptance Scenarios**:

1. **Given** candles fully cover a required window, **When** coverage is checked, **Then** the window is reported as complete with source label, observed start and end timestamps, and no missing-candle item for that window.
2. **Given** candles cover only part of a required window, **When** coverage is checked or outcomes are updated, **Then** the window is reported as partial and any updated outcome is marked inconclusive rather than completed.
3. **Given** no candles exist for a required window, **When** coverage is checked or outcomes are updated, **Then** the window remains pending and the missing-candle checklist identifies the missing window.
4. **Given** the price source is a proxy such as GC futures, Yahoo GC=F, or GLD, **When** coverage or outcome results are shown, **Then** the source is labeled with the required proxy label and includes a limitation note explaining that the source is not true XAUUSD spot.

---

### User Story 3 - Inspect Updated Outcomes In The Dashboard (Priority: P3)

As an XAU researcher, I want the existing XAU Vol-OI Forward Journal panel to show price-source coverage, missing windows, proxy limitations, and updated outcome status so that I can review forward evidence without opening raw files.

**Why this priority**: The dashboard makes the research workflow repeatable, but it depends on the outcome update and coverage behavior being correct first.

**Independent Test**: Can be tested by opening the Forward Journal panel for a synthetic entry after an outcome update and verifying the source label, coverage status, missing windows, updated labels, proxy limitations, pending or inconclusive status, and research-only disclaimer are visible.

**Acceptance Scenarios**:

1. **Given** a journal entry has updated price outcomes, **When** the researcher opens the XAU Vol-OI Forward Journal panel, **Then** the panel shows the price data source, coverage status, updated outcome labels, artifact references, and research-only disclaimer.
2. **Given** one or more outcome windows remain missing or partial, **When** the entry is inspected, **Then** the panel shows those windows as pending or inconclusive and lists the missing candle checklist.
3. **Given** proxy price data was used, **When** the entry is inspected, **Then** the panel clearly labels the proxy source and displays proxy limitation notes near the related outcomes.

---

### Edge Cases

- The journal id does not exist or does not refer to an XAU Forward Journal entry.
- The journal entry already has completed outcomes and the new price update would change them.
- The snapshot time is missing, invalid, timezone-ambiguous, or later than the supplied candles.
- The local OHLC file is missing, empty, unreadable, duplicated, unsorted, or contains unsupported columns.
- OHLC rows contain impossible values, such as high below low or close outside the high-low range.
- Candles include gaps, overlapping timestamps, mixed timezones, or a frequency too coarse to support a requested window.
- Candles fully cover short windows but not session_close or next_day.
- The requested source symbol is inconsistent with the selected source label.
- The source is a proxy and cannot be treated as true XAUUSD spot.
- Snapshot price is unavailable, so direction from snapshot cannot be computed.
- A window has partial data and must become inconclusive rather than completed.
- A window has no candle data and must remain pending.
- Generated outcome reports exist locally but must remain ignored and untracked.
- Requests or notes include forbidden credential, session, endpoint replay, execution, profitability, prediction, safety, or live-readiness material.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a researcher to update a saved XAU Forward Journal entry by journal id using approved OHLC candle data from a local CSV file, local Parquet file, or existing public research data output.
- **FR-002**: The system MUST determine required outcome windows from the journal entry snapshot time for `30m`, `1h`, `4h`, `session_close`, and `next_day`.
- **FR-003**: The system MUST validate that candle timestamps cover each required outcome window before computing outcome metrics for that window.
- **FR-004**: The system MUST validate OHLC schema and values, including timestamp, open, high, low, and close availability; internally consistent high-low-open-close values; deterministic ordering; and unambiguous timestamp interpretation.
- **FR-005**: The system MUST support optional source symbols `XAUUSD spot`, `GC futures`, `GC=F proxy`, and `GLD proxy` without treating any proxy as true XAUUSD spot.
- **FR-006**: The system MUST label every price source with exactly one of: `true_xauusd_spot`, `gc_futures`, `yahoo_gc_f_proxy`, `gld_etf_proxy`, `local_csv`, `local_parquet`, or `unknown_proxy`.
- **FR-007**: The system MUST clearly label proxy source limitations wherever proxy-driven coverage or outcomes are reported.
- **FR-008**: For each fully covered window, the system MUST compute observed high, low, close, range, and direction from snapshot price when snapshot price is available.
- **FR-009**: If snapshot price is unavailable, the system MUST compute available observed price metrics and mark direction as unavailable rather than inferring it.
- **FR-010**: If candles are missing for a window, the system MUST keep that outcome pending and MUST NOT fabricate candles, prices, coverage, direction, or labels.
- **FR-011**: If candles partially cover a window, the system MUST mark that outcome inconclusive and include the partial coverage reason.
- **FR-012**: The system MUST update only outcome-related fields and MUST preserve original snapshot data, source report references, walls, reactions, missing context, and original notes as immutable evidence.
- **FR-013**: The system MUST produce an outcome update report, updated journal outcomes, source coverage summary, missing candle checklist, proxy limitation notes, and local artifact references for each update attempt.
- **FR-014**: Generated artifact references MUST stay under ignored `data/reports/xau_forward_journal/` paths and MUST NOT require committing generated data.
- **FR-015**: The system MUST provide a local research action to update outcomes from price data at `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data`.
- **FR-016**: The system MUST provide a local research action to inspect price coverage at `GET /api/v1/xau/forward-journal/entries/{journal_id}/price-coverage`.
- **FR-017**: The coverage result MUST include per-window status, observed candle coverage range, missing windows, source label, source symbol, proxy limitations, and reasons for pending or inconclusive outcomes.
- **FR-018**: The XAU Vol-OI Forward Journal panel MUST show price data source, coverage status, missing windows, updated outcome labels, proxy limitations, pending or inconclusive status, artifact paths, and a research-only disclaimer.
- **FR-019**: The system MUST reject or flag credential/session-like fields and MUST NOT store cookies, tokens, headers, HAR files, screenshots, viewstate, private URLs, credentials, paid-vendor secrets, endpoint replay material, broker fields, order fields, wallet fields, or execution fields.
- **FR-020**: The system MUST NOT add live trading, paper trading, shadow trading, broker integration, real execution, private trading keys, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML model training.
- **FR-021**: The system MUST NOT present outcome updates as trading signals, order instructions, profitability evidence, predictive proof, safety evidence, or live-readiness evidence.
- **FR-022**: The system MUST preserve an auditable record of each outcome update attempt, including source label, coverage status, warnings, limitations, and artifact references.

### Key Entities *(include if feature involves data)*

- **Forward Journal Entry**: Existing local research entry identified by journal id, containing immutable snapshot data and mutable outcome windows.
- **Outcome Window**: A required post-snapshot observation period such as 30m, 1h, 4h, session_close, or next_day, with status, price metrics, label, source, and limitations.
- **OHLC Candle Dataset**: Supplied local or existing public research output containing timestamped open, high, low, and close values for a selected source symbol.
- **Price Data Source Label**: Controlled label that distinguishes true spot, futures, Yahoo proxy, GLD proxy, local file type, or unknown proxy status.
- **Coverage Summary**: Per-window assessment describing whether supplied candles fully cover, partially cover, or miss each required outcome window.
- **Missing Candle Checklist**: Research checklist naming each window or interval that lacks sufficient candles for a completed outcome.
- **Outcome Update Report**: Local research artifact summarizing update results, source coverage, missing candles, proxy limitations, pending or inconclusive windows, and generated artifact paths.
- **Proxy Limitation Note**: Explicit note explaining that a non-spot source may differ from true XAUUSD spot and must not be treated as a direct substitute without review.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A synthetic journal entry with pending outcomes can be updated from synthetic complete OHLC candles, producing computed high, low, close, and range for every fully covered supplied window.
- **SC-002**: 100% of missing-window validation cases leave the related outcome pending and include a missing-candle checklist item.
- **SC-003**: 100% of partial-window validation cases mark the related outcome inconclusive and include a partial-coverage reason.
- **SC-004**: 100% of outcome update attempts preserve original snapshot fields and source report references unchanged.
- **SC-005**: 100% of updated or coverage-checked outcomes display one required source label and, when applicable, a proxy limitation note.
- **SC-006**: A researcher can retrieve a coverage summary for a journal entry and identify complete, partial, and missing windows without opening raw candle files.
- **SC-007**: The Forward Journal dashboard panel shows updated outcome status, source coverage, missing windows, proxy limitations, and research-only disclaimer for at least one saved entry.
- **SC-008**: Automated validation covers OHLC schema validation, window calculation, complete/partial/missing candle coverage, proxy source limitation labels, synthetic integration update, local research interface contracts, dashboard build, and generated artifact guard.
- **SC-009**: Review of generated reports and dashboard copy finds zero trading-signal, order, profitability, predictive-proof, safety, or live-readiness claims.
- **SC-010**: Generated outcome report artifacts remain ignored and untracked in repository status checks.

## Assumptions

- Existing feature 015 journal entries already provide journal id, snapshot time, outcome windows, optional snapshot price, and immutable snapshot/source sections.
- Outcome windows are derived from snapshot time using the same timezone-safe conventions as the existing Forward Journal; ambiguous candle timestamps are rejected or left pending rather than guessed.
- `session_close` and `next_day` use the project’s current XAU research session conventions when available; if the boundary cannot be determined from local context, those windows remain pending or inconclusive with an explicit limitation.
- Local CSV and local Parquet inputs are research files supplied by the user or created by approved existing public-data workflows; this feature does not add paid-vendor ingestion or private endpoint replay.
- Public-source outputs may include Yahoo GC=F or GLD proxies, but those are always labeled as proxies and not treated as true XAUUSD spot.
- Direction from snapshot is computed only when the journal entry already contains a usable snapshot price.
- This feature is local-only and research-only; it is not a paper trading, shadow trading, live trading, execution, or strategy-validation workflow.
