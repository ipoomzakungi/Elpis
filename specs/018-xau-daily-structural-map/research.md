# Research: XAU Daily Structural Map

**Date**: 2026-06-04
**Feature**: 018-xau-daily-structural-map

## Decisions

### Decision: Use Feature 017 Snapshot As Range Source

The map uses `XauExpectedRangeSnapshot` fields directly. CME-native numeric bands are preferred when available. IV-derived bands are allowed only when Feature 017 already labeled them as fallback. Unavailable range remains unavailable.

**Rationale**: Feature 017 already encoded the source hierarchy and limitations. Recomputing or relabeling ranges in Feature 018 would create drift.

### Decision: Basis Mapping Is Required For Traded-Chart Wall Levels

Spot-equivalent wall levels are computed only when `XauFusionBasisState.status` is available and `basis_points` exists.

**Rationale**: CME strikes are futures-based while the inspected chart may be XAUUSD or GO. Without basis, the map can show futures strikes but cannot safely place them on the traded chart.

### Decision: Session Open Is Optional But Lowers Readiness

Missing session open still allows a map to be built, but readiness becomes `partial_missing_session_open`.

**Rationale**: The map is useful for structural review without open context, but later acceptance/rejection research needs the session open.

### Decision: Signals Are Disabled By Schema And Builder

`signal_allowed` is always false and maps carry a map-only no-signal reason.

**Rationale**: Feature 018 is not a signal, alert, strategy, or backtest feature. Even full context is not permission to trade.

### Decision: Wall Optional Metrics Stay Null

The current `XauOiWall` model does not always carry OI change or volume. Feature 018 keeps those fields nullable instead of inventing zero values.

**Rationale**: Null preserves source uncertainty and keeps Matrix blank-cell semantics intact.

## Alternatives Considered

### Add A Strategy Classifier Now

Rejected. The prompt explicitly says Feature 018 is a map only. Candidate classification and backtesting belong to later features.

### Use Fixed $25 Ranges As Default

Rejected. Feature 017 provides CME-native and IV-derived range hierarchy. Fixed bands may be a debug fallback in future tooling, but not the production default for this feature.

### Store Generated Maps In This Slice

Rejected. The current task only needs schema, builder, and tests. Persistence can be added when a dashboard or journal flow requires it.
