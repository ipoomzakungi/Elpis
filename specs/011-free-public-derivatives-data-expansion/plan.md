# Implementation Plan: Free Public Derivatives Data Expansion

**Branch**: `011-free-public-derivatives-data-expansion` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/011-free-public-derivatives-data-expansion/spec.md`

## Summary

Add a research-only free derivatives data expansion workflow that collects or imports official/public CFTC COT gold positioning, public GVZ daily close proxy volatility, and Deribit public crypto options IV/OI snapshots. The feature adds focused backend modules under `backend/src/free_derivatives/`, schemas under `backend/src/models/free_derivatives.py`, additive API routes under `backend/src/api/routes/free_derivatives.py`, readiness/capability integration with existing `backend/src/data_sources/`, ignored raw/processed/report artifact storage, and a small `/data-sources` dashboard extension for source status, output paths, and limitations.

The feature builds on 008/009/010 by reusing data-source readiness, public bootstrap, missing-data, local artifact, and dashboard conventions. It does not redesign the system, add trading or execution behavior, require paid vendors, or treat CFTC/GVZ/Deribit as replacements for local XAU strike-level options OI.

## Technical Context

**Language/Version**: Python 3.11+ for backend data collection, parsing, processing, and orchestration; TypeScript with Next.js for dashboard inspection  
**Primary Dependencies**: Existing FastAPI, Pydantic, Pydantic Settings, Polars, PyArrow/Parquet, httpx-style public HTTP clients, existing data-source readiness/bootstrap/report-store patterns, Next.js, TypeScript, Tailwind CSS  
**Storage**: Local ignored filesystem artifacts under `data/raw/cftc/`, `data/raw/gvz/`, `data/raw/deribit/`, `data/processed/cftc/`, `data/processed/gvz/`, `data/processed/deribit/`, and `data/reports/free_derivatives/`; no database server  
**Testing**: pytest unit, integration, and API contract tests with mocked responses/local fixtures only; backend import check; full backend pytest suite; frontend production build; generated artifact guard  
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow  
**Project Type**: Existing FastAPI backend plus Next.js dashboard with local research files  
**Performance Goals**: Mocked/fixture bootstrap runs complete inside normal backend test time; real explicit runs preserve partial per-source results and should not fail all sources when one public source is unavailable  
**Constraints**: Research-only, free/no-paid-vendor sources only, no private keys, no secret exposure, no generated artifact commits, no live external downloads in automated tests, no trading endpoints, no forbidden v0 technologies  
**Scale/Scope**: CFTC gold/COMEX weekly positioning for selected years/categories; GVZ daily close for requested date window; Deribit public option snapshots for BTC/ETH baseline and SOL only when public options are available

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature collects and labels research data only; it does not claim strategy validity or enable execution.
- **Language Split**: PASS. Python is used for research data processing and orchestration; TypeScript is used for dashboard inspection; no Rust execution component is added.
- **Frontend Stack**: PASS. Dashboard work stays in the existing Next.js/TypeScript/Tailwind application.
- **Backend Stack**: PASS. API and schemas remain FastAPI/Pydantic-based and reuse existing backend conventions.
- **Data Processing**: PASS. Processing is deterministic and timestamp/date-safe, with Polars and Parquet for local research outputs.
- **Storage v0**: PASS. Raw data, processed data, and run reports stay under local ignored `data/` paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service redesign is introduced.
- **Data-Source Principle**: PASS. Official/public data is used first; paid vendors are not required; source limits are visible.
- **Reliability Principle**: PASS. Source limitations, partial statuses, missing-data actions, and fixture-only tests prevent hidden assumptions.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, account, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/011-free-public-derivatives-data-expansion/
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
|   |       |-- data_sources.py              # extend dashboard aggregation if useful
|   |       `-- free_derivatives.py          # new free-derivatives bootstrap routes
|   |-- data_sources/
|   |   |-- capabilities.py                  # add cftc_cot/gvz/deribit entries
|   |   |-- missing_data.py                  # add free-derivatives missing actions
|   |   `-- readiness.py                     # include free public source statuses
|   |-- free_derivatives/
|   |   |-- __init__.py
|   |   |-- cftc.py                          # CFTC request planning, parsing, filtering
|   |   |-- gvz.py                           # GVZ request planning, parsing, gap labeling
|   |   |-- deribit.py                       # Deribit public option normalization
|   |   |-- processing.py                    # processed summaries and wall snapshots
|   |   |-- orchestration.py                 # run lifecycle and source fan-out
|   |   `-- report_store.py                 # metadata and artifact persistence
|   `-- models/
|       |-- data_sources.py                  # add provider enum entries if needed
|       `-- free_derivatives.py             # new request/result/source schemas
`-- tests/
    |-- unit/
    |   |-- test_free_derivatives_cftc.py
    |   |-- test_free_derivatives_gvz.py
    |   |-- test_free_derivatives_deribit.py
    |   |-- test_free_derivatives_models.py
    |   `-- test_free_derivatives_limitations.py
    |-- integration/
    |   `-- test_free_derivatives_flow.py
    `-- contract/
        `-- test_free_derivatives_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- data-sources/
    |       `-- page.tsx                    # add compact free-derivatives section
    |-- services/
    |   `-- api.ts                         # add free-derivatives client methods
    `-- types/
        `-- index.ts                       # add free-derivatives request/result types
```

