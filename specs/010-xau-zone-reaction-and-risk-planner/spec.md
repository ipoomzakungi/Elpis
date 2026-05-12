# Feature Specification: XAU Zone Reaction and Risk Planner

**Feature Branch**: `010-xau-zone-reaction-and-risk-planner`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "Add an XAU zone reaction classifier and bounded risk planner."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify Zone Reactions From XAU Wall Evidence (Priority: P1)

A researcher can create a reaction report from an existing XAU Vol-OI wall analysis and receive deterministic reaction classifications that distinguish reversal candidates, breakout candidates, pin magnets, squeeze risks, vacuum moves, and no-trade states without converting walls into buy or sell signals.

**Why this priority**: The core value is the decision layer that prevents raw OI walls from being interpreted as standalone trade instructions.

**Independent Test**: Can be fully tested with synthetic XAU wall and zone scenarios that cover all six required reaction labels and verify the explanation, confidence, invalidation, target reference, and no-trade fields.

**Acceptance Scenarios**:

1. **Given** a high-score wall, fresh data, price stretched near an expected range edge, and a candle rejection at the wall, **When** the researcher creates a reaction report, **Then** the reaction is labeled `REVERSAL_CANDIDATE` with explanation notes, confidence, invalidation level, and target references.
2. **Given** price accepts beyond a wall, volatility stress is present, and the next wall is distant through a low-OI area, **When** the researcher creates a reaction report, **Then** the reaction is labeled as `BREAKOUT_CANDIDATE`, `SQUEEZE_RISK`, or `VACUUM_TO_NEXT_WALL` according to the dominant evidence.
3. **Given** stale, thin, prior-day, unknown-basis, or conflicting evidence, **When** the report is created, **Then** the reaction is labeled `NO_TRADE` and the no-trade reasons state which evidence blocked the candidate.

---

### User Story 2 - Gate Reactions With Freshness And Volatility Context (Priority: P2)

A researcher can see whether intraday options evidence is valid, thin, stale, prior-day, or unknown, and can compare implied volatility, realized volatility, and price location against IV/RV ranges before trusting a reaction candidate.

**Why this priority**: OI walls are only useful when the surrounding data quality and volatility context are visible; stale or thin intraday flow must not receive the same treatment as current evidence.

**Independent Test**: Can be tested by submitting synthetic freshness and IV/RV inputs, then verifying freshness status, VRP values, volatility regime labels, IV edge stress, RV extension state, and their effect on confidence or no-trade outcomes.

**Acceptance Scenarios**:

1. **Given** intraday options data older than the maximum allowed age, **When** a reaction report is generated, **Then** freshness is `STALE` and candidate confidence is reduced or converted to `NO_TRADE`.
2. **Given** total intraday contracts below the minimum threshold, **When** a reaction report is generated, **Then** freshness is `THIN` and the report explains that low participation weakens the reaction evidence.
3. **Given** implied volatility is much higher than realized volatility and price has not exceeded the IV edge, **When** volatility context is calculated, **Then** the report shows wide VRP and reduces confidence in simple mean-reversion interpretations.
4. **Given** price breaks beyond the IV expected range edge, **When** volatility context is calculated, **Then** the report marks IV edge stress as a squeeze warning rather than treating it as ordinary RV extension.

---

### User Story 3 - Use Session Open And Candle Reaction As Confirmation Evidence (Priority: P3)

A researcher can inspect the current price relationship to the session open and whether candles accepted beyond or rejected a wall before the system promotes any wall zone into a reaction candidate.

**Why this priority**: Session open behavior and candle acceptance help separate a wick through a wall from a meaningful acceptance or rejection event.

**Independent Test**: Can be tested with synthetic open, current price, initial move, and candle OHLC/next-open scenarios that verify open-side, open-distance, open-flip, support/resistance test, acceptance, rejection, failed breakout, and confirmed breakout outputs.

**Acceptance Scenarios**:

1. **Given** price initially moves above the open and later returns to the open without acceptance below it, **When** the opening price regime is evaluated, **Then** the report treats the open as a tactical boundary and does not assume a full open flip.
2. **Given** a candle wicks through a wall but closes back inside the wall buffer, **When** candle reaction is evaluated, **Then** the report marks wick rejection and does not mark confirmed breakout.
3. **Given** a candle closes beyond the wall and the next bar opens or holds beyond the wall buffer, **When** candle reaction is evaluated, **Then** the report marks accepted beyond wall and confirmed breakout.

