# Feature Specification: XAU Daily Research Workbench

**Feature Branch**: `022-xau-daily-research-workbench`
**Created**: 2026-06-07
**Status**: Completed
**Input**: User description: "Make the XAU/CME system usable as a clean daily local workflow: fetch or load CME data, get GC/XAU prices, calculate basis, build daily structural map, run Feature 021 candidate classification, persist outputs, expose polished local API/page."

## User Scenarios & Testing

### User Story 1 - Run One Daily Local Workbench (Priority: P1)

As an XAU researcher, I want one local command/API run to load a CME/XAU bundle, apply reference prices, build a structural map, run Feature 021 candidates, and persist artifacts so that the daily review starts from one reproducible result.

**Why this priority**: Features 017-021 already build the pieces. The next useful milestone is orchestration, not another classifier.

**Independent Test**: Run a fixture local bundle with manual GC/traded/session-open prices and verify a map plus candidate sidecars are created.

**Acceptance Scenarios**:

1. Given a complete local XAU bundle, GC reference, traded reference, and session open, when the workbench runs, then it persists map artifacts, candidate artifacts, and a workbench run artifact.
2. Given the run succeeds, when the result is inspected, then `research_only=true` and `signal_allowed=false`.
3. Given candidate classification runs, when artifacts are inspected, then `candidates.json`, `candidates.md`, and `candidate_metadata.json` exist beside the map.

### User Story 2 - Preserve Missing Context (Priority: P2)

As an XAU researcher, I want missing CME source, basis, traded price, expected range, or session open to produce explicit blocked/partial output so that incomplete data cannot be mistaken for an actionable setup.

**Why this priority**: The project doctrine says missing context means no signal. A daily workbench must make the blocker visible.

**Independent Test**: Run missing-source, missing-basis, and missing-session-open cases and verify blocked/no-trade candidate behavior.

**Acceptance Scenarios**:

1. Given the CME local bundle is missing, when the workbench runs, then it returns a clean blocked response with `missing_inputs`.
2. Given basis is unavailable, when candidates run, then the candidate is `no_trade`, readiness is blocked, and `signal_allowed=false`.
3. Given session open is unavailable, when candidates run, then the candidate is `no_trade`, readiness is blocked, and `signal_allowed=false`.

### User Story 3 - Expose Local Research API (Priority: P3)

As an XAU researcher, I want local API endpoints for running the workbench, reading the latest run, reading maps, and reading candidates so that a future dashboard can use the same source-backed artifacts.

**Why this priority**: The dashboard should consume stable local contracts instead of reconstructing artifact paths ad hoc.

**Independent Test**: Use FastAPI TestClient to run the workbench and read latest/map/candidate endpoints.

## Edge Cases

- `local_bundle` source is selected without `input_dir`.
- Bundle directory or required report JSON is missing.
- `api_only` is selected before an API fetcher is configured.
- `latest_existing` has no matching structural map.
- Basis is unavailable.
- Session open is unavailable.
- Traded price is unavailable.
- Candidate sidecar files are missing.
- Repeated runs use generated workbench run ids and path-safe artifact writes.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide `run_xau_daily_research_workbench(...)`.
- **FR-002**: The run request MUST accept `session_date`, `expiration_code`, `traded_instrument`, `cme_source`, optional `input_dir`, optional GC/traded/session-open references, optional `output_root`, and `run_candidates`.
- **FR-003**: The system MUST support `cme_source=local_bundle`.
- **FR-004**: The system MUST support `cme_source=latest_existing`.
- **FR-005**: The system MUST return a clean blocked response for unconfigured `cme_source=api_only`.
- **FR-006**: The system MUST define provider interfaces for CME data, GC/futures price, traded price, and session open.
- **FR-007**: The system MUST implement local bundle, latest-existing artifact, and static fixture price providers without live trading access.
- **FR-008**: The system MUST build or load a persisted `XauDailyStructuralMap`.
- **FR-009**: The system MUST run Feature 021 candidate classification when `run_candidates=true`.
- **FR-010**: The system MUST persist `candidates.json`, `candidates.md`, and `candidate_metadata.json` beside the structural map.
- **FR-011**: The system MUST persist a workbench run artifact under `data/reports/xau_daily_workbench/`.
- **FR-012**: Every API response MUST include `research_only`, `signal_allowed`, `readiness`, `missing_inputs`, `no_signal_reasons`, and `artifact_paths`.
- **FR-013**: The system MUST expose `POST /api/v1/research/xau/workbench/run`.
- **FR-014**: The system MUST expose `GET /api/v1/research/xau/workbench/latest`.
- **FR-015**: The system MUST expose `GET /api/v1/research/xau/workbench/maps/{map_id}`.
- **FR-016**: The system MUST expose `GET /api/v1/research/xau/workbench/candidates/{map_id}`.
- **FR-017**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, order routing, PnL, position sizing, automatic trade placement, or buy/sell instructions.

## Success Criteria

- **SC-001**: Fixture workbench runs create a map and candidate sidecars.
- **SC-002**: Missing CME source returns blocked output without traceback.
- **SC-003**: Missing basis creates blocked/no-trade candidates.
- **SC-004**: Missing session open creates blocked/no-trade candidates.
- **SC-005**: Candidate artifacts round-trip through the service.
- **SC-006**: API run returns `map_id` and `candidate_set_id`.
- **SC-007**: Latest endpoint handles empty state.
- **SC-008**: `signal_allowed=false` everywhere.

## Assumptions

- Feature 020A remains the canonical local bundle adapter.
- Feature 021 remains the canonical candidate classifier.
- API-only CME fetching is deferred until the local read-only source contract is fully validated.
- Frontend page polish is deferred; this slice exposes backend API and docs.
