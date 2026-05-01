# Feature Specification: Real Research Execution Runbook

**Feature Branch**: `007-real-research-execution-runbook`  
**Created**: 2026-05-01  
**Status**: Draft  
**Input**: User description: "Add a real research execution runbook and evidence report workflow."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Crypto Research Execution (Priority: P1)

A researcher can start a research execution run for configured crypto assets and receive a complete or blocked workflow status for each asset, using the existing multi-asset research reports and validation hardening outputs.

**Why this priority**: Crypto assets are the primary research domain for the existing OI, funding, regime, backtest, and robustness workflow. The runbook must prove the completed system can be used for actual research execution, not more infrastructure.

**Independent Test**: Can be tested with one crypto asset that has existing processed features and one crypto asset with missing features, then verifying the execution run records both completed and blocked outcomes without omitting missing data.

**Acceptance Scenarios**:

1. **Given** processed features exist for BTCUSDT, **When** a researcher starts a crypto execution workflow, **Then** the run references or triggers the existing multi-asset research report and records strategy, baseline, stress, sensitivity, walk-forward, regime coverage, and concentration evidence for BTCUSDT.
2. **Given** processed features are missing for ETHUSDT or SOLUSDT, **When** the workflow runs, **Then** the asset is marked blocked with clear download and processing instructions.
3. **Given** optional crypto assets are disabled, **When** the workflow runs, **Then** those assets are not treated as failed or missing.

---

### User Story 2 - Run Yahoo And Proxy OHLCV Research (Priority: P2)

A researcher can include Yahoo Finance or proxy OHLCV assets in an execution run and see them clearly labeled as OHLCV-only comparison assets with unsupported OI, funding, gold options OI, futures OI, IV, and XAUUSD execution capabilities.

**Why this priority**: Proxy assets provide non-crypto context, but the workflow must not misrepresent their data capabilities or use them as derivatives sources.

**Independent Test**: Can be tested with one available OHLCV proxy asset such as SPY or GC=F and one requested unsupported capability, then verifying the asset remains visible with explicit limitation labels.

**Acceptance Scenarios**:

1. **Given** processed OHLCV features exist for SPY or GC=F, **When** a proxy workflow runs, **Then** the evidence report records the asset as a price-only comparison source.
2. **Given** a Yahoo asset is requested with OI, funding, IV, gold options OI, futures OI, or XAUUSD spot execution requirements, **When** the workflow runs, **Then** the unsupported capability is labeled clearly instead of failing silently.
3. **Given** GLD or GC=F is used for gold context, **When** the evidence report is generated, **Then** the report states that the asset is an OHLCV proxy only and not a source for gold options OI, futures OI, IV, or spot execution data.

---

### User Story 3 - Run XAU Vol-OI Research Workflow (Priority: P3)

A researcher can include an XAU Vol-OI workflow using local gold options OI CSV or Parquet input and receive source validation, basis snapshot, expected range, wall table, zone table, missing-data instructions, and source limitation notes.

**Why this priority**: Gold derivatives zone research depends on local CME/COMEX-style options data, basis adjustment, and transparent limitations. This workflow connects the completed XAU wall engine to a real evidence report.

**Independent Test**: Can be tested with a synthetic local options OI fixture in automated tests and with a real local file in manual research execution, then verifying that missing files and missing IV or basis inputs produce actionable instructions.

**Acceptance Scenarios**:

1. **Given** a valid local gold options OI file and reference prices are supplied, **When** the XAU workflow runs, **Then** the execution evidence links to the generated XAU Vol-OI report and summarizes source validation, basis, expected range, wall count, and zone count.
2. **Given** the local options OI file is missing or invalid, **When** the XAU workflow runs, **Then** the XAU workflow is marked blocked with the required local import schema and instructions.
3. **Given** IV or basis inputs are unavailable, **When** the XAU workflow runs, **Then** the missing component is labeled unavailable and no IV range or spot-equivalent mapping is fabricated.

---

### User Story 4 - Produce A Final Evidence Summary (Priority: P4)

A researcher can open one final evidence report that links all produced report identifiers, summarizes completed and blocked workflows, lists missing-data actions, and assigns a research decision of continue, refine, reject, data_blocked, or inconclusive.

**Why this priority**: The runbook is valuable only if it converts many report artifacts into a concise research decision record without claiming strategy profitability or live readiness.

**Independent Test**: Can be tested by creating an execution run with one completed workflow and one blocked workflow, then verifying the evidence report contains workflow statuses, report references, limitations, missing-data instructions, and a bounded decision label.

**Acceptance Scenarios**:

