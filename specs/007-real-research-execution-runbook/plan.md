# Implementation Plan: Real Research Execution Runbook

**Branch**: `007-real-research-execution-runbook` | **Date**: 2026-05-01 | **Spec**: `specs/007-real-research-execution-runbook/spec.md`
**Input**: Feature specification from `specs/007-real-research-execution-runbook/spec.md`

## Summary

Add a research-only execution runbook that coordinates completed Elpis research systems instead of creating new strategy logic. The feature introduces a focused `research_execution` backend package, Pydantic schemas, FastAPI endpoints, local report persistence under `data/reports/research_execution/`, and an Evidence dashboard page. It reuses the multi-asset research reports from feature 005, the XAU Vol-OI reports from feature 006, and existing validation artifacts to produce a final evidence summary with completed, partial, blocked, skipped, or failed workflow statuses and bounded research decision labels.

## Technical Context

**Language/Version**: Python 3.11+ for backend orchestration; TypeScript with Next.js for dashboard UI  
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, DuckDB, Parquet, PyArrow, Next.js, Tailwind CSS, Recharts/lightweight-charts where already present  
**Storage**: Existing local ignored filesystem storage; generated evidence artifacts under `data/reports/research_execution/`  
**Testing**: `pytest` for backend unit/integration/contract tests; `npm run build` for frontend; `scripts/check_generated_artifacts.ps1` for artifact guard  
**Target Platform**: Local research workstation and GitHub Actions compatible with the existing validation workflow  
**Project Type**: Full-stack research web application with FastAPI backend and Next.js dashboard  
**Performance Goals**: Evidence aggregation should complete quickly for small local report sets and should avoid reprocessing data when existing report IDs are supplied  
**Constraints**: Research-only; no live, paper, shadow, broker, private-key, real execution, Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML model training additions  
**Scale/Scope**: One execution run coordinates crypto, proxy OHLCV, and XAU workflows across the asset lists defined in the spec; initial implementation is local-file/report based

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. Feature summarizes evidence and missing data; it does not create execution or trading approval behavior.
- **Language Split**: PASS. Uses Python for orchestration/report aggregation and TypeScript for dashboard UI; no Rust execution components.
- **Frontend Stack**: PASS. Uses the existing Next.js/TypeScript/Tailwind dashboard.
- **Backend Stack**: PASS. Uses FastAPI and Pydantic schemas within the existing backend.
- **Data Processing**: PASS. Reuses existing Polars/Parquet report and validation artifacts; no timestamp-sensitive feature logic is reinvented.
- **Storage v0**: PASS. Stores generated artifacts under ignored local `data/reports/research_execution/`.
- **Event Architecture**: PASS. No Kafka, Redpanda, NATS, or service bus.
- **Data-Source Principle**: PASS. Reads existing processed features and report artifacts; keeps Yahoo/proxy limitations explicit.
- **TradingView Principle**: PASS. No TradingView dependency or source-of-truth change.
- **Reliability Principle**: PASS. Requires preflight and missing-data states before evidence decisions.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, key, wallet, or order behavior.

## Project Structure

### Documentation (this feature)

```text
specs/007-real-research-execution-runbook/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
`-- tasks.md
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- api/
|   |   |-- routes/
|   |   |   `-- research_execution.py
|   |   `-- validation.py
|   |-- models/
|   |   `-- research_execution.py
|   |-- research/
|   |   `-- report_store.py        # existing feature 005 dependency
|   |-- research_execution/
|   |   |-- __init__.py
|   |   |-- aggregation.py
|   |   |-- orchestration.py
|   |   |-- preflight.py
|   |   `-- report_store.py
|   |-- reports/
|   |   `-- writer.py
|   `-- xau/
|       `-- report_store.py        # existing feature 006 dependency
`-- tests/
    |-- contract/
    |   `-- test_research_execution_api_contracts.py
    |-- integration/
    |   |-- test_research_execution_flow.py
    |   |-- test_research_execution_missing_crypto.py
    |   `-- test_research_execution_missing_xau.py
    `-- unit/
        |-- test_research_execution_aggregation.py
        |-- test_research_execution_config.py
        |-- test_research_execution_preflight.py
        `-- test_research_execution_unsupported_capabilities.py

frontend/
`-- src/
    |-- app/
    |   `-- evidence/
    |       `-- page.tsx
    |-- components/
    |   `-- ui/
    |       `-- Header.tsx
    |-- services/
    |   `-- api.ts
    `-- types/
        `-- index.ts
```

**Structure Decision**: Add a focused backend package under `backend/src/research_execution/` and a dashboard page at `/evidence`. Keep existing feature 005 and 006 packages as dependencies rather than merging or redesigning them.

## Data Preflight Flow

1. Normalize the execution request into explicit crypto, proxy, and XAU workflow configs.
2. Resolve processed feature paths for requested crypto/proxy assets using existing storage conventions.
3. Validate that each required path remains under allowed local research data/report roots.
4. Inspect processed feature files for readability, row count, date range, and required capability columns.
5. Validate XAU local options OI file paths and required schema through the existing XAU import/report workflow.
6. Detect unsupported capabilities such as Yahoo/proxy OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data.
7. Return preflight results with status, missing-data instructions, source limitations, and research-only warnings before orchestration proceeds.

## Execution Run Lifecycle