---

### User Story 4 - Review Bounded Research Risk Plans (Priority: P4)

A researcher can review bounded risk-planning annotations for reaction candidates, including entry conditions, invalidation levels, stop buffers, target references, recovery limits, cancel conditions, and risk notes, while `NO_TRADE` reactions produce no entry plan.

**Why this priority**: Risk planning must remain bounded and explicit so research annotations do not imply live execution readiness, martingale behavior, or unlimited averaging.

**Independent Test**: Can be tested by creating reaction scenarios with configured maximum total risk, maximum recovery legs, and minimum reward/risk requirements, then verifying that plans are capped, cancel conditions are present, and no plan is emitted for `NO_TRADE`.

**Acceptance Scenarios**:

1. **Given** a valid reaction candidate and bounded risk inputs, **When** the risk planner runs, **Then** the output contains entry condition text, invalidation level, stop buffer, two target references where available, maximum recovery legs, cancel conditions, and research-only risk notes.
2. **Given** requested recovery behavior exceeds the configured maximum recovery legs or implies unlimited averaging, **When** the risk planner runs, **Then** the plan caps the recovery legs and records a risk note that unlimited averaging is not allowed.
3. **Given** a `NO_TRADE` reaction, **When** the risk planner runs, **Then** entry condition text, stop buffer, and target levels are omitted or marked unavailable, and the no-trade reasons remain visible.

---

### User Story 5 - Inspect Reaction Reports Through API And Dashboard (Priority: P5)

A researcher can create, list, open, and inspect XAU reaction reports through the research API and the `/xau-vol-oi` dashboard, including freshness, volatility, open-anchor, candle reaction, reaction labels, risk plans, no-trade reasons, and research-only disclaimers.

**Why this priority**: The classifier is useful only if researchers can audit report outputs and understand why each zone was or was not promoted to a candidate.

**Independent Test**: Can be fully tested by creating a synthetic reaction report, retrieving its sections, and opening the dashboard to confirm every required panel and table renders without any execution-signal wording.

**Acceptance Scenarios**:

1. **Given** a saved reaction report exists, **When** the researcher retrieves the report list and detail, **Then** the report metadata, reaction count, no-trade count, warnings, and limitations are visible.
2. **Given** a saved reaction report exists, **When** the researcher opens the reaction and risk-plan sections, **Then** the reaction table and bounded risk planner table include the same report id and traceable zone/wall references.
3. **Given** the researcher opens `/xau-vol-oi`, **When** a reaction report is selected, **Then** the page shows freshness badge, IV/RV/VRP panel, opening price panel, acceptance/rejection state, reaction label table, risk planner table, no-trade reasons, and research-only disclaimer.

### Edge Cases

