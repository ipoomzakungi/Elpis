# Requirements Checklist: XAU Real Structural Map From Bundle

**Feature**: 020a-xau-real-structural-map-from-bundle
**Date**: 2026-06-04

## Completeness

- [x] Feature objective is scoped to local bundle to persisted map.
- [x] Required input artifact shapes are listed.
- [x] Basis precedence and unavailable behavior are specified.
- [x] Expected-range no-fabrication behavior is specified.
- [x] Wall parquet and embedded fallback behavior are specified.
- [x] Null preservation is specified.
- [x] Persistence through Feature 019 is specified.
- [x] Research-only forbidden scope is specified.

## Safety

- [x] No live trading is requested.
- [x] No paper or shadow trading is requested.
- [x] No broker execution is requested.
- [x] No alerts are requested.
- [x] No private API keys or wallet/private-key handling are requested.
- [x] No PnL or backtest is requested.
- [x] No ML model training is requested.
- [x] No v0-forbidden infrastructure is requested.

## Test Coverage

- [x] Full-context bundle test specified.
- [x] Missing-basis test specified.
- [x] Missing-expected-range test specified.
- [x] Range-label-only test specified.
- [x] Null wall flow preservation test specified.
- [x] Parquet fallback and no-wall tests specified.
