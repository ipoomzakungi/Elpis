# Feature Specification: Free Public Derivatives Data Expansion

**Feature Branch**: `011-free-public-derivatives-data-expansion`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "Expand Elpis free/no-paid-vendor data coverage using official/public CFTC COT gold positioning, FRED GVZCLS gold volatility proxy, and Deribit public crypto options IV/OI snapshots for research-only evidence."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add Public CFTC Gold Positioning Context (Priority: P1)

A researcher can collect or import official public CFTC Commitments of Traders data, isolate gold/COMEX-relevant rows, and review weekly broad positioning context without treating it as strike-level gold options open interest.

**Why this priority**: XAU research currently has local options OI and wall-level workflows, but it lacks a free official weekly positioning context that can help explain broad futures participation regimes.

**Independent Test**: Can be fully tested with a public or fixture CFTC historical report containing gold rows, then verifying raw preservation, processed gold-only output, a positioning summary, source limitations, and missing-data instructions.

**Acceptance Scenarios**:

1. **Given** an official public CFTC report is available, **When** the researcher starts a COT collection or import, **Then** the run stores the raw report, filters gold/COMEX-relevant rows, and produces a processed weekly positioning summary.
2. **Given** both futures-only and futures-and-options combined COT rows are available, **When** the processed summary is reviewed, **Then** the report distinguishes those categories and does not merge them without labels.
3. **Given** the CFTC source is unavailable, malformed, or lacks gold rows, **When** the run finishes, **Then** the failure is visible with missing-data instructions and no fabricated positioning values.

---

### User Story 2 - Add GVZ Gold Volatility Proxy Context (Priority: P2)

A researcher can collect or import daily GVZ close data and use it as a clearly labeled GLD-options-derived volatility proxy when full CME gold options implied volatility is unavailable.

**Why this priority**: The XAU reaction workflow needs volatility context, and GVZ provides a free public proxy that is useful only when its limitations are explicit.

**Independent Test**: Can be fully tested with public or fixture GVZ daily close rows, then verifying raw preservation, processed daily output, proxy labeling, date coverage, and limitations that prevent confusing GVZ with a CME gold options IV surface.

**Acceptance Scenarios**:

1. **Given** GVZ daily close data is available, **When** the researcher collects the series, **Then** the run stores raw rows and produces processed daily close rows with date range and row count.
2. **Given** a downstream workflow reviews GVZ context, **When** the value is displayed, **Then** it is labeled as a gold ETF options volatility proxy and not as CME gold options IV.
3. **Given** the GVZ source is unavailable or returns gaps, **When** the run finishes, **Then** gaps are visible and the summary explains what volatility context remains unavailable.

---

### User Story 3 - Add Deribit Public Crypto Options IV/OI Snapshots (Priority: P3)

A researcher can collect public Deribit options instruments and option summary data for supported crypto underlyings, normalize option IV/OI fields, and produce processed option wall snapshots without any private account access.

**Why this priority**: Crypto options provide a free public testbed for option-wall research logic, especially where XAU strike-level options data still depends on local files.

**Independent Test**: Can be fully tested with mocked public Deribit instrument and summary responses, then verifying normalized expiry, strike, option type, open interest, IV fields, underlying price, raw snapshots, processed wall snapshots, and research-only limitations.

**Acceptance Scenarios**:

1. **Given** public options data is available for a requested supported underlying, **When** the researcher collects a Deribit snapshot, **Then** instruments and summary fields are normalized into a processed options snapshot with traceable raw data.
2. **Given** a requested underlying has no public options or returns incomplete fields, **When** the run finishes, **Then** that asset is marked skipped or partial with visible limitations.
3. **Given** a Deribit response includes only public market data, **When** the run is reviewed, **Then** no private keys, account state, order data, or trading endpoints are required or displayed.

---

### User Story 4 - Inspect Free Derivatives Readiness And Bootstrap Runs (Priority: P4)

A researcher can inspect the data-source readiness and dashboard surfaces to see whether CFTC COT, GVZ, and Deribit public options data are available, what files were produced, and what remains missing.

**Why this priority**: Free data expansion is only useful if researchers can see source readiness, limitations, output paths, and missing actions without opening files manually.

**Independent Test**: Can be fully tested by opening the data-source readiness view after mocked or fixture runs and confirming all three new sources, output files, limitations, and missing-data actions are visible without secret values.

