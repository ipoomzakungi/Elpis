# Feature Specification: Public Data Bootstrapper

**Feature Branch**: `009-public-data-bootstrapper`  
**Created**: 2026-05-03  
**Status**: Draft  
**Input**: User description: "Add a public data bootstrapper for first evidence runs."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap Public Crypto Research Data (Priority: P1)

A researcher can start a no-key public crypto data bootstrap for the primary crypto assets and receive raw and processed research outputs that are ready for the existing evidence preflight workflow.

**Why this priority**: The first evidence workflow cannot run useful crypto research until public market data exists in the expected local research paths.

**Independent Test**: Can be fully tested by requesting the default crypto bootstrap and confirming each requested asset is reported as downloaded, skipped, or failed with row counts, date ranges, output paths, and source limitations.

**Acceptance Scenarios**:

1. **Given** no private trading keys are configured, **When** the researcher starts the default crypto bootstrap, **Then** BTCUSDT, ETHUSDT, and SOLUSDT are attempted through public data sources only and the report lists per-asset outcomes.
2. **Given** public OHLCV downloads complete for a crypto asset, **When** the bootstrap finishes, **Then** the asset has raw data and a processed feature file in ignored research data paths using the expected symbol and timeframe naming convention.
3. **Given** public open-interest or funding history is unavailable, shallow, or incomplete, **When** the bootstrap finishes, **Then** the report clearly labels the limitation and next missing-data actions instead of silently treating the data as complete.

---

### User Story 2 - Bootstrap Yahoo Proxy OHLCV Research Data (Priority: P2)

A researcher can start a no-key proxy-asset bootstrap for Yahoo Finance assets and receive OHLCV-only research outputs while unsupported capabilities remain visible.

**Why this priority**: Proxy assets provide the non-crypto comparison baseline needed by the evidence workflow, but they must not be confused with derivatives or execution datasets.

**Independent Test**: Can be fully tested by requesting SPY, QQQ, GLD, and GC=F and verifying the report marks successful OHLCV outputs while labeling unsupported OI, funding, IV, gold options OI, futures OI, and XAUUSD execution data.

**Acceptance Scenarios**:

1. **Given** the researcher requests Yahoo proxy assets, **When** the bootstrap runs, **Then** SPY, QQQ, GLD, GC=F, and optional BTC-USD are handled as OHLCV-only assets.
2. **Given** a user expects OI, funding, IV, gold options OI, futures OI, or XAUUSD execution data from Yahoo Finance, **When** the bootstrap report is reviewed, **Then** those capabilities are labeled unsupported by that source.
3. **Given** a Yahoo proxy asset returns no usable rows, **When** the bootstrap finishes, **Then** the asset is listed as failed or skipped with a clear explanation and next action.

---

### User Story 3 - Review Bootstrap Results And Evidence Readiness (Priority: P3)

A researcher can inspect a bootstrap run and immediately understand which data is ready for first evidence runs, which assets failed, and what still requires manual local import.

**Why this priority**: The bootstrapper is valuable only if users can see what changed, what is still blocked, and how to proceed without checking files manually.

**Independent Test**: Can be fully tested by reviewing a saved bootstrap report and confirming it includes downloaded assets, skipped assets, failed assets, output paths, limitations, and next missing-data actions.

**Acceptance Scenarios**:

1. **Given** a bootstrap run includes completed and failed assets, **When** the researcher opens the run detail, **Then** all outcomes remain visible and no failed or skipped asset is omitted.
2. **Given** processed outputs were created, **When** the researcher reviews the readiness summary, **Then** the report states whether the existing evidence preflight should now recognize those assets as ready.
3. **Given** XAU options OI data is not provided locally, **When** the researcher reviews the run, **Then** the report explains that XAU options OI remains a local CSV or Parquet import workflow with the required schema.

---

### User Story 4 - Start Bootstrap From The Dashboard (Priority: P4)

A researcher can use the data-source dashboard to start or inspect public bootstrap runs without exposing secrets or suggesting trading readiness.

**Why this priority**: Dashboard access reduces operational friction after the core bootstrap behavior is available.

**Independent Test**: Can be fully tested by opening the data-source dashboard, starting a public bootstrap with default settings, and confirming the status, outputs, limitations, and research-only disclaimer render.

**Acceptance Scenarios**:

1. **Given** the researcher opens the data-source dashboard, **When** bootstrap controls are shown, **Then** the page clearly states that only public/no-key or local-file research sources are used.
2. **Given** a bootstrap run exists, **When** the researcher reviews the dashboard, **Then** the run status, downloaded assets, output files, limitations, and next actions are visible.
3. **Given** optional paid provider key detection exists elsewhere in the product, **When** this bootstrap is used, **Then** paid provider keys are not required and no secret values are displayed.

### Edge Cases

