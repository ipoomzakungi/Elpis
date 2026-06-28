# Requirements Checklist: XAU SD OI Mean Reversion Candidate Research

**Feature**: 021-xau-sd-oi-mean-reversion-candidate-research
**Date**: 2026-06-07

## Scope And Safety

- [x] Research-only scope is explicit.
- [x] `signal_allowed=false` is required.
- [x] `research_only=true` is required.
- [x] Live trading, paper trading, broker execution, alerts, PnL, orders, real position sizing, and ML training are excluded.
- [x] Candidate labels are not described as profitability, predictive, safety, or live-readiness evidence.

## Context Requirements

- [x] Missing basis blocks candidate creation.
- [x] Missing expected range blocks candidate creation.
- [x] Missing traded price blocks candidate creation.
- [x] Missing session open blocks candidate creation.
- [x] Range-label-only context cannot fabricate numeric SD bands.
- [x] Null OI-change and volume fields remain null.

## Candidate Logic

- [x] Upper 2SD-3SD rejection case is defined.
- [x] Lower 2SD-3SD rejection case is defined.
- [x] Breakout-risk override is defined.
- [x] Inside +/-2SD monitor/no-trade case is defined.
- [x] 3.5SD derivation and limitation are defined.
- [x] 2SD is not treated as an automatic entry.
- [x] High OI is not treated as direction.

## Validation

- [x] Focused candidate tests are required.
- [x] Feature 018 structural-map regression is required.
- [x] Feature 017 expected-range regression is required.
- [x] Field-inventory regression is required.
- [x] Backend import check is required.
- [x] Ruff on touched files is required.