**Acceptance Scenarios**:

1. **Given** no free derivatives run exists yet, **When** the researcher opens data-source readiness, **Then** CFTC COT, GVZ, and Deribit public options appear with clear missing-data actions.
2. **Given** one or more free derivatives runs completed, **When** the researcher opens the run history or dashboard, **Then** each source shows status, row counts, date or snapshot coverage, output paths, and source limitations.
3. **Given** optional paid vendor sources remain unavailable, **When** readiness is reviewed, **Then** those missing paid sources remain non-blocking for this feature and no secret values are exposed.

### Edge Cases

- CFTC files are unavailable, compressed differently than expected, contain multiple report formats, or have column names that differ by year.
- CFTC gold rows use alternate market names, exchange labels, or futures-only versus futures-and-options categories.
- CFTC data is weekly and cannot satisfy intraday or strike-level XAU options OI requirements.
- GVZ data is unavailable, delayed, missing recent sessions, revised, or contains non-trading-day gaps.
- GVZ is mistaken for CME gold options IV rather than GLD-options-derived proxy volatility.
- Deribit public endpoints are unavailable, rate limited, return partial responses, or omit IV/OI fields for some instruments.
- Deribit instrument names include unexpected underlyings, expired contracts, unsupported assets, or symbols that could create unsafe paths.
- A requested Deribit underlying has no public options data or has options but no usable open interest.
- Raw downloads succeed but processed outputs have too few rows or too few instruments for downstream research.
- A bootstrap run partially succeeds across sources, leaving one completed source and one failed source.
- Existing generated files already exist for the same source and date or snapshot window.
- Dashboard or report copy accidentally implies paid-vendor coverage, live readiness, strategy profitability, predictive power, or execution instructions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST add a research-only free derivatives data expansion workflow covering CFTC COT gold positioning, GVZ gold volatility proxy, and Deribit public crypto options data.
- **FR-002**: System MUST NOT require or accept live trading access, paper trading access, shadow trading access, private trading keys, broker credentials, wallet/private-key handling, paid vendor credentials, real execution permissions, or order-management permissions for this feature.
- **FR-003**: System MUST NOT introduce Rust execution components, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, ML model training, or other v0-forbidden technology for this feature.
- **FR-004**: System MUST represent CFTC COT, GVZ, and Deribit public options in data-source readiness, capability, and missing-data summaries.
- **FR-005**: System MUST allow a researcher to start and inspect a free derivatives bootstrap run and retrieve saved run summaries and details.
- **FR-006**: Every free derivatives run MUST include per-source status, requested coverage, completed outputs, skipped outputs, failed outputs, row or instrument counts, date or snapshot coverage, limitations, and next missing-data actions.
- **FR-007**: System MUST preserve partial results when one source completes and another source fails.
- **FR-008**: System MUST save raw CFTC data under ignored `data/raw/cftc/` paths and processed CFTC outputs under ignored `data/processed/cftc/` paths.
- **FR-009**: System MUST filter CFTC data to gold/COMEX-relevant rows and produce a broad weekly positioning summary.
- **FR-010**: CFTC summaries MUST distinguish futures-only positioning from futures-and-options combined positioning when both are available.
- **FR-011**: CFTC outputs MUST clearly label COT as weekly broad positioning and not strike-level options open interest.
- **FR-012**: System MUST save raw GVZ data under ignored `data/raw/gvz/` paths and processed GVZ outputs under ignored `data/processed/gvz/` paths.
- **FR-013**: GVZ outputs MUST include daily close values, date coverage, missing-row visibility, and a limitation label.
- **FR-014**: GVZ outputs MUST clearly label GVZ as a GLD-options-derived volatility proxy and not as a CME gold options implied-volatility surface.
- **FR-015**: System MUST save raw Deribit public options snapshots under ignored `data/raw/deribit/` paths and processed option wall snapshots under ignored `data/processed/deribit/` paths.
- **FR-016**: Deribit collection MUST use public market-data access only and MUST NOT call account, order, private, or trading operations.
- **FR-017**: Deribit normalized outputs MUST include instrument name, underlying asset, expiry, strike, option type, open interest, mark IV, bid IV and ask IV when available, underlying price when available, volume when available, and available greeks when present.
- **FR-018**: Deribit outputs MUST clearly label the source as crypto options data and not as gold/XAU options data.
- **FR-019**: System MUST make unsupported, unavailable, or incomplete assets visible instead of silently excluding them.
- **FR-020**: System MUST keep XAU strike-level options OI as a local CSV or Parquet import workflow unless a future approved public gold options source is added.
- **FR-021**: System MUST provide missing-data instructions for XAU local options OI files including required columns: date or timestamp, expiry, strike, option type, and open interest.
- **FR-022**: System MUST show CFTC COT, GVZ, and Deribit public options readiness, limitations, output files, and missing-data actions on the data-source dashboard.
- **FR-023**: System MUST NOT expose secret values, masked secret values, partial secret values, or secret hashes in reports, logs intended for users, readiness views, or dashboard views.
- **FR-024**: System MUST keep generated raw data, processed data, and reports ignored and untracked.
- **FR-025**: System MUST include source limitation labels wherever CFTC, GVZ, or Deribit outputs are used in downstream research.
- **FR-026**: System MUST NOT claim profitability, predictive power, safety, execution readiness, live readiness, or replacement of paid institutional datasets.
- **FR-027**: Automated validation MUST use mocked public responses or local fixtures and MUST NOT depend on live external downloads.

