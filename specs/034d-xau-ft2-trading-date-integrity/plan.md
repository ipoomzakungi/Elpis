# Implementation Plan: XAU FT2 Trading-Date And Execution Integrity

## Phase 1 - Alignment Audit

- Reproduce stale source-label joins from the 034C report.
- Separate source session, activation timestamp, and Bangkok trading date.
- Select synchronized fully closed XAU bars from the full retained timeline.

## Phase 2 - Corrected Historical Sample

- Reject source gaps above 120 seconds.
- Recover July 5 if July 6 bars synchronize.
- Rebuild mapped plans, events, outcomes, and prior-versus-corrected comparison.

## Phase 3 - Executable Fill Model

- Model bid/ask entry and exits for long and short events.
- Run the frozen 0.3, 0.5, 1.0, 1.5, and 2.5-point spread scenarios.
- Keep reference touches distinct from executable fills.

## Phase 4 - Manual Execution Journal

- Extend acknowledgement with optional actual fill details.
- Resolve outcomes only from actual acknowledged fills.
- Preserve reference entry separately.

## Phase 5 - Validation

- Add focused alignment, fill, acknowledgement, hash, and guardrail tests.
- Run every retained completed session and all prior feature regressions.
- Commit and push only code, tests, config, specs, and documentation.
