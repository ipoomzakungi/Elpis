# Research: XAU Zone Reaction and Risk Planner

**Date**: 2026-05-12  
**Feature**: 010-xau-zone-reaction-and-risk-planner

## Decision: Additive Reaction Package

**Decision**: Implement a new `backend/src/xau_reaction/` package with pure context modules, classifier, bounded risk planner, orchestration, and report persistence.

**Rationale**: Feature 006 already owns local XAU options import, basis adjustment, expected ranges, wall scoring, zone classification, and XAU report storage. The 010 feature is a dependent decision layer and should not modify raw wall construction.

**Alternatives considered**:

- Add reaction logic directly to `backend/src/xau/zones.py`: rejected because it would mix wall/zone generation with higher-level reaction confirmation logic.
- Create a generalized strategy module: rejected because the feature is XAU-specific and research-only.

## Decision: Reuse Feature 006 Reports

**Decision**: `XauReactionReportRequest` references a saved feature 006 XAU Vol-OI report id. Orchestration loads report metadata, expected range, wall rows, and zone rows through `XauReportStore`.

**Rationale**: This keeps the workflow reproducible and avoids re-importing local options OI files or duplicating basis/wall calculations.

**Alternatives considered**:

- Accept raw wall rows directly in the request: useful for testing but weaker for auditability; synthetic tests may still construct models directly.
- Re-run feature 006 from the reaction request: rejected because it expands scope and blurs feature boundaries.

## Decision: Transcript Source Handling

**Decision**: Treat `xau_vol_oi_transcript_distillation.md` as a source document for implementation when available, and use the user-provided distilled rules as the planning source in this session.

**Rationale**: The file was requested but could not be found under `C:\Users\punnawat_s\Guthib` during planning. The prompt provided the operational rules needed for the plan: OI walls are research zones, not signals; reaction candidates require basis, expected range, VRP, freshness, open behavior, candle confirmation, and bounded risk planning.

**Alternatives considered**:

- Block planning until the file is present: rejected because the prompt contained enough requirements to produce a complete plan.
- Ignore the missing file entirely: rejected because implementation should still read it if it is added before coding.

## Decision: Freshness State Precedence

**Decision**: Freshness classification uses this precedence: `UNKNOWN`, `PRIOR_DAY`, `STALE`, `THIN`, `VALID`.

**Rationale**: Missing or unparsable timestamp/count inputs cannot be trusted. Prior-day data must never be treated as fresh intraday flow. Stale data is a stronger blocker than low but current participation. Thin but current data may reduce confidence or become no-trade depending on thresholds.

**Alternatives considered**:

- Score freshness numerically only: rejected because the spec requires explicit labels.
- Treat thin before stale: rejected because old data with enough contracts is still stale.

## Decision: Volatility Context States

**Decision**: `vol_regime.py` computes or accepts realized volatility, calculates `vrp = implied_volatility - realized_volatility`, and emits VRP regime, IV edge state, and RV extension state.

**Rationale**: The reaction classifier needs to distinguish ordinary realized extension from options-market stress. IV edge breaks are stress/squeeze warnings, while RV-only extension is treated as chart stretch without the same options stress implication.

**Alternatives considered**:

- Only use feature 006 `XauExpectedRange`: rejected because the feature explicitly requires IV/RV/VRP comparison.
- Add model training for regimes: rejected by v0 forbidden scope and unnecessary for deterministic classification.

## Decision: Opening Price Regime

**Decision**: `open_regime.py` emits open side, distance from open, open flip state, and open support/resistance context. Full open flip requires acceptance evidence, not just crossing the open.

**Rationale**: The session open is a tactical anchor, but a single cross is insufficient for a regime flip. This keeps open behavior as context instead of an automatic signal.

**Alternatives considered**:

- Classify only above/below open: rejected because the spec requires flip and support/resistance context.
- Treat any cross as a flip: rejected because it conflicts with the acceptance requirement.

## Decision: Candle Acceptance And Rejection

**Decision**: `acceptance.py` classifies wick rejection, failed breakout, accepted beyond wall, and confirmed breakout from wall level, high, low, close, next-bar open, and buffer.

**Rationale**: The transcript-derived rule is that a wick through a wall is not a breakout. Close beyond the wall plus next-bar hold is the deterministic acceptance gate.

**Alternatives considered**:

- Use close-only acceptance: rejected because it ignores next-bar hold.
- Use high/low penetration as breakout: rejected because it confuses wick probes with acceptance.

## Decision: Reaction Label Priority

**Decision**: Use a fixed classification priority: hard no-trade gates, pin magnet, squeeze risk, vacuum to next wall, breakout candidate, reversal candidate, fallback no-trade.

**Rationale**: Multiple conditions can be true at once. A fixed order makes the classifier deterministic and testable. Hard data-quality gates always win over attractive candidate evidence.

**Alternatives considered**:

- Highest score wins across labels: rejected because it can hide hard data-quality failures.
- Return multiple labels for one row: rejected because the spec requires a reaction label per row.

## Decision: Bounded Risk Plans

**Decision**: `risk_plan.py` creates research-only annotations for non-`NO_TRADE` reactions and emits no entry plan for `NO_TRADE`.

**Rationale**: The risk plan must cap total risk, cap recovery legs, include cancel conditions, and avoid martingale or unlimited averaging. It must not imply live execution readiness.

**Alternatives considered**:

- Generate plans for all labels including no-trade: rejected because it would undermine no-trade gates.
- Add order-like fields: rejected because execution scope is forbidden.

## Decision: Report Persistence

**Decision**: Persist reaction reports under `data/reports/xau_reaction/{reaction_report_id}/` with metadata JSON, report JSON, report Markdown, reactions Parquet, and risk-plan Parquet when rows exist.

**Rationale**: This mirrors feature 006 local report patterns while keeping reaction artifacts separate and ignored by git.

**Alternatives considered**:

- Persist inside `data/reports/xau_vol_oi/`: rejected because reaction reports are derived artifacts with their own lifecycle.
- Use a database: rejected because v0 uses local DuckDB/Parquet/files and PostgreSQL is forbidden.

## Decision: Dashboard Surface

**Decision**: Extend `/xau-vol-oi` with reaction-report panels/tables instead of adding a separate route for the first version.

**Rationale**: Researchers need to inspect source walls/zones and derived reactions together. A single XAU page reduces navigation and keeps the dependency visible.

**Alternatives considered**:

- Add `/xau-reaction`: acceptable later if the page becomes too dense, but not needed for the initial vertical slice.

## Decision: Testing Boundary

**Decision**: Automated tests use synthetic feature 006 XAU reports and synthetic reaction contexts only. They do not require real downloads, live feeds, private provider data, or external market access.

**Rationale**: Deterministic behavior and no-trade gates can be fully validated with fixtures, and CI should not depend on external data availability.

**Alternatives considered**:

- Test against real XAU data: rejected for reproducibility and because the project is in v0 research mode.
