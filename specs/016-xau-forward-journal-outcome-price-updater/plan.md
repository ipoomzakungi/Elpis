# Implementation Plan: XAU Forward Journal Outcome Price Updater

**Branch**: `016-xau-forward-journal-outcome-price-updater` | **Date**: 2026-05-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/016-xau-forward-journal-outcome-price-updater/spec.md`

## Summary

Add a research-only outcome price updater for existing XAU Forward Journal entries. The updater loads approved local CSV/Parquet OHLC candles or existing public OHLC outputs, calculates the required post-snapshot windows, validates per-window candle coverage, computes observed high/low/close/range/direction only when data is present, and updates only the journal outcome section. Missing windows remain `pending`; partial windows become `inconclusive`; original snapshot/source/wall/reaction evidence remains immutable.

The implementation will extend the existing `backend/src/xau_forward_journal/` package with price-data loading, source labeling, window coverage, update-report persistence, and orchestration. It will add two local research endpoints, frontend service/type additions, and a compact `/xau-vol-oi` Forward Journal panel extension for price source, coverage, missing windows, proxy limitations, and pending/inconclusive status. It does not add live/paper/shadow trading, private credentials, paid vendors, endpoint replay, new infrastructure, or strategy claims.

## Technical Context

**Language/Version**: Python 3.11+ for backend validation, OHLC loading, deterministic outcome calculation, and local report persistence; TypeScript with Next.js for dashboard display
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, PyArrow/Parquet support, existing XAU Forward Journal package, existing local report-store conventions, existing frontend API client/types, Next.js, TypeScript, Tailwind CSS
**Storage**: Ignored local filesystem artifacts under `data/reports/xau_forward_journal/` and `backend/data/reports/xau_forward_journal/`; no database server
**Testing**: pytest unit/integration/contract tests with synthetic journal entries and synthetic candles; backend import check; full backend pytest suite; frontend production build; generated artifact guard
**Target Platform**: Local research workstation and CI-compatible Windows/Linux validation flow
**Project Type**: Existing FastAPI backend plus Next.js dashboard
**Performance Goals**: Local update/coverage checks for one journal entry and one candle file should complete within normal local API interaction time; tests should use small synthetic fixtures and stay within the existing backend test envelope
**Constraints**: Research-only, local-only, no fabricated candles, timestamp-safe window calculation, immutable snapshot fields, explicit proxy labeling, generated artifacts ignored, no secret/session/replay material, no live/paper/shadow trading, no forbidden v0 technologies, no profitability/prediction/safety/live-readiness claims
**Scale/Scope**: One request updates or checks one saved journal entry; supported windows are `30m`, `1h`, `4h`, `session_close`, and `next_day`; supported source labels are `true_xauusd_spot`, `gc_futures`, `yahoo_gc_f_proxy`, `gld_etf_proxy`, `local_csv`, `local_parquet`, and `unknown_proxy`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature attaches observed price outcomes to saved research snapshots and explicitly avoids execution or strategy claims.
- **Language Split**: PASS. Python remains the research/orchestration language and TypeScript remains dashboard-only. No Rust execution component is introduced.
- **Frontend Stack**: PASS. Dashboard work stays inside the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. Local research routes and schemas use the existing FastAPI/Pydantic pattern.
- **Data Processing**: PASS. Polars is the planned OHLC file engine, and all window calculations are timestamp-safe and conservative.
- **Storage v0**: PASS. Generated outcome update reports stay under ignored local `data/` report paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service is introduced.
- **Data-Source Principle**: PASS. The feature accepts modular local/public OHLC outputs and labels proxy source limitations instead of hardcoding strategy logic.
- **TradingView Principle**: PASS. No TradingView dependency or source-of-truth behavior is added.
- **Reliability Principle**: PASS. Missing or partial candles remain pending/inconclusive and source coverage is visible before interpretation.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/016-xau-forward-journal-outcome-price-updater/
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
|   |       `-- xau_forward_journal.py        # add price update and coverage routes
|   |-- models/
|   |   `-- xau_forward_journal.py            # add price-source, coverage, and update models
|   `-- xau_forward_journal/
|       |-- outcome.py                        # reuse conservative outcome update helpers
|       |-- orchestration.py                  # add price-data update and coverage workflows
|       |-- price_data.py                     # load/validate OHLC CSV/Parquet and source labels
|       |-- price_outcome.py                  # window calculation, coverage, metrics, direction
|       `-- report_store.py                   # persist/read price update artifacts
|-- tests/
|   |-- unit/
|   |   |-- test_xau_forward_journal_price_data.py
|   |   |-- test_xau_forward_journal_price_outcome.py
|   |   |-- test_xau_forward_journal_models.py
|   |   `-- test_xau_forward_journal_report_store.py
|   |-- integration/
|   |   `-- test_xau_forward_journal_price_update_flow.py
|   `-- contract/
|       `-- test_xau_forward_journal_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx                      # show source coverage and updated outcomes
    |-- services/
    |   `-- api.ts                            # add price update and coverage clients
    `-- types/
        `-- index.ts                          # add coverage/update response types

