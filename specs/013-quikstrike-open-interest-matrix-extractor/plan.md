# Implementation Plan: QuikStrike Open Interest Matrix Extractor

**Branch**: `codex/013-quikstrike-open-interest-matrix-extractor` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/013-quikstrike-open-interest-matrix-extractor/spec.md`

## Summary

Add a local-only, research-only extractor for QuikStrike Gold Open Interest Matrix tables discovered under `OPEN INTEREST`. The feature parses sanitized HTML table snapshots for OI Matrix, OI Change Matrix, and Volume Matrix, validates strike/expiration/option-side mapping, writes normalized rows to ignored local artifacts, and converts valid rows into the existing XAU Vol-OI local input shape without duplicating wall scoring or adding execution behavior.

The implementation builds on feature 012's privacy boundary and local report conventions, but uses a dedicated `quikstrike_matrix` backend package because this source is HTML table based, not Highcharts based. Endpoint replay, credential/session reuse, HAR capture, screenshots/OCR, paid-vendor automation, and trading behavior remain out of scope.

## Technical Context

**Language/Version**: Python 3.11+ for backend parsing, validation, conversion, report persistence, and optional local adapter; TypeScript with Next.js for optional status inspection
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, PyArrow/Parquet, JSON/Markdown report patterns, existing XAU Vol-OI local input conventions, Next.js, TypeScript, Tailwind CSS
**Storage**: Local ignored filesystem artifacts under `data/raw/quikstrike_matrix/`, `data/processed/quikstrike_matrix/`, and `data/reports/quikstrike_matrix/`; no database server
**Testing**: pytest unit/integration/contract tests using synthetic sanitized HTML table fixtures only; backend import check; full backend pytest suite; frontend production build if UI changes; generated artifact guard
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow
**Project Type**: Existing FastAPI backend plus optional Next.js dashboard inspection, with local research files
**Performance Goals**: Synthetic fixture extraction and conversion complete within normal backend test time; a local matrix run should process the three MVP table views without requiring a long-running service
**Constraints**: Local-only, research-only, user manual login/navigation, no secret/session persistence, no endpoint replay, no screenshot OCR, no generated artifact commits, no live/paper/shadow trading, no forbidden v0 technologies
**Scale/Scope**: Gold Open Interest Matrix only; three MVP views: `open_interest_matrix`, `oi_change_matrix`, and `volume_matrix`; one extraction report per local run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature adds local research extraction, validation, and conversion only.
- **Language Split**: PASS. Python is used for research parsing/conversion; TypeScript is used only for optional dashboard inspection; no Rust execution component is introduced.
- **Frontend Stack**: PASS. Any dashboard work stays within the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. Optional routes and schemas remain FastAPI/Pydantic-based.
- **Data Processing**: PASS. Extraction, validation, and conversion are deterministic and timestamped; local file artifacts remain the storage path.
- **Storage v0**: PASS. Raw rows, processed conversion output, and reports stay under ignored local `data/` paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service fan-out is introduced.
- **Data-Source Principle**: PASS. QuikStrike Matrix is treated as a local browser/manual research source with visible limitations.
- **Reliability Principle**: PASS. Strike, expiration, option-side, numeric parsing, and missing-cell checks gate downstream conversion.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/013-quikstrike-open-interest-matrix-extractor/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- api.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- api/
|   |   `-- routes/
|   |       `-- quikstrike_matrix.py
|   |-- models/
|   |   `-- quikstrike_matrix.py
|   `-- quikstrike_matrix/
|       |-- __init__.py
|       |-- table_reader.py
|       |-- metadata.py
|       |-- extraction.py
|       |-- conversion.py
|       |-- report_store.py
|       `-- local_browser.py
`-- tests/
    |-- fixtures/
    |   `-- quikstrike_matrix/
    |       `-- .gitkeep
    |-- unit/
    |   |-- test_quikstrike_matrix_models.py
    |   |-- test_quikstrike_matrix_table_reader.py
    |   |-- test_quikstrike_matrix_extraction.py
    |   |-- test_quikstrike_matrix_conversion.py
    |   |-- test_quikstrike_matrix_report_store.py
    |   `-- test_quikstrike_matrix_local_browser.py
    |-- integration/
    |   `-- test_quikstrike_matrix_flow.py
    `-- contract/
        `-- test_quikstrike_matrix_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx
    |-- services/
    |   `-- api.ts
    `-- types/
        `-- index.ts
