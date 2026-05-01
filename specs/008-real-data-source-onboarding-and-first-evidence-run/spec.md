# Feature Specification: Real Data-Source Onboarding And First Evidence Run

**Feature Branch**: `008-real-data-source-onboarding-and-first-evidence-run`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "Add real data-source onboarding and first evidence run workflow."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review Data-Source Readiness (Priority: P1)

A researcher can open a data-source onboarding workflow and immediately see which public, local, and optional paid research data sources are configured, available, missing, optional, or unsupported.

**Why this priority**: The first real evidence run is only useful if researchers know whether required data exists and whether each source is appropriate for the requested evidence. This prevents silent misuse of Yahoo proxy data, missing XAU options files, or absent optional vendor access.

**Independent Test**: Can be tested by running onboarding with no paid provider keys, public/no-key sources available, and one missing local XAU file, then verifying the readiness output clearly separates available, missing, optional, and unsupported sources without exposing secret values.

**Acceptance Scenarios**:

1. **Given** public/no-key sources are available and no optional vendor keys are configured, **When** the researcher checks data-source readiness, **Then** Binance public, Yahoo Finance, and local-file import paths are shown as usable where relevant, while optional paid vendors are marked unavailable but not failed.
2. **Given** Yahoo Finance is included as a proxy source, **When** the capability matrix is displayed, **Then** Yahoo Finance is labeled OHLCV/proxy-only and not a source for crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data.
3. **Given** optional vendor environment variables exist, **When** readiness is displayed, **Then** the system indicates configuration presence without returning the secret values.

---

### User Story 2 - Receive Missing-Data Instructions (Priority: P2)

A researcher can run a preflight check before the first evidence run and receive clear instructions for every missing required or optional data source.

**Why this priority**: The workflow must help a researcher collect and import real data safely before running evidence workflows, instead of failing with unclear errors or substituting synthetic data.

**Independent Test**: Can be tested by requesting crypto, proxy, and XAU workflows with selected missing inputs and verifying the output includes specific download, processing, or local import instructions for each blocked requirement.

**Acceptance Scenarios**:

1. **Given** crypto processed features are missing, **When** preflight runs, **Then** the response explains how to fetch/process public Binance data for the requested symbols and timeframe.
2. **Given** proxy OHLCV features are missing, **When** preflight runs, **Then** the response explains how to fetch/process Yahoo Finance OHLCV data and preserves OHLCV-only limitations.
3. **Given** a local XAU options OI file is missing or has the wrong schema, **When** preflight runs, **Then** the response lists the required and optional XAU options OI columns and does not treat GC=F or GLD as options OI sources.
4. **Given** optional paid vendor keys are missing, **When** preflight runs, **Then** the response explains how to configure them if available while confirming that the MVP does not require them.

---

### User Story 3 - Run The First Evidence Workflow (Priority: P3)

A researcher can start the first evidence workflow after preflight and have it reuse the completed multi-asset research, XAU Vol-OI, and final evidence run systems to produce one final evidence report.

**Why this priority**: The feature's business value is proving that the completed platform can move from data readiness into a real research evidence run without adding new strategy logic or execution behavior.

**Independent Test**: Can be tested with synthetic fixtures in automated tests and with real local/public data manually by verifying a first evidence run produces or references research, XAU, and execution evidence report identifiers when required data exists.

**Acceptance Scenarios**:

1. **Given** required crypto, proxy, and XAU inputs exist, **When** the first evidence run starts, **Then** it reuses existing research workflows and returns one final evidence run identifier with links to generated or referenced reports.
2. **Given** one workflow is blocked by missing data, **When** the first evidence run starts, **Then** the final evidence output still includes the blocked workflow, missing-data checklist, and bounded research decision label.
3. **Given** optional paid provider keys are absent, **When** the first evidence run starts with public/local MVP inputs available, **Then** the run is allowed to proceed and optional vendors remain marked unavailable.

---

### User Story 4 - Inspect Onboarding And Evidence Results In The Dashboard (Priority: P4)

A researcher can inspect data-source readiness, provider capabilities, missing-data actions, optional provider key presence, and first evidence run status in one dashboard surface.

**Why this priority**: Researchers need a visible operating checklist for real data onboarding and first evidence execution, especially when some sources are optional, unsupported, or local-file based.

**Independent Test**: Can be tested by loading the dashboard after a preflight or first evidence run and confirming readiness cards, capability matrix, missing-data checklist, report links, and research-only disclaimer are visible.

