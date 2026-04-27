# Research: Validation and Research Hardening

**Date**: 2026-04-27  
**Feature**: 004-validation-and-research-hardening

## Decision: Keep Hardening Additive to the Existing Backtest MVP

**Rationale**: Feature 003 already provides the engine, reports, APIs, and dashboard inspection path. This feature should improve correctness and validation depth without redesigning the provider layer, dashboard root, or report storage.

**Alternatives considered**:

- Rebuild the backtest engine around a new framework: rejected because it would risk regressions and violate the instruction to avoid a broad redesign.
- Create a separate service for validation reports: rejected because v0 is a local research platform and no microservice/event architecture is needed.

## Decision: Buy-and-Hold Uses Capital-Based Sizing by Default

**Rationale**: A passive buy-and-hold baseline should represent capital exposure, not a risk-sized trade with a distant stop. Defaulting to 100% capital fraction provides an intuitive passive benchmark while still allowing a configured fraction for experiments.

**Alternatives considered**:

- Keep using fixed fractional risk sizing: rejected because it can create tiny passive positions and misleading baseline comparisons.
- Force 100% exposure with no configuration: rejected because researchers may need smaller passive exposure for controlled comparisons.

## Decision: Enforce No-Leverage in Accounting, Not Only Schema

**Rationale**: Schema validation already constrains leverage to 1, but risk-based sizing can still create notional exposure above available equity when stop distance is very small. Accounting must cap notional and record the event.

**Alternatives considered**:

- Reject all oversized risk-sized trades: rejected because capping gives a clear no-leverage research result and preserves run continuity.
- Allow oversized notional because leverage is only metadata: rejected because it violates the economic meaning of no leverage.

## Decision: Make Per-Mode Metrics Canonical

**Rationale**: Feature 003 can compare independent strategy and baseline equity curves. A single global headline can be mistaken for a combined portfolio result. Per-mode metrics should be primary, while any aggregate row must be labeled as a comparison summary.

**Alternatives considered**:

- Remove all summary metrics: rejected because users still need a compact overview.
- Combine all modes into one portfolio: rejected because portfolio-combination mode is not part of this feature and would require separate assumptions.

## Decision: Add Mark-to-Market Total Equity While Preserving Realized Equity

**Rationale**: Realized-only equity hides open-position risk. Close-price mark-to-market total equity gives a more truthful drawdown picture during holding periods while realized equity remains useful for compatibility and auditability.

**Alternatives considered**:

- Keep realized-only equity: rejected because open-position risk can be invisible.
- Use intrabar high/low valuation: rejected because it may overstate or understate risk without tick-order evidence.

## Decision: Use Bounded Validation Runners

**Rationale**: Fee/slippage stress, parameter sensitivity, and walk-forward validation should be deterministic, local, and bounded. The goal is robustness evidence, not large-scale optimization.

**Alternatives considered**:

- Unbounded parameter search: rejected because it can become optimization and produce misleading overfit results.
- External experiment tracker or database: rejected because v0 stores generated research artifacts locally.

## Decision: Implement Validation Orchestration in `backend/src/backtest/validation.py`

**Rationale**: Stress profiles, parameter grids, walk-forward splits, regime coverage, and concentration analysis cross-cut engine, metrics, and report writing. A validation module keeps orchestration out of strategy generation and portfolio accounting.

**Alternatives considered**:

- Put validation directly in `engine.py`: rejected because engine orchestration would become too broad.
- Put validation in reports only: rejected because validation needs to rerun simulations and inspect feature data, not just format output.

## Decision: Real-Data Validation Requires Existing Processed Features

**Rationale**: The final research report should not silently fall back to synthetic data. If BTCUSDT 15m processed features are missing, the user should receive clear download/process instructions.

**Alternatives considered**:

- Auto-download data during validation: rejected because validation should not unexpectedly perform network/data generation side effects.
- Use synthetic fallback for final research report: rejected because it weakens real-data trustworthiness.

## Decision: Add CI Without Secrets

**Rationale**: Hardening must remain reproducible for contributors and future agents. Backend tests, frontend build, and artifact guard checks can run without private credentials.

**Alternatives considered**:

- Require exchange credentials in CI: rejected because v0 uses public/local research data only.
- Skip CI until live phases: rejected because correctness hardening depends on repeatable validation now.

## Decision: Keep Dashboard Changes Focused on Validation Report Inspection

**Rationale**: The dashboard should help researchers audit outputs, not become a new optimization studio or trading cockpit. Extend `/backtests` if practical; add `/validation` only if needed for readability.

**Alternatives considered**:

- Redesign the dashboard: rejected by user instruction and unnecessary for validation report inspection.
- Hide validation details in files only: rejected because researchers need to inspect stress, sensitivity, split, and concentration outputs visually.