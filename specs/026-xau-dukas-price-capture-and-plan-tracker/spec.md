# Feature Specification: XAU Dukascopy Price Capture And Plan Tracker

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`
**Created**: 2026-06-08
**Status**: Draft
**Input**: User requested a research-only traded-side XAUUSD price capture layer and morning/evening plan tracker for CME-native SD Range Desk plans.

## User Scenarios & Testing

### User Story 1 - Capture Or Import Traded-Side XAU Bars (Priority: P1)

As an XAU researcher, I want to import local XAUUSD bars or run a configurable Dukascopy CLI command so that CME futures/options plans can be evaluated against traded-side spot/CFD prices.

**Independent Test**: Given a CSV fixture with timestamp/open/high/low/close and optional volume, the adapter returns normalized XAU bars. Given a failing command, it returns failed/unavailable without crashing.

### User Story 2 - Build 10:10 And 18:10 Mapped Research Plans (Priority: P1)

As an XAU researcher, I want 10:10 and 18:10 Asia/Bangkok traded reference prices mapped against the latest CME-native SD sidecar so that I can see long/short Range Desk plans for each session.

**Independent Test**: Given fixture native SD and XAU bars with exact 10:10 and 18:10 closes, the service creates two snapshots with Diff, native SD, and long/short plans.

### User Story 3 - Track Simulated Plan Status, PnL Points, And Drawdown (Priority: P2)

As an XAU researcher, I want each simulated plan marked planned, triggered, target hit, stop hit, recovery triggered, expired, open, ambiguous, or unavailable so that intraday outcomes can be reviewed without live orders.

**Independent Test**: Given bars after a long entry, the tracker computes trigger time, current PnL points, MFE, MAE/drawdown, and final status.

### User Story 4 - Preserve Research-Only Guardrails (Priority: P3)

As the project owner, I want every API/CLI output to remain research-only and signal-disabled.

**Independent Test**: API and CLI result models always return `research_only=true` and `signal_allowed=false`.

## Requirements

- **FR-001**: The system MUST parse local CSV or JSON XAUUSD bars with timestamp/open/high/low/close and optional volume.
- **FR-002**: The system MUST run a configurable Dukascopy CLI command template when no local price bars path is supplied.
- **FR-003**: The system MUST sanitize command output and return failed/unavailable results without crashing.
- **FR-004**: The system MUST extract traded reference prices at 10:10 and 18:10 Asia/Bangkok using exact bar close or a latest-before bar within tolerance.
- **FR-005**: The system MUST calculate `diff_points = future_reference_price - traded_reference_price` and mapped traded levels through Feature 025 planning logic.
- **FR-006**: The system MUST prefer saved CME-native `range_bands.json` and MUST NOT convert `range_label` into numeric SD.
- **FR-007**: The system MUST persist snapshots, tracked orders, metadata, and Markdown reports under ignored local report paths.
- **FR-008**: The system MUST compute simulated current PnL points, MFE, MAE/drawdown, trigger time, exit time, and status when bars are available.
- **FR-009**: Missing bars or missing traded reference prices MUST produce partial/unavailable results, not fabricated prices.
- **FR-010**: All outputs MUST include `research_only=true` and `signal_allowed=false`.
- **FR-011**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, real order placement, real PnL, position sizing, broker IDs, or profitability claims.

## Key Entities

- **Dukascopy Capture Request/Result**: CLI settings, output path, status, bar count, and limitations.
- **XAU Price Bar**: Normalized traded-side OHLCV bar.
- **Plan Tracker Request**: Session date, planning times, CME source, price source, SD plan settings, and output settings.
- **Plan Tracker Snapshot**: One planning time with future reference, traded reference, Diff, native SD, and long/short plan levels.
- **Tracked Order**: One simulated research order with status, PnL points, drawdown/MAE, and limitations.
- **Plan Tracker Run Result**: Persisted local run summary and artifact paths.

## Success Criteria

- **SC-001**: CSV and JSON bar fixtures parse into normalized XAU bars.
- **SC-002**: Exact and within-tolerance reference extraction works for 10:10 and 18:10.
- **SC-003**: The service creates two snapshots and tracked orders from fixture SD plus fixture bars.
- **SC-004**: Long and short simulated status/PnL/drawdown logic is covered by tests.
- **SC-005**: API and CLI smoke checks return research-only signal-disabled outputs.

## Assumptions

- CME/QuikStrike remains the source for futures/options/SD/OI.
- Dukascopy is a traded-side XAUUSD research price feed only.
- Feature 025 remains the source of Range Desk SD mapping and order-plan generation.
- Dashboard display is a later feature.
