# Requirements Checklist: XAU Daily Structural Map

**Feature**: 018-xau-daily-structural-map
**Date**: 2026-06-04

## Scope

- [X] Research-only scope is explicit.
- [X] No buy/sell signal, alert, broker execution, order, position, ML, or backtest behavior is required.
- [X] Expected-range source hierarchy reuses Feature 017.
- [X] Basis mapping behavior is explicit.
- [X] Session-open behavior is explicit.
- [X] Null/blank Matrix semantics are preserved.

## Test Coverage

- [X] Full-context map test defined.
- [X] Missing-basis test defined.
- [X] Missing-expected-range test defined.
- [X] Missing-session-open test defined.
- [X] Blank Matrix cell test defined.
- [X] Feature 017 integration test defined.

## Risks

- [X] Missing wall OI-change and volume values remain nullable.
- [X] Missing basis blocks spot-equivalent mapping.
- [X] Missing expected range blocks SD annotations.
- [X] Complete maps still cannot be treated as signals.