**Acceptance Scenarios**:

1. **Given** readiness has been checked, **When** the dashboard page is opened, **Then** it shows public/no-key availability, optional key presence, local-file readiness, and unsupported capability labels.
2. **Given** a first evidence run has completed or partially completed, **When** the dashboard page is opened, **Then** it shows first-run status, report links, missing-data actions, and research-only warnings.
3. **Given** no run has been started, **When** the dashboard page is opened, **Then** it still shows the capability matrix and next actions needed to run the first evidence workflow.

### Edge Cases

- Optional paid provider keys are absent, blank, malformed, or present in the environment but should never be returned to the user.
- A user requests Yahoo Finance as a source for OI, funding, IV, gold options OI, futures OI, or XAUUSD spot execution data.
- A local XAU options OI file is missing, unreadable, empty, outside allowed local research paths, or missing required columns.
- Public Binance endpoints are reachable for OHLCV but have limited or unavailable historical public OI/funding coverage.
- Processed feature files exist but are stale, unreadable, empty, or missing required columns for the requested workflow.
- A user requests only optional paid vendor sources without configuring those providers.
- Generated raw data, processed data, reports, `.env` files, or local import files exist locally and must remain untracked.
- A user attempts to interpret readiness or evidence labels as live, paper, shadow, or execution-ready trading approval.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a data-source onboarding workflow that reports readiness for public/no-key sources, local file sources, optional paid research vendors, and forbidden credential categories.
- **FR-002**: The system MUST expose a capability matrix covering Binance public, Yahoo Finance, local files, Kaiko, Tardis, CoinGlass, CryptoQuant, CME/QuikStrike-style gold options sources, and forbidden v0 private trading/broker/wallet keys.
- **FR-003**: The system MUST label Binance public as supporting crypto OHLCV and limited public derivatives fields where available, with a limitation that deeper historical OI may require vendor data.
- **FR-004**: The system MUST label Yahoo Finance as OHLCV/proxy-only and MUST NOT label it as supporting crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data.
- **FR-005**: The system MUST label local files as schema-dependent and report whether required columns are present for the requested local dataset.
- **FR-006**: The system MUST mark Kaiko, Tardis, CoinGlass, CryptoQuant, and CME/QuikStrike-style vendor access as optional research providers that require explicit configuration.
- **FR-007**: The system MUST mark absent optional paid provider keys as unavailable without failing the MVP public/local workflow.
- **FR-008**: The system MUST detect configured optional research provider keys without returning secret values, partial values, hashes, or values embedded in errors.
- **FR-009**: The system MUST distinguish optional public-data vendor keys from forbidden private trading keys, broker keys, wallet/private keys, and execution credentials.
- **FR-010**: The system MUST reject or clearly flag forbidden v0 credential categories if a user attempts to onboard them.
- **FR-011**: The system MUST provide missing-data instructions for downloading and processing public Binance crypto data for BTCUSDT, ETHUSDT, SOLUSDT, and configured optional crypto symbols.
- **FR-012**: The system MUST provide missing-data instructions for downloading and processing Yahoo Finance OHLCV/proxy data for SPY, QQQ, GLD, GC=F, and BTC-USD when requested.
- **FR-013**: The system MUST provide local import instructions for XAU options OI files, including required columns `date` or `timestamp`, `expiry`, `strike`, `option_type`, and `open_interest`.
- **FR-014**: The system SHOULD document optional XAU local file columns `oi_change`, `volume`, `implied_volatility`, `underlying_futures_price`, `xauusd_spot_price`, `delta`, and `gamma`.
- **FR-015**: The system MUST preflight crypto processed feature readiness before the first evidence run.
- **FR-016**: The system MUST preflight proxy OHLCV feature readiness before the first evidence run.
- **FR-017**: The system MUST preflight XAU options OI local-file readiness before the first evidence run.
- **FR-018**: The system MUST reuse existing multi-asset research, XAU Vol-OI, and final evidence run workflows for the first evidence run instead of creating new strategy logic.
- **FR-019**: The system MUST produce or reference one final evidence report when the first evidence workflow is started.
- **FR-020**: The final evidence output MUST include completed, partial, blocked, skipped, or failed workflow status where applicable.
- **FR-021**: The final evidence output MUST include links or identifiers for generated or referenced multi-asset research, XAU Vol-OI, and evidence reports where present.
- **FR-022**: Missing workflows or assets MUST remain visible in onboarding and evidence outputs and MUST NOT be silently omitted.
- **FR-023**: The system MUST include research-only warnings and MUST NOT claim profitability, predictive power, safety, or live readiness.
- **FR-024**: The system MUST NOT require paid provider keys for the MVP first evidence workflow.
- **FR-025**: Synthetic data MAY be used in automated tests and smoke tests only, and MUST NOT be substituted for final real research runs.
- **FR-026**: Generated raw data, processed data, report artifacts, `.env` files, and local import files MUST remain ignored and untracked.
- **FR-027**: If external onboarding endpoints are provided, they SHOULD include `GET /api/v1/data-sources/readiness`, `GET /api/v1/data-sources/capabilities`, `GET /api/v1/data-sources/missing-data`, `POST /api/v1/data-sources/preflight`, `POST /api/v1/evidence/first-run`, and `GET /api/v1/evidence/first-run/{run_id}`.
- **FR-028**: The dashboard MUST show source readiness cards, provider capability matrix, configured-vs-missing optional key status, missing-data checklist, first evidence run status, report links, and research-only disclaimer.
- **FR-029**: The feature MUST NOT add live trading, paper trading, shadow trading, private exchange trading keys, broker integration, real order execution, wallet/private-key handling, Rust execution, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML model training.

