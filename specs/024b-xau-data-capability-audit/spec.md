# Feature Specification: XAU Data Capability Audit

**Feature Branch**: `codex/xau-vol-oi-research-pipeline`
**Created**: 2026-06-07
**Status**: Draft
**Input**: User requested Feature 024B to audit current CME/QuikStrike data readiness for OI, OI change, volume, volatility, SD ranges, Greeks, and GEX possibility while staying research-only.

## User Scenarios & Testing

### User Story 1 - Inventory Current Data Capabilities (Priority: P1)

As an XAU researcher, I want a local audit of saved CME/QuikStrike and XAU artifacts so that I can see which fields are actually present before building more research logic.

**Why this priority**: The next research features depend on knowing whether source artifacts contain OI, OI change, volume, volatility, DTE, native SD, delta, gamma, and GEX prerequisites.

**Independent Test**: Given local Vol2Vol and Matrix fixture reports, the audit marks source-backed OI, OI change, and DTE as available while leaving missing fields unavailable.

**Acceptance Scenarios**:

1. Given saved Vol2Vol, Matrix, Fusion, or XAU Vol-OI reports, when the audit runs, then it returns one capability result per required field.
2. Given a capability is present in at least one audited artifact, when the result is inspected, then it includes source type, report ID, field names, row count, and non-null count.
3. Given a capability is not present, when the result is inspected, then it is marked unavailable or blocked with a clear limitation.

### User Story 2 - Distinguish Partial And Blocked Capabilities (Priority: P2)

As an XAU researcher, I want partial fields and blocked derived capabilities to be explicit so that downstream features do not treat weak data as complete.

**Why this priority**: Matrix volume and XAU Vol-OI volume may exist without being intraday-qualified, while GEX is impossible without source-backed gamma and open interest.

**Independent Test**: Given volume without intraday qualification, the audit marks intraday volume partial; given no gamma, GEX is blocked even when OI is available.

**Acceptance Scenarios**:

1. Given only non-intraday-qualified volume, when the audit runs, then `has_intraday_volume` is partial with a limitation.
2. Given OI but no gamma, when the audit runs, then `has_gex_possible` is blocked.
3. Given source-backed gamma and OI, when the audit runs, then `has_gex_possible` is available without calculating a GEX signal.

### User Story 3 - Preserve Research-Only Guardrails (Priority: P3)

As the project owner, I want the audit endpoint to prove data readiness only, not produce trade signals, so that the project stays inside v0 research constraints.

**Why this priority**: Capability readiness can inform future research work, but it must not become a live-trading or signal layer.

**Independent Test**: Calling the audit endpoint always returns `research_only=true`, `signal_allowed=false`, and no-signal reasons.

**Acceptance Scenarios**:

1. Given any audit request, when the response is returned, then `signal_allowed` is false.
2. Given the response contains missing or available capabilities, when the result is inspected, then no buy/sell, entry, alert, order, PnL, or position-sizing instruction exists.

## Edge Cases

- No local reports exist for one or more source types.
- A requested report ID is unreadable, legacy-shaped, or missing.
- A field exists but all values are null.
- Volume exists but cannot be proven to be intraday volume.
- Native SD is present only in a sidecar or fusion expected-range snapshot.
- Delta or gamma exists only in local XAU import rows, not QuikStrike normalized rows.

## Requirements

- **FR-001**: The system MUST audit saved local Vol2Vol, Matrix, Fusion, and XAU Vol-OI reports without fetching fresh external data.
- **FR-002**: The system MUST report statuses for `has_oi`, `has_oi_change`, `has_intraday_volume`, `has_vol`, `has_vol_chg`, `has_future_chg`, `has_dte`, `has_future_reference`, `has_native_sd`, `has_delta`, `has_gamma`, `has_delta_ranges`, `has_sd_ranges`, and `has_gex_possible`.
- **FR-003**: The system MUST include source evidence with source type, report ID, field names, row count, non-null count, and sample values when available.
- **FR-004**: The system MUST mark missing fields unavailable rather than infer or fabricate them.
- **FR-005**: The system MUST mark GEX possibility available only when source-backed gamma and OI are both available.
- **FR-006**: The system MUST mark volume partial when the audited source exposes volume but does not prove intraday-volume qualification.
- **FR-007**: The system MUST return source report summaries and top-level limitations.
- **FR-008**: The system MUST keep every response `research_only=true` and `signal_allowed=false`.
- **FR-009**: The feature MUST NOT implement live trading, paper trading, alerts, broker access, order routing, PnL, position sizing, automatic trade placement, buy/sell instructions, ML training, or profitability claims.

## Key Entities

- **Capability Audit Request**: Optional local reports directory, optional report ID filters, maximum reports per source, and research-only acknowledgement.
- **Source Summary**: One audited source artifact with source type, report ID, status, row count, artifact paths, and limitations.
- **Capability Result**: One required capability with status, aggregate counts, evidence, and limitations.
- **Capability Evidence**: Source-backed proof for a capability.
- **Audit Result**: Overall readiness, source summaries, capability results, missing capabilities, blocked capabilities, limitations, and research-only guardrails.

## Success Criteria

- **SC-001**: A fixture audit over saved Vol2Vol and Matrix reports marks OI, OI change, and DTE as available.
- **SC-002**: A fixture audit without gamma marks gamma unavailable and GEX blocked.
- **SC-003**: A fixture audit with source-backed gamma and OI marks delta, gamma, and GEX possibility available.
- **SC-004**: The local API endpoint returns a complete research-only audit response with `signal_allowed=false`.
- **SC-005**: Code and docs review finds no PnL, execution, alert, order, broker, position-sizing, live-readiness, predictive-proof, or profitability behavior.

## Assumptions

- The audit reads existing local artifacts only.
- Fresh CME/QuikStrike capture and price-provider automation are later features.
- GEX calculation is a later feature and remains blocked unless source-backed gamma and OI are available.
- Frontend display for this audit is a later feature.