- Public endpoints are unavailable, rate limited, or return partial data during a run.
- Binance public open-interest or funding responses contain fewer rows than the OHLCV window.
- A requested symbol or timeframe is not supported by the selected public source.
- A Yahoo Finance asset returns empty rows or unexpected column names.
- A rerun requests the same source, symbol, and timeframe as an existing local output.
- A symbol contains characters that could create unsafe file paths.
- Only some assets complete, leaving a mixed completed, skipped, and failed run.
- Processed outputs have too few rows for downstream feature or evidence validation.
- XAU options OI data is requested but no local CSV or Parquet file is present.
- Optional paid vendor keys are absent; absence must not fail the public bootstrap.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a public/no-key bootstrap workflow for research data collection.
- **FR-002**: System MUST NOT require private trading keys, broker credentials, wallet keys, paid vendor keys, or execution credentials for the MVP bootstrap.
- **FR-003**: System MUST support default crypto bootstrap assets BTCUSDT, ETHUSDT, and SOLUSDT.
- **FR-004**: System MUST allow optional crypto assets BNBUSDT, XRPUSDT, and DOGEUSDT to be requested.
- **FR-005**: System MUST support crypto timeframes needed by the existing evidence workflow, with 15m as the default and 1h and 1d as allowed configured timeframes.
- **FR-006**: System MUST download public crypto OHLCV data when available.
- **FR-007**: System MUST attempt public crypto funding and open-interest fields only where the public source supports them.
- **FR-008**: System MUST label Binance public open-interest history as limited when the returned depth or date coverage is shallower than the requested research window.
- **FR-009**: System MUST support default Yahoo proxy OHLCV assets SPY, QQQ, GLD, and GC=F.
- **FR-010**: System MUST allow optional Yahoo proxy asset BTC-USD to be requested.
- **FR-011**: System MUST treat Yahoo Finance as OHLCV-only and unsupported for crypto OI, funding, gold options OI, futures OI, IV, and XAUUSD execution data.
- **FR-012**: System MUST keep XAU options OI as a local CSV or Parquet import workflow unless a future approved source is explicitly added.
- **FR-013**: System MUST show XAU local import instructions including required columns date or timestamp, expiry, strike, option_type, and open_interest.
- **FR-014**: System MUST save raw downloaded research data under ignored raw data paths.
- **FR-015**: System MUST save processed readiness files under ignored processed data paths using the expected `{symbol}_{timeframe}_features.parquet` naming convention.
- **FR-016**: System MUST create a bootstrap report for every run.
- **FR-017**: Each bootstrap report MUST include requested assets, downloaded assets, skipped assets, failed assets, row counts, date ranges, output paths, source limitations, and next missing-data actions.
- **FR-018**: System MUST expose a way to start a public bootstrap run and retrieve saved bootstrap run summaries and details.
- **FR-019**: System MUST support these external interaction paths: `POST /api/v1/data-sources/bootstrap/public`, `GET /api/v1/data-sources/bootstrap/runs`, and `GET /api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}`.
- **FR-020**: System MUST show bootstrap run status, downloaded assets, output files, limitations, and start controls on the data-source dashboard or a dedicated bootstrap dashboard.
- **FR-021**: System MUST never return, log in reports, or display secret values, masked secret values, partial secret values, or secret hashes.
- **FR-022**: System MUST keep generated raw data, processed data, reports, and environment files ignored and untracked.
- **FR-023**: System MUST not claim profitability, predictive power, safety, execution readiness, or live-readiness.
- **FR-024**: System MUST not introduce live trading, paper trading, shadow trading, broker integration, real order execution, wallet/private-key handling, or forbidden v0 technologies.
- **FR-025**: System MUST preserve partial bootstrap results so completed assets remain usable even when other requested assets fail.
- **FR-026**: System MUST make failed and skipped assets visible with actionable reasons.
- **FR-027**: System MUST make clear whether generated processed files should be recognized by the existing first evidence preflight.

### Key Entities

- **Public Bootstrap Request**: A researcher's requested sources, assets, timeframes, date window, and acknowledgement that the workflow is research-only.
- **Bootstrap Source**: A public or local data source category such as Binance public, Yahoo Finance, or XAU local file import.
- **Bootstrap Asset Result**: Per-source and per-asset outcome containing status, row count, date range, output paths, limitations, and missing-data actions.
- **Bootstrap Artifact**: A raw or processed local file produced by the bootstrap and kept under ignored research data paths.
- **Bootstrap Report**: A saved run record summarizing completed, skipped, and failed assets plus downstream readiness and limitations.
- **Source Limitation**: A user-facing statement describing unavailable, incomplete, unsupported, or shallow source coverage.
- **Missing Data Action**: A concrete next step for obtaining or importing data needed by an evidence workflow.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can start the default public bootstrap for BTCUSDT, ETHUSDT, and SOLUSDT without entering any private key or paid vendor credential.
- **SC-002**: A researcher can start the default Yahoo proxy bootstrap for SPY, QQQ, GLD, and GC=F without entering any private key or paid vendor credential.
- **SC-003**: For every requested asset, the saved bootstrap report shows exactly one final status: downloaded, skipped, or failed.
- **SC-004**: Completed assets show row count, start date, end date, and at least one output path in the bootstrap report.
- **SC-005**: 100% of Yahoo Finance bootstrap results label unsupported OI, funding, IV, gold options OI, futures OI, and XAUUSD execution capabilities as unsupported when those capabilities are relevant.
- **SC-006**: Completed processed outputs can be detected by the existing evidence preflight without manual path edits.
- **SC-007**: XAU options OI remains blocked with local import instructions when no local CSV or Parquet file is provided.
- **SC-008**: No generated raw data, processed data, reports, environment files, or secret values are included in version control.
- **SC-009**: The dashboard or report allows a researcher to understand what data is ready, what failed, and what next action is needed in under 2 minutes.

## Assumptions

- The default crypto bootstrap uses the 15m timeframe because prior evidence workflows rely on BTCUSDT 15m-style processed features.
- 1h and 1d are supported as configured research timeframes when requested.
- The default Yahoo proxy bootstrap uses daily OHLCV because Yahoo proxy assets are used for longer-history comparison baselines.
- If the same source, symbol, and timeframe are bootstrapped again, the system may update the local raw and processed files while preserving a new bootstrap report record.
- Optional paid vendor key detection may continue to exist as readiness context, but this feature does not require or use paid vendor integrations.
- Automated tests use mocked public responses or synthetic local fixtures; real external downloads are only used by an explicit user-run bootstrap.
- Existing feature 008 preflight naming and readiness conventions remain the downstream contract for processed outputs.