### Key Entities

- **Data Source Readiness**: The current status of a data source, including availability, optional-key presence, missing requirements, unsupported capabilities, and research-only limitations.
- **Provider Capability Matrix**: A normalized list of each provider/source tier and the data categories it can and cannot support for the requested research workflows.
- **Onboarding Preflight Result**: A grouped readiness result for crypto, proxy, and XAU workflows before running evidence.
- **Missing Data Instruction**: A concrete action for downloading, processing, importing, or configuring data required to unblock a workflow.
- **Optional Provider Configuration Status**: A safe indicator showing whether a paid research provider appears configured without exposing any secret value.
- **First Evidence Run**: A research-only workflow that reuses completed report systems and produces or references one final evidence report.
- **First Evidence Run Result**: The final status, report identifiers, missing-data checklist, limitations, and research decision summary from the first evidence run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can identify available, missing, optional, and unsupported data sources for the default crypto, proxy, and XAU workflows within 2 minutes.
- **SC-002**: 100% of optional paid provider keys are reported only as configured or missing, with no secret values returned in readiness, preflight, dashboard, logs, or errors.
- **SC-003**: 100% of Yahoo Finance requests for OI, funding, IV, gold options OI, futures OI, or XAUUSD spot execution data are labeled unsupported.
- **SC-004**: 100% of missing crypto processed-feature cases return actionable Binance download/process instructions.
- **SC-005**: 100% of missing proxy OHLCV cases return actionable Yahoo Finance download/process instructions.
- **SC-006**: 100% of missing or invalid XAU options OI local files return required schema instructions.
- **SC-007**: A first evidence workflow can complete or partially complete with public/no-key and local-file MVP inputs when required data exists.
- **SC-008**: A first evidence workflow with at least one blocked workflow still returns a final evidence result that includes the blocked workflow and missing-data checklist.
- **SC-009**: The dashboard lets a researcher inspect readiness, capabilities, missing-data actions, optional-key status, first-run status, and report links without reading local files directly.
- **SC-010**: No generated raw data, processed data, reports, `.env` files, local import files, or secrets are tracked after onboarding or first-run smoke validation.
- **SC-011**: Existing backend checks, frontend build checks, and generated-artifact guard checks pass after the feature is implemented.
- **SC-012**: Reports and dashboard copy contain no buy/sell instructions and no profitability, predictive power, safety, or live-readiness claims.

## Assumptions

- Features 001 through 007 are available and provide the existing ingestion, provider, report, validation, XAU, and evidence workflow capabilities.
- MVP onboarding uses Binance public data, Yahoo Finance OHLCV/proxy data, and local CSV/Parquet imports without requiring paid data vendor keys.
- Optional paid research data providers may be detected through environment variable presence, but their values are never exposed.
- CME/QuikStrike-style gold options data is handled as local CSV/Parquet import unless a configured research provider is later added.
- Final real research runs use real public/local data; synthetic fixtures are limited to automated tests and smoke validation.
- The first evidence workflow orchestrates and documents existing systems rather than adding new strategy rules.
- Generated data and reports remain under ignored local data paths.
