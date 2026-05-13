# Implementation Plan: XAU QuikStrike Context Fusion

**Branch**: `014-xau-quikstrike-context-fusion` | **Date**: 2026-05-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/014-xau-quikstrike-context-fusion/spec.md`

## Summary

Add a local-only, research-only fusion layer that combines completed QuikStrike Vol2Vol extraction reports from feature 012 and completed QuikStrike Matrix extraction reports from feature 013 before handing enriched local context to the existing XAU Vol-OI wall engine and XAU reaction/risk planner. The feature creates a focused `backend/src/xau_quikstrike_fusion/` package, schemas in `backend/src/models/xau_quikstrike_fusion.py`, optional local API routes under `backend/src/api/routes/xau_quikstrike_fusion.py`, ignored report persistence under `data/reports/xau_quikstrike_fusion/`, and a compact `/xau-vol-oi` inspection panel.

The implementation reuses existing QuikStrike report stores, feature 006 XAU Vol-OI report creation, and feature 010 XAU reaction/risk planner orchestration. It does not add extraction menus, browser automation, endpoint replay, credential/session storage, execution behavior, or a parallel wall-scoring engine.

## Technical Context

**Language/Version**: Python 3.11+ for backend fusion, matching, validation, optional orchestration, and report persistence; TypeScript with Next.js for dashboard inspection  
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars/PyArrow local data conventions, JSON/Markdown report patterns, QuikStrike Vol2Vol report store, QuikStrike Matrix report store, XAU Vol-OI orchestration/report store, XAU reaction orchestration/report store, Next.js, TypeScript, Tailwind CSS  
**Storage**: Local ignored filesystem artifacts under `data/reports/xau_quikstrike_fusion/`; optional derived XAU input artifacts stay under existing ignored local data/report roots; no database server  
**Testing**: pytest unit/integration/contract tests with synthetic Vol2Vol and Matrix reports; backend import check; full backend pytest suite; frontend production build when UI changes; generated artifact guard  
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow  
**Project Type**: Existing FastAPI backend plus Next.js dashboard inspection with local research files  
**Performance Goals**: Synthetic fusion of hundreds to low-thousands of rows completes inside normal backend test time; operational local fusion should process one Vol2Vol report plus one Matrix report without long-running services  
**Constraints**: Local-only, research-only, no generated artifact commits, no secret/session persistence, no browser RPA, no endpoint replay, no paid vendors, no live/paper/shadow trading, no forbidden v0 technologies  
**Scale/Scope**: One fusion report references one Vol2Vol extraction report and one Matrix extraction report; optional source context includes spot/futures basis references, session open, OHLC/candle reaction context, and realized-volatility estimate

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature adds context fusion, validation, and explanatory reports only.
- **Language Split**: PASS. Python remains the research/orchestration language and TypeScript remains dashboard-only. No Rust execution component is introduced.
- **Frontend Stack**: PASS. Dashboard work stays inside the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. API and request/response schemas stay in FastAPI and Pydantic.
- **Data Processing**: PASS. Fusion is deterministic, timestamp-aware, and based on existing local extraction reports.
- **Storage v0**: PASS. Generated reports stay under ignored local `data/` report paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service fan-out is introduced.
- **Data-Source Principle**: PASS. Vol2Vol and Matrix are explicit local research sources with limitations and provenance.
- **Reliability Principle**: PASS. Join-key confidence, source agreement, missing context, and downstream no-trade states are surfaced before interpretation.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/014-xau-quikstrike-context-fusion/
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
|   |       `-- xau_quikstrike_fusion.py
|   |-- models/
|   |   `-- xau_quikstrike_fusion.py
|   `-- xau_quikstrike_fusion/
|       |-- __init__.py
|       |-- loaders.py          # load and validate 012/013 report-store outputs
|       |-- matching.py         # join keys, coverage, mismatch/agreement states
|       |-- fusion.py           # fused rows, provenance, missing context checklist
|       |-- basis.py            # optional basis and spot-equivalent calculations
|       |-- orchestration.py    # fusion run plus optional XAU Vol-OI/reaction runs
|       `-- report_store.py     # metadata, rows, JSON/Markdown report persistence
|-- tests/
|   |-- unit/
|   |   |-- test_xau_quikstrike_fusion_models.py
|   |   |-- test_xau_quikstrike_fusion_loaders.py
|   |   |-- test_xau_quikstrike_fusion_matching.py
|   |   |-- test_xau_quikstrike_fusion_basis.py
|   |   |-- test_xau_quikstrike_fusion_fusion.py
|   |   `-- test_xau_quikstrike_fusion_report_store.py
|   |-- integration/
|   |   `-- test_xau_quikstrike_fusion_flow.py
|   `-- contract/
|       `-- test_xau_quikstrike_fusion_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx        # QuikStrike Fusion inspection panel
    |-- services/
    |   `-- api.ts             # fusion report clients
    `-- types/
        `-- index.ts           # fusion request/report/row types
