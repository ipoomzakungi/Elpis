# Research: XAU SD OI Mean Reversion Candidate Research

**Feature**: 021-xau-sd-oi-mean-reversion-candidate-research
**Date**: 2026-06-07

## Decision: Consume The Daily Structural Map

Use `XauDailyStructuralMap` as the only structural source for basis, SD bands, session open, and enriched wall rows.

**Rationale**: Features 017-020A already preserve expected-range source, basis readiness, session open, wall mapping, null wall fields, and no-signal semantics. Recomputing from bundle rows would duplicate and risk changing the point-in-time map.

**Alternatives rejected**:

- Reading raw QuikStrike bundle files again: duplicates Feature 020A and may create inconsistent context.
- Creating a persistence layer now: unnecessary for a focused candidate function and can be added later if outcome labeling needs artifacts.

## Decision: Caller Supplies Confirmation, IV, Flow, And Wall State

The classifier accepts controlled context states rather than deriving candle acceptance or order flow from unavailable feeds.

**Rationale**: This slice is timestamp-safe only if it labels what the caller supplies. Inferring unavailable flow or IV behavior would fabricate confirmation.

## Decision: Derive 3.5SD Only From 1SD Geometry

When native 3.5SD bands are not present, derive them from the midpoint of lower/upper 1SD and the one-SD distance.

**Rationale**: Feature 017 stores 1SD/2SD/3SD bands but not 3.5SD. The course stop reference can be represented as a research reference only if the derived source is visible.

## Decision: No Signal Semantics

Every model keeps `signal_allowed=false` and `research_only=true`.

**Rationale**: A candidate label is an input to future validation, not evidence of profitability, safety, or tradability.

## Open Follow-Ups

- Define source-backed price confirmation states from OHLCV bars.
- Define source-backed IV expansion and flow-through-wall states.
- Add forward outcome labels and backtest logic only in a later feature with explicit validation gates.
