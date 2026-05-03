# Implementation Plan: Real Data-Source Onboarding And First Evidence Run

**Branch**: `008-real-data-source-onboarding-and-first-evidence-run` | **Date**: 2026-05-02 | **Spec**: `specs/008-real-data-source-onboarding-and-first-evidence-run/spec.md`
**Input**: Feature specification from `/specs/008-real-data-source-onboarding-and-first-evidence-run/spec.md`

## Summary

Add a research-only data-source onboarding layer that makes real data readiness explicit before the first evidence run. The feature introduces `backend/src/data_sources/` services, `backend/src/models/data_sources.py` schemas, provider readiness/capability endpoints, missing-data preflight, and a first evidence run wrapper that delegates to the completed research execution workflow from feature 007. The dashboard adds a `/data-sources` operating checklist for provider readiness, capability limitations, optional key presence, missing-data actions, and links to generated evidence artifacts.

This feature does not add strategy logic, live execution, paper trading, private trading credentials, or new infrastructure storage.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript, Node.js/Next.js  
**Primary Dependencies**: FastAPI, Pydantic, Pydantic Settings, Polars, DuckDB, Parquet/PyArrow, httpx, Next.js, Tailwind CSS  
**Storage**: Local filesystem under existing ignored `data/raw`, `data/processed`, and `data/reports` paths; reuse `data/reports/research_execution` for first-run evidence artifacts  
**Testing**: pytest, FastAPI TestClient, frontend `npm run build`, generated artifact guard PowerShell script  
**Target Platform**: Local research workstation and GitHub Actions compatible with Windows and Ubuntu  
**Project Type**: Existing backend API plus Next.js dashboard  
**Performance Goals**: Onboarding readiness and preflight should complete using local metadata and filesystem checks without external downloads; first evidence run delegates to existing execution workflow  
**Constraints**: No generated data or reports tracked in git; no secret values returned; no paid keys required for MVP; no live/paper/shadow trading or execution claims  
**Scale/Scope**: Default crypto assets BTCUSDT, ETHUSDT, SOLUSDT; optional crypto assets BNBUSDT, XRPUSDT, DOGEUSDT; proxy assets SPY, QQQ, GLD, GC=F, BTC-USD; one local XAU options OI import path per first-run request

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| Research-first, no premature trading | PASS | Feature is onboarding and evidence orchestration only. It explicitly excludes live, paper, shadow, broker, wallet, and order execution behavior. |
| Reproducible local data and calculations | PASS | Uses existing local data roots and report stores; no generated artifacts are committed. |
| Timestamp-safe feature engineering | PASS | The feature only checks existing processed features and local XAU files; it does not create new feature engineering logic. |
| Small vertical slices | PASS | Work is split into foundation, preflight MVP, first-run orchestration, dashboard, and final validation. |
| Test before commit | PASS | Plan includes unit, integration, API contract, backend suite, frontend build, and artifact guard checks. |
| No hidden assumptions | PASS | Capability matrix, optional provider availability, missing-data instructions, and unsupported capability labels are surfaced in API and dashboard responses. |
| No strategy claims without evidence | PASS | Output is constrained to readiness, limitations, and research-only evidence labels. |
| Allowed v0 stack only | PASS | Uses existing Python/FastAPI/Pydantic/Polars/Parquet and Next.js/TypeScript stack. |
| Forbidden v0 technologies absent | PASS | No Rust, ClickHouse, PostgreSQL, Kafka/Redpanda/NATS, Kubernetes, or ML training are introduced. |

## Project Structure

### Documentation (this feature)

