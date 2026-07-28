# Implementation Plan: XAU Vol2Vol First-Touch Replication

## Phase 1 - Frozen Contract

- Add the v1 study registry and canonical hash validation.
- Add source and methodology notes for the supplied external study.

## Phase 2 - Core Research Engine

- Implement exact-session loading and deterministic source snapshot selection.
- Implement T0/T1/T2 anchor modes and both mapping modes.
- Build aggregated and side-specific first-touch events.
- Evaluate eventual-reversal and strict first-passage labels.

## Phase 3 - Analysis And Shadow State

- Run barrier, DTE, time-anchor, mapping, side, cost, and external-prior comparisons.
- Add chronological development/holdout and session bootstrap.
- Add deterministic shadow-only state transitions and promotion gates.

## Phase 4 - Artifacts And Validation

- Add report store and CLI.
- Add focused guardrail and behavior tests.
- Execute the study against all retained completed sessions.
- Commit only code, tests, config, specs, and documentation.
