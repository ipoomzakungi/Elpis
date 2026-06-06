# Research: XAU Real Structural Map From Bundle

**Date**: 2026-06-04
**Feature**: 020a-xau-real-structural-map-from-bundle

## Decisions

### Decision: Reuse Feature 018 and Feature 019 Instead Of A New Map Writer

The adapter will normalize local bundle artifacts into `build_daily_structural_map(...)` inputs and persist through `XauDailyStructuralMapReportStore`.

**Rationale**: Feature 018 owns readiness and no-signal semantics. Feature 019 owns artifact paths, metadata, markdown, and round-trip persistence.

**Alternatives considered**:

- Writing a separate bundle report store: rejected because it would duplicate path safety and persistence contracts.
- Adding an API route: rejected for this slice because the request is a local service/helper with tests.

### Decision: Preserve Missing Basis

Manual basis wins when supplied. If manual basis is absent, basis is computed only when both traded and GC reference prices are provided. Otherwise the existing unavailable-basis state is passed through.

**Rationale**: CME futures strikes cannot be mapped to XAU spot levels without basis context. Fabricating basis would make walls appear actionable when they are not.

### Decision: Preserve Expected-Range Source Rules

The adapter uses an existing Feature 017 snapshot when present. If only `range_label` exists, the adapter creates an unavailable snapshot with the Feature 017 range-label limitation. It does not convert labels or per-strike IV into numeric SD bands.

**Rationale**: Feature 017 explicitly forbids numeric promotion from labels and per-strike IV.

### Decision: Treat Local Bundle Data As Independently Verifiable

Every adapter-generated map includes a limitation that local imported options data must be independently verified.

**Rationale**: Local bundles may be manually created, partial, stale, or copied from previous research artifacts.

## Deferred Work

- Forward outcome labels.
- Reaction classifier.
- Dashboard.
- Candidate signal engine.
- 2SD entry research.
- 3.5SD stop research.
- PnL or backtest.