```text
specs/008-real-data-source-onboarding-and-first-evidence-run/
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
|   |-- models/
|   |   `-- data_sources.py
|   |-- data_sources/
|   |   |-- __init__.py
|   |   |-- capabilities.py
|   |   |-- readiness.py
|   |   |-- missing_data.py
|   |   |-- preflight.py
|   |   `-- first_run.py
|   |-- api/
|   |   `-- routes/
|   |       `-- data_sources.py
|   |-- research_execution/
|   |   |-- orchestration.py
|   |   `-- report_store.py
|   |-- research/
|   |   `-- report_store.py
|   `-- xau/
|       |-- imports.py
|       `-- report_store.py
`-- tests/
    |-- unit/
    |   |-- test_data_source_readiness.py
    |   |-- test_data_source_capabilities.py
    |   |-- test_data_source_missing_data.py
    |   `-- test_data_source_preflight.py
    |-- integration/
    |   |-- test_data_source_public_mvp_flow.py
    |   |-- test_data_source_optional_keys.py
    |   |-- test_data_source_xau_local_file.py
    |   `-- test_first_evidence_run_flow.py
    `-- contract/
        `-- test_data_sources_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- data-sources/
    |       `-- page.tsx
    |-- components/
    |   `-- ui/
    |       `-- Header.tsx
    |-- services/
    |   `-- api.ts
    `-- types/
        `-- index.ts
