# Implementation Plan: QuikStrike Local Highcharts Extractor

**Branch**: `012-quikstrike-local-highcharts-extractor` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/012-quikstrike-local-highcharts-extractor/spec.md`

## Summary

Add a local-only, research-only QuikStrike extraction workflow for Gold options data exposed in the user-controlled authenticated QuikStrike `QUIKOPTIONS VOL2VOL` page. The feature parses sanitized Highcharts chart objects and sanitized visible DOM metadata, validates view coverage and strike mapping confidence, writes normalized QuikStrike rows to ignored local artifacts, and converts validated rows into the existing XAU Vol-OI local input shape without duplicating feature 006 wall scoring logic.

The feature builds on 006, 010, and 011 by providing a guarded local data source for XAU options research. Direct ASP.NET endpoint replay, credential/session reuse, HAR capture, screenshots/OCR, paid-vendor integration, and trading/execution behavior are out of scope.

## Technical Context

**Language/Version**: Python 3.11+ for backend parsing, validation, conversion, report persistence, and optional local adapter; TypeScript with Next.js for status inspection if dashboard work is included
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, PyArrow/Parquet, JSON/Markdown report patterns, existing XAU Vol-OI local input conventions, Next.js, TypeScript, Tailwind CSS
**Storage**: Local ignored filesystem artifacts under `data/raw/quikstrike/`, `data/processed/quikstrike/`, and `data/reports/quikstrike/`; no database server
**Testing**: pytest unit/integration/contract tests using synthetic Highcharts and DOM fixtures; backend import check; full backend pytest suite; frontend production build if UI changes; generated artifact guard
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow
**Project Type**: Existing FastAPI backend plus optional Next.js dashboard inspection, with local research files
**Performance Goals**: Synthetic fixture extraction and conversion complete within normal backend test time; real local extraction should process five Vol2Vol chart views in an interactive research run without long-running background services
**Constraints**: Local-only, research-only, user manual login/navigation, no secret/session persistence, no ASP.NET endpoint replay, no screenshot OCR, no generated artifact commits, no live/paper/shadow trading, no forbidden v0 technologies
**Scale/Scope**: Gold `QUIKOPTIONS VOL2VOL` only; five supported views: `intraday_volume`, `eod_volume`, `open_interest`, `oi_change`, and `churn`; one extraction report per local run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature adds a local research data extraction and validation workflow only.
- **Language Split**: PASS. Python is used for research parsing/conversion; TypeScript is used only for dashboard inspection; no Rust execution component is introduced.
- **Frontend Stack**: PASS. Any dashboard work stays within the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. Optional routes and schemas remain FastAPI/Pydantic-based.
- **Data Processing**: PASS. Extraction, validation, and conversion are deterministic and timestamped; Polars/Parquet remain the local data path.
- **Storage v0**: PASS. Raw rows, processed conversion output, and reports stay under ignored local `data/` paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service fan-out is introduced.
- **Data-Source Principle**: PASS. QuikStrike is treated as a local browser/manual research source with visible limitations, not as a hidden strategy dependency.
- **Reliability Principle**: PASS. Strike mapping confidence, missing views, and source limitations are validation gates before downstream use.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/012-quikstrike-local-highcharts-extractor/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md                 # Created later by /speckit-tasks
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- api/
|   |   `-- routes/
|   |       `-- quikstrike.py               # optional local extraction/report routes
|   |-- models/
|   |   `-- quikstrike.py                   # request/result/row/report schemas
|   `-- quikstrike/
|       |-- __init__.py
|       |-- highcharts_reader.py            # parse sanitized Highcharts chart objects
|       |-- dom_metadata.py                 # parse product/expiry/DTE/reference price
|       |-- extraction.py                   # normalize rows and validate coverage/mapping
|       |-- conversion.py                   # convert valid rows to XAU Vol-OI input rows
|       |-- report_store.py                 # metadata, rows, conversion, JSON/Markdown
|       `-- local_browser.py                # local adapter skeleton, no secret storage
`-- tests/
    |-- fixtures/
    |   `-- quikstrike/
    |       `-- .gitkeep
    |-- unit/
    |   |-- test_quikstrike_models.py
    |   |-- test_quikstrike_highcharts_reader.py
    |   |-- test_quikstrike_dom_metadata.py
    |   |-- test_quikstrike_extraction.py
    |   |-- test_quikstrike_conversion.py
    |   |-- test_quikstrike_report_store.py
    |   `-- test_quikstrike_local_browser.py
    |-- integration/
    |   `-- test_quikstrike_extraction_flow.py
    `-- contract/
        `-- test_quikstrike_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   |-- data-sources/
    |   |   `-- page.tsx                    # optional local source status panel
    |   `-- xau-vol-oi/
    |       `-- page.tsx                    # optional extraction coverage panel
    |-- services/
    |   `-- api.ts                         # optional QuikStrike report clients
    `-- types/
        `-- index.ts                       # optional QuikStrike status types
```

