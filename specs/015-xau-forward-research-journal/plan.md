# Implementation Plan: XAU Forward Research Journal

**Branch**: `015-xau-forward-research-journal` | **Date**: 2026-05-14 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/015-xau-forward-research-journal/spec.md`

## Summary

Add a local-only, research-only forward evidence journal for XAU/Gold QuikStrike snapshots. The journal records what was known at snapshot time by linking existing Vol2Vol, Matrix, XAU QuikStrike Fusion, XAU Vol-OI, and XAU reaction reports, then allows later outcome-window updates from supplied OHLC observations. This creates honest forward evidence collection without pretending historical QuikStrike strike-level OI backtests exist.

The implementation will add a focused `backend/src/xau_forward_journal/` package, schemas in `backend/src/models/xau_forward_journal.py`, local API routes under `backend/src/api/routes/xau_forward_journal.py`, ignored report persistence under `data/reports/xau_forward_journal/`, and a Forward Journal section in `/xau-vol-oi`. It reuses existing report ids and source report stores from completed features 012, 013, 014, 006, and 010. It does not extract browser data, replay endpoints, store session material, create execution behavior, or claim profitability, predictive power, safety, or live readiness.

## Technical Context

**Language/Version**: Python 3.11+ for backend journal building, validation, outcome labeling, orchestration, and local report persistence; TypeScript with Next.js for dashboard inspection  
**Primary Dependencies**: Existing FastAPI, Pydantic, local JSON/Markdown/Parquet report patterns, XAU Vol-OI report outputs, XAU reaction report outputs, QuikStrike Vol2Vol report outputs, QuikStrike Matrix report outputs, XAU QuikStrike Fusion report outputs, Next.js, TypeScript, Tailwind CSS  
**Storage**: Local ignored filesystem artifacts under `data/reports/xau_forward_journal/` and `backend/data/reports/xau_forward_journal/`; no database server  
**Testing**: pytest unit/integration/contract tests with synthetic report fixtures and synthetic OHLC outcome windows; backend import check; full backend pytest suite; frontend production build when UI changes; generated artifact guard  
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow  
**Project Type**: Existing FastAPI backend plus Next.js dashboard inspection with local research files  
**Performance Goals**: Creating or reading one journal entry should complete within normal local API interaction time; synthetic fixture tests should run within the existing backend test envelope  
**Constraints**: Local-only, research-only, forward evidence only, no generated artifact commits, no secret/session persistence, no browser RPA, no endpoint replay, no paid vendors, no live/paper/shadow trading, no forbidden v0 technologies, no fabricated outcome data  
**Scale/Scope**: One journal entry links one snapshot set of source reports; outcome updates cover the five supported windows: 30m, 1h, 4h, session_close, and next_day

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature records forward research evidence and explicitly avoids execution or strategy claims.
- **Language Split**: PASS. Python remains the research/orchestration language and TypeScript remains dashboard-only. No Rust execution component is introduced.
- **Frontend Stack**: PASS. Dashboard inspection stays inside the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. Local research endpoints and request/response schemas use the existing FastAPI/Pydantic pattern.
- **Data Processing**: PASS. Journal entries are timestamped and preserve source report provenance; outcome labeling is deterministic and conservative from supplied observations.
- **Storage v0**: PASS. Generated journal reports stay under ignored local `data/` report paths.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service is introduced.
- **Data-Source Principle**: PASS. Journal entries reference existing approved local reports and later supplied OHLC observations; limitations remain visible.
- **TradingView Principle**: PASS. No TradingView dependency or source-of-truth behavior is added.
- **Reliability Principle**: PASS. Missing context, unavailable outcomes, and source warnings are surfaced before any interpretation.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/015-xau-forward-research-journal/
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
|   |       `-- xau_forward_journal.py
|   |-- models/
|   |   `-- xau_forward_journal.py
|   `-- xau_forward_journal/
|       |-- __init__.py
|       |-- entry_builder.py      # create journal entries from source report ids
|       |-- outcome.py            # validate and apply outcome-window updates
|       |-- orchestration.py      # create/update/list/detail workflow assembly
|       `-- report_store.py       # metadata, JSON/Markdown report persistence
|-- tests/
|   |-- unit/
|   |   |-- test_xau_forward_journal_models.py
|   |   |-- test_xau_forward_journal_entry_builder.py
|   |   |-- test_xau_forward_journal_outcome.py
|   |   `-- test_xau_forward_journal_report_store.py
|   |-- integration/
|   |   `-- test_xau_forward_journal_flow.py
|   `-- contract/
|       `-- test_xau_forward_journal_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx          # Forward Journal inspection section
    |-- services/
    |   `-- api.ts               # journal entry clients
    `-- types/
        `-- index.ts             # journal request/report/outcome types
