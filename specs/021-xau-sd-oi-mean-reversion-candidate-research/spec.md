# Feature Specification: XAU SD OI Mean Reversion Candidate Research

**Feature Branch**: `021-xau-sd-oi-mean-reversion-candidate-research`
**Created**: 2026-06-07
**Status**: Draft
**Input**: User description: "Turn the course 2SD-3SD mean-reversion hypothesis into timestamp-safe XAU research candidates using the existing daily structural map, OI walls, IV/flow/price-confirmation context, and explicit no-signal guardrails."

## User Scenarios & Testing

### User Story 1 - Classify One Timestamp Candidate (Priority: P1)

As an XAU researcher, I want a single timestamp-safe candidate payload derived from an existing daily structural map so that price stretch, expected-range bands, nearest wall context, and no-signal reasons can be reviewed without producing a trading signal.

**Why this priority**: Feature 018-020A created auditable map artifacts. Feature 021 is useful only if it consumes that map context and keeps the result explicitly research-only.

**Independent Test**: Build synthetic daily maps and classify one observed traded price with supplied confirmation, IV, flow, and wall states.

**Acceptance Scenarios**:

1. Given price is between upper 2SD and upper 3SD with rejection confirmation and no breakout context, when a candidate is built, then the side is `short_reversion_candidate`, target 1 is upper 1SD, the stop reference is upper 3.5SD, and `signal_allowed` remains false.
2. Given price is between lower 3SD and lower 2SD with rejection confirmation and no breakout context, when a candidate is built, then the side is `long_reversion_candidate`, target 1 is lower 1SD, the stop reference is lower 3.5SD, and `signal_allowed` remains false.
3. Given price is inside the +/-2SD range, when a candidate is built, then the side remains `no_trade` with a monitor reason and `signal_allowed` remains false.

### User Story 2 - Preserve Missing And Breakout Context (Priority: P2)

As an XAU researcher, I want missing basis/range/price/open context and breakout-risk context to override candidate creation so that missing data or strong continuation evidence is not misread as a mean-reversion setup.

**Why this priority**: The course hypothesis requires confirmation and context. The project must not hard-code 2SD as an entry rule or treat high OI as direction.

**Independent Test**: Run focused missing-context, breakout-risk, and null-preservation cases without a live feed.

**Acceptance Scenarios**:

1. Given basis is missing, when a candidate is built, then the side is `no_trade`, `signal_allowed` is false, and the reasons include missing basis.
2. Given price is in an upper 2SD-3SD stretch with IV expansion and flow-through-wall acceptance, when a candidate is built, then the side is `breakout_risk`.
3. Given wall OI change or volume is null, when nearest-wall context is copied, then null remains null and is not converted to zero.

### User Story 3 - Document Research-Only Candidate Contract (Priority: P3)

As an XAU researcher, I want the candidate schema, contract, and quickstart documented so that future backtest/outcome features can attach evidence without mutating the original structural map.

**Why this priority**: Later validation needs stable candidate fields and clear limitations before any outcome labeling or backtest exists.

**Independent Test**: Review the Speckit artifacts and candidate models for forbidden signal, execution, PnL, alert, broker, or live-readiness behavior.

## Edge Cases

- Basis, expected range, traded price, or session open is missing.
- Expected range exists but one or more required 1SD/2SD/3SD fields are null.
- Native 3.5SD bands are absent and must be derived from the 1SD distance with a limitation.
- Price is outside 3SD or 3.5SD.
- IV expansion, flow-through-wall, and candle acceptance indicate breakout risk.
- Confirmation state is unavailable or neutral.
- Nearest wall exists with null OI-change or volume fields.
- No mapped wall exists.
- Range label or per-strike IV exists without numeric SD bands.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST represent a research-only candidate set linked to a source `XauDailyStructuralMap`.
- **FR-002**: The system MUST represent candidate side values including `long_reversion_candidate`, `short_reversion_candidate`, `no_trade`, and `breakout_risk`.
- **FR-003**: The system MUST represent stretch zones including `upper_2sd_to_3sd`, `lower_2sd_to_3sd`, `outside_3sd`, `inside_normal_range`, and `unavailable`.
- **FR-004**: The system MUST keep `signal_allowed=false` and `research_only=true` for every candidate and candidate set.
- **FR-005**: Missing basis, expected range, traded price, or session open MUST produce `no_trade` with explicit reasons.
- **FR-006**: Upper 2SD-3SD rejection context without breakout confirmation MUST produce a short reversion research candidate with target 1 at upper 1SD and stop reference at upper 3.5SD.
- **FR-007**: Lower 2SD-3SD rejection context without breakout confirmation MUST produce a long reversion research candidate with target 1 at lower 1SD and stop reference at lower 3.5SD.
- **FR-008**: Price beyond 3SD or IV expansion plus flow-through-wall plus acceptance MUST produce `breakout_risk`.
- **FR-009**: Price inside +/-2SD MUST produce `no_trade` with a monitor reason.
- **FR-010**: The classifier MUST NOT treat 2SD as an automatic entry rule.
- **FR-011**: The classifier MUST NOT treat high OI as direction.
- **FR-012**: Null wall OI-change and volume values MUST remain null and MUST NOT be converted to zero.
- **FR-013**: If native 3.5SD bands are unavailable, the classifier MUST derive 3.5SD from the center of the 1SD band plus/minus 3.5 one-SD distances and include a source limitation.
- **FR-014**: The feature MUST NOT implement buy/sell live signals, alerts, broker execution, auto trading, paper trading, real position sizing, order routing, PnL, ML training, or backtests.

### Key Entities

- **XAU SD/OI Candidate Set**: One research-only output for a map and timestamp.
- **XAU SD/OI Candidate**: The classified state for the observed price and context.
- **Candidate Reason**: Structured explanation for no-trade, candidate, breakout-risk, or missing-context decisions.
- **Candidate Target**: Research reference levels such as 1SD, session open, or range midpoint.
- **Candidate Invalidation**: Research stop-reference context such as derived 3.5SD.

## Success Criteria

- **SC-001**: Missing-basis tests produce `no_trade`, `signal_allowed=false`, and a basis-missing reason.
- **SC-002**: Upper 2SD-3SD rejection tests produce `short_reversion_candidate`, target 1 upper 1SD, stop upper 3.5SD, and `signal_allowed=false`.
- **SC-003**: Lower 2SD-3SD rejection tests produce `long_reversion_candidate`, target 1 lower 1SD, stop lower 3.5SD, and `signal_allowed=false`.
- **SC-004**: Breakout context tests produce `breakout_risk`.
- **SC-005**: Inside +/-2SD tests produce `no_trade` or monitor state with `signal_allowed=false`.
- **SC-006**: Null OI-change and volume tests preserve null values.
- **SC-007**: Derived 3.5SD tests compute from 1SD distance and expose the limitation.
- **SC-008**: Review of code and docs finds zero execution, alert, broker, order, PnL, profitability, predictive-proof, safety, or live-readiness claims.

## Assumptions

- Existing Feature 018-020A structural maps are the source context.
- Price confirmation, IV state, flow state, and OI wall state are supplied by the caller as research context for this feature.
- Candidate output is an observation label for later validation, not a signal.
- Later outcome/backtest features may consume candidate sets, but this feature does not compute outcomes.
