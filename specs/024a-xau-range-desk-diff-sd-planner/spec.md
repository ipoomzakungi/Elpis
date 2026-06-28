# Feature Specification: XAU Range Desk / Diff-SD Planner

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`
**Created**: 2026-06-07
**Status**: Draft
**Input**: User requested the next practical layer: map CME futures-side SD and OI levels to the traded XAU/GO chart using future-vs-spot diff, while staying research-only.

## User Scenarios & Testing

### User Story 1 - Map Futures Levels To Traded Levels (Priority: P1)

As an XAU researcher, I want to enter a GC futures reference price, a traded XAU/GO reference price, and future-side CME SD levels so that I can review the equivalent traded-chart levels without hand-calculating the diff.

**Why this priority**: The practical planning problem is translating a CME level such as `4520` to a traded chart level such as `4490` when the future-vs-traded diff is `30`.

**Independent Test**: Given future `4500`, traded `4470`, and futures level `4520`, the mapped traded level is `4490` and the response remains `signal_allowed=false`.

**Acceptance Scenarios**:

1. Given valid future and traded reference prices, when a futures level is supplied, then the system returns `diff_points`, `traded_offset`, and the mapped traded level.
2. Given the mapped level output, when the response is inspected, then it is marked research-only and cannot enable trading signals.

### User Story 2 - Build Planning Zones And Targets (Priority: P2)

As an XAU researcher, I want the planner to show no-trade, 2SD-3SD stretch, and planning-only target/reference levels so that chart review is consistent with the course doctrine.

**Why this priority**: The doctrine says inside 1SD is monitor/no-trade context, while 2SD-3SD is a research candidate area that still needs reaction, IV, flow, and outcome evidence.

**Independent Test**: Given full 1SD/2SD/3SD levels and OI walls, the planner returns no-trade zone, upper/lower stretch zones, mapped OI walls, and target plans without entries or PnL.

**Acceptance Scenarios**:

1. Given lower/upper 1SD, when a plan is built, then it includes a no-trade zone inside 1SD.
2. Given lower/upper 2SD and 3SD, when a plan is built, then it includes upper and lower 2SD-3SD stretch zones.
3. Given OI walls, when a plan is built, then it maps the walls to traded levels and may use nearest inner walls as planning-only target references.

### User Story 3 - Preserve Missing Context (Priority: P3)

As an XAU researcher, I want incomplete SD or wall inputs to remain explicit so that no fake planning table is created from missing data.

**Why this priority**: Missing context must produce partial research output, not fabricated SD bands or trade instructions.

**Independent Test**: Given only one SD level, the response is partial, lists missing SD inputs, and keeps `signal_allowed=false`.

**Acceptance Scenarios**:

1. Given incomplete SD inputs, when a plan is built, then readiness is partial and missing inputs are listed.
2. Given no OI wall inputs, when a plan is built, then OI wall targets are marked unavailable through limitations.

## Edge Cases

- Future reference and traded reference are supplied at different timestamps.
- SD levels are incomplete.
- OI wall rows are absent.
- Session open is absent.
- Inputs are manual research values rather than source-backed weekday captures.

## Requirements

- **FR-001**: The system MUST compute `diff_points = future_reference_price - traded_reference_price`.
- **FR-002**: The system MUST compute `traded_offset = traded_reference_price - future_reference_price`.
- **FR-003**: The system MUST map every supplied futures level using `mapped_traded_level = futures_level + traded_offset`.
- **FR-004**: The system MUST return mapped SD levels and mapped OI wall levels.
- **FR-005**: The system MUST identify no-trade context inside 1SD when lower and upper 1SD are present.
- **FR-006**: The system MUST identify upper and lower 2SD-3SD research stretch zones when required bands are present.
- **FR-007**: The system MUST return planning-only target and invalidation references without entries, PnL, alerts, or orders.
- **FR-008**: The system MUST preserve missing SD, session-open, and OI wall context as explicit limitations or missing inputs.
- **FR-009**: Every response MUST keep `research_only=true` and `signal_allowed=false`.
- **FR-010**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, order routing, PnL, position sizing, automatic trade placement, buy/sell instructions, ML training, or profitability claims.

## Key Entities

- **Range Desk Plan Request**: Manual or source-supplied future/traded reference prices, future-side SD levels, optional session open, and optional OI walls.
- **Basis Snapshot**: Diff and traded offset used for mapping.
- **Mapped Level**: One futures level with traded-chart equivalent and distance from traded reference.
- **Mapped OI Wall**: One OI wall mapped to traded-chart level.
- **Planning Zone**: No-trade or stretch-zone context.
- **Target Plan**: Planning-only references for later research review, not an entry or signal.

## Success Criteria

- **SC-001**: Future `4500`, traded `4470`, and futures level `4520` maps to traded level `4490`.
- **SC-002**: Full SD inputs produce no-trade and 2SD-3SD planning zones.
- **SC-003**: OI wall inputs are mapped to traded levels with OI, OI change, and volume preserved when supplied.
- **SC-004**: Missing SD inputs produce partial readiness and explicit missing input names.
- **SC-005**: Code and docs review finds no PnL, execution, alert, order, broker, position-sizing, live-readiness, predictive-proof, or profitability behavior.

## Assumptions

- Inputs are local/manual or source-supplied research values for this slice.
- Automatic GC/XAU price providers are a later feature.
- Capability audit, automatic reaction state, IV state, flow state, and statistics remain separate follow-up features.
