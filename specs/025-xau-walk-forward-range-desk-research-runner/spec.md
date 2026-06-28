# Feature Specification: XAU Walk-Forward Range Desk Research Runner

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`
**Created**: 2026-06-08
**Status**: Draft
**Input**: User requested a research-only runner that creates 10:10 and 19:10 Range Desk planning records, optional 10-minute walk-forward records, native SD-based entry/target/stop/recovery research plans, and simulated outcomes from local bars.

## User Scenarios & Testing

### User Story 1 - Generate Walk-Forward Planning Snapshots (Priority: P1)

As an XAU researcher, I want planning snapshots at 10:10 and 19:10 Asia/Bangkok, plus optional 10-minute weekday walk-forward snapshots, so that each decision record uses its own timestamp, DTE, SD, and diff context.

**Independent Test**: Given a weekday session date and walk-forward mode, the schedule contains 10-minute timestamps from 10:10 through 21:50 and tags 10:10 and 19:10 as planning snapshots.

### User Story 2 - Use Source-Backed Native SD And Diff Mapping (Priority: P1)

As an XAU researcher, I want native CME SD bands from `range_bands.json` to be preferred and mapped to traded XAU/CFD levels using Diff/Basis so that the plan does not fabricate SD from labels.

**Independent Test**: Given a `range_bands.json` fixture with 1SD/2SD/3SD cumulative bands and future/traded prices, the runner creates a Range Desk plan with mapped traded levels and keeps `signal_allowed=false`.

### User Story 3 - Create Research-Only Order And Recovery Plans (Priority: P2)

As an XAU researcher, I want configurable 2SD entry, 1SD target, 2.5SD stop, and 3SD recovery research plans so that the idea can be tested before any paper/live trading discussion.

**Independent Test**: Given complete SD levels, the order planner creates long and short research plans with target/stop distances and blocks recovery sizing when risk inputs are missing or too large.

### User Story 4 - Simulate Outcomes From Local OHLCV Bars (Priority: P3)

As an XAU researcher, I want local bars to label planned orders as triggered, target hit, stop hit, expired, ambiguous, or unavailable so that walk-forward evidence can be aggregated later.

**Independent Test**: Given a long plan and bars crossing entry then target, the outcome is `target_hit`; given missing bars, the outcome is `unavailable`.

## Requirements

- **FR-001**: The system MUST generate Asia/Bangkok schedule timestamps for planning-only and walk-forward modes.
- **FR-002**: The system MUST block or return no snapshots for weekends when `weekdays_only=true`.
- **FR-003**: The system MUST prefer `range_bands.json` native CME SD values when available.
- **FR-004**: The system MUST NOT convert `range_label` or `sigma_label` into numeric SD bands.
- **FR-005**: The system MUST calculate `diff_points = future_reference_price - traded_reference_price` and map futures levels using `mapped_traded_level = futures_level + traded_offset`.
- **FR-006**: The system MUST store DTE per snapshot and avoid reusing old SD values without their source timestamp.
- **FR-007**: The system MUST generate research-only initial and recovery order plans from configurable SD references.
- **FR-008**: The system MUST cap or block recovery sizing when risk inputs are missing or configured limits are exceeded.
- **FR-009**: The system MUST simulate outcomes from supplied local OHLCV bars without live order behavior.
- **FR-010**: All outputs MUST include `research_only=true` and `signal_allowed=false`.
- **FR-011**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, real order placement, real PnL, real position management, broker IDs, or profitability claims.

## Key Entities

- **Schedule Config**: Times, interval, timezone, weekday-only behavior.
- **Price Snapshot**: Futures price, traded price, diff, source quality, alignment state.
- **SD Snapshot**: Native or fallback SD levels, DTE, source report, source view.
- **Research Order Plan**: Entry/target/stop/recovery template and risk status.
- **Research Order Outcome**: Local-bar simulated result.
- **Snapshot Record**: One timestamp with price, SD, Range Desk, orders, limitations.
- **Run Result**: Persisted local artifact summary.

## Success Criteria

- **SC-001**: Weekday schedule generation creates expected 10-minute timestamps and planning tags.
- **SC-002**: Native SD from `range_bands.json` produces `sd_source=cme_native`.
- **SC-003**: Future 4500 and traded 4470 maps CME 4520 to 4490.
- **SC-004**: Long and short 2SD/1SD/2.5SD plans are produced as research-only records.
- **SC-005**: Missing risk inputs block recovery sizing rather than inventing size.
- **SC-006**: API and CLI runs return persisted artifacts with `signal_allowed=false`.

## Assumptions

- Yahoo Finance is a research fallback only and is optional.
- Gamma/GEX remains skipped when unavailable.
- Frontend display is a later slice unless explicitly requested.
