# Implementation Plan: XAU Zone Reaction and Risk Planner

**Branch**: `010-xau-zone-reaction-and-risk-planner` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/010-xau-zone-reaction-and-risk-planner/spec.md`

## Summary

Add a research-only deterministic decision layer on top of the completed XAU Vol-OI Wall Engine. The feature introduces a focused `backend/src/xau_reaction/` package, `backend/src/models/xau_reaction.py`, `backend/src/api/routes/xau_reaction.py`, local report persistence under ignored `data/reports/xau_reaction/`, and dashboard inspection by extending `/xau-vol-oi` with reaction-report sections. It reuses feature 006 XAU wall report metadata, expected ranges, wall rows, and zone rows, then adds intraday freshness, IV/RV/VRP context, session-open context, candle acceptance/rejection, deterministic reaction labels, and bounded research risk-plan annotations.

The feature does not redesign the system and does not add strategy execution, live trading, paper trading, shadow trading, private keys, broker integration, real execution, buy/sell execution signals, or forbidden v0 technologies.

## Technical Context

**Language/Version**: Python 3.11+ for backend research logic and orchestration; TypeScript with Next.js for dashboard UI  
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, PyArrow/Parquet, local report stores, Next.js, TypeScript, Tailwind CSS, existing dashboard services/types  
**Storage**: Local ignored filesystem artifacts under `data/reports/xau_reaction/`; generated JSON, Markdown, and Parquet outputs remain untracked  
**Testing**: pytest unit/integration/contract tests, backend import check, full backend pytest suite, frontend `npm run build`, generated artifact guard, API smoke, dashboard smoke  
**Target Platform**: Local research workstation and existing CI-compatible Windows/Linux validation flow  
**Project Type**: Existing FastAPI backend plus Next.js dashboard  
**Performance Goals**: Synthetic reaction reports should run in under 2 minutes locally; classifier/risk-plan logic should be deterministic for the same inputs and scale to hundreds of wall/zone rows without reprocessing source OI files  
**Constraints**: Research-only, deterministic, timestamp-safe, no generated artifact commits, no external downloads in automated tests, no execution credentials, no broker/wallet/order behavior, no forbidden v0 technologies  
**Scale/Scope**: One reaction report references one existing XAU Vol-OI report and evaluates its wall/zone rows with optional intraday freshness, volatility, session-open, candle, event-risk, and bounded risk configuration inputs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature adds decision annotations for research review only; it does not approve or execute trades.
- **Language Split**: PASS. Python remains the research/orchestration language and TypeScript remains dashboard-only. No Rust execution component is introduced.
- **Frontend Stack**: PASS. Dashboard work stays inside the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. API and request/response schemas stay in FastAPI and Pydantic.
- **Data Processing**: PASS. Calculations are deterministic, local, and timestamp-aware. Polars/Parquet are used only for local persisted report tables when needed.
- **Storage v0**: PASS. Generated reports are local files under ignored `data/reports/xau_reaction/`.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse is introduced.
- **Event Architecture**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service redesign is introduced.
- **Data-Source Principle**: PASS. Feature reuses validated XAU wall reports and labels missing or limited data; it does not create a new source provider or treat Yahoo proxies as derivatives data.
- **Reliability Principle**: PASS. The plan adds stale/thin/prior-day gates, basis/volatility limitations, no-trade reasons, and bounded risk annotations.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/010-xau-zone-reaction-and-risk-planner/
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
|   |       |-- xau.py                 # existing feature 006 routes
|   |       `-- xau_reaction.py        # new reaction-report routes
|   |-- models/
|   |   |-- xau.py                    # existing feature 006 schemas
|   |   `-- xau_reaction.py           # new reaction schemas
|   |-- reports/
|   |   `-- writer.py                 # extend with XAU reaction JSON/Markdown composition
|   |-- xau/
|   |   `-- report_store.py           # existing wall/zone report dependency
|   `-- xau_reaction/
|       |-- __init__.py
|       |-- freshness.py              # intraday OI freshness state
|       |-- vol_regime.py             # RV, IV/RV/VRP, IV edge, RV extension
|       |-- open_regime.py            # session-open anchor state
|       |-- acceptance.py             # wall acceptance/rejection state
|       |-- classifier.py             # six deterministic reaction labels
|       |-- risk_plan.py              # bounded research risk annotations
|       |-- report_store.py           # xau_reaction report persistence
|       `-- orchestration.py          # load XAU report and assemble reaction report
|-- tests/
|   |-- unit/
|   |   |-- test_xau_reaction_freshness.py
|   |   |-- test_xau_reaction_vol_regime.py
|   |   |-- test_xau_reaction_open_regime.py
|   |   |-- test_xau_reaction_acceptance.py
|   |   |-- test_xau_reaction_classifier.py
|   |   `-- test_xau_reaction_risk_plan.py
|   |-- integration/
|   |   `-- test_xau_reaction_flow.py
|   `-- contract/
|       `-- test_xau_reaction_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx              # extend with reaction report inspection
    |-- services/
    |   `-- api.ts                    # add reaction-report client methods
    `-- types/
        `-- index.ts                  # add reaction report types
