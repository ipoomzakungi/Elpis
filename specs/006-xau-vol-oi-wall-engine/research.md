# Research: XAU Vol-OI Wall Engine

**Date**: 2026-05-01  
**Feature**: 006-xau-vol-oi-wall-engine

## Decision 1: Use local imported options datasets for v0

**Decision**: Feature 006 will accept local CSV/Parquet gold options OI datasets for CME/COMEX or QuikStrike-style research input.

**Rationale**: The project has no approved institutional gold derivatives feed in v0, and the user explicitly allowed local imports. Local files let the wall engine validate schema and scoring logic without adding private keys, broker integrations, or new infrastructure.

**Alternatives considered**:

- Direct CME/QuikStrike integration: rejected for v0 because access, licensing, and authentication are outside the current research-only scope.
- Yahoo Finance for options OI: rejected because Yahoo GC=F/GLD are OHLCV proxies only and must not be treated as gold options OI or IV sources.

## Decision 2: Keep Yahoo Finance GC=F and GLD as OHLCV proxies only

**Decision**: GC=F and GLD may provide contextual OHLCV reference data, but every report must label them as proxies only and not as sources of gold options OI, futures OI, IV, or XAUUSD spot execution data.

**Rationale**: The user explicitly called out this limitation, and feature 005 already established source-aware research reporting. Keeping the boundary explicit prevents misleading wall interpretation.

**Alternatives considered**:

- Infer OI or IV from proxy OHLCV: rejected because it would fabricate unavailable derivatives data.
- Block all gold proxy usage: rejected because GC=F/GLD are still useful as clearly labeled OHLCV context.

## Decision 3: Basis adjustment is mandatory for spot-equivalent wall levels

**Decision**: Every spot-equivalent wall level must use:

```text
spot_equivalent_level = futures_strike - futures_spot_basis
futures_spot_basis = gold_futures_price - xauusd_spot_or_proxy_price
```

Manual basis is allowed only when labeled as manual.

**Rationale**: Gold options strikes are futures-based while the dashboard analysis target is XAUUSD spot or a proxy. Persisting the basis and source references keeps the mapping auditable.

**Alternatives considered**:

- Display raw futures strikes only: rejected because it does not satisfy spot-equivalent XAU analysis.
- Assume zero basis by default: rejected because that silently hides an important mapping assumption.

## Decision 4: Expected ranges are source-labeled and optional

**Decision**: The engine computes IV-based expected move and 1SD range only when IV and days-to-expiry are available. It may compute 2SD stress ranges when configured and required inputs exist. Realized-volatility and manually imported ranges are separate source labels.

**Rationale**: The spec requires the system to avoid inventing IV-based ranges. Source labels let researchers distinguish IV, realized volatility, and manual range inputs.

**Alternatives considered**:

- Always compute range from realized volatility: rejected because it would not be an IV-based expected move.
- Fill missing IV from a default value: rejected because it would fabricate source data.

## Decision 5: Wall score remains simple and transparent

**Decision**: Use the v0 formula:

```text
wall_score = oi_share * expiry_weight * freshness_factor
```

The report must persist each component.

**Rationale**: A transparent formula is easier to audit and test than a black-box score. It matches the user requirement and avoids ML/model-training scope.

**Alternatives considered**:

- Weighted model calibrated from historical outcomes: rejected because it would imply training and broader validation not requested for v0.
- Rank-only walls with no numeric score: rejected because the dashboard/report needs wall score and components.

## Decision 6: Zone labels are research annotations, not signals

**Decision**: Zone classification produces annotations such as support candidate, resistance candidate, pin-risk zone, squeeze-risk zone, breakout candidate, reversal candidate, and no-trade zone. Reports must state that these are research zones only.

**Rationale**: The spec explicitly says 1SD and OI are not standalone buy/sell signals. Zone labels help inspection while preserving research-only boundaries.

**Alternatives considered**:

- Emit buy/sell or trade-ready actions: rejected as forbidden execution/live-readiness behavior.
- Omit zone labels and show walls only: rejected because the feature goal is to classify research zones.

## Decision 7: Persist XAU reports using existing report conventions

**Decision**: Store XAU report metadata, wall tables, zone tables, and JSON/Markdown reports under existing `data/reports/{report_id}/` patterns and keep generated artifacts ignored.

**Rationale**: Features 003-005 already established local report persistence and artifact guard expectations. Reuse avoids new storage systems.

**Alternatives considered**:

- Add a server database: rejected because PostgreSQL/ClickHouse are forbidden in v0.
- Store only in memory: rejected because reports must be listable/readable after generation.