1. `requested`: API accepts `ResearchExecutionRunRequest`.
2. `preflighted`: `preflight.py` produces workflow-level readiness, blocked states, and missing-data actions.
3. `orchestrating`: `orchestration.py` references or invokes existing multi-asset and XAU workflows where inputs are ready.
4. `aggregating`: `aggregation.py` reads existing report outputs and creates evidence summaries.
5. `persisted`: `report_store.py` writes metadata, normalized config, evidence JSON, evidence Markdown, and missing-data checklist under `data/reports/research_execution/`.
6. `readable`: API list/detail/evidence/missing-data endpoints return persisted artifacts to the dashboard.

Workflow statuses are limited to `completed`, `partial`, `blocked`, `skipped`, and `failed`.

## Evidence Aggregation Flow

1. Load linked multi-asset research report summaries from feature 005.
2. Load linked validation sections for stress survival, parameter sensitivity, walk-forward stability, regime coverage, and trade concentration.
3. Load linked XAU Vol-OI reports from feature 006 for source validation, basis snapshot, expected range, wall table, and zone table summaries.
4. Normalize all evidence into workflow result rows with workflow type, status, source identity, row counts, date ranges, report references, warnings, limitations, and missing-data actions.
5. Classify each workflow with exactly one decision label.
6. Produce a final evidence summary table and missing-data checklist.

## Decision Classification Rules

- `data_blocked`: Required processed features, XAU options OI file, or required referenced reports are missing, unreadable, empty, or outside allowed paths.
- `inconclusive`: Inputs exist but evidence is too thin, such as too few rows, too few trades, incomplete validation sections, or unavailable date ranges.
- `reject`: Evidence is consistently worse than relevant baselines or fails required robustness checks under the documented assumptions.
- `refine`: Some evidence exists, but stress, walk-forward, concentration, regime coverage, or source-limitation warnings are significant.
- `continue`: Baseline comparison, stress survival, walk-forward stability, regime coverage, and concentration checks are acceptable under the documented assumptions.

Every decision label is a research decision only. It is not a trading approval, profitability claim, predictive claim, safety claim, or live-readiness claim.

## API Design

All endpoints are FastAPI routes under `/api/v1/research/execution-runs`:

- `POST /api/v1/research/execution-runs`: Create an execution run and persist evidence artifacts.
- `GET /api/v1/research/execution-runs`: List saved execution runs.
- `GET /api/v1/research/execution-runs/{execution_run_id}`: Read one persisted execution run.
- `GET /api/v1/research/execution-runs/{execution_run_id}/evidence`: Read final evidence summary.
- `GET /api/v1/research/execution-runs/{execution_run_id}/missing-data`: Read missing-data checklist.

Structured error helpers will cover invalid config, unsupported capabilities, unsafe paths, and missing execution run IDs.

## Dashboard Design

Add `/evidence` with:

- Execution run selector.
- Workflow status cards for crypto, proxy, XAU, and final evidence.
- Linked multi-asset and XAU report IDs.
- Evidence decision table with labels and reasons.
- Missing-data checklist with download, processing, or local import actions.
- Capability and source limitation notes, including Yahoo/proxy OHLCV-only labeling.
- Research-only disclaimer that avoids profitability, predictive, safety, live-readiness, and buy/sell wording.

## Test Strategy

- Unit tests for execution config validation and forbidden field rejection.
- Unit tests for processed feature and XAU options OI preflight.
- Unit tests for unsupported capability handling.
- Unit tests for evidence decision rules.
- Integration tests using synthetic processed features and synthetic XAU local options files only.
- Integration tests for missing crypto processed features and missing XAU options OI file.
- API contract tests for create/list/detail/evidence/missing-data endpoints.
- Frontend production build for `/evidence`.
- Existing backend test suite and artifact guard.

## Implementation Phases

1. **Setup**: Create `research_execution` package, model file, API route placeholder, evidence page placeholder, and shared test helpers.
2. **Foundation**: Add Pydantic schemas, preflight skeleton, aggregation skeleton, report store skeleton, API validation helpers, route registration, report writer hooks, frontend types, and API client placeholders.
3. **User Story 1**: Implement crypto research execution using existing multi-asset reports and processed feature preflight.
4. **User Story 2**: Implement proxy OHLCV workflow and unsupported capability labeling.
5. **User Story 3**: Implement XAU Vol-OI workflow references and local file missing-data handling.
6. **User Story 4**: Implement final evidence summary, decision labels, endpoints, and Evidence dashboard.
7. **Polish**: Run backend/frontend/artifact guard checks, API smoke, dashboard smoke, forbidden-scope review, and final task completion updates.

## Post-Design Constitution Check

- **Research-only scope**: PASS. All workflow outputs are evidence and missing-data summaries, not trading actions.
- **No forbidden v0 technology**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/DuckDB/Parquet and Next.js/TypeScript stack.
- **No new strategy logic**: PASS. Design references and aggregates existing reports from features 005 and 006.
- **Reproducible storage**: PASS. Generated artifacts remain under ignored local `data/reports/research_execution/`.
- **Timestamp/data safety**: PASS. Preflight requires row counts, date ranges, and path safety before evidence classification.
- **Dashboard clarity**: PASS. UI explicitly separates completed, partial, blocked, skipped, and failed workflows with limitations.

## Complexity Tracking

No constitution violations are introduced.