### Key Entities

- **Free Derivatives Bootstrap Run**: A saved research run that records requested sources, per-source outcomes, created artifacts, limitations, and missing-data actions.
- **CFTC COT Gold Positioning Record**: A weekly gold/COMEX positioning row with report date, report category, participant positioning fields, and source-identification fields.
- **CFTC Gold Positioning Summary**: A processed weekly summary that highlights broad long, short, net, and change-style positioning context where available.
- **GVZ Volatility Proxy Record**: A daily GVZ close value with date, source coverage, and proxy limitation labels.
- **Deribit Option Instrument**: A public crypto option contract with underlying, expiry, strike, option type, and instrument name.
- **Deribit Option Summary Snapshot**: A public market-data snapshot with IV/OI, underlying price, volume, and greeks where available.
- **Processed Option Wall Snapshot**: A normalized crypto options research view grouped by underlying, expiry, strike, and option type.
- **Source Limitation**: A user-facing statement describing what the source can and cannot represent in downstream research.
- **Missing Data Action**: A clear next step for data that cannot be collected from these free public sources.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can complete a CFTC COT gold collection or fixture import and see at least one processed gold/COMEX positioning row when the source contains gold data.
- **SC-002**: 100% of CFTC outputs label the data as weekly broad positioning and not strike-level options open interest.
- **SC-003**: A researcher can complete a GVZ collection or fixture import and see daily close rows with date coverage and a visible GLD-options-derived proxy limitation.
- **SC-004**: 100% of GVZ outputs avoid labeling the series as a CME gold options implied-volatility surface.
- **SC-005**: A researcher can complete a Deribit public options fixture run for at least one supported crypto underlying and see normalized IV/OI option rows with expiry, strike, and option type.
- **SC-006**: 100% of Deribit outputs label the data as crypto options data and not gold/XAU options data.
- **SC-007**: Every requested source in a free derivatives run ends with exactly one visible status: completed, skipped, partial, or failed.
- **SC-008**: Completed source results show row or instrument count, coverage window or snapshot timestamp, output paths, limitations, and next actions in the saved run detail.
- **SC-009**: A researcher can identify readiness, limitations, output files, and missing-data actions for all three sources from the data-source dashboard in under 2 minutes.
- **SC-010**: No private keys, paid vendor credentials, generated raw data, generated processed data, or generated reports are included in version control after validation.
- **SC-011**: Existing backend validation, frontend build, and generated artifact guard pass after the feature is implemented.

## Assumptions

- CFTC COT is useful as weekly broad positioning context only and does not replace XAU strike-level options OI.
- GVZCLS or equivalent public GVZ close data is used as a proxy when available; if the public source is unavailable, local import remains acceptable for research validation.
- Deribit public options coverage may vary by underlying; unsupported or incomplete underlyings are treated as skipped or partial instead of failed silently.
- BTC and ETH are expected baseline Deribit option underlyings; SOL is attempted only where public options data is available.
- Existing local XAU options OI CSV/Parquet import remains the source for XAU wall-by-strike reports.
- Existing data-source readiness and public bootstrap concepts remain the user-facing model for source status and missing-data actions.
- Automated tests use mocked responses or local fixtures; real public downloads are reserved for explicit operational runs.
