# Research: Real Research Execution Runbook

## Decision: Add A Focused `research_execution` Package

**Rationale**: Feature 007 coordinates existing systems and should not change strategy, validation, or XAU wall logic. A focused package under `backend/src/research_execution/` keeps orchestration, preflight, aggregation, and persistence separate from feature 005 multi-asset research and feature 006 XAU Vol-OI internals.

**Alternatives considered**:
- Extend `backend/src/research/`: Rejected because feature 005 remains responsible for multi-asset report generation, while 007 is a higher-level evidence runbook.
- Extend `backend/src/xau/`: Rejected because the execution runbook also covers crypto and proxy OHLCV workflows.

## Decision: Reuse Existing Reports Instead Of Creating New Strategy Logic

**Rationale**: The spec requires no new strategy logic. The execution workflow should either reference existing report IDs or call existing report workflows when inputs are ready, then aggregate evidence from persisted artifacts.

**Alternatives considered**:
- Recompute backtests directly in 007: Rejected because it duplicates feature 003/004/005 responsibility and increases risk of inconsistent metrics.
- Create new strategy variants: Rejected by the spec and constitution.

## Decision: Use Preflight As The First-Class Gate

**Rationale**: Real research execution must clearly distinguish completed work from blocked work. Preflight records missing processed features, missing XAU local files, unsafe paths, unreadable artifacts, and unsupported provider capabilities before evidence aggregation.

**Alternatives considered**:
- Fail the whole run on the first missing asset: Rejected because the evidence report must show mixed completed and blocked workflows.
- Skip missing assets silently: Rejected by success criteria and data-source transparency requirements.

## Decision: Persist Evidence Under `data/reports/research_execution/`

**Rationale**: This matches the existing report convention and keeps generated artifacts ignored and local. Each execution run can store normalized config, metadata, evidence JSON, evidence Markdown, and missing-data checklist without committing generated files.

**Alternatives considered**:
- Store evidence in a database: Rejected because PostgreSQL is forbidden in v0 and local Parquet/JSON/Markdown storage is sufficient.
- Store under feature-specific spec folders: Rejected because generated artifacts must not be committed.

## Decision: Add API Namespace `/api/v1/research/execution-runs`

**Rationale**: The path is explicit, groups all execution-run resources, and avoids overloading feature 005 `/research/runs` endpoints. It also matches the user-specified API shape.

**Alternatives considered**:
- Add subroutes under existing multi-asset research endpoints: Rejected because execution runs aggregate multiple workflow families, not only multi-asset reports.
- Add XAU execution endpoints under `/xau`: Rejected because the final evidence report crosses crypto, proxy, and XAU workflows.

## Decision: Use `/evidence` For The Dashboard Page

**Rationale**: The page is a final research evidence surface rather than a raw run-management page. The route name is concise and fits the dashboard requirement for an Evidence or Research Execution page.

**Alternatives considered**:
- `/research-execution`: Clear but longer; acceptable if routing conventions later prefer it.
- Extending `/research`: Rejected because feature 005 already owns grouped multi-asset research reporting.

## Decision: Keep Decision Labels Rule-Based And Bounded

**Rationale**: Decision labels must support research triage without implying profitability or trading readiness. Simple documented rules make the output auditable and avoid hidden assumptions.

**Alternatives considered**:
- Score-based opaque ranking: Rejected because it would obscure why a workflow was labeled continue, refine, reject, data_blocked, or inconclusive.
- ML classification: Rejected because ML model training is forbidden in v0.

## Decision: Treat Yahoo/Proxy Assets As OHLCV-Only Unless Local Data Proves Otherwise

**Rationale**: Yahoo Finance and proxy assets must not be treated as sources of crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD spot execution data. Unsupported capability labels are part of the evidence report.

**Alternatives considered**:
- Infer derivatives context from GC=F or GLD: Rejected because those are OHLCV proxies only in this project.
- Drop unsupported capability requests: Rejected because blocked and limited inputs must stay visible.
