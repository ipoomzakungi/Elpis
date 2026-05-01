# Implementation Plan: XAU Vol-OI Wall Engine

**Branch**: `006-xau-vol-oi-wall-engine` | **Date**: 2026-05-01 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/006-xau-vol-oi-wall-engine/spec.md`

## Summary

Feature 006 adds a research-only XAU/gold derivatives zone engine that turns locally imported gold options OI, volatility, spot/proxy references, and futures references into basis-adjusted spot-equivalent OI wall levels, expected ranges, wall scores, and zone classifications. The implementation is additive: it introduces a focused `backend/src/xau/` package, `backend/src/models/xau.py`, `backend/src/api/routes/xau.py`, report persistence under existing `data/reports`, and a focused dashboard page at `frontend/src/app/xau-vol-oi/page.tsx`. It does not redesign the provider, backtest, validation, or research report systems.

## Technical Context

**Language/Version**: Python 3.11+ backend and TypeScript dashboard, matching the existing repository  
**Primary Dependencies**: Existing FastAPI, Pydantic, Polars, DuckDB/Parquet, Next.js, TypeScript, Tailwind, and existing report/storage helpers  
**Storage**: Existing local research storage under `data/reports`; imported source files remain local CSV/Parquet inputs and generated artifacts stay ignored  
**Testing**: Existing pytest backend tests, API contract tests, integration tests, frontend production build, and artifact guard script  
**Target Platform**: Local research workstation workflow with public/proxy OHLCV sources and local imported gold derivatives datasets  
**Project Type**: Existing backend API plus dashboard web application  
**Performance Goals**: Complete a sample XAU wall report from a small local options OI dataset in under 2 minutes; keep report inspection responsive for hundreds to low thousands of wall rows  
**Constraints**: Research-only; no live trading, paper trading, shadow trading, private keys, broker integration, real execution, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training  
**Scale/Scope**: v0 local report workflow for XAU/gold derivatives research using spot/proxy references, futures references, local options OI rows, optional IV/OI-change/volume fields, and report/dashboard inspection

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-first architecture**: PASS. The feature creates historical research zones and reports only.
- **Language split**: PASS. Uses the existing Python research backend and TypeScript dashboard. No Rust execution engine is introduced.
- **Frontend stack**: PASS. Adds a focused dashboard page using the existing app structure.
- **Backend stack**: PASS. Uses existing FastAPI and Pydantic patterns.
- **Data processing**: PASS. Uses Polars-compatible local CSV/Parquet processing and timestamp-safe validation.
- **Storage v0**: PASS. Persists generated reports under `data/reports`; imported and generated artifacts remain ignored.
- **Event architecture**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or service redesign.
- **Data-source principle**: PASS. Treats Yahoo Finance GC=F/GLD as OHLCV proxies only and requires local options OI/IV imports for wall analysis.
- **Reliability principle**: PASS. Adds preflight validation, missing-data instructions, freshness scoring, and limitation notes.
- **Live trading principle**: PASS. No execution, broker, wallet, private-key, paper, shadow, or live behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/006-xau-vol-oi-wall-engine/
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
|   |       `-- xau.py
|   |-- models/
|   |   `-- xau.py
|   |-- reports/
|   |   `-- writer.py              # Add XAU JSON/Markdown report composition
|   `-- xau/
|       |-- __init__.py
|       |-- imports.py             # Local CSV/Parquet validation and normalization
|       |-- basis.py               # Futures-to-spot basis and level mapping
|       |-- volatility.py          # Expected move and 1SD/2SD ranges
|       |-- walls.py               # OI share, freshness, expiry weight, wall score
|       |-- zones.py               # Zone classification and explanation notes
|       |-- orchestration.py       # Report workflow coordinator
|       `-- report_store.py        # XAU report persistence
|-- tests/
|   |-- unit/
|   |   |-- test_xau_basis.py
|   |   |-- test_xau_imports.py
|   |   |-- test_xau_volatility.py
|   |   |-- test_xau_walls.py
|   |   `-- test_xau_zones.py
|   |-- integration/
|   |   `-- test_xau_vol_oi_flow.py
|   `-- contract/
|       `-- test_xau_api_contracts.py

