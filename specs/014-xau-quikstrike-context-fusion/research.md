# Research: XAU QuikStrike Context Fusion

**Date**: 2026-05-13  
**Feature**: 014-xau-quikstrike-context-fusion

## Decision: Fuse Saved Reports, Not Browser Sessions

**Decision**: The fusion layer loads saved feature 012 Vol2Vol reports and saved feature 013 Matrix reports through their local report stores.

**Rationale**: The source extractors already enforce local-only boundaries and sanitize Highcharts/table data. Fusion should operate on trusted local report artifacts and should not touch authenticated browser sessions, endpoint payloads, cookies, headers, screenshots, HAR files, or viewstate values.

**Alternatives considered**:

- Re-run browser extraction during fusion: rejected because it mixes extraction concerns with context fusion and risks session handling.
- Reparse generated raw browser snapshots: rejected because existing report stores already expose normalized rows and conversion outputs.
- Create a new QuikStrike data provider: rejected because the feature is local-only research composition, not a general data-source abstraction.

## Decision: Use Deterministic Join Keys

**Decision**: Match rows by normalized strike, expiration key, option type, and value type.

**Rationale**: These fields are the stable research identity across Vol2Vol chart rows and Matrix table rows. The Matrix report may provide broader expiry coverage, while Vol2Vol may provide richer context for the selected/current expiry. The join must be deterministic and explain unmatched rows.

**Alternatives considered**:

- Match by row order: rejected because Vol2Vol and Matrix reports have different shapes and coverage.
- Match by strike only: rejected because cross-expiry Matrix data would merge unrelated expirations.
- Match by source row id: rejected because source row ids are report-specific and do not express cross-source equivalence.

## Decision: Preserve Both Values On Overlap

**Decision**: When both sources provide comparable values for the same match key, keep both values and mark agreement, disagreement, or unavailable comparison.

**Rationale**: Source disagreements are research evidence. Silent overwrite would hide data-quality problems and make downstream wall/reaction outputs difficult to audit.

**Alternatives considered**:

- Prefer Matrix values globally: rejected because Vol2Vol can contain fresher current-expiry context.
- Prefer Vol2Vol values globally: rejected because Matrix provides cross-expiry structure.
- Average overlapping values: rejected because counts and source definitions may differ.

## Decision: Matrix Provides Broad Structure, Vol2Vol Provides Current-Expiry Context

**Decision**: Matrix data is the primary source for cross-expiry open interest, OI change, and volume structure. Vol2Vol is the primary source for selected/current-expiry volume, OI, churn, range, and volatility-style context where present.

**Rationale**: This follows the actual source shapes discovered in operational runs. Matrix is table-based and cross-expiry; Vol2Vol is chart-based and richer around the active view/expiry.

**Alternatives considered**:

- Treat both sources as identical replacements: rejected because the fields are related but not interchangeable.
- Use only Matrix because it already converted to XAU input: rejected because the latest reaction output lacked context that Vol2Vol may help explain.

## Decision: Basis Is Optional And Explicit

**Decision**: Compute basis only when both XAUUSD spot reference and GC futures reference are supplied. Use `basis_points = gc_futures_reference - xauusd_spot_reference` and `spot_equivalent_level = futures_strike - basis_points`.

**Rationale**: QuikStrike levels are futures/options context. Spot-equivalent levels are useful only when the basis input is explicit and auditable.

**Alternatives considered**:

- Infer basis from Yahoo or other proxies: rejected because it would fabricate a source not provided by the user.
- Require basis for all fusion reports: rejected because futures-strike research is still useful, and missing basis should be visible rather than fatal.

## Decision: Missing Context Becomes Checklist Items

**Decision**: Basis, IV/range, realized volatility, session open, candle acceptance, source quality, and source agreement are represented as structured context statuses and checklist items.

**Rationale**: The recent operational run produced all `NO_TRADE` reactions because confirmation context was missing. The fusion feature should explain what is missing and let the existing reaction engine remain conservative.

**Alternatives considered**:

- Promote candidates despite missing context: rejected by research-only reliability rules.
- Hide missing context in warnings only: rejected because dashboard/API users need structured blockers.

## Decision: Optional Downstream Orchestration Reuses Existing XAU Workflows

**Decision**: Fusion may optionally create an XAU Vol-OI report and an XAU reaction report by calling existing feature 006 and feature 010 orchestration.

**Rationale**: This avoids duplicate wall scoring and duplicate reaction/risk logic while letting users validate the complete research chain from fused QuikStrike context.

**Alternatives considered**:

- Build fused wall scoring inside this package: rejected because it duplicates feature 006.
- Build a new reaction classifier inside this package: rejected because feature 010 already implements deterministic reaction logic.

## Decision: API And Dashboard Are Local Inspection Surfaces

**Decision**: Add local endpoints and a compact `/xau-vol-oi` panel for saved fusion reports, source ids, coverage, source agreement, missing context, generated paths, and linked downstream report ids.

**Rationale**: Fusion needs operational visibility, but it should remain a local research report surface and not a live data collector or execution surface.

**Alternatives considered**:

- No API/dashboard: rejected because feature success criteria require inspection and linked downstream visibility.
- Add browser extraction controls: rejected because features 012 and 013 own extraction and privacy boundaries.

## Decision: Generated Artifacts Stay Local And Ignored

**Decision**: Fusion metadata, rows, conversion outputs, JSON reports, and Markdown reports are written under ignored `data/reports/xau_quikstrike_fusion/` and existing ignored local data/report roots.

**Rationale**: Fusion outputs can contain proprietary local research data and should not be tracked. This matches features 012 and 013.

**Alternatives considered**:

- Commit sample real fusion reports: rejected because generated research artifacts and QuikStrike-derived rows must remain local.
- Persist to a database: rejected because v0 storage is local files and no database server is needed.