```

**Structure Decision**: Use a new additive `backend/src/xau_forward_journal/` package because the feature records forward evidence across multiple existing report families rather than changing extraction, fusion, wall scoring, or reaction classification. Keep source extraction and XAU report creation packages unchanged.

## Source Report Loading Strategy

- Load source report ids through existing local report outputs:
  - QuikStrike Vol2Vol reports from feature 012.
  - QuikStrike Matrix reports from feature 013.
  - XAU QuikStrike Fusion reports from feature 014.
  - XAU Vol-OI reports from feature 006.
  - XAU reaction reports from feature 010.
- Validate that source reports are XAU/Gold-compatible and refer to a coherent snapshot set.
- Accept partial reports only when they contain usable summaries and their warnings/limitations are copied into the journal entry.
- Preserve source report ids, statuses, artifact references, warnings, limitations, and creation timestamps.
- Never reload browser sessions, replay QuikStrike endpoints, inspect credentials/session material, or copy generated report contents into tracked docs.

## Journal Entry Creation Flow

1. Validate request and research-only acknowledgement.
2. Validate source report ids and load local report metadata.
3. Confirm product compatibility and source linkage where available.
4. Derive snapshot context from request inputs and source report metadata.
5. Summarize top walls by open interest, OI change, and volume.
6. Summarize reaction labels, NO_TRADE reasons, and bounded risk annotations if present.
7. Copy missing-context checklist items from fusion and reaction reports.
8. Initialize all outcome windows as `pending` unless explicit outcome observations are included.
9. Persist journal metadata, entry JSON, optional Markdown, and artifact metadata under ignored journal paths.

## Outcome Update And Labeling Flow

- Outcome updates apply to a single existing journal entry.
- Supported windows: `30m`, `1h`, `4h`, `session_close`, `next_day`.
- Supported labels: `wall_held`, `wall_rejected`, `wall_accepted_break`, `moved_to_next_wall`, `reversed_before_target`, `stayed_inside_range`, `no_trade_was_correct`, `inconclusive`, `pending`.
- Price observations are accepted only when supplied by the user or approved local research data. Missing windows remain `pending`.
- If OHLC values are incomplete or stale, the label must remain `pending` or `inconclusive`.
- If an update changes a previously assigned non-pending label, the request must include a note explaining the conflict/update.
- The original snapshot section remains immutable; only outcome-window state and journal notes are updated.
- Outcome labels are research annotations only and must not imply signals, tradability, or profitability.

## Report Persistence

Journal persistence should follow existing local report-store patterns:

```text
data/reports/xau_forward_journal/
`-- <journal_id>/
    |-- metadata.json
    |-- entry.json
    |-- outcomes.json
    |-- report.json
    `-- report.md
```

Artifact guard coverage must include the journal report root. Generated journal data must stay ignored and untracked.

## API Design

Local research endpoints:

- `POST /api/v1/xau/forward-journal/entries`
- `GET /api/v1/xau/forward-journal/entries`
- `GET /api/v1/xau/forward-journal/entries/{journal_id}`
- `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes`
- `GET /api/v1/xau/forward-journal/entries/{journal_id}/outcomes`

Responses must include research-only warnings, source report links, outcome status, missing context, generated artifact references, and structured errors for invalid requests, missing source reports, missing entries, invalid outcome windows, conflicting outcome updates, and secret/session-like fields.

## Dashboard Design

Extend `/xau-vol-oi` with a compact Forward Journal section:

- saved journal entries and selected journal id
- snapshot time and capture session
- linked Vol2Vol, Matrix, Fusion, XAU Vol-OI, and XAU reaction report ids
- top walls/zones and reaction labels
- NO_TRADE reasons and missing context checklist
- outcome-window status and labels
- notes and artifact paths
- local-only and research-only disclaimer

The dashboard is inspection-only for this feature. It must not add trading controls or execution language.

## Test Strategy

- Unit tests for schema validation, enum values, strict secret-field rejection, and forbidden wording.
- Unit tests for journal entry creation from synthetic source reports.
- Unit tests for top wall/reaction summary selection.
- Unit tests for outcome-window validation and conservative label handling.
- Unit tests for path-safe report-store helpers and JSON/Markdown persistence.
- Integration tests for creating a journal entry from synthetic report ids.
- Integration tests for updating outcomes and preserving the immutable snapshot.
- API contract tests for create/list/detail/outcome endpoints and structured error cases.
- Frontend production build after adding the dashboard section.
- Full backend pytest suite and generated artifact guard before completion.

## Implementation Phases

1. **Setup and schemas**: Create package, models, route skeleton, report-store skeleton, artifact guard coverage, placeholder dashboard/types/clients.
2. **Journal entry creation**: Load synthetic source reports, validate compatibility, summarize snapshot walls/reactions/missing context, persist entries.
3. **Outcome update and labeling**: Add outcome-window models, validation, conservative label update rules, conflict handling, persistence.
4. **API and report persistence**: Complete endpoints, structured errors, list/detail/outcome reads, JSON/Markdown reports.
5. **Dashboard inspection**: Render journal list/detail, source links, top walls/reactions, missing context, outcomes, notes, disclaimers.
6. **Final validation and forbidden-scope review**: Run backend/frontend/artifact checks, API/dashboard smoke, ignored-artifact and forbidden-scope review.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. The design records forward evidence and outcome annotations only.
- **Language Split**: PASS. Python and TypeScript remain in their established project roles; no Rust is introduced.
- **Frontend Stack**: PASS. UI work stays in the existing Next.js dashboard.
- **Backend Stack**: PASS. Local research routes and schemas stay in FastAPI/Pydantic.
- **Data Processing**: PASS. Snapshot and outcome updates preserve timestamps and source provenance.
- **Storage v0**: PASS. Local JSON/Markdown artifacts stay under ignored report roots.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, or Kubernetes.
- **Data-Source Principle**: PASS. Existing local reports and later supplied OHLC observations keep limitations visible.
- **Reliability Principle**: PASS. Missing outcome data remains pending/inconclusive and cannot be fabricated.
- **Live Trading Principle**: PASS. No execution, broker, wallet, private-key, paper, shadow, or live trading behavior.

No constitution violations require complexity tracking.