frontend/
`-- src/
    |-- app/
    |   `-- xau-vol-oi/
    |       `-- page.tsx
    |-- components/
    |   `-- ui/
    |       `-- Header.tsx          # Add navigation link if needed
    |-- services/
    |   `-- api.ts                  # XAU report client methods
    `-- types/
        `-- index.ts                # XAU response/table types
```

**Structure Decision**: Use an additive feature package under `backend/src/xau/` and a focused dashboard route under `frontend/src/app/xau-vol-oi/`. Keep provider, backtest, validation, and multi-asset research modules unchanged except for shared report writer/API registration touchpoints.

## Data Schema

- `XauVolOiReportRequest`: selected session/date, local options OI file path, optional spot/futures references, optional manual basis, volatility range preferences, and report format.
- `XauReferencePrice`: reference kind, symbol/source, timestamp, price, freshness status, and limitation notes.
- `XauBasisSnapshot`: futures price, spot/proxy price, manual or computed basis, timestamp alignment status, and notes.
- `XauOptionsOiRow`: normalized source row with date/session, expiry, strike, option type, open interest, and optional OI change, volume, IV, futures price, spot price, delta, and gamma.
- `XauVolatilitySnapshot`: IV, realized volatility, manual expected range values, source labels, and unavailable reasons.
- `XauExpectedRange`: expected move, 1SD range, optional 2SD stress range, source type, expiry/days-to-expiry, and notes.
- `XauOiWall`: original strike, spot-equivalent level, expiry, OI, OI share, expiry weight, freshness factor, wall score, wall type, and limitations.
- `XauZone`: zone type, level/range bounds, linked walls, pin-risk score, squeeze-risk score, confidence, notes, and no-trade warnings.
- `XauVolOiReport`: persisted report metadata, request, references, basis snapshot, expected range, wall rows, zone rows, warnings, limitations, and artifacts.
- `XauVolOiReportSummary`: report id, status, session, source row counts, top wall count, warning count, and created timestamp.

## Local Import Flow

1. Accept a local CSV or Parquet file path from the request.
2. Resolve the path under approved local research data directories and reject unsafe paths.
3. Read the file using structured parsing, not ad hoc string manipulation.
4. Validate required columns: `date` or `timestamp`, `expiry`, `strike`, `option_type`, `open_interest`.
5. Normalize optional columns when present: `oi_change`, `volume`, `implied_volatility`, `underlying_futures_price`, `xauusd_spot_price`, `delta`, `gamma`.
6. Parse session timestamp/date, expiry date, strike numeric value, option type, and OI numeric value.
7. Report missing required columns, unreadable files, parse failures, duplicate rows, stale references, and unavailable IV/OI-change/volume without fabricating data.

## Basis-Adjustment Flow

1. Prefer explicit spot and futures references from the request or validated source rows.
2. If manual basis is provided, use it and mark basis source as manual.
3. Otherwise compute `futures_spot_basis = gold_futures_price - xauusd_spot_or_proxy_price`.
4. Map each strike with `spot_equivalent_level = futures_strike - futures_spot_basis`.
5. Persist original strike, basis value, basis source, spot reference, futures reference, timestamp alignment status, and spot-equivalent level.
6. If basis cannot be established, block spot-equivalent wall mapping and return missing-data instructions.

## Wall Scoring Method

Default transparent v0 formula:

```text
wall_score = oi_share * expiry_weight * freshness_factor
```

- `oi_share`: strike OI divided by total OI for the selected expiry or configured expiry window.
- `expiry_weight`: higher for nearer expiries; bounded and visible in each report row.
- `freshness_factor`: neutral when optional confirmation is missing; increased when OI change or volume confirms recent activity; reduced when data is stale or contradictory.
- `wall_type`: put wall, call wall, mixed wall, or unknown based on option type and put/call split availability.

The report must show component values and notes for each wall.

## Zone Classification Method

The classifier creates research zones, not buy/sell signals:

- **support candidate**: significant put wall or mixed wall below/near spot with supportive score and non-stale data.
- **resistance candidate**: significant call wall or mixed wall above/near spot with supportive score and non-stale data.
- **pin-risk zone**: strong near-expiry wall near current spot or expected-range center.
- **squeeze-risk zone**: strong wall cluster plus freshness evidence indicating active positioning.
- **breakout candidate**: expected range boundary or wall breach area where wall support/resistance is thin or stale.
- **reversal candidate**: expected range edge with strong opposing wall evidence.
- **no-trade zone**: missing, stale, contradictory, low-OI, or unreliable evidence.

Each classification must include notes and limitation text, especially when IV, basis, put/call split, or freshness evidence is unavailable.

## API Design

Endpoints are additive under `/api/v1/xau/vol-oi`:

- `POST /api/v1/xau/vol-oi/reports`
- `GET /api/v1/xau/vol-oi/reports`
- `GET /api/v1/xau/vol-oi/reports/{report_id}`
- `GET /api/v1/xau/vol-oi/reports/{report_id}/walls`
- `GET /api/v1/xau/vol-oi/reports/{report_id}/zones`

Responses include structured errors for missing columns, unsafe paths, missing basis inputs, unavailable IV, and missing reports. All responses include research-only limitations where report interpretation could be confused with trading advice.

## Dashboard Design

Add `/xau-vol-oi` as a focused report inspection page:

- Report selector and report status.
- Selected session/date.
- Spot/proxy reference and futures reference.
- Futures-to-spot basis snapshot.
- Expected range card with source label and unavailable state.
- Basis-adjusted OI wall table.
- Zone classification table.
- Missing-data warnings and source limitation notes.
- Research-only disclaimer and no-trade warnings.

No broader dashboard redesign is planned.

## Test Strategy

- Unit tests:
  - Basis computation, manual basis handling, and strike-to-spot mapping.
  - Expected move, 1SD range, optional 2SD range, and unavailable-IV behavior.
  - Local CSV/Parquet validation for required/optional columns and parse failures.
  - OI share, expiry weight, freshness factor, wall score, and wall type classification.
  - Zone classification and explanation notes.
- Integration tests:
  - Synthetic local gold options OI dataset with spot/futures references produces report metadata, wall rows, zone rows, JSON/Markdown artifacts, and no tracked generated artifacts.
  - Missing OI/IV/basis inputs produce clear missing-data instructions.
- Contract tests:
  - Report run/list/detail/walls/zones endpoints.
  - Structured error responses for missing columns, unsafe paths, missing basis inputs, and unknown reports.
- Regression checks:
  - Existing backend tests continue passing.
  - Frontend build passes.
  - Artifact guard passes.
  - Forbidden-scope scan confirms no execution, private keys, broker, infrastructure, or ML additions.

## Implementation Phases

1. **Foundation**: Add models, `backend/src/xau/` package, route skeleton, report store skeleton, frontend route skeleton, and API/types placeholders.
2. **Local Import MVP**: Validate CSV/Parquet options OI rows and missing-data instructions.
3. **Basis And Volatility**: Implement basis snapshots, spot-equivalent mapping, IV expected move, 1SD range, and unavailable-range handling.
4. **Wall Scoring And Zones**: Implement OI share, expiry/freshness weighting, wall score, wall type, zone classification, and explanation notes.
5. **Report Persistence And API**: Persist metadata, walls, zones, JSON/Markdown, and expose report/list/detail/walls/zones endpoints.
6. **Dashboard Inspection**: Add `/xau-vol-oi` tables, selector, basis/range cards, warnings, and disclaimers.
7. **Final Validation**: Run backend tests, frontend build, artifact guard, API smoke, dashboard smoke, and forbidden-scope review.

## Constitution Check: Post-Design

- **Research-first architecture**: PASS. Outputs are zones and diagnostics only.
- **Language split**: PASS. Python research backend and TypeScript dashboard only.
- **Frontend stack**: PASS. Focused Next.js dashboard page.
- **Backend stack**: PASS. Existing FastAPI/Pydantic patterns.
- **Data processing**: PASS. Polars-compatible CSV/Parquet normalization.
- **Storage v0**: PASS. Local `data/reports`; no generated artifacts committed.
- **Storage v1+ avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event architecture**: PASS. No Kafka, Redpanda, NATS, or Kubernetes.
- **Data-source principle**: PASS. Yahoo proxies are explicitly OHLCV-only.
- **Reliability/live-trading principles**: PASS. No paper, shadow, live, broker, wallet, private key, or order-execution behavior.

## Complexity Tracking

No constitution violations are introduced.
