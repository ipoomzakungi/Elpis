# Requirements Checklist: XAU Daily Structural Map Persistence And Sample Run

**Feature**: 019-xau-daily-structural-map-persistence-and-sample-run
**Date**: 2026-06-04

## Scope

- [X] Research-only scope is explicit.
- [X] No buy/sell signal, alert, broker execution, order, position, ML, or backtest behavior is required.
- [X] Persistence target is local ignored report artifacts.
- [X] Sample-run helper avoids live CME/browser/session access.
- [X] Null/blank semantics are preserved.

## Test Coverage

- [X] Full-context persistence test defined.
- [X] Missing-basis persistence test defined.
- [X] Missing-expected-range persistence test defined.
- [X] Missing-session-open persistence test defined.
- [X] Null-preservation test defined.
- [X] Round-trip test defined.
- [X] Sample-run helper test defined.

## Risks

- [X] Generated artifacts must not be committed.
- [X] Source report ids may be synthetic until a real local 2026-06-02 bundle is supplied.
- [X] Forward outcomes remain deferred.
- [X] Complete maps still cannot be treated as signals.