scripts/
`-- check_generated_artifacts.ps1             # verify outcome artifacts remain ignored
```

**Structure Decision**: Use additive modules inside the existing XAU Forward Journal package because the feature updates outcomes for saved journal entries and should reuse existing journal models, conservative outcome rules, API route grouping, and report-store safety. Keep QuikStrike extraction, fusion, XAU Vol-OI, and reaction packages unchanged.

## Price Data And Source Labeling Strategy

- Load OHLC candles from local CSV, local Parquet, or existing public research output paths only.
- Normalize timestamp, open, high, low, close, and optional volume into a single internal candle shape.
- Validate sorted, unique, timezone-safe timestamps and internally consistent OHLC values.
- Reject or block ambiguous source inputs instead of guessing.
- Apply one required source label to every coverage/update result:
  - `true_xauusd_spot`
  - `gc_futures`
  - `yahoo_gc_f_proxy`
  - `gld_etf_proxy`
  - `local_csv`
  - `local_parquet`
  - `unknown_proxy`
- Attach proxy limitation notes for every non-spot source. GC futures, Yahoo GC=F, GLD, local files, and unknown proxy sources must not be represented as true XAUUSD spot.

## Window And Coverage Strategy

- Derive fixed windows from `snapshot_time`:
  - `30m`: snapshot time through snapshot time plus 30 minutes
  - `1h`: snapshot time through snapshot time plus 1 hour
  - `4h`: snapshot time through snapshot time plus 4 hours
- Derive `session_close` from existing XAU session conventions when available; otherwise mark the window inconclusive or pending with a boundary limitation.
- Derive `next_day` from the next research-session boundary when available; otherwise mark the window inconclusive or pending with a boundary limitation.
- A window is `complete` only when candles span the required start/end interval with no blocking schema or timestamp gaps.
- A window is `partial` when at least one candle overlaps the required interval but coverage does not satisfy the full window.
- A window is `missing` when no usable candle overlaps the required interval.
- Missing windows remain `pending`; partial windows become `inconclusive`; complete windows can receive computed metrics.

## Outcome Update Strategy

- Load the saved journal entry by journal id.
- Compute coverage for all required windows from the supplied OHLC source.
- For complete windows, compute observed high, low, close, range, observation start/end, source label, source symbol, and direction from snapshot price when available.
- If snapshot price is unavailable, compute price metrics and record direction as unavailable.
- Preserve original snapshot, source reports, walls, reactions, missing context, and original notes.
- Reuse existing conflict behavior for changing non-pending outcomes: a non-pending label/status change requires an explicit update note.
- Persist updated `entry.json`, `outcomes.json`, report files, and price-update artifacts under the existing ignored journal report directory.
- Record every update attempt with coverage status, missing-candle checklist, proxy limitations, warnings, and artifact references.

## Report Persistence

Extend the existing journal artifact layout:

```text
data/reports/xau_forward_journal/
`-- <journal_id>/
    |-- metadata.json
    |-- entry.json
    |-- outcomes.json
    |-- report.json
    |-- report.md
    `-- price_updates/
        |-- <update_id>_coverage.json
        |-- <update_id>_report.json
        `-- <update_id>_report.md
