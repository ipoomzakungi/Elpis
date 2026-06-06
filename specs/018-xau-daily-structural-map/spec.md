# Feature Specification: XAU Daily Structural Map

**Feature Branch**: `018-xau-daily-structural-map`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: "Create Feature 018: xau-daily-structural-map. Combine Feature 017 expected range, XAU/GO/spot basis mapping, existing XAU Vol-OI walls/zones, session-open context, source quality/readiness, and forward-journal compatibility. Keep it research-only and do not create signals or backtests."

## User Scenarios & Testing

### User Story 1 - Build One Daily Research Map (Priority: P1)

As an XAU researcher, I want one daily structural map object for a session so that CME expected range, basis-adjusted wall levels, session open, and source limitations are visible in one auditable payload.

**Why this priority**: Feature 017 made expected-range context available. The next useful step is a map object that can be reviewed and journaled before any candidate classifier, signal logic, or backtest exists.

**Independent Test**: Build a synthetic map with an expected-range snapshot, available basis, one or more walls, and a session open, then verify mapped wall levels, range fields, readiness, and no-signal state.

**Acceptance Scenarios**:

1. Given expected range, basis, walls, and session open are available, when the map is built, then wall spot-equivalent levels and distances are populated and readiness is `structural_map_ready`.
2. Given the map is complete, when the payload is inspected, then `signal_allowed` remains false because Feature 018 is map-only.
3. Given an expected-range snapshot came from CME-native or IV-derived Feature 017 logic, when the map is built, then the range source, IV, fractional DTE, and SD bands are preserved.

### User Story 2 - Preserve Partial Context Without Fabrication (Priority: P2)

As an XAU researcher, I want maps to be created when basis, expected range, or session open is missing so that missing context is visible without fabricating prices, ranges, or signals.

**Why this priority**: Previous reaction output correctly blocked promotion when basis/open/range context was missing. Feature 018 must keep that risk behavior explicit.

**Independent Test**: Build maps with missing basis, missing expected range, and missing session open, then verify null fields and no-signal reasons.

**Acceptance Scenarios**:

1. Given basis is unavailable, when the map is built, then spot-equivalent levels remain null and no-signal reasons include "Basis mapping unavailable."
2. Given expected range is unavailable, when the map is built, then SD fields remain null and no-signal reasons include "Expected range unavailable."
3. Given session open is unavailable, when the map is built, then session-open fields remain null and readiness is partial.

### User Story 3 - Keep Forward-Journal Compatibility (Priority: P3)

As an XAU researcher, I want the structural map to carry stable identifiers, source product, session date, wall summaries, source quality, and limitations so that later forward journal and outcome-label features can attach evidence without changing the original map.

**Why this priority**: Later features should attach outcomes to what was known at capture time, not reconstruct context after the fact.

**Independent Test**: Inspect the structural map schema and verify it has stable ids, source timing/range context, wall ids, limitations, and research-only no-signal guardrails.

### Edge Cases

- Feature 017 expected-range snapshot is missing or marked unavailable.
- Basis is unavailable, blocked, or conflicting.
- Session open is missing.
- Walls exist without OI change or volume values.
- No walls exist for the selected session.
- Expected range uses IV-derived fallback and must retain its limitation.
- Blank or unavailable Matrix values remain null rather than zero.
- Requests include trading, alerting, execution, broker, private-key, endpoint replay, profitability, predictive, safety, or live-readiness language.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST represent a research-only XAU daily structural map with map id, session date, created timestamp, source product, option product code, futures symbol, expiration, reference futures price, traded instrument, traded reference price, basis context, expected range context, session-open context, walls, readiness state, limitations, and no-signal reasons.
- **FR-002**: The map MUST populate expected-range fields from `XauExpectedRangeSnapshot` when present.
- **FR-003**: CME-native numeric bands MUST remain labeled `cme_native`; IV-derived bands MUST remain labeled `derived_from_iv`; unavailable range MUST remain unavailable.
- **FR-004**: The map MUST compute `spot_equivalent_level = cme_strike - basis` only when basis is available.
- **FR-005**: When basis is unavailable, the map MUST preserve futures strike and leave spot-equivalent fields null.
- **FR-006**: Each wall MUST include wall id, expiry, expiration code, strike, wall type, open interest, optional OI change, optional volume, wall score, freshness state, mapping status, distances, expected-range membership, and limitations.
- **FR-007**: Session-open context MUST include session open price, source, availability, open side versus 1SD, and distance from the traded reference when available.
- **FR-008**: Missing basis, expected range, or session open MUST produce explicit readiness and no-signal reasons.
- **FR-009**: `signal_allowed` MUST always be false for Feature 018.
- **FR-010**: The system MUST NOT output buy/sell labels, alerts, live trading behavior, broker execution, order instructions, position instructions, ML training, or strategy backtests.
- **FR-011**: Blank, null, unavailable, invalid, or missing Matrix values MUST NOT be converted to zero.
- **FR-012**: The map MUST remain compatible with later forward journal outcome labeling by preserving stable ids and source limitations.
- **FR-013**: The system MUST provide tests for full context, missing basis, missing expected range, missing session open, blank Matrix cells, and Feature 017 integration.
- **FR-014**: The feature MUST NOT store cookies, tokens, headers, HAR files, screenshots, private URLs, credentials, endpoint replay material, broker fields, wallet fields, order fields, or execution fields.

### Key Entities

- **XAU Daily Structural Map**: One session-level research payload combining expected range, basis, walls, session open, readiness, and limitations.
- **Structural Map Wall**: One wall row enriched with spot mapping, distance, and expected-range membership.
- **Structural Map Basis**: Basis and mapping availability for translating CME futures strikes to the traded chart.
- **Structural Map Range**: Feature 017 expected-range fields carried into the map.
- **Structural Map Readiness**: Controlled state describing whether the map is ready for research inspection or partial/blocked by missing context.

## Success Criteria

- **SC-001**: Full-context tests create a map with mapped wall levels, expected range fields, readiness `structural_map_ready`, and `signal_allowed = false`.
- **SC-002**: Missing-basis tests keep spot-equivalent levels null and include the required no-signal reason.
- **SC-003**: Missing-expected-range tests keep SD fields null and include the required no-signal reason.
- **SC-004**: Missing-session-open tests keep session-open fields null and mark readiness partial.
- **SC-005**: Blank Matrix cell tests preserve null numeric values.
- **SC-006**: Feature 017 integration tests prove `XauExpectedRangeSnapshot` populates the map range fields.
- **SC-007**: Review of docs and output finds zero buy/sell, alert, execution, profitability, predictive-proof, safety, or live-readiness claims.

## Assumptions

- Feature 017 expected-range snapshots are already available and tested.
- Existing XAU Vol-OI wall objects remain the source for wall score and freshness.
- OI change and volume may be absent in the current wall model and must remain null.
- Session open may be supplied manually or by a future approved price-bar ingestion feature.
- Feature 018 is a map and readiness payload only. Later features may add forward outcome labels and research-only classifiers.
