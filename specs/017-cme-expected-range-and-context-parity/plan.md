# Implementation Plan: CME Expected Range And Context Parity

**Branch**: `017-cme-expected-range-and-context-parity` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/017-cme-expected-range-and-context-parity/spec.md`

## Summary

Add a research-only CME expected-range and context parity slice that makes the current XAU pipeline daily-structural-map ready without implementing trading signals. The implementation adds a point-in-time expected-range snapshot model, distinguishes CME-native numeric SD bands from IV-derived fallback bands, blocks range-label-only numeric promotion, carries the snapshot optionally through fusion and XAU Vol-OI report models, and updates the field inventory to recognize the new parity context.

Manual CME page exploration remains a documented follow-up unless an authenticated local page is explicitly available. This feature stores only sanitized visible values or local structured artifacts and never stores session, credential, endpoint replay, broker, wallet, or execution material.

## Technical Context

**Language/Version**: Python 3.11+ for backend models and research validation; Markdown for Speckit artifacts
**Primary Dependencies**: Existing Pydantic, Polars, pytest, FastAPI import surface; no new dependencies
**Storage**: Existing ignored local report paths only; no new database server
**Testing**: Focused pytest unit tests, inventory tests, backend import check
**Target Platform**: Local research workstation and CI-compatible backend test environment
**Project Type**: Existing FastAPI backend plus local research scripts
**Performance Goals**: Expected-range snapshot creation is constant-time for one expiry context and should not affect extractor runtime meaningfully
**Constraints**: Research-only, no live/paper/shadow trading, no private credentials, no endpoint replay, no null-to-zero coercion, no new v0-forbidden infrastructure, no claims of predictive power or tradability
**Scale/Scope**: One expected-range context object per source report/expiration snapshot; later daily structural map may aggregate these objects

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. Feature only improves data parity and research context.
- **Language Split**: PASS. Uses Python research/backend models only; no Rust execution component.
- **Frontend Stack**: PASS. No frontend stack change in this slice.
- **Backend Stack**: PASS. Extends existing Pydantic/FastAPI import surface.
- **Data Processing**: PASS. No timestamp-unsafe feature calculation; fractional DTE is preserved.
- **Storage v0**: PASS. Uses local ignored artifacts and schemas only.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, or streaming service.
- **Data-Source Principle**: PASS. Treats CME/QuikStrike context as modular source metadata.
- **TradingView Principle**: PASS. No TradingView dependency.
- **Reliability Principle**: PASS. Missing bands, missing basis, and range-label-only context remain limited or unavailable.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, private-key, order, or position-management behavior.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/017-cme-expected-range-and-context-parity/
|-- spec.md
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- expected-range-snapshot.md
|-- checklists/
|   `-- requirements.md
`-- tasks.md
```

### Source Code (repository root)

```text
backend/
|-- src/
|   |-- models/
|   |   |-- xau.py                         # expected-range snapshot and report fields
|   |   `-- xau_quikstrike_fusion.py       # optional snapshot propagation field
|   `-- xau_quikstrike_fusion/
|       `-- expected_range.py              # native/fallback parity builder
`-- tests/
    `-- unit/
        `-- test_xau_expected_range_context_parity.py

research_xau_vol_oi/
|-- systematic_engine_field_inventory.py
`-- tests/
    `-- test_systematic_engine_field_inventory.py
```

**Structure Decision**: Use additive models and helper functions inside the existing XAU and fusion modules because this feature enriches source/report context and should not introduce a new strategy module or execution path.

## Phase 0 Research Decisions

See [research.md](./research.md).

## Phase 1 Design Decisions

See [data-model.md](./data-model.md), [contracts/expected-range-snapshot.md](./contracts/expected-range-snapshot.md), and [quickstart.md](./quickstart.md).

## Expected Range Strategy

- CME-native numeric 1SD/2SD/3SD and upper/lower bands are source-of-truth when present.
- IV-derived fallback is allowed only when reference futures price, report-level IV, and fractional DTE are present.
- `range_label` and per-strike `vol_settle` are context only and cannot create numeric SD bands by themselves.
- Fallback output must carry an explicit limitation and remain research-only.
- Basis and blank/null Matrix semantics remain independent guardrails and are not relaxed by expected-range availability.

## Manual CME Discovery Strategy

Manual browser work is limited to identifying visible field locations for ATM/report-level IV, expected move, numeric SD bands, delta ranges, DTE, expiration, futures reference price, source view, and capture timestamp. It must not store session cookies, headers, HAR files, screenshots, private URLs, credentials, endpoint replay payloads, or broker/execution fields.

## Test Strategy

- Unit tests for native numeric expected range.
- Unit tests for IV-derived fallback and limitations.
- Unit tests for range-label-only unavailable context.
- Unit tests for missing basis and blank Matrix cell preservation.
- Inventory tests proving expected-range snapshot fields close P0 field gaps.
- Backend import check.

## Post-Design Constitution Check

- **Research-First Architecture**: PASS. No strategy/backtest is promoted.
- **Language Split**: PASS. No Rust or execution component.
- **Frontend Stack**: PASS. No frontend change.
- **Backend Stack**: PASS. Existing Pydantic model patterns are used.
- **Data Processing**: PASS. Fractional DTE is preserved and nulls remain null.
- **Storage v0**: PASS. No new persistent database.
- **Storage v1+ Avoidance**: PASS. No PostgreSQL or ClickHouse.
- **Event Architecture v0**: PASS. No event infrastructure.
- **Data-Source Principle**: PASS. Source limitations are visible.
- **TradingView Principle**: PASS. No TradingView source-of-truth dependency.
- **Reliability Principle**: PASS. Missing basis and missing bands remain explicit blockers.
- **Live Trading Principle**: PASS. No execution behavior or live-readiness claim.

No constitution violations require complexity tracking.
