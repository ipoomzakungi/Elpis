# Research: QuikStrike Local Highcharts Extractor

**Date**: 2026-05-13
**Feature**: 012-quikstrike-local-highcharts-extractor

## Decision: Use Highcharts Browser Memory As The Primary Extraction Surface

**Rationale**: The discovery spike found that the Gold `QUIKOPTIONS VOL2VOL` page renders as Highcharts SVG and keeps structured series arrays in browser memory. The tested chart exposed Put, Call, Vol Settle, and Ranges series with point x/y values and metadata. This provides a machine-readable local extraction path without relying on screenshots or image exports.

**Alternatives considered**:

- Image/PDF/SVG export: rejected for normalized research rows because the visible export menu was image/PDF/SVG oriented and did not expose CSV/Excel/JSON.
- Screenshot OCR: rejected because it is brittle, privacy-sensitive, and explicitly forbidden.
- HTML table parsing only: rejected as primary path because the target chart data is represented in Highcharts structures; table presence alone is not enough.

## Decision: Reject ASP.NET Endpoint Replay

**Rationale**: The page uses authenticated ASP.NET navigation and postback behavior with generated control ids, `__VIEWSTATE`, `__EVENTTARGET`, `__EVENTARGUMENT`, and related state. Replaying those requests would be brittle and risks capturing session-specific material. The safer local path is to let the user manually authenticate and navigate, then read sanitized browser-memory objects.

**Alternatives considered**:

- Direct POST replay: rejected due to viewstate/session sensitivity and the user's explicit prohibition.
- HAR capture and replay: rejected because HAR capture can store cookies, headers, tokens, and private URLs.
- Building a CME/QuikStrike API integration: rejected because this feature is local-only and not a vendor API integration.

## Decision: Keep Local Browser Automation Minimal And User-Controlled

**Rationale**: The extractor should not become an RPA system. The user logs in and navigates manually; any local browser adapter only validates that the current page is the supported Gold Vol2Vol surface and reads sanitized DOM/chart structures. It must not store session state, cookies, headers, HAR files, screenshots, or private full URLs.

**Alternatives considered**:

- Full browser automation for login/product navigation: rejected because it expands privacy and access-control risk.
- Stored browser profile reuse: rejected because it creates credential/session persistence concerns.
- Production scraping service: rejected because the scope is local research extraction only.

## Decision: Use Sanitized DOM Metadata For Product And Session Context

**Rationale**: The feature needs product, option code, expiration, DTE, and future reference price. These were visible in the page header and selected controls during discovery. Parsing sanitized visible text keeps the workflow auditable and avoids private request metadata.

**Alternatives considered**:

- Query parameter values: rejected as primary source because private full URLs and query values should not be persisted.
- Hidden form fields: rejected because they can include generated ASP.NET state and should not be stored.
- Manual user entry: retained only as a fallback if parsing fails, but not the primary workflow.

## Decision: Treat Strike Mapping Confidence As A Conversion Gate

**Rationale**: Highcharts points expose x/y values and `StrikeId` metadata, but downstream XAU Vol-OI analysis requires reliable strike-level meaning. The extractor should compare chart x-values, `StrikeId`, visible labels, or tooltip-derived labels where possible. If confidence is not high enough, rows may be saved as partial research artifacts but must not be converted automatically into XAU Vol-OI local input.

**Alternatives considered**:

- Always treat point x-values as strikes: rejected because the discovery called them strike-like and validation is required.
- Drop rows when strike confidence is uncertain: rejected because partial extraction reports are useful for diagnosing mapping gaps.
- Manually approve uncertain mapping: deferred; v0 should fail closed rather than rely on hidden manual overrides.

## Decision: Persist Only Normalized Rows, Conversion Output, And Reports

**Rationale**: The user explicitly requires that no secrets/session material be persisted. Allowed artifacts are normalized QuikStrike rows, optional processed XAU Vol-OI compatible rows, and extraction reports under ignored local paths.

**Alternatives considered**:

- Store raw HTML/partial response bodies: rejected because they can contain private state and hidden fields.
- Store raw Highcharts object dumps: rejected as a default because objects can contain implementation or source-specific metadata beyond needed rows.
- Store screenshots or exports: rejected because they are not needed for normalized row extraction and are explicitly sensitive/out of scope.

## Decision: Add Optional Local Status/API Contracts

**Rationale**: Existing features expose local research reports and dashboard inspection. Optional routes should accept sanitized extraction payloads, list saved extraction reports, return normalized rows, and run gated conversion. They must not initiate login, accept cookies/headers/viewstate/HAR/screenshot payloads, or replay endpoints.

**Alternatives considered**:

- No API routes: acceptable for a pure backend library, but less consistent with existing report inspection flows.
- API-driven browser automation: rejected due to privacy and RPA scope concerns.
- Dashboard-only controls: rejected as insufficient for testable contract coverage.

## Decision: Reuse Existing XAU Vol-OI Input Conventions

**Rationale**: Feature 006 already owns wall scoring. This feature should only produce compatible local input rows and source limitations. It should not duplicate wall scoring, reaction classification, or risk planning.

**Alternatives considered**:

- Add QuikStrike-specific wall scoring: rejected because it duplicates feature 006.
- Feed partial rows into XAU Vol-OI with warnings: rejected because uncertain strike mapping could corrupt wall research.
- Treat churn as OI: rejected; churn is context/freshness-style data, not open interest.