```

**Structure Decision**: Use `backend/src/quikstrike_matrix/` as a focused package because matrix extraction has separate table parsing and validation concerns from feature 012's Highcharts extraction. Optional API routes should accept sanitized fixtures/local table snapshots and expose saved reports; they must not log in, store credentials, replay QuikStrike endpoints, or persist session material. Dashboard work is limited to saved status/report inspection.

## Phase 0 Research Decisions

Research decisions are documented in [research.md](./research.md). Key outcomes:

- HTML table extraction is the MVP path because discovery found strike rows, expiration columns, and call/put subcolumns for OI, OI Change, and Volume.
- The matrix extractor should be separate from the Highcharts extractor to avoid mixing chart-series assumptions with table header parsing.
- Conversion should require strike and expiration mapping; blank cells remain unavailable rather than zero.
- Local browser support, if included, must be a skeleton that consumes sanitized visible table snapshots only.
- Optional API/dashboard surfaces should inspect sanitized reports and fixtures, not authenticated browser sessions.

## Phase 1 Design

Design artifacts are generated with this plan:

- [data-model.md](./data-model.md): Matrix view enums, sanitized table snapshots, normalized rows, mapping validation, conversion output, report model, and state transitions.
- [contracts/api.md](./contracts/api.md): Optional local API contracts for sanitized matrix extraction, listing/detail reads, row reads, conversion, and structured errors.
- [quickstart.md](./quickstart.md): Fixture validation, optional local browser-shape smoke, artifact guard, API/dashboard smoke, and forbidden-scope review.

## Security And Privacy Constraints

- User login and QuikStrike navigation are manual and user-controlled.
- Do not store cookies, tokens, headers, authorization values, viewstate values, HAR files, screenshots, downloaded private files, credentials, or private full URLs.
- Do not replay QuikStrike ASP.NET POSTs or automate endpoint request construction.
- Do not use screenshot OCR.
- Do not accept or persist request fields named like secrets, cookies, headers, viewstate, account data, order data, broker credentials, wallet values, or private endpoint material.
- Persist only normalized table rows, conversion outputs, metadata, limitations, warnings, and local artifact references.
- Real browser extraction must fail closed if the active page is not the supported Gold Open Interest Matrix surface.

## Table Extraction Flow

1. User manually logs into QuikStrike in a local browser session.
2. User manually opens `OPEN INTEREST` and selects `Metals -> Precious Metals -> Gold (OG|GC)`.
3. User selects OI Matrix, OI Change Matrix, and Volume Matrix views.
4. The extractor receives or collects sanitized visible HTML table snapshots plus sanitized visible metadata.
5. `metadata.py` parses product, option product code, source menu, selected view, capture timestamp, and any visible futures symbol, DTE, or reference price.
6. `table_reader.py` parses table header rows, strike rows, expiration column groups, call/put subcolumns, combined columns, and cell values.
7. `extraction.py` validates table presence, strike mapping, expiration mapping, option-side mapping, numeric parsing, unavailable cells, and duplicate rows.
8. Valid and partial normalized rows are written to ignored raw matrix artifact paths.
9. `report_store.py` writes extraction metadata, JSON report, and Markdown report under ignored report paths.

## Strike / Expiration / Call-Put Mapping

- Strike is taken from numeric strike-row labels after excluding totals, separators, subtotals, and non-strike labels.
- Expiration is taken from column group headers; if headers include DTE, futures symbol, or reference price, those are preserved as metadata.
- Option type is `call` or `put` when the table has visible side-specific subcolumns.
- Option type is `combined` only when the table explicitly presents a combined value without separable call/put columns.
- Missing, blank, dash, or unavailable cells remain unavailable and are not converted to zero.
- Signed, negative, parenthesized, and comma-formatted OI Change values are normalized as numeric values when unambiguous.
- Conversion is blocked when strike or expiration cannot be determined for required rows.

## Conversion Flow

1. Load a completed or partial matrix extraction report and normalized rows.
2. Confirm every conversion-eligible row has strike, expiration, option type, value type, and numeric value.
3. Block conversion when any requested required mapping gate is missing or blocked.
4. Map `open_interest_matrix` rows to `open_interest`.
5. Map `oi_change_matrix` rows to `oi_change`.
6. Map `volume_matrix` rows to `volume`.
7. Preserve source menu, source view, table labels, missing-cell warnings, and source limitations in conversion metadata.
8. Write processed XAU Vol-OI compatible local input rows under ignored `data/processed/quikstrike_matrix/`.
9. Do not run or duplicate feature 006 wall scoring inside this feature.

## Artifact Storage

```text
data/raw/quikstrike_matrix/
|-- {extraction_id}_normalized_rows.parquet
|-- {extraction_id}_normalized_rows.json
`-- {extraction_id}_metadata.json

data/processed/quikstrike_matrix/
|-- {extraction_id}_xau_vol_oi_input.parquet
|-- {extraction_id}_xau_vol_oi_input.csv
`-- {extraction_id}_conversion_metadata.json

data/reports/quikstrike_matrix/
`-- {extraction_id}/
    |-- report.json
    `-- report.md
