# Research: XAU Forward Research Journal

**Date**: 2026-05-14  
**Feature**: 015-xau-forward-research-journal

## Decision: Build A Forward Journal Instead Of A Historical Backtest

**Decision**: Treat this feature as forward evidence collection. Each entry records a real snapshot and later outcome labels. It must not claim historical full-strategy backtest coverage.

**Rationale**: The project does not have historical QuikStrike strike-level OI snapshots. A full OI-wall historical backtest would require data that was not captured. Forward journaling creates verifiable evidence from today onward while preserving what was known at snapshot time.

**Alternatives considered**:

- Reconstruct historical OI walls from incomplete sources: rejected because it would fabricate or overstate evidence.
- Use proxy OHLC-only data as a substitute for historical strike-level OI: rejected because it cannot represent historical option-wall structure.
- Wait for paid vendors: rejected for this feature because the no-paid-vendor path is explicitly required.

## Decision: Reuse Existing Report IDs As Source Provenance

**Decision**: A journal entry references existing report ids from Vol2Vol, Matrix, Fusion, XAU Vol-OI, and XAU Reaction outputs instead of copying full source data into the journal.

**Rationale**: The existing report ids already carry local artifact provenance, source limitations, and report statuses. Referencing them keeps the journal compact and traceable while avoiding duplication of large generated artifacts.

**Alternatives considered**:

- Copy every source row into each journal entry: rejected because it duplicates generated report data and makes artifact size grow quickly.
- Store only human notes and no report ids: rejected because it would lose reproducibility.
- Require all source reports to be completed with no warnings: rejected because real local research runs can be partial; warnings should be visible rather than hidden.

## Decision: Make Snapshot Observations Immutable

**Decision**: Journal entry snapshot fields should not be overwritten by later outcome updates. Outcome windows and notes can be updated separately.

**Rationale**: The journal must preserve what was known at capture time. Mutating snapshot observations after outcomes are known would damage forward-evidence integrity.

**Alternatives considered**:

- Allow full entry edits: rejected because it makes it unclear whether evidence was recorded before or after the outcome.
- Create a new journal entry for every outcome update: rejected because it fragments one snapshot across multiple records.

## Decision: Store Outcome Windows As Conservative Research Annotations

**Decision**: Outcome windows support `30m`, `1h`, `4h`, `session_close`, and `next_day`. Labels are controlled values and may remain `pending` or `inconclusive`.

**Rationale**: These windows cover immediate, intraday, session, and next-day behavior without implying a trade lifecycle. Controlled labels keep later analysis consistent, and pending/inconclusive states avoid fabricated labels when price data is missing.

**Alternatives considered**:

- Use arbitrary custom windows only: rejected because aggregation becomes hard to compare across snapshots.
- Require all windows before saving outcomes: rejected because forward evidence often arrives incrementally.
- Force a non-pending label for every window: rejected because missing or insufficient candles must remain visible.

## Decision: Validate OHLC Observations But Do Not Fabricate Candles

**Decision**: Outcome updates may include supplied OHLC values and observation metadata. The journal validates shape and timestamps, but missing windows stay pending or inconclusive.

**Rationale**: The journal can evaluate outcomes only from data that exists. It should be possible to attach later OHLC observations from approved local research sources, but the feature must not synthesize missing candles.

**Alternatives considered**:

- Auto-download all outcome candles inside the journal: rejected for the first version because data-source selection and gaps should remain explicit.
- Infer missing highs/lows from close-only data: rejected because wall acceptance/rejection labels need range information.

## Decision: Use Local Ignored Report Persistence

**Decision**: Persist generated journal entries under `data/reports/xau_forward_journal/` or `backend/data/reports/xau_forward_journal/` using JSON/Markdown plus metadata.

**Rationale**: Existing XAU and QuikStrike features already use ignored local report roots. The journal should follow that pattern and remain local-only.

**Alternatives considered**:

- Store entries in a database: rejected because v0 storage avoids PostgreSQL/ClickHouse and the feature does not need a server database.
- Store entries in tracked docs: rejected because generated research artifacts must not be committed.

## Decision: Dashboard Inspection Only

**Decision**: Extend `/xau-vol-oi` with a Forward Journal inspection section that lists entries, linked reports, top walls/reactions, missing context, outcomes, notes, and disclaimers.

**Rationale**: The journal is part of the XAU research workflow and should be visible where QuikStrike fusion and XAU reports are inspected. The dashboard should support review, not execution.

**Alternatives considered**:

- Create a separate new dashboard route immediately: rejected because the XAU workflow already lives under `/xau-vol-oi`.
- Add controls that resemble trading decisions: rejected because this feature is research-only.

## Decision: Explicit Forbidden-Scope Guardrails

**Decision**: Requests, notes, outputs, and dashboard text must avoid secret/session material, endpoint replay material, execution behavior, and performance claims.

**Rationale**: The journal touches real local QuikStrike-derived artifacts and later price outcomes. Strong guardrails prevent accidental evolution into execution, credential storage, or unsupported strategy claims.

**Alternatives considered**:

- Rely on user discipline only: rejected because automated tests should enforce the boundary.
- Allow private/session metadata for audit: rejected because the project explicitly forbids storing that material.