- Intraday timestamp is missing, unparsable, in the future, or in a different timezone than the current timestamp.
- Total intraday contract count is zero, negative, missing, or below the configured minimum threshold.
- Intraday data is prior-day while the report session is current-day.
- Session flag is unavailable or contradicts timestamps.
- IV is missing, zero, negative, stale, or expressed in an unexpected format.
- RV is missing, zero, negative, or calculated over an incompatible window.
- Price is outside both IV and RV ranges, inside one range but outside the other, or exactly on an edge.
- Session open is missing, current price equals the open, or the initial move direction is unknown.
- Price crosses the open after an initial move but does not hold beyond it.
- Candle high/low crosses a wall but close and next-bar open disagree.
- Wall buffer is zero, missing, unusually large, or larger than the distance between nearby walls.
- Multiple walls compete for the same zone, or the next wall reference is unavailable.
- A high-score wall has stale data or unknown basis.
- A low-OI gap exists but event risk or freshness blocks a candidate.
- Pin-like evidence exists outside the expected range or away from spot.
- Risk inputs are missing, minimum reward/risk cannot be met, or targets lie beyond unavailable next-wall references.
- A request or dashboard copy attempts to interpret output as a buy/sell, execution, live, paper, or shadow trading signal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a deterministic research-only reaction-report workflow on top of existing XAU Vol-OI wall and zone evidence.
- **FR-002**: System MUST NOT create live trading, paper trading, shadow trading, broker integration, private trading keys, wallet/private-key handling, real execution, order routing, position management, or buy/sell execution signals.
- **FR-003**: System MUST support exactly these reaction labels: `REVERSAL_CANDIDATE`, `BREAKOUT_CANDIDATE`, `PIN_MAGNET`, `SQUEEZE_RISK`, `VACUUM_TO_NEXT_WALL`, and `NO_TRADE`.
- **FR-004**: System MUST produce for each evaluated reaction: reaction label, confidence label, explanation notes, no-trade reasons, invalidation level, first target reference, second target reference, and next-wall reference when those values are available.
- **FR-005**: System MUST evaluate intraday OI freshness from intraday timestamp, current timestamp, total intraday contracts, minimum contract threshold, maximum allowed age, and session flag when available.
- **FR-006**: System MUST classify intraday freshness as `VALID`, `THIN`, `STALE`, `PRIOR_DAY`, or `UNKNOWN`.
- **FR-007**: System MUST ensure stale, thin, prior-day, or unknown freshness reduces confidence or forces `NO_TRADE` according to the severity and other evidence.
- **FR-008**: System MUST NOT treat prior-day data as fresh intraday flow.
- **FR-009**: System MUST calculate volatility risk premium as implied volatility minus realized volatility when both inputs are available.
- **FR-010**: System MUST classify VRP regime, IV edge state, and RV extension state from implied volatility, realized volatility, price position versus IV range, and price position versus RV range.
- **FR-011**: System MUST distinguish IV edge stress from RV-only extension.
- **FR-012**: System MUST reduce confidence in simple mean-reversion interpretations when VRP is wide and price has not confirmed rejection.
- **FR-013**: System MUST treat price breaking an IV expected-range edge as stress or squeeze warning evidence.
- **FR-014**: System MUST evaluate opening price regime from session open, current price, initial move direction, and whether price crossed the open after the initial move.
- **FR-015**: System MUST produce open-side, open-distance, open-flip state, and open-as-support-or-resistance outputs.
- **FR-016**: System MUST NOT assume a full open flip unless there is acceptance beyond the open.
- **FR-017**: System MUST evaluate candle acceptance and rejection from wall level, high, low, close, next-bar open, and wall buffer.
- **FR-018**: System MUST produce accepted-beyond-wall, wick-rejection, failed-breakout, and confirmed-breakout outputs.
- **FR-019**: System MUST NOT treat a wick through a wall as a confirmed breakout unless close and next-bar hold evidence support acceptance.
- **FR-020**: System MUST combine wall score, expected range, distance to wall, sigma position, IV/RV/VRP state, data freshness, opening price state, candle reaction state, next-wall distance, and optional event-risk state to classify reactions.
- **FR-021**: System MUST classify a high-score wall with rejection, stretched sigma position, and fresh data as `REVERSAL_CANDIDATE` when no blocking evidence dominates.
- **FR-022**: System MUST classify accepted breaks through walls with IV or flow expansion and low-OI gaps as `BREAKOUT_CANDIDATE`, `SQUEEZE_RISK`, or `VACUUM_TO_NEXT_WALL` based on the dominant evidence.
- **FR-023**: System MUST classify near-expiry large OI near spot inside the 1SD range as `PIN_MAGNET` when freshness and basis evidence are usable.
- **FR-024**: System MUST classify stale data, thin flow, unknown basis, conflicting signals, missing required context, or explicit event-risk blocks as `NO_TRADE` or include them as no-trade reasons.
- **FR-025**: System MUST create bounded risk-planning annotations for non-`NO_TRADE` reaction candidates.
- **FR-026**: Risk-planning annotations MUST include entry condition text, invalidation level, stop buffer points, target 1, target 2, maximum recovery legs, cancel conditions, and risk notes when available.
- **FR-027**: System MUST NOT create an entry plan for `NO_TRADE` reactions.
- **FR-028**: System MUST enforce capped total risk per idea, bounded recovery legs, minimum reward/risk checks, and explicit cancel conditions.
- **FR-029**: System MUST NOT permit martingale wording, unlimited averaging, uncapped recovery, execution readiness, or implied live-trading readiness in any risk plan.
- **FR-030**: System MUST support these external interaction paths: `POST /api/v1/xau/reaction-reports`, `GET /api/v1/xau/reaction-reports`, `GET /api/v1/xau/reaction-reports/{report_id}`, `GET /api/v1/xau/reaction-reports/{report_id}/reactions`, and `GET /api/v1/xau/reaction-reports/{report_id}/risk-plan`.
- **FR-031**: System MUST show reaction-report outputs on or from the `/xau-vol-oi` dashboard, including freshness badge, IV/RV/VRP panel, opening price panel, acceptance/rejection state, reaction label table, bounded risk planner table, no-trade reasons, and research-only disclaimer.
- **FR-032**: System MUST preserve traceability from each reaction and risk plan back to source wall, zone, expected range, freshness, volatility, open, and candle evidence.
- **FR-033**: System MUST persist reaction reports and generated report artifacts only in ignored research-output paths.
- **FR-034**: System MUST allow synthetic scenario validation for all six reaction labels and no-trade gates.
- **FR-035**: System MUST NOT claim profitability, predictive power, safety, or live readiness.
- **FR-036**: System MUST NOT introduce Rust, ClickHouse, PostgreSQL, Kafka, Redpanda, NATS, Kubernetes, ML model training, or other forbidden v0 technologies.