```

All generated paths must remain ignored and untracked. Report artifacts should store project-relative paths and validate that writes remain under configured matrix raw, processed, or report roots.

## API And Dashboard Decision

Implement API routes only as local status/report and sanitized payload helpers:

- `POST /api/v1/quikstrike-matrix/extractions/from-fixture` for sanitized metadata + HTML table fixture/local payload extraction.
- `GET /api/v1/quikstrike-matrix/extractions` for saved extraction summaries.
- `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}` for saved report detail.
- `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/rows` for normalized row inspection.
- `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/conversion` for conversion status and rows.

Do not expose endpoints that accept cookies, headers, viewstate, HAR, screenshots, credentials, or full private URLs. Do not make the API responsible for logging into QuikStrike or replaying endpoint calls.

Dashboard scope is a small `/xau-vol-oi` status panel:

- latest matrix extraction status
- OI/OI Change/Volume view coverage
- row, strike, expiry, and missing-cell counts
- conversion eligibility and blocked reasons
- generated local artifact paths
- local-only, research-only, no-secret disclaimer

## Test Strategy

- Unit tests for model validation, enum values, safe ids, safe paths, and forbidden secret/session field rejection.
- Unit tests for sanitized HTML matrix table parsing across OI, OI Change, and Volume fixtures.
- Unit tests for strike-row parsing and exclusion of totals/subtotals/non-strike labels.
- Unit tests for expiration header parsing, including DTE, futures symbol, and reference price when visible.
- Unit tests for call/put/combined option-side mapping.
- Unit tests for missing, blank, dash, zero, signed, negative, parenthesized, and comma-formatted numeric cells.
- Unit tests for normalized row generation, view coverage, duplicate-row warnings, and conversion gating.
- Unit tests for XAU Vol-OI compatible conversion and blocked conversion cases.
- Unit tests for report-store path safety, artifact metadata, JSON report, and Markdown report.
- Unit tests for local browser adapter skeleton proving it does not accept or persist cookies, headers, viewstate, HAR, screenshots, credentials, or private URLs.
- Integration test using synthetic sanitized table fixtures for all three MVP views.
- API contract tests if routes are implemented.
- Existing backend suite, frontend production build if UI changes, and generated artifact guard.
- Forbidden-scope scan for live trading, paper trading, shadow trading, private keys, broker integration, execution, credential/session storage, endpoint replay, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, and ML training.

## Implementation Phases

1. **Setup and schemas**: Add `backend/src/quikstrike_matrix/`, `backend/src/models/quikstrike_matrix.py`, safe enums/models, path helpers, fixture directory, optional route skeleton, optional frontend placeholders, and artifact guard coverage.
2. **Sanitized table parser**: Parse synthetic HTML table fixtures into header groups, strike rows, side columns, and raw cells for the three MVP views.
3. **Metadata and mapping validation**: Parse product/menu/view metadata and validate table presence, strike rows, expiration columns, option-side mapping, numeric values, missing cells, and duplicate rows.
4. **Normalized extraction**: Build normalized rows, extraction summaries, view coverage, warnings, limitations, and blocked/partial/completed statuses.
5. **XAU Vol-OI conversion**: Convert valid matrix rows to existing XAU local input fields; block unsafe rows and preserve limitations.
6. **Report persistence and optional API/dashboard**: Persist metadata, normalized rows, conversion outputs, JSON/Markdown reports; implement local report/status routes and small inspection panel.
7. **Local browser adapter skeleton**: Add minimal user-controlled adapter boundaries for sanitized visible table inputs; no credential/session/header/HAR/screenshot persistence and no endpoint replay.
8. **Final validation**: Run backend import, focused matrix unit/integration/contract tests, full backend suite, frontend build if touched, artifact guard, local fixture smoke, optional dashboard smoke, and forbidden-scope review.

## Complexity Tracking

No constitution violations or extra architectural complexity are required. The feature is additive, local-only, file-backed, and stays within existing research data-source patterns.

## Post-Design Constitution Check

- **Research-only scope**: PASS. Outputs are normalized research rows, conversion artifacts, validation metadata, and limitations only.
- **No execution behavior**: PASS. Design excludes live, paper, shadow, broker, wallet, private-key, account, order, and position workflows.
- **Allowed v0 stack**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/Parquet and optional Next.js/TypeScript/Tailwind surfaces.
- **Reproducible local storage**: PASS. Generated artifacts stay under ignored `data/raw`, `data/processed`, and `data/reports` paths.
- **Timestamp/data safety**: PASS. Capture timestamps, expiration, DTE, source view, value type, and validation status are explicit.
- **No hidden assumptions**: PASS. Strike, expiration, option-side, and missing-cell validation are required gates before downstream conversion.
- **No strategy claims**: PASS. No profitability, predictive, safety, or live-readiness claims are included.
- **No architecture redesign**: PASS. Feature 006 wall scoring and feature 010 reaction logic remain downstream consumers, not duplicated.