1. **Given** crypto, proxy, or XAU workflows complete, **When** the evidence report is read, **Then** it lists generated report IDs, source identities, row counts, date ranges, robustness summaries, and decision labels.
2. **Given** one or more workflows are blocked, **When** the evidence report is read, **Then** blocked workflows remain visible and include next actions.
3. **Given** the dashboard is opened, **When** a researcher selects an execution run, **Then** the page shows workflow status cards, report references, missing-data checklist, evidence summary table, decision labels, and a research-only disclaimer.

### Edge Cases

- A configured asset has no processed feature file.
- A processed feature file exists but has zero rows, unreadable content, or missing required feature groups.
- A Yahoo/proxy asset is requested with OI, funding, IV, gold options OI, futures OI, or XAUUSD execution requirements.
- A crypto asset lacks OI or funding columns even though the strategy request expects them.
- A local XAU options file is missing, outside the allowed local research paths, unreadable, or missing required columns.
- XAU IV, basis, spot reference, or futures reference is unavailable.
- A referenced multi-asset, validation, or XAU report ID no longer exists.
- Some workflows complete while others are blocked.
- Generated reports or imported data exist locally but must remain untracked.
- A user attempts to interpret evidence as a live, paper, shadow, or execution-ready trading signal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a research execution run that coordinates existing crypto multi-asset research, Yahoo/proxy OHLCV research, XAU Vol-OI research, and final evidence summary workflows.
- **FR-002**: The system MUST NOT introduce new strategy logic; it MUST reuse existing research reports, validation outputs, and XAU wall reports as evidence sources.
- **FR-003**: The system MUST allow execution runs to configure primary crypto assets BTCUSDT, ETHUSDT, and SOLUSDT.
- **FR-004**: The system SHOULD allow optional crypto assets BNBUSDT, XRPUSDT, and DOGEUSDT when enabled by the researcher.
- **FR-005**: The system MUST allow proxy assets SPY, QQQ, GLD, GC=F, and BTC-USD when their required processed features are available.
- **FR-006**: The system MUST label Yahoo Finance and proxy assets as OHLCV-only where applicable.
- **FR-007**: The system MUST NOT treat Yahoo Finance or proxy assets as sources of crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data.
- **FR-008**: The system MUST check for required processed feature data before starting each asset workflow.
- **FR-009**: If processed features are missing, unreadable, empty, or incomplete, the system MUST mark the workflow blocked and provide download or processing instructions.
- **FR-010**: The crypto workflow MUST summarize regime-aware grid/range strategy, regime-aware breakout strategy, buy-and-hold baseline, price-only breakout baseline, no-trade baseline, stress tests, parameter sensitivity, walk-forward validation, regime coverage, and trade concentration when those outputs are available.
- **FR-011**: The proxy OHLCV workflow MUST summarize price-only and baseline comparisons separately from crypto OI/funding research.
- **FR-012**: The XAU workflow MUST support local CSV or Parquet gold options OI inputs and summarize source validation, basis snapshot, expected range, wall table, zone table, missing-data instructions, and source limitations.
- **FR-013**: If XAU options OI data is missing or invalid, the system MUST provide local import instructions and required schema details.
- **FR-014**: The evidence summary MUST include which workflows ran, which workflows were blocked, data sources used, row counts, date ranges, report references, limitations, warnings, and missing-data actions.
- **FR-015**: The evidence summary MUST include strategy/baseline comparison, robustness status, stress survival, walk-forward stability, trade concentration warnings, and XAU wall/zone findings when available.
- **FR-016**: The system MUST assign each workflow or asset a decision label from continue, refine, reject, data_blocked, or inconclusive.
- **FR-017**: Decision labels MUST be based on documented evidence categories and MUST NOT claim profitability, predictive power, safety, or live readiness.
- **FR-018**: The system MUST keep missing assets and blocked workflows visible in the evidence report.
- **FR-019**: The system MUST save generated evidence reports under ignored report paths and MUST NOT require committing generated reports or imported data.
- **FR-020**: The system MUST provide endpoints, if needed by the dashboard or automation, for creating, listing, reading, and inspecting execution runs, evidence, and missing-data summaries.
- **FR-021**: The dashboard MUST show an execution run selector, workflow status cards, report references, missing-data checklist, evidence summary table, decision labels, and a research-only disclaimer.
- **FR-022**: The dashboard MUST clearly distinguish crypto OI/funding research, Yahoo/proxy OHLCV-only research, and XAU local derivatives research.
- **FR-023**: The system MUST allow synthetic data only in automated tests and MUST NOT substitute synthetic data for final real-data research reports.
- **FR-024**: The feature MUST NOT add live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, Rust execution, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, or ML model training.
- **FR-025**: Reports and dashboards MUST NOT emit buy/sell instructions or claim profitability, predictive power, safety, or live readiness.