```

**Structure Decision**: Use a new additive `backend/src/xau_quikstrike_fusion/` package because the feature composes source reports and downstream XAU workflows rather than extending either extractor. Keep feature 012 and 013 extraction packages unchanged, and keep feature 006 wall scoring plus feature 010 reaction logic as downstream dependencies.

## Source Report Loading Strategy

- Load Vol2Vol reports through the existing QuikStrike report store and read normalized rows plus conversion rows where available.
- Load Matrix reports through the existing QuikStrike Matrix report store and read normalized rows plus conversion rows where available.
- Validate that both source reports identify Gold/OG/GC research data.
- Accept completed source reports by default; partial reports may be loaded only when usable rows and mapping metadata are present and blocked reasons are preserved in the fusion report.
- Never reload browser sessions, reparse private pages, replay QuikStrike endpoints, or inspect generated private files outside allowed report/data roots.
- Treat source report warnings and limitations as inherited limitations in the fusion report.

## Match Key Design

Primary match key:

```text
(normalized_strike, normalized_expiration_key, normalized_option_type, normalized_value_type)
```

Rules:

- `normalized_strike` is a decimal-compatible futures strike level.
- `normalized_expiration_key` prefers explicit calendar expiration when available, otherwise uses expiration code.
- `normalized_option_type` is `call`, `put`, or `combined`; `combined` does not match call/put unless a later implementation explicitly expands it with safe evidence.
- `normalized_value_type` keeps source semantics: open interest, OI change, volume, intraday volume, EOD volume, churn, range, or volatility-style context.
- Matrix volume and Vol2Vol volume-like fields are comparable only through explicit value-type mapping, not silent overwrite.
- Match status is deterministic: `matched`, `vol2vol_only`, `matrix_only`, `conflict`, or `blocked`.
- Coverage summaries count matched keys, source-only keys, conflicting keys, strike coverage, expiry coverage, and option-side coverage.

## Fusion Row Schema

Each fused row preserves:

- fusion row id
- source report ids
- match key fields
- source provenance (`vol2vol`, `matrix`, or `fused`)
- Vol2Vol source value and metadata when present
- Matrix source value and metadata when present
- agreement/disagreement status
- basis-adjusted spot-equivalent level when available
- source warnings and limitations
- missing context notes

No source value is overwritten. When both sources provide overlapping evidence, both values remain visible and the agreement state explains whether they match, disagree, or cannot be compared.

## Missing Context Logic

The fusion report must produce a structured checklist covering:

- basis status: available, partial, unavailable, conflict, or blocked
- IV/range status: available, partial, unavailable, conflict, or blocked
- open-regime status: available, partial, unavailable, conflict, or blocked
- candle-acceptance status: available, partial, unavailable, conflict, or blocked
- realized-volatility status: available, partial, unavailable, conflict, or blocked
- source report quality status
- source agreement/disagreement status

Missing optional context should reduce downstream confidence or preserve NO_TRADE behavior. It must not trigger fabricated basis, spot, IV, range, open, candle, or volatility values.

## Optional Basis Logic

- Basis can be computed only when both XAUUSD spot reference and GC futures reference are provided and positive.
- Basis definition: `basis_points = gc_futures_reference - xauusd_spot_reference`.
- Spot-equivalent strike level: `spot_equivalent_level = futures_strike - basis_points`.
- If either reference is absent, invalid, stale, or conflicting, basis status is unavailable or blocked and the report keeps futures-strike levels only.
- Basis notes must be carried into the fused XAU Vol-OI input and downstream reaction context.

## API Design

Add local research endpoints under `/api/v1/xau/quikstrike-fusion`:

- `POST /api/v1/xau/quikstrike-fusion/reports`
- `GET /api/v1/xau/quikstrike-fusion/reports`
- `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}`
- `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}/rows`
- `GET /api/v1/xau/quikstrike-fusion/reports/{report_id}/missing-context`

Structured errors should cover missing source reports, incompatible source reports, blocked join-key mapping, invalid optional context, missing fusion report ids, and research-only acknowledgement failures. Responses must include research-only limitations and must not contain credentials, cookies, headers, viewstate values, HAR data, screenshots, private full URLs, endpoint replay material, or execution wording.

## Dashboard Design

Extend `/xau-vol-oi` with a compact QuikStrike Fusion panel:

- selected Vol2Vol report id
- selected Matrix report id
- fused row count
- strike coverage and expiry coverage
- source agreement/disagreement summary
- basis status
- IV/range status
- open-regime status
- candle-acceptance status
- missing context checklist
- generated fused artifact paths
- linked XAU Vol-OI report id when created
- linked XAU reaction report id when created
- whether downstream reaction rows are all `NO_TRADE`
- research-only and local-only disclaimer

The panel is an inspection surface only. It must not drive browser extraction, credential handling, order placement, alerts, broker connectivity, or live readiness.

## Test Strategy

- Unit tests for schema validation, safe ids, forbidden secret/session field rejection, and research-only acknowledgement.
- Unit tests for loading source reports from synthetic 012 and 013 report artifacts.
- Unit tests for product compatibility and source status validation.
- Unit tests for strike, expiration, option type, and value type normalization.
- Unit tests for match key generation, matched/source-only/conflict states, and coverage counts.
- Unit tests for source agreement/disagreement with exact count fields and tolerance-bound price/context fields.
- Unit tests for missing context checklist generation.
- Unit tests for optional basis computation, invalid basis blocking, and spot-equivalent levels.
- Unit tests for fused XAU Vol-OI compatible rows and blocked/partial conversion.
- Unit tests for report-store path safety, artifact metadata, JSON report, and Markdown report.
- Integration test fusing synthetic Vol2Vol plus Matrix reports and optionally running existing XAU Vol-OI and XAU reaction orchestration.
- API contract tests for create/list/detail/rows/missing-context endpoints and structured errors.
- Frontend build and dashboard smoke if `/xau-vol-oi` changes.
- Existing backend suite and generated artifact guard.
- Forbidden-scope scan for live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet/private-key handling, endpoint replay, credential/session storage, browser RPA, OCR, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, and ML training.

## Implementation Phases

1. **Setup and schemas**: Add `xau_quikstrike_fusion` package, models, route skeleton, report-store skeleton, route registration, frontend type/API placeholders, dashboard placeholder, and artifact guard coverage.
2. **Source loading and compatibility**: Load existing Vol2Vol and Matrix reports, read rows/conversion outputs, validate Gold product compatibility, status, warnings, and limitations.
3. **Matching and coverage**: Implement join-key normalization, match status, coverage counts, and conflict detection.
4. **Fusion and missing context**: Build fused rows, source agreement/disagreement, missing-context checklist, IV/range status, open/candle status, and source warnings.
5. **Basis and XAU input conversion**: Compute optional basis and spot-equivalent levels, produce fused XAU Vol-OI compatible rows, and block unsafe mapping.
6. **Optional downstream orchestration**: Reuse existing XAU Vol-OI report creation and XAU reaction/risk planner when requested and when inputs are eligible.
7. **API/report persistence**: Persist metadata, fused rows, conversion outputs, JSON/Markdown reports, artifact references, and API endpoints.
8. **Dashboard inspection**: Extend `/xau-vol-oi` with fusion report selector/status, coverage, missing context, source agreement, linked report ids, and disclaimers.
9. **Final validation and forbidden-scope review**: Run backend import, focused fusion tests, full backend tests, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope scan.

## Complexity Tracking

No constitution violations or extra architectural complexity are required. The feature is additive, local-only, file-backed, and composes existing research modules.

## Post-Design Constitution Check

- **Research-only scope**: PASS. Outputs are fused research rows, context checks, conversion artifacts, and linked research report ids only.
- **No execution behavior**: PASS. Design excludes live, paper, shadow, broker, wallet, private-key, account, order, and position workflows.
- **Allowed v0 stack**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/Parquet and Next.js/TypeScript/Tailwind surfaces.
- **Reproducible local storage**: PASS. Generated artifacts stay under ignored `data/reports/xau_quikstrike_fusion/` and existing ignored data/report roots.
- **Timestamp/data safety**: PASS. Source report ids, capture timestamps, expiration keys, optional basis references, and missing-context states are explicit.
- **No hidden assumptions**: PASS. Missing basis, IV/range, open, candle, and RV context are represented as checklist items and downstream no-trade reasons.
- **No strategy claims**: PASS. No profitability, predictive, safety, or live-readiness claims are included.
- **No architecture redesign**: PASS. Features 006, 010, 012, and 013 remain dependencies, not replaced.
