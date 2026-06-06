# Requirements Checklist: XAU Daily Research Workbench

**Feature**: 022-xau-daily-research-workbench
**Date**: 2026-06-07

## Completeness

- [X] Spec has user stories.
- [X] Spec has functional requirements.
- [X] Spec has edge cases.
- [X] Plan records constitution checks.
- [X] Data model documents request, result, providers, and artifacts.
- [X] API contract documents run/latest/map/candidate endpoints.
- [X] API contract documents run-detail endpoint.
- [X] Quickstart documents local usage and validation.
- [X] Quickstart documents CLI usage.
- [X] Tasks are dependency ordered.

## Research-Only Guardrails

- [X] `research_only=true` is required in outputs.
- [X] `signal_allowed=false` is required in outputs.
- [X] Missing source returns blocked output.
- [X] Missing basis returns blocked/no-trade candidate output.
- [X] Missing session open returns blocked/no-trade candidate output.
- [X] No buy/sell signal behavior was added.
- [X] No alert behavior was added.
- [X] No broker/order/execution behavior was added.
- [X] No PnL or position sizing behavior was added.

## Validation Coverage

- [X] Fixture full workbench run creates map and candidates.
- [X] Missing CME source fails cleanly.
- [X] Missing basis blocks candidate.
- [X] Missing session open blocks candidate.
- [X] Candidate artifacts round-trip.
- [X] API run returns map and candidate ids.
- [X] Latest endpoint handles empty state.
- [X] API run-detail endpoint returns persisted run.
- [X] Provider abstractions are tested.
- [X] CLI help and fixture run are tested.
- [X] Candidate store is tested.
- [X] Upper/lower 2SD-3SD and breakout-risk pass-through are tested.
- [X] Signal-disabled invariant is tested.