**Structure Decision**: Use `backend/src/quikstrike/` as a focused package because the feature has source-specific parsing, validation, conversion, and local artifact responsibilities. Keep optional API routes additive under `backend/src/api/routes/quikstrike.py`; they should accept sanitized payloads and inspect saved reports, not drive authenticated browsing or replay private endpoint requests. Dashboard work is optional and limited to readiness/status inspection.

## Phase 0 Research Decisions

Research decisions are documented in [research.md](./research.md). Key outcomes:

- Highcharts memory is the preferred extraction source because discovery found structured chart series and no CSV/Excel/JSON export.
- ASP.NET postback replay is rejected because it depends on viewstate/event fields and risks session material capture.
- The local browser adapter should be a small skeleton that consumes a user-controlled authenticated session and returns sanitized DOM/chart objects only.
- Strike mapping must be a validation gate; uncertain mapping blocks XAU Vol-OI conversion.
- API routes, if implemented, should support sanitized extraction payloads and saved report reads, not credential/session handling.

## Phase 1 Design

Design artifacts are generated with this plan:

- [data-model.md](./data-model.md): View/series enums, sanitized input objects, normalized rows, validation result, conversion output, report model, and state transitions.
- [contracts/api.md](./contracts/api.md): Optional local API contracts for sanitized extraction creation, listing/detail reads, row reads, conversion, readiness, and structured errors.
- [quickstart.md](./quickstart.md): Fixture validation, optional local browser shape smoke, artifact guard, API/dashboard smoke, and forbidden-scope review.

## Security And Privacy Constraints

- User login and QuikStrike navigation are manual and user-controlled.
- Do not store cookies, tokens, headers, authorization values, viewstate values, HAR files, screenshots, downloaded private files, or private full URLs.
- Do not replay ASP.NET POSTs or automate endpoint request construction.
- Do not use screenshot OCR.
- Do not accept or persist request fields named like secrets, cookies, headers, viewstate, account data, order data, broker credentials, wallet values, or private endpoint material.
- Persist only normalized chart rows, conversion outputs, metadata, limitations, warnings, and local artifact references.
- Real browser extraction must fail closed if the active page is not the supported Gold Vol2Vol surface.

## Extraction Flow

1. User manually logs into QuikStrike in a local browser session.
2. User manually opens `QUIKOPTIONS VOL2VOL` and selects `Metals -> Precious Metals -> Gold (OG|GC)`.
3. The local extractor receives or collects sanitized DOM metadata and sanitized Highcharts chart objects.
4. `dom_metadata.py` parses product, option product code, expiration, DTE, and future reference price from sanitized visible text.
5. `highcharts_reader.py` parses series metadata and point shapes for Put, Call, Vol Settle, and Ranges.
6. `extraction.py` validates requested view type, non-empty rows, Put/Call separation, Vol Settle/Range availability, DTE/reference price availability, and strike mapping confidence.
7. Valid and partial normalized rows are written to ignored raw QuikStrike artifact paths.
8. `report_store.py` writes extraction metadata, JSON report, and Markdown report under ignored report paths.

## Conversion Flow

1. Load a completed QuikStrike extraction report and normalized rows.
2. Confirm all required fields exist and strike mapping confidence is high enough.
3. Block conversion if any required view or mapping gate is missing or partial.
4. Map `intraday_volume` and `eod_volume` rows into volume-style XAU local input fields.
5. Map `open_interest` rows into `open_interest`.
6. Map `oi_change` rows into `oi_change`.
7. Preserve `churn` as a churn/freshness context field without treating it as strike-level OI.
8. Preserve source limitations and extraction warnings in conversion metadata.
9. Write processed XAU Vol-OI compatible local input rows under ignored `data/processed/quikstrike/`.

## Artifact Storage

```text
data/raw/quikstrike/
|-- {extraction_id}_normalized_rows.parquet
|-- {extraction_id}_normalized_rows.json
`-- {extraction_id}_metadata.json

data/processed/quikstrike/
|-- {extraction_id}_xau_vol_oi_input.parquet
|-- {extraction_id}_xau_vol_oi_input.csv
`-- {extraction_id}_conversion_metadata.json

data/reports/quikstrike/
`-- {extraction_id}/
    |-- report.json
    `-- report.md
```

All generated paths must remain ignored and untracked. Report artifacts should store project-relative paths and validate that writes remain under configured QuikStrike raw, processed, or report roots.

## API And Dashboard Decision

Implement API routes only as local status/report and sanitized payload helpers:

- `POST /api/v1/quikstrike/extractions` for sanitized DOM + Highcharts fixture/local payload extraction.
- `GET /api/v1/quikstrike/extractions` for saved extraction summaries.
- `GET /api/v1/quikstrike/extractions/{extraction_id}` for saved report detail.
- `GET /api/v1/quikstrike/extractions/{extraction_id}/rows` for normalized row inspection.
- `POST /api/v1/quikstrike/extractions/{extraction_id}/convert-xau-vol-oi` for gated conversion.

Do not expose endpoints that accept cookies, headers, viewstate, HAR, screenshots, credentials, or full private URLs. Do not make the API responsible for logging into QuikStrike or replaying ASP.NET postbacks.

Dashboard scope is a small status panel only if needed by implementation phase:

- local browser extraction readiness checklist
- latest extraction status
- five-view coverage
- row counts
- strike mapping confidence
- missing view warnings
- conversion eligibility
- generated local artifact paths
- research-only and local-only disclaimer

## Test Strategy

- Unit tests for model validation, enum values, safe ids, safe paths, and forbidden secret/session field rejection.
- Unit tests for Highcharts fixture parsing across Put, Call, Vol Settle, and Ranges.
- Unit tests for DOM metadata parsing of product, option code, expiration, DTE, and future reference price.
- Unit tests for view type mapping and value type assignment.
- Unit tests for normalized row generation, non-empty view coverage, Put/Call separation, and missing-series warnings.
- Unit tests for strike mapping confidence: confident, partial, conflicting, and unavailable.
- Unit tests for conversion to XAU Vol-OI compatible local rows and conversion blocking when mapping is uncertain.
- Unit tests for report-store path safety and JSON/Markdown composition.
- Unit tests for local browser adapter skeleton proving it does not accept/persist cookies, headers, viewstate, HAR, screenshots, or private URLs.
- Integration test using synthetic Highcharts + DOM fixtures for all five views.
- API contract tests if routes are implemented.
- Existing backend suite, frontend production build if UI changes, and generated artifact guard.
- Forbidden-scope scan for live trading, paper trading, shadow trading, private keys, broker integration, execution, credential/session storage, endpoint replay, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, and ML training.

## Implementation Phases

1. **Setup and schemas**: Add `backend/src/quikstrike/`, `backend/src/models/quikstrike.py`, safe enums/models, path helpers, fixture directory, optional route skeleton, frontend placeholders if dashboard/API status is included, and artifact guard coverage.
2. **Highcharts fixture parser**: Parse sanitized chart objects, series names, point x/y values, and point metadata for Put, Call, Vol Settle, and Ranges.
3. **DOM metadata parser**: Parse product, option product code, expiration, DTE, future reference price, and supported page surface markers from sanitized text.
4. **Normalized row builder and validation**: Combine DOM metadata and chart series, validate view type coverage, Put/Call separation, row counts, missing series, and strike mapping confidence.
5. **XAU Vol-OI conversion**: Convert confidently mapped normalized rows to existing XAU local input fields; block partial/uncertain outputs and preserve limitations.
6. **Report persistence and optional API/dashboard**: Persist metadata, normalized rows, conversion outputs, JSON/Markdown reports; implement local report/status routes and small inspection panel if included.
7. **Local browser adapter skeleton**: Add minimal user-controlled adapter boundaries for sanitized browser-memory inputs; no credential/session/header/HAR/screenshot persistence and no endpoint replay.
8. **Final validation**: Run backend import, focused QuikStrike unit/integration/contract tests, full backend suite, frontend build if touched, artifact guard, local fixture smoke, optional dashboard smoke, and forbidden-scope review.

## Complexity Tracking

No constitution violations or extra architectural complexity are required. The feature is additive, local-only, file-backed, and stays within existing research data-source patterns.

## Post-Design Constitution Check

- **Research-only scope**: PASS. Outputs are normalized research rows, conversion artifacts, validation metadata, and limitations only.
- **No execution behavior**: PASS. Design excludes live, paper, shadow, broker, wallet, private-key, account, order, and position workflows.
- **Allowed v0 stack**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/Parquet and optional Next.js/TypeScript/Tailwind surfaces.
- **Reproducible local storage**: PASS. Generated artifacts stay under ignored `data/raw`, `data/processed`, and `data/reports` paths.
- **Timestamp/data safety**: PASS. Capture timestamps, expiration, DTE, future reference price, view type, and validation status are explicit.
- **No hidden assumptions**: PASS. Strike mapping confidence and source limitations are required gates before downstream conversion.
- **No strategy claims**: PASS. No profitability, predictive, safety, or live-readiness claims are included.
- **No architecture redesign**: PASS. Feature 006 wall scoring and feature 010 reaction logic remain downstream consumers, not duplicated.