### API Surface Requirements

- **API-001**: The system SHOULD expose `POST /api/v1/research/execution-runs` for starting a research execution run when an endpoint is needed.
- **API-002**: The system SHOULD expose `GET /api/v1/research/execution-runs` for listing saved execution runs when an endpoint is needed.
- **API-003**: The system SHOULD expose `GET /api/v1/research/execution-runs/{execution_run_id}` for reading one execution run when an endpoint is needed.
- **API-004**: The system SHOULD expose `GET /api/v1/research/execution-runs/{execution_run_id}/evidence` for reading the evidence summary when an endpoint is needed.
- **API-005**: The system SHOULD expose `GET /api/v1/research/execution-runs/{execution_run_id}/missing-data` for reading missing-data actions when an endpoint is needed.
- **API-006**: Missing execution run IDs MUST return structured not-found errors.
- **API-007**: Invalid configuration and unsupported capabilities MUST return structured validation responses with user-actionable details.

### Key Entities

- **Research Execution Run**: A grouped research workflow request and result containing selected workflows, assets, report references, status, warnings, limitations, decisions, and generated evidence artifacts.
- **Workflow Configuration**: The selected crypto, proxy, and XAU workflows plus asset lists, required capabilities, local file references, and evidence options.
- **Workflow Result**: The completed, blocked, or partial outcome for one workflow, including report IDs, source identity, row counts, date ranges, warnings, and missing-data actions.
- **Evidence Summary**: The final report that links all generated report IDs and summarizes strategy/baseline comparisons, robustness, stress survival, walk-forward stability, regime coverage, concentration warnings, XAU wall/zone findings, and decision labels.
- **Missing Data Action**: A concrete instruction for downloading, processing, or locally importing data needed to unblock a workflow.
- **Capability Limitation**: A documented unsupported capability such as Yahoo OHLCV-only assets not providing OI, funding, IV, gold options OI, futures OI, or XAUUSD spot execution data.
- **Research Decision**: A bounded label of continue, refine, reject, data_blocked, or inconclusive attached to a workflow or asset based on evidence and limitations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can create an execution run containing at least one available workflow and one blocked workflow, and both outcomes appear in the evidence report.
- **SC-002**: 100% of missing processed feature cases return clear download or processing instructions.
- **SC-003**: 100% of missing or invalid XAU options OI cases return the required local import schema and instructions.
- **SC-004**: 100% of Yahoo/proxy assets requested with unsupported OI, funding, IV, gold options OI, futures OI, or XAUUSD execution capabilities are labeled unsupported instead of being silently omitted.
- **SC-005**: The evidence report links every generated crypto, proxy, validation, and XAU report ID used by the execution run.
- **SC-006**: The evidence report shows row counts and date ranges for every completed asset workflow where source data is available.
- **SC-007**: Every workflow receives exactly one decision label from continue, refine, reject, data_blocked, or inconclusive.
- **SC-008**: The dashboard evidence page lets a researcher identify completed workflows, blocked workflows, missing-data actions, and decision labels within 2 minutes for a sample execution run.
- **SC-009**: No generated data, generated evidence reports, imported local files, or synthetic test artifacts are tracked by version control after a smoke run.
- **SC-010**: Existing backend checks, frontend build checks, and artifact guard checks pass after the feature is implemented.
- **SC-011**: Reports and dashboard copy contain research-only disclaimers and contain no profitability, predictive power, safety, live-readiness, or buy/sell instruction claims.

## Assumptions

- Features 001 through 006 are available and provide the existing ingestion, feature processing, backtest reporting, validation hardening, multi-asset research, and XAU Vol-OI report capabilities.
- The first version orchestrates and summarizes existing workflows rather than creating new strategy rules.
- Real research runs use existing processed feature files and local XAU options files; synthetic data is limited to automated tests.
- If a workflow can reference an existing report instead of rerunning it, that reference is acceptable as long as the evidence report records source identity and status.
- Default crypto assets are BTCUSDT, ETHUSDT, and SOLUSDT; optional crypto assets are disabled unless requested.
- Yahoo/proxy assets are price-only context unless processed features already contain additional supported local-file columns.
- XAU options OI, IV, and basis inputs come from local imports or explicit references, not Yahoo Finance.
- Generated data and reports remain under ignored local data paths.