**Structure Decision**: Use `backend/src/free_derivatives/` as the canonical implementation package because the feature has multi-source parsing and processing responsibilities that are larger than static readiness metadata. Integrate into `backend/src/data_sources/` only for readiness, capability, and missing-data surfaces. Keep routes additive under `/api/v1/data-sources/bootstrap/free-derivatives` so the user-facing data-source bootstrap model from 008/009 remains intact.

## Phase 0 Research Decisions

Research decisions are documented in [research.md](./research.md). Key outcomes:

- CFTC COT will be treated as weekly broad gold/COMEX positioning and never as strike-level options OI or intraday wall data.
- GVZ will be treated as a daily GLD-options-derived volatility proxy, not as a CME gold options IV surface.
- Deribit will be treated as public crypto options data only, using public market-data calls and never private/account/order methods.
- Automated tests will use local fixtures and mocked public responses only.
- The free derivatives run lifecycle will mirror 009 public bootstrap: request, plan, per-source collection, raw write, processed write, run summary, readiness/dashboard integration.

## Phase 1 Design

Design artifacts are generated with this plan:

- [data-model.md](./data-model.md): Source enums, request/result schemas, raw and processed row models, run state, artifact contracts, validation rules.
- [contracts/api.md](./contracts/api.md): API request/response contracts for create/list/detail free derivatives bootstrap runs and readiness/capability integration.
- [quickstart.md](./quickstart.md): Local validation path, fixture smoke flow, optional real public smoke, dashboard checks, artifact guard, and forbidden-scope review.

## Raw And Processed Storage Contracts

```text
data/raw/cftc/
|-- cot_{category}_{year}.zip or .csv
|-- cot_{category}_{year}_metadata.json

data/processed/cftc/
|-- gold_positioning_{category}.parquet
|-- gold_positioning_summary.parquet

data/raw/gvz/
|-- gvzcls_{start}_{end}.csv
|-- gvzcls_{start}_{end}_metadata.json

data/processed/gvz/
|-- gvz_daily_close.parquet
|-- gvz_gap_summary.parquet

data/raw/deribit/
|-- {snapshot_id}_{underlying}_instruments.json
|-- {snapshot_id}_{underlying}_book_summary.json

data/processed/deribit/
|-- {snapshot_id}_{underlying}_options.parquet
|-- {snapshot_id}_{underlying}_option_walls.parquet

data/reports/free_derivatives/
`-- {run_id}/
    |-- metadata.json
    |-- report.json
    `-- report.md
```

All generated paths must remain ignored and untracked. Report artifacts should store project-relative paths where possible and validate that paths remain under the configured raw, processed, and reports roots.

## Source Limitation Labels

Required limitation labels:

- CFTC COT: "Weekly broad positioning context only; not strike-level options open interest and not intraday wall data."
- CFTC category: "Futures-only and futures-and-options combined reports must remain separately labeled."
- GVZ: "GVZ is a GLD-options-derived volatility proxy, not a CME gold options implied-volatility surface."
- Deribit: "Deribit public options data is crypto options data only, not gold or XAU data."
- Public-only: "This run uses public/no-key market-data access only and does not use private account, broker, wallet, order, or paid vendor credentials."
- Artifact scope: "Generated raw, processed, and report outputs are local research artifacts and must remain untracked."

## Bootstrap Run Lifecycle

1. Validate `FreeDerivativesBootstrapRequest` and require `research_only_acknowledged=true`.
2. Build a per-source plan for enabled CFTC, GVZ, and Deribit sections.
3. For CFTC, use public historical compressed files when requested or fixture/local import when supplied; write raw files and filter processed gold/COMEX rows.
4. For GVZ, use public daily close download path or fixture/local import; write raw rows, processed daily close rows, and gap summary.
5. For Deribit, use public instruments and book-summary/ticker snapshots or mocked fixtures; write raw JSON and processed normalized options/wall snapshots.
6. Produce one `FreeDerivativesSourceResult` per requested source with completed, partial, skipped, or failed status.
7. Preserve partial results and source-specific errors without failing the whole run when another source succeeds.
8. Persist run metadata and report artifacts under `data/reports/free_derivatives/{run_id}/`.
9. Expose run list/detail through API and dashboard.
10. Update readiness/capability/missing-data surfaces so researchers can see source availability and limitations without starting a run.