```

**Structure Decision**: Use a new additive `backend/src/xau_reaction/` package because reaction classification is a dependent decision layer, not part of raw XAU wall construction. Keep feature 006 `backend/src/xau/` as the source of wall reports and avoid merging reaction logic into wall scoring. Extend `/xau-vol-oi` so researchers inspect walls, zones, reactions, and bounded risk annotations from one XAU research surface.

## Phase 0 Research Decisions

The supporting decisions are documented in [research.md](./research.md). Key outcomes:

- The first implementation reads persisted feature 006 reports through `XauReportStore` and does not re-import options OI source files.
- Freshness, volatility, open, and candle modules are pure deterministic functions with Pydantic input/output schemas.
- Hard no-trade gates run before candidate promotion.
- Reaction label priority is deterministic when multiple labels could apply.
- Risk plans are research annotations only and are omitted for `NO_TRADE`.
- The requested `xau_vol_oi_transcript_distillation.md` file was not present in this workspace during planning; the user-provided distilled rules are incorporated, and implementation should read the file if it becomes available before coding.

## Phase 1 Design

Design artifacts are generated with this plan:

- [data-model.md](./data-model.md): Pydantic schema plan, fields, relationships, and validation rules.
- [contracts/api.md](./contracts/api.md): API request/response contracts and structured errors.
- [quickstart.md](./quickstart.md): validation path, smoke flow, dashboard checks, and forbidden-scope review.

## Reaction Report Flow

1. Accept `XauReactionReportRequest` with a source XAU Vol-OI report id and optional context inputs.
2. Load the source report, walls, and zones through existing feature 006 report-store behavior.
3. Validate source report status, wall/zone availability, expected-range availability, basis mapping state, and research-only acknowledgement.
4. Run intraday freshness classification.
5. Run IV/RV/VRP and price-position classification.
6. Run session-open regime classification.
7. Run candle acceptance/rejection classification per wall or per evaluated zone.
8. Run deterministic reaction classifier against each eligible wall/zone.
9. Run bounded risk planner for non-`NO_TRADE` reactions only.
10. Persist metadata, reaction rows, risk-plan rows, JSON report, Markdown report, and optional Parquet tables under `data/reports/xau_reaction/`.
11. Return report detail through API and dashboard with no-trade reasons, limitations, and research-only warnings.

## Deterministic Classification Order

The classifier should use an explicit order so repeated runs are stable:

1. **Blocking gates**: missing source report, missing walls/zones, unavailable basis, stale/prior-day/unknown freshness when configured as hard block, thin flow below hard threshold, missing expected range where required, contradictory candle/open evidence, or explicit event-risk block -> `NO_TRADE`.
2. **Pin evidence**: near-expiry large OI near spot and inside 1SD with usable basis/freshness -> `PIN_MAGNET`.
3. **Squeeze stress**: accepted wall break with IV edge stress, flow expansion, or fresh high-score wall cluster -> `SQUEEZE_RISK`.
4. **Vacuum evidence**: accepted break or directional acceptance into a low-OI gap with distant next wall -> `VACUUM_TO_NEXT_WALL`.
5. **Breakout evidence**: close plus next-bar hold beyond wall buffer, non-stale data, and supportive IV/RV/open context -> `BREAKOUT_CANDIDATE`.
6. **Reversal evidence**: high-score wall, wick rejection or failed breakout, stretched sigma position, and fresh usable data -> `REVERSAL_CANDIDATE`.
7. **Fallback**: insufficient or mixed evidence -> `NO_TRADE`.

Each output must include explanation notes showing which rule branch won and which evidence reduced confidence.

## API Design

Routes are additive under `/api/v1/xau/reaction-reports`:

- `POST /api/v1/xau/reaction-reports`
- `GET /api/v1/xau/reaction-reports`
- `GET /api/v1/xau/reaction-reports/{report_id}`
- `GET /api/v1/xau/reaction-reports/{report_id}/reactions`
- `GET /api/v1/xau/reaction-reports/{report_id}/risk-plan`

Structured errors should cover missing source reports, invalid source report ids, invalid context inputs, blocked report creation, and unknown reaction report ids. Responses must contain research-only warnings and must not contain buy/sell execution signal wording.

## Dashboard Design

Extend `/xau-vol-oi` with a reaction-report section or tab:

- Source XAU Vol-OI report selector.
- Reaction report selector/status.
- Freshness badge.
- IV/RV/VRP panel.
- Session open panel.
- Acceptance/rejection state summary.
- Reaction label table.
- Bounded risk planner table.
- No-trade reasons panel.
- Research-only disclaimer.

The page should remain an inspection surface, not a workflow that suggests order placement, alerting, broker connectivity, or live readiness.

## Test Strategy

- Unit tests for intraday freshness state precedence and confidence/no-trade gates.
- Unit tests for realized volatility, IV/RV/VRP comparison, IV edge state, and RV extension state.
- Unit tests for session-open side, distance, flip state, and support/resistance interpretation.
- Unit tests for wall acceptance, wick rejection, failed breakout, and confirmed breakout.
- Unit tests for all six reaction labels and deterministic tie/priority behavior.
- Unit tests for bounded risk planner output, no plan for `NO_TRADE`, capped recovery legs, minimum reward/risk handling, and forbidden wording.
- Integration test using a synthetic feature 006 XAU wall report persisted through or compatible with `XauReportStore`.
- API contract tests for create/list/detail/reactions/risk-plan endpoints and structured errors.
- Frontend production build and focused dashboard smoke for `/xau-vol-oi`.
- Existing backend suite and generated artifact guard.
- Forbidden-scope scan for live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell execution signals, and prohibited claims.

## Implementation Phases

1. **Setup and schemas**: Add `xau_reaction` package skeleton, models, route skeleton, report-store skeleton, route registration, frontend types/API placeholders, and writer placeholders.
2. **Freshness / IV-RV-VRP / opening / acceptance foundations**: Implement pure deterministic context modules and their unit tests.
3. **Reaction classifier**: Implement six labels, hard no-trade gates, deterministic priority rules, confidence labels, explanation notes, target/invalidation references, and classifier tests.
4. **Bounded risk planner**: Implement capped research-only plan annotations, no plan for `NO_TRADE`, cancel conditions, recovery caps, minimum reward/risk checks, and forbidden wording tests.
5. **API/report persistence**: Implement orchestration, feature 006 report loading, report persistence, JSON/Markdown/Parquet artifacts, API endpoints, and contract tests.
6. **Dashboard inspection**: Extend `/xau-vol-oi` with reaction reports, freshness/vol/open/acceptance panels, reaction/risk tables, no-trade reasons, and disclaimer.
7. **Final validation and forbidden-scope review**: Run backend import, full backend tests, focused 010 tests, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope scan.

## Post-Design Constitution Check

- **Research-only scope**: PASS. Outputs are reaction candidates, no-trade states, and bounded annotations only.
- **No execution behavior**: PASS. Design has no live, paper, shadow, broker, wallet, key, order, or position-management behavior.
- **Allowed v0 stack**: PASS. Design uses existing Python/FastAPI/Pydantic/Polars/Parquet and Next.js/TypeScript/Tailwind surfaces.
- **Reproducible local storage**: PASS. Generated artifacts stay under ignored `data/reports/xau_reaction/`.
- **Timestamp/data safety**: PASS. Freshness and open/candle states explicitly depend on timestamped inputs and stale/prior-day gates.
- **No hidden assumptions**: PASS. Missing IV/RV/open/candle/event context is represented as unknown or no-trade reasons.
- **No strategy claims**: PASS. Text and contracts prohibit profitability, predictive, safety, and live-readiness claims.
- **No architecture redesign**: PASS. Feature 006, 007, 008, and 009 surfaces are dependencies, not replaced.

## Complexity Tracking

No constitution violations or extra architectural complexity are required.