### Key Entities

- **XAU Reaction Report**: A saved research report containing metadata, source XAU wall report references, reaction rows, risk plans, warnings, limitations, and generated artifacts.
- **Intraday OI Freshness Assessment**: The status and notes describing whether intraday options data is valid, thin, stale, prior-day, or unknown.
- **Volatility Context**: The IV/RV/VRP comparison, IV range position, RV range position, stress state, and range-source notes used to contextualize reaction candidates.
- **Opening Price Regime**: The session-open anchor, current price relationship to open, distance from open, open-flip state, and support/resistance interpretation.
- **Candle Reaction State**: The wall-level OHLC and next-bar confirmation result describing acceptance, wick rejection, failed breakout, or confirmed breakout.
- **Zone Reaction**: One classified reaction candidate or no-trade state linked to source wall and zone evidence, with confidence, explanations, invalidation, targets, and next-wall reference.
- **Bounded Risk Plan**: A research-only annotation describing conditions, invalidation, buffers, target references, recovery bounds, cancel conditions, and risk notes for non-`NO_TRADE` reactions.
- **No-Trade Reason**: A structured explanation for why a zone must not be promoted into a reaction candidate.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Synthetic scenarios can classify at least one example into each of the six required reaction labels.
- **SC-002**: 100% of stale, thin, prior-day, unknown-basis, or conflicting synthetic scenarios either produce `NO_TRADE` or include an explicit confidence reduction with a visible reason.
- **SC-003**: Re-running classification with the same inputs produces the same reaction labels, confidence labels, levels, and no-trade reasons.
- **SC-004**: Every non-`NO_TRADE` reaction includes explanation notes, invalidation level, target 1, next-wall reference or an unavailable reason.
- **SC-005**: 100% of `NO_TRADE` reactions have no entry plan and include at least one no-trade reason.
- **SC-006**: 100% of bounded risk plans cap total risk, cap recovery legs, include cancel conditions, and avoid martingale or unlimited-averaging behavior.
- **SC-007**: A researcher can create and inspect a synthetic reaction report through the API and dashboard in under 2 minutes on a local workstation.
- **SC-008**: The dashboard allows a researcher to identify freshness status, IV/RV/VRP state, open-anchor state, candle reaction state, reaction label, risk plan, and no-trade reasons for a selected report in under 2 minutes.
- **SC-009**: API responses and dashboard text contain no buy/sell execution signals, profitability claims, predictive claims, safety claims, or live-readiness claims.
- **SC-010**: Generated reaction reports and imported/generated research data remain excluded from version control after a completed smoke run.

## Assumptions

- Feature 006 XAU Vol-OI wall reports already provide wall rows, zone rows, basis-adjusted wall levels, expected range context, wall scores, and source limitations.
- The transcript-distilled XAU framework is treated as research guidance for classification rules, not as proof of profitability or tradability.
- Confidence labels use a bounded qualitative scale such as high, medium, low, or blocked/unavailable; exact names may be finalized during planning as long as behavior remains testable.
- Event risk is optional for the first version; when unavailable, the report labels it unknown and does not invent event context.
- The first version uses synthetic fixtures for automated validation and does not require live market feeds or private data access.
- Risk plan levels are research annotations for manual analysis only and are not orders, alerts, broker instructions, or execution signals.
- Existing ignored data/report folder conventions remain the storage boundary for generated reaction reports.