```

Artifact guard coverage already denies `data/reports/xau_forward_journal/` and `backend/data/reports/xau_forward_journal/`. The implementation must verify generated price-update artifacts remain ignored and untracked.

## API Design

Add local research endpoints to the existing XAU Forward Journal route group:

- `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data`
- `GET /api/v1/xau/forward-journal/entries/{journal_id}/price-coverage`

Responses must include research-only warnings, source label, source symbol, coverage status by window, missing-candle checklist, proxy limitation notes, updated outcome windows where applicable, generated artifact references, and structured errors for invalid journal ids, missing entries, invalid source labels, invalid OHLC schema, missing files, partial/missing coverage, conflicts, and secret/session/execution material.

## Dashboard Design

Extend the existing `/xau-vol-oi` Forward Journal section without adding trading controls:

- price data source and source symbol
- coverage status per outcome window
- missing window list and missing-candle checklist
- updated high/low/close/range/direction fields when present
- pending and inconclusive status badges
- proxy limitation notes near the affected source/outcomes
- generated artifact paths
- local-only and research-only disclaimer

The dashboard remains an inspection surface. It must not trigger trading behavior or describe outcomes as signals, predictions, safety checks, or live readiness.

## Test Strategy

- Unit tests for OHLC schema validation, accepted aliases, bad columns, duplicate timestamps, mixed/ambiguous timestamps, impossible OHLC values, missing files, and local CSV/Parquet source labels.
- Unit tests for window calculation from snapshot time, including `30m`, `1h`, `4h`, session-close boundary limitations, and next-day boundary limitations.
- Unit tests for complete, partial, and missing candle coverage.
- Unit tests for proxy source limitation labels for true spot, GC futures, Yahoo GC=F, GLD, local CSV, local Parquet, and unknown proxy.
- Unit tests for outcome metric and direction calculation with and without snapshot price.
- Unit tests proving missing candles remain pending and partial candles become inconclusive.
- Unit tests for report-store price update artifact path safety and serialization.
- Integration test updating a synthetic journal entry from synthetic candles while preserving immutable snapshot fields.
- API contract tests for price update, coverage read, invalid OHLC schema, missing journal, missing file, invalid source label, conflict, and forbidden content.
- Frontend type/API client compile coverage and production build.
- Generated artifact guard and `git status --ignored --short` review before completion.

## Implementation Phases

1. **Setup and schemas**: Add price-data enums, request/response models, artifact types, module skeletons, frontend type/client placeholders, and report-store artifact placeholders.
2. **OHLC loading and validation**: Load local CSV/Parquet and existing output paths, normalize schema, validate timestamps and OHLC consistency, and label sources.
3. **Window coverage and metrics**: Calculate required windows, evaluate complete/partial/missing coverage, compute high/low/close/range/direction, and build coverage summaries.
4. **Outcome update orchestration**: Update only outcome fields, preserve immutable snapshot/source evidence, handle conflicts, and persist update reports.
5. **API contracts**: Add coverage and update endpoints with structured errors and research-only guardrails.
6. **Dashboard extension**: Render source labels, coverage status, missing windows, updated metrics, proxy limitations, artifact paths, and disclaimers.
7. **Final validation and forbidden-scope review**: Run focused/full backend tests, frontend build, artifact guard, API/dashboard smoke, ignored-artifact review, and forbidden-scope scan.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. The design records observed outcomes against forward snapshots only.
- **Language Split**: PASS. Python and TypeScript stay in established project roles; no Rust is introduced.
- **Frontend Stack**: PASS. UI work stays in the existing Next.js dashboard.
- **Backend Stack**: PASS. Local research routes and schemas stay in FastAPI/Pydantic.
- **Data Processing**: PASS. Polars handles OHLC normalization, and window calculations are timestamp-safe.
- **Storage v0**: PASS. Local JSON/Markdown artifacts stay under ignored report roots.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, or Kubernetes.
- **Data-Source Principle**: PASS. Local/public OHLC outputs are labeled and proxy limitations remain visible.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing and partial candles are surfaced and cannot become completed outcomes.
- **Live Trading Principle**: PASS. No execution, broker, wallet, private-key, paper, shadow, or live trading behavior.

No constitution violations require complexity tracking.