```

**Structure Decision**: Use `backend/src/data_sources/` because the public API and user language are data-source onboarding. Keep first-run orchestration as a thin adapter to `backend/src/research_execution/` instead of duplicating feature 007. Add one dashboard page at `/data-sources` to keep onboarding distinct from the existing `/evidence` inspection page.

## Design Phases

### Phase 0 - Research Decisions

- Confirm the provider readiness design, optional key policy, and source limitation language.
- Decide how local processed feature paths and XAU local file paths are resolved safely.
- Decide the first evidence run delegation boundary to feature 007.
- Document why optional paid provider absence is non-blocking for the MVP.

### Phase 1 - Data Model And Contracts

- Define `DataSourceReadiness`, `DataSourceCapability`, `DataSourceProviderStatus`, `DataSourceMissingDataAction`, `DataSourcePreflightRequest`, `DataSourcePreflightResult`, `FirstEvidenceRunRequest`, and `FirstEvidenceRunResult`.
- Define API contracts for readiness, capabilities, missing-data instructions, preflight, first evidence run creation, and first-run detail.
- Define dashboard data shapes for readiness cards, capability matrix rows, missing-data checklist, first-run links, and warnings.

### Phase 2 - Tasks

- Generate dependency-ordered implementation tasks grouped by user story.
- Keep tests before implementation for each story.
- Keep dashboard work separate from backend preflight and first-run behavior.

## Data-Source Readiness Flow

1. Load static capability matrix from `backend/src/data_sources/capabilities.py`.
2. Inspect provider metadata from the existing provider registry when available.
3. Inspect optional paid provider environment variable presence through a fixed allowlist only.
4. Return configured/missing/unavailable/unsupported statuses without returning values, prefixes, hashes, or exception strings containing secrets.
5. Include research-only limitations for Binance public history depth, Yahoo OHLCV-only data, local schema-dependent imports, and optional vendor access.

## Data Preflight Flow

1. Validate request shape and reject forbidden credential categories.
2. Check crypto processed feature readiness for requested symbols/timeframe using existing processed feature path conventions.
3. Check proxy OHLCV processed feature readiness and label unsupported OI, funding, IV, gold options OI, futures OI, and XAUUSD execution capabilities.
4. Check XAU local options OI file readiness by reusing feature 006 local import validation rules.
5. Mark optional paid provider keys as missing/unavailable without blocking public/local MVP workflows.
6. Return grouped missing-data actions for Binance processing, Yahoo OHLCV processing, XAU local import schema, and optional paid provider configuration.

## First Evidence Run Flow

1. Accept `FirstEvidenceRunRequest` with public/local workflow configuration and `research_only_acknowledged=true`.
2. Run data-source preflight and preserve blocked workflows.
3. Translate ready crypto/proxy/XAU onboarding config into a `ResearchExecutionRunRequest`.
4. Delegate execution to `ResearchExecutionOrchestrator` from feature 007.
5. Persist or reference generated evidence under existing `data/reports/research_execution` paths.
6. Return first-run status with execution run id, workflow statuses, report links, missing-data checklist, capability snapshot, and research-only warnings.

## Provider Capability Matrix

| Provider Type | Tier | Supported | Unsupported / Limits | Blocking For MVP |
|---------------|------|-----------|----------------------|------------------|
| `binance_public` | 0 | Crypto OHLCV, limited public OI/funding where endpoint/history exists | No account data, no execution, deeper OI history may need vendor data | No |
| `yahoo_finance` | 0 | OHLCV/proxy assets | No crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD execution data | No |
| `local_file` | 0 | Schema-dependent CSV/Parquet imports | Missing or invalid schema blocks the specific workflow | Only if required local file is missing |
| `kaiko_optional` | 1 | Optional normalized crypto derivatives/OI research data | Requires configured research key; no execution | No |
| `tardis_optional` | 1 | Optional native replay/archive research data | Requires configured research key; no execution | No |
| `coinglass_optional` | 1 | Optional aggregate/dashboard overlay data | Requires configured research key; no execution | No |
| `cryptoquant_optional` | 1 | Optional aggregate/on-chain/dashboard overlay data | Requires configured research key; no execution | No |
| `cme_quikstrike_local_or_optional` | 0/1 | Local CSV/Parquet gold options OI first; optional configured provider later | Not Yahoo GC=F/GLD; no XAUUSD execution data | Only if XAU workflow requires it and no local file/report exists |

## Secret Handling Policy

- Only a fixed allowlist of optional public-data research env vars is inspected.
- Responses return `configured: true` or `configured: false` and a variable name such as `KAIKO_API_KEY`, never values.
- `.env`, `.env.*`, generated data, and local import files remain ignored.
- Private trading, broker, wallet, or execution credential names are classified as forbidden and not onboarded.
- Error messages and logs must avoid echoing request-provided secret values.

## Dashboard Design

Add `/data-sources` with a compact operational layout:

- Source readiness cards for public/no-key, local file, optional paid vendors, and forbidden credentials.
- Capability matrix table with provider type, tier, supported categories, unsupported categories, key requirement, and limitations.
- Optional provider key status shown only as configured or missing.
- Missing-data checklist grouped by crypto, proxy, XAU, and optional vendors.
- First evidence run panel with status, linked research execution run id, linked research/XAU/evidence report ids, and blocked workflow list.
- Research-only disclaimer stating the page is not a live, paper, shadow, broker, or execution workflow.

## Test Strategy

- Unit tests for provider readiness detection, including configured/missing optional key presence.
- Unit tests that API/model outputs never contain secret values.
- Unit tests for provider capability matrix and unsupported capability labels.
- Unit tests for missing-data instruction generation.
- Unit tests for local-file schema capability detection.
- Integration test for the public/no-key MVP preflight using synthetic processed data fixtures.
- Integration test proving missing optional paid provider keys are non-blocking.
- Integration test for XAU local file readiness with synthetic CSV/Parquet fixtures.
- Integration test for first evidence run delegation to feature 007 using ignored synthetic smoke fixtures.
- API contract tests for all data-source and first-run endpoints.
- Existing backend suite, frontend production build, and artifact guard must pass.

## Implementation Phases

1. **Setup And Foundation**: Add schemas, capability matrix, readiness service, missing-data service, route skeleton, frontend placeholder, and generated artifact checks.
2. **Data-Source Preflight MVP**: Implement Binance/Yahoo/local-file readiness, XAU local schema checks, optional key presence checks, and missing-data instructions.
3. **First Evidence Run**: Delegate to research execution workflow, persist/reference first-run status, and expose first-run endpoints.
4. **Dashboard**: Render readiness cards, capability matrix, optional key status, missing-data checklist, first-run status, and report links.
5. **Final Validation**: Run backend tests, frontend build/install, artifact guard, API smoke, dashboard smoke, and forbidden-scope review.

## Complexity Tracking

No constitution violations or extra architectural complexity are required. The feature adds a thin onboarding/orchestration layer and reuses completed systems.

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Research-only scope | PASS | Contracts and models explicitly exclude execution credentials and trading behavior. |
| Existing architecture reuse | PASS | First evidence run delegates to feature 007; source capability checks reuse feature 002 and feature 006 logic where possible. |
| Generated artifacts ignored | PASS | Reports/data stay under existing ignored `data/` paths and artifact guard remains required. |
| No secret leakage | PASS | Env checks are presence-only and responses never expose secret values. |
| Testable vertical slices | PASS | Phases separate foundation, preflight, first-run orchestration, dashboard, and final validation. |
