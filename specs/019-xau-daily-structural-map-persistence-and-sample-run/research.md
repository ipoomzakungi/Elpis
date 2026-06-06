# Research: XAU Daily Structural Map Persistence And Sample Run

**Date**: 2026-06-04
**Feature**: 019-xau-daily-structural-map-persistence-and-sample-run

## Decisions

### Decision: Use `map.json` As Canonical Payload

`map.json` stores the full `XauDailyStructuralMap` and must validate back into that schema.

**Rationale**: Later forward outcomes need a stable immutable snapshot. The Feature 018 map schema already captures readiness, no-signal reasons, and wall rows.

### Decision: Store Wall Rows As JSON

`walls.json` stores the map wall list using JSON rather than Parquet.

**Rationale**: JSON preserves nulls directly, is easy to inspect, and avoids a heavier artifact for one map-sized wall list.

### Decision: Add A Dedicated Store Package

Use `backend/src/xau_daily_structural_map/` for persistence and sample-run helpers.

**Rationale**: Feature 018 builder remains in the existing fusion-adjacent module. Persistence is a separate concern and follows the existing fusion/forward-journal store pattern.

### Decision: Keep Sample Run Input-Driven

The sample-run helper accepts supplied expected range, walls, basis, and session open. It does not fetch CME or browser data.

**Rationale**: The prompt asks for a sample-run path but forbids live/session material. Input-driven generation is testable and safe.

### Decision: Keep Signals Disabled

All persisted metadata and markdown keep `signal_allowed = false` and map-only language.

**Rationale**: Feature 019 is artifact persistence. Candidate logic and backtests are later features.

## Alternatives Considered

### Add API Endpoints

Deferred. The current task asks for persistence and sample generation. API endpoints can be added when dashboard or external local interfaces need them.

### Write Generated Sample Artifact Into The Repo

Rejected. Generated artifacts belong under ignored local report paths and should not be committed.

### Add Forward Outcomes Now

Rejected. Outcomes should attach after this stable map artifact exists.
