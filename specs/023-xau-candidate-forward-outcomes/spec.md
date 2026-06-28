# Feature Specification: XAU Candidate Forward Outcomes

**Feature Branch**: `023-xau-candidate-forward-outcomes`
**Created**: 2026-06-07
**Status**: Draft
**Input**: User description: "Attach forward price outcomes to Feature 021/022 XAU SD/OI research candidates so we can measure whether the 2SD-3SD mean-reversion hypothesis works."

## User Scenarios & Testing

### User Story 1 - Compute Candidate Outcome Windows (Priority: P1)

As an XAU researcher, I want every saved SD/OI candidate to receive 30m, 1h, 4h, session-close, and next-day forward outcome labels from local price bars so that candidate evidence can be reviewed without turning the candidate into a signal.

**Why this priority**: Feature 021 can label a candidate and Feature 022 can persist it. The next evidence layer is whether price later mean-reverted, stopped, continued, or remained unresolved.

**Independent Test**: Build fixture candidate sets and fixture OHLC bars, then verify MFE, MAE, target hits, stop hits, continuation flags, and outcome labels for each window.

**Acceptance Scenarios**:

1. Given a short reversion candidate and future bars that touch target 1 before stop, when outcomes are computed, then the outcome is labeled as mean reversion or target hit, `returned_to_1sd=true`, and `signal_allowed=false`.
2. Given a short reversion candidate and future bars that touch the stop reference before target, when outcomes are computed, then the outcome is labeled `stop_hit`, `touched_3_5sd=true`, and `signal_allowed=false`.
3. Given a long reversion candidate and future bars that touch target 1, when outcomes are computed, then MFE/MAE are correct and `returned_to_1sd=true`.

### User Story 2 - Preserve Missing And Partial Price Coverage (Priority: P2)

As an XAU researcher, I want missing or incomplete price bars to remain explicit so that outcome evidence is not fabricated from gaps or proxy candles.

**Why this priority**: The project doctrine requires reproducible data and no hidden assumptions. Outcome labels must not be invented when price coverage is unavailable.

**Independent Test**: Run missing-bar and partial-window fixtures and verify unavailable/partial coverage states, preserved null OHLC fields, and limitation notes.

**Acceptance Scenarios**:

1. Given no usable bars for a candidate window, when outcomes are computed, then the outcome is `unavailable`, OHLC fields remain null, and the run does not crash.
2. Given bars that overlap but do not cover the requested window, when outcomes are computed, then coverage is `partial`, OHLC is computed only from available bars, and a limitation is recorded.

### User Story 3 - Persist And Serve Outcome Runs (Priority: P3)

As an XAU researcher, I want outcome runs persisted and available through a local API and CLI so that later dashboard or research-stat features can consume the same evidence artifacts.

**Why this priority**: Evidence must be reproducible and inspectable before any backtest statistics or strategy claims are added.

**Independent Test**: Persist a fixture candidate outcome run, load it back by id and latest-state APIs, and run the CLI on local fixture artifacts.

**Acceptance Scenarios**:

1. Given a candidate artifact and local OHLC bars, when the outcome run is executed, then `outcome_metadata.json`, `outcomes.json`, and `outcomes.md` are written under the ignored local report tree.
2. Given a saved outcome run, when the local API reads latest or by id, then the same research-only outcome set is returned.
3. Given the CLI is invoked with local paths, when it completes, then it prints `outcome_run_id`, candidate and outcome counts, unavailable count, artifact paths, and `signal_allowed=false`.

### Edge Cases

- Candidate set has zero candidates.
- Candidate timestamps are timezone-naive.
- Price bars are missing for one or all requested windows.
- Price bars overlap a window but do not cover the full interval.
- Price bar OHLC values are invalid.
- Candidate target or stop fields are null.
- Candidate side is `no_trade` or `breakout_risk`.
- Next-wall references are absent.
- Price source is a local proxy rather than true XAUUSD spot.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST represent candidate outcome windows: `30m`, `1h`, `4h`, `session_close`, and `next_day`.
- **FR-002**: The system MUST represent outcome labels: `target_hit`, `stop_hit`, `mean_reverted`, `breakout_continued`, `unresolved`, and `unavailable`.
- **FR-003**: The system MUST compute one outcome per candidate per requested window.
- **FR-004**: The system MUST compute OHLC, MFE, and MAE from supplied local price bars without fabricating missing bars.
- **FR-005**: The system MUST treat missing price bars as unavailable outcomes with null OHLC values and explicit limitations.
- **FR-006**: The system MUST mark partial price windows as partial coverage and compute OHLC only from observed bars.
- **FR-007**: The system MUST detect target 1/2/3 hits, stop-reference hits, 1SD returns, 2SD touches, 3SD touches, 3.5SD touches, next-wall touches, and breakout continuation flags where source fields allow.
- **FR-008**: The system MUST persist outcome artifacts under ignored local report paths and load them by run id.
- **FR-009**: The system MUST expose local research API endpoints for running, reading latest, and reading one outcome run.
- **FR-010**: The system MUST expose a local CLI for fixture/local artifact outcome runs.
- **FR-011**: Every outcome, outcome set, run result, API response, and CLI result MUST keep `research_only=true` and `signal_allowed=false`.
- **FR-012**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, order routing, PnL, position sizing, automatic trade placement, buy/sell instructions, ML training, or profitability claims.

### Key Entities

- **XAU Candidate Outcome Window**: A forward time window over which candidate evidence is measured.
- **XAU Candidate Price Bar**: One local OHLCV candle used as source evidence.
- **XAU Candidate Outcome**: One candidate-window measurement with OHLC, MFE/MAE, hit flags, label, coverage status, limitations, and no-signal guardrails.
- **XAU Candidate Outcome Set**: The complete outcome collection for a candidate set and price source.
- **XAU Candidate Outcome Run Result**: A persisted run with metadata, artifact paths, unavailable count, no-signal reasons, and the outcome set.

## Success Criteria

- **SC-001**: Short reversion target fixtures produce `returned_to_1sd=true`, `hit_stop_reference=false`, and `signal_allowed=false`.
- **SC-002**: Short stop fixtures produce `outcome_label=stop_hit` and `touched_3_5sd=true`.
- **SC-003**: Long reversion fixtures compute correct favorable/adverse excursion and `returned_to_1sd=true`.
- **SC-004**: Breakout-risk fixtures set `continued_breakout=true` when price extends beyond the 3SD/3.5SD boundary.
- **SC-005**: Missing bars produce `outcome_label=unavailable` without a crash.
- **SC-006**: Partial windows record `coverage_status=partial` and retain computed OHLC from observed bars.
- **SC-007**: Candidate artifact roundtrip produces loadable outcome artifacts.
- **SC-008**: API and CLI runs return outcome ids, artifact paths, and `signal_allowed=false`.
- **SC-009**: Review of code and docs finds zero PnL, execution, alert, order, broker, position-sizing, live-readiness, safety, predictive-proof, or profitability behavior.

## Assumptions

- Feature 021 candidate sets are the source candidate contract.
- Feature 022 candidate sidecars are the primary persisted candidate source.
- Price bars are supplied from local CSV, JSON, or Parquet research files for this slice.
- Session close defaults to 21:00 UTC until a later source-backed session calendar feature overrides it.
- Outcome labels are evidence annotations only and are not strategy performance statistics.
