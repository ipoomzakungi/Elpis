# Research: CME Expected Range And Context Parity

**Date**: 2026-06-04
**Feature**: 017-cme-expected-range-and-context-parity

## Decision: Treat CME-native numeric SD bands as authoritative

**Rationale**: The project goal is parity with the map a researcher sees on CME/QuikStrike. If CME-native numeric bands are captured, they should be preserved as source values rather than recomputed or overwritten.

**Alternatives considered**:

- Always compute SD bands from IV: rejected because it cannot prove UI parity when the page exposes numeric values.
- Use `range_label` as a numeric SD source: rejected because labels classify buckets and are not upper/lower price bands.

## Decision: Allow IV-derived fallback only with report-level IV, reference futures price, and fractional DTE

**Rationale**: The fallback formula is reproducible and useful when native numeric bands are absent, but only if the correct anchor inputs exist. Per-strike IV is not the same as report-level IV.

**Alternatives considered**:

- Use any available `vol_settle`: rejected because per-strike IV may differ from the report-level Vol2Vol anchor.
- Use rounded integer DTE: rejected because previous inventory work showed fractional DTE materially changes bands.

## Decision: Preserve expected-range context as an optional snapshot

**Rationale**: Existing fusion and XAU Vol-OI reports already carry source context and missing-data status. Adding an optional snapshot avoids a large rewrite while making the daily structural map possible.

**Alternatives considered**:

- Create a full daily structural map now: rejected because this feature is P0 data parity, while the daily map is the next feature.
- Add a new database table: rejected because v0 uses local report artifacts and Pydantic models.

## Decision: Keep manual CME discovery as a narrow later checklist

**Rationale**: The current session does not include an authenticated CME page. The safe next step is to document the exact visible fields to look for and enforce sanitized capture rules.

**Alternatives considered**:

- Browse randomly across CME pages: rejected because it risks wasting effort and does not target the P0 gaps.
- Store screenshots or browser session artifacts: rejected by project guardrails.