## API Design

Add routes under the existing v0 API prefix:

- `POST /api/v1/data-sources/bootstrap/free-derivatives`
- `GET /api/v1/data-sources/bootstrap/free-derivatives/runs`
- `GET /api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}`

Extend existing surfaces:

- `GET /api/v1/data-sources/readiness`
- `GET /api/v1/data-sources/capabilities`
- `GET /api/v1/data-sources/missing-data`

Route responses must include research-only warnings, per-source limitations, generated output paths, and no secret values. Missing run ids return structured `NOT_FOUND`. Invalid source/date/underlying requests return structured validation errors. External public-source failures return completed/partial/failed source statuses rather than raw exception dumps.

## Dashboard Design

Extend `/data-sources` with a compact free-derivatives section:

- Readiness cards or rows for CFTC COT, GVZ, and Deribit public options.
- Capability matrix entries with supported and unsupported data categories.
- Missing-data actions for local fixture/import fallback and XAU local options OI reminder.
- Latest free-derivatives run selector and summary.
- Per-source status table with row/instrument counts, coverage, output paths, and limitations.
- Source limitation panel that explicitly says CFTC is weekly broad positioning, GVZ is proxy volatility, and Deribit is crypto options only.
- Research-only disclaimer and no secret-value display.

Do not add chart-heavy analysis or new strategy interpretation in this feature. The dashboard goal is readiness and artifact inspection only.

## Test Strategy

- Unit tests for CFTC request planning, compressed-file/fixture parsing, gold/COMEX row filtering, category separation, and positioning summary creation.
- Unit tests for GVZ request planning, CSV/fixture parsing, daily close normalization, gap detection, and proxy limitation labels.
- Unit tests for Deribit instrument parsing, expiry/strike/option-type extraction, public snapshot normalization, IV/OI fields, and option wall aggregation.
- Unit tests for schema validation, safe ids, safe output paths, source status aggregation, and forbidden wording.
- Unit tests proving limitation labels exist for CFTC, GVZ, Deribit, public-only, and artifact scope.
- Integration tests with mocked responses/local fixtures only; no live external downloads in CI.
- API contract tests for create/list/detail endpoints, validation errors, missing run ids, partial runs, and response shape.
- Existing backend suite, frontend production build, and generated artifact guard.
- Dashboard smoke for `/data-sources` after implementation where browser tooling is available.
- Forbidden-scope scan covering live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet/private-key handling, paid vendor credentials, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, and prohibited strategy claims.

## Implementation Phases

1. **Setup and schemas**: Add `free_derivatives` package, Pydantic schemas, route skeleton, report-store skeleton, readiness/capability enum entries, frontend type/API placeholders, and ignored path guard tests.
2. **CFTC COT slice**: Add CFTC parser/request planner, fixture importer, gold/COMEX filter, futures-only vs combined category labels, processed summary writer, limitations, and tests.
3. **GVZ slice**: Add GVZ parser/request planner, daily close normalization, gap summary, proxy labels, processed writer, and tests.
4. **Deribit public options slice**: Add public request planner, instrument parser, option summary normalizer, wall snapshot processor, public-only guardrails, and tests.
5. **Orchestration and report persistence**: Implement run lifecycle, partial result handling, raw/processed/report artifact persistence, list/detail reads, and integration tests.
6. **API and readiness integration**: Implement free-derivatives endpoints, structured errors, readiness/capability/missing-data entries, and API contract tests.
7. **Dashboard inspection**: Extend `/data-sources` with free-derivatives readiness, run selector, output paths, limitations, and missing actions; run frontend build.
8. **Final validation**: Run backend import, focused tests, full backend suite, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope review.

## Complexity Tracking

No constitution violations or extra architectural complexity are required. The feature is additive, file-backed, and stays within existing public/local data-source patterns.

## Post-Design Constitution Check

- **Research-only scope**: PASS. Outputs are source readiness, raw/processed research artifacts, and limitation-labeled summaries only.
- **No execution behavior**: PASS. Design excludes account, order, broker, wallet, private-key, live, paper, and shadow workflows.
- **Allowed v0 stack**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/Parquet and Next.js/TypeScript/Tailwind surfaces.
- **Reproducible local storage**: PASS. Generated artifacts stay under ignored `data/raw`, `data/processed`, and `data/reports` paths.
- **Timestamp/data safety**: PASS. CFTC weekly dates, GVZ daily dates, and Deribit snapshot timestamps are explicit fields and validation targets.
- **No hidden assumptions**: PASS. CFTC, GVZ, and Deribit source limitations are required labels and missing-data actions.
- **No strategy claims**: PASS. Contracts and dashboard copy prohibit profitability, predictive, safety, and live-readiness claims.
- **No architecture redesign**: PASS. Feature 008/009 data-source surfaces and feature 010 XAU research outputs are dependencies, not replaced.
