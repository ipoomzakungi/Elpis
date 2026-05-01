# Feature Specification: XAU Vol-OI Wall Engine

**Feature Branch**: `006-xau-vol-oi-wall-engine`  
**Created**: 2026-05-01  
**Status**: Draft  
**Input**: User description: "Add an XAU volatility and open-interest wall engine."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Gold Derivatives Research Data (Priority: P1)

A researcher can import or select local gold options and futures-derived datasets, pair them with XAUUSD spot or proxy price references, and see whether the required fields are usable before any wall analysis is calculated.

**Why this priority**: The feature is only meaningful if the system can verify source data and clearly explain when CME/COMEX-style options OI, implied volatility, basis, or spot references are missing.

**Independent Test**: Can be fully tested by loading one sample options OI dataset plus spot and futures references, then verifying the system accepts the usable inputs and produces missing-data instructions for absent optional fields.

**Acceptance Scenarios**:

1. **Given** a local gold options OI dataset with strikes, expiries, OI, and timestamps plus spot and futures references, **When** the researcher starts an XAU wall analysis, **Then** the system validates the inputs and records source freshness, date/session, expiry coverage, and limitations.
2. **Given** implied volatility or recent OI-change data is missing, **When** the researcher starts analysis, **Then** the system marks the affected range or freshness components unavailable instead of inventing values.
3. **Given** only Yahoo Finance GC=F or GLD OHLCV proxy data is available, **When** the researcher requests options OI wall analysis, **Then** the system explains that those sources are OHLCV proxies only and provides instructions for importing gold options OI and volatility data.

---

### User Story 2 - Map Futures Strikes To Spot-Equivalent Levels (Priority: P2)

A researcher can convert futures/options strike levels into XAUUSD spot-equivalent levels using an explicit futures-to-spot basis adjustment so gold derivatives zones can be compared with spot price charts.

**Why this priority**: Gold options strikes are futures-based while many researchers inspect XAUUSD spot. Without basis adjustment, wall levels can be misleading.

**Independent Test**: Can be tested by providing a futures strike, a futures reference price, and a spot reference price, then verifying the adjusted spot-equivalent level follows the documented basis formula.

**Acceptance Scenarios**:

1. **Given** a futures strike of 2400, a futures reference of 2410, and a spot reference of 2403, **When** the system computes the spot-equivalent level, **Then** it uses a basis of 7 and outputs 2393.
2. **Given** no reliable basis input exists, **When** the system attempts to create wall levels, **Then** it marks spot-equivalent mapping unavailable and explains which reference data is required.
3. **Given** multiple expiries are present, **When** levels are mapped, **Then** each mapped wall keeps its source expiry, strike, basis, and spot-equivalent level.

---

### User Story 3 - Classify Research Zones With Transparent Scores (Priority: P3)

A researcher can turn basis-adjusted wall levels, volatility ranges, expiry weights, and freshness evidence into transparent research zones such as support candidate, resistance candidate, pin-risk zone, squeeze-risk zone, breakout candidate, reversal candidate, or no-trade zone.

**Why this priority**: The core value is not raw OI display; it is an explainable research interpretation that distinguishes wall types and risk zones without treating them as buy/sell signals.

**Independent Test**: Can be tested with a small dataset containing put/call OI, expiry, IV, and volume-change evidence, then verifying wall score, freshness score, expiry weight, expected range, and zone labels are computed and explained.

**Acceptance Scenarios**:

1. **Given** strike OI, total OI, expiry distance, and recent OI-change or volume evidence, **When** the system scores a wall, **Then** it shows the wall score components and final score.
2. **Given** IV is available, **When** the system computes a volatility range, **Then** it reports an IV-based expected move and 1SD range and labels that range as IV-based.
3. **Given** IV is unavailable but realized volatility or a manually imported expected range is available, **When** the range is shown, **Then** the system labels the range source clearly.
4. **Given** the evidence is stale, incomplete, or contradictory, **When** a zone is classified, **Then** the system lowers confidence, includes limitation notes, or marks the area as a no-trade zone.

---

### User Story 4 - Inspect XAU Wall Reports (Priority: P4)

A researcher can review an XAU Vol-OI report in the dashboard or saved report view, including selected session, spot/futures references, basis, expected range, wall table, zone classification table, scores, source limitations, and no-trade warnings.

**Why this priority**: The wall engine must be inspectable by researchers without implying profitability, predictive power, safety, or live readiness.

**Independent Test**: Can be tested by opening a saved XAU wall report and verifying all wall, range, limitation, and disclaimer sections render for a sample dataset and for a missing-data case.

**Acceptance Scenarios**:

1. **Given** a completed wall analysis exists, **When** the researcher opens the report, **Then** the report displays the selected date/session, spot reference, futures reference, basis, 1SD range, and wall levels.
2. **Given** zone classifications exist, **When** the report is viewed, **Then** each zone includes its classification, wall score, freshness score, expiry weight, put/call wall type, notes, and limitations.
3. **Given** required OI or volatility data is missing, **When** the report is viewed, **Then** the missing-data panel explains what must be imported and does not hide the unavailable sections.

### Edge Cases

- The options dataset has duplicate strike/expiry rows for the same session.
- The options dataset contains strikes but no put/call split.
- The selected expiry has very low total OI, making OI share unstable.
- The futures and spot references have mismatched timestamps or stale prices.
- The futures-to-spot basis is negative, unusually large, or manually supplied.
- IV is missing, stale, zero, or expressed in an unexpected annualization convention.
- Realized volatility is available but IV is not.
- OI change or intraday volume is unavailable, so freshness must be neutral or unavailable.
- Multiple expiries produce nearby but conflicting wall levels.
- Yahoo Finance GC=F or GLD data is present without true gold options OI or XAUUSD spot data.
- The analysis is requested for live or execution use; the system must refuse that interpretation and keep the result research-only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support a research-only XAU/gold wall analysis workflow using XAUUSD spot or proxy prices, gold futures references, futures-to-spot basis, and gold options OI by strike and expiry.
- **FR-002**: The system MUST validate required inputs before analysis and report whether spot/proxy prices, futures references, basis, OI, expiry, IV, realized volatility, OI change, volume, and put/call split are present or missing.
- **FR-003**: The system MUST allow local imported gold options datasets in tabular file form for CME/COMEX or QuikStrike-style research inputs.
- **FR-004**: The system MUST provide missing-data instructions when options OI, IV, basis, spot references, or futures references are unavailable.
- **FR-005**: The system MUST NOT treat Yahoo Finance GC=F, GLD, or similar proxy OHLCV sources as providers of gold options OI, futures OI, implied volatility, or XAUUSD spot execution data.
- **FR-006**: The system MUST map each futures/options strike to a spot-equivalent level using `spot_equivalent_level = futures_strike - futures_spot_basis`.
- **FR-007**: The system MUST define `futures_spot_basis` as the gold futures reference price minus the XAUUSD spot or selected proxy reference price, unless the researcher supplies an explicit manual basis.
- **FR-008**: The system MUST preserve the original futures strike, expiry, source session, basis value, and spot-equivalent level for every mapped wall.
- **FR-009**: The system MUST compute wall score using transparent components that include OI share, expiry weight, and freshness factor.
- **FR-010**: The system MUST make the wall score formula and component values visible in reports so researchers can audit the result.
- **FR-011**: The system MUST compute OI share as strike OI divided by total OI for the selected expiry or analysis window.
- **FR-012**: The system MUST assign higher expiry weight to nearer expiries while showing the selected expiry weighting rule.
- **FR-013**: The system MUST increase, decrease, or mark unavailable the freshness factor based on available OI change or intraday volume evidence.
- **FR-014**: The system MUST classify wall type as put wall, call wall, mixed wall, or unknown when put/call split is unavailable.
- **FR-015**: The system MUST compute an IV-based expected move and 1SD range when IV and time-to-expiry are available.
- **FR-016**: The system SHOULD compute a 2SD stress range when the required volatility inputs are available.
- **FR-017**: The system MUST clearly label expected ranges as IV-based, realized-volatility-based, manually imported, or unavailable.
- **FR-018**: The system MUST NOT invent IV-based ranges when IV is missing.
- **FR-019**: The system MUST produce basis-adjusted OI wall levels, wall score, freshness score, expiry weight, put/call wall classification, pin-risk score, squeeze-risk score, zone classification, notes, and limitations.
- **FR-020**: The system MUST support zone classifications of support candidate, resistance candidate, pin-risk zone, squeeze-risk zone, breakout candidate, reversal candidate, and no-trade zone.
- **FR-021**: The system MUST document that 1SD levels and OI walls are research zones, not standalone buy/sell signals.
- **FR-022**: The system MUST save XAU wall reports with input metadata, source freshness, basis details, expected range, wall table, zone table, warnings, and limitation notes.
- **FR-023**: The dashboard/report view MUST show selected date/session, spot and futures references, futures-spot basis, expected range, wall table, zone classification table, scores, put/call type, limitations, and no-trade warnings.
- **FR-024**: The system MUST keep generated XAU wall reports and imported research datasets out of version control.
- **FR-025**: The system MUST NOT add live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, Rust execution, new analytical infrastructure, orchestration platforms, or model training.
- **FR-026**: Reports and dashboards MUST NOT claim profitability, predictive power, safety, or live readiness.

### Key Entities

- **XAU Wall Analysis Run**: A research run for one selected date/session containing input metadata, data-readiness status, basis details, wall levels, volatility ranges, zones, warnings, and generated report references.
- **Gold Options OI Dataset**: A local or imported research dataset containing strike, expiry, open interest, timestamp/session, and optional OI change, volume, IV, and put/call split.
- **Spot/Futures Reference Pair**: The spot or proxy price reference and gold futures reference used to calculate futures-to-spot basis.
- **Basis Adjustment**: The explicit difference between futures and spot/proxy references used to convert futures strikes into spot-equivalent levels.
- **OI Wall Level**: A strike-derived level with original strike, expiry, OI, OI share, basis, spot-equivalent level, wall type, score components, freshness, and limitations.
- **Volatility Range**: An expected move and range labeled by source: IV-based, realized-volatility-based, manually imported, or unavailable.
- **XAU Research Zone**: A classified price area such as support candidate, resistance candidate, pin-risk zone, squeeze-risk zone, breakout candidate, reversal candidate, or no-trade zone.
- **Source Limitation**: A documented boundary explaining missing true options OI, missing IV, stale basis, proxy-only OHLCV data, or unsupported execution interpretation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can load a local sample gold options OI dataset and receive a completed wall-analysis report in under 2 minutes on a local workstation.
- **SC-002**: 100% of wall levels in a completed report include both original futures strike and basis-adjusted spot-equivalent level.
- **SC-003**: Given known futures, spot, and strike values, the basis-adjusted level matches the documented formula exactly within normal decimal rounding.
- **SC-004**: At least 95% of valid sample rows with required strike, expiry, and OI fields are accepted into the wall table, while invalid rows are reported with row-level or summary validation notes.
- **SC-005**: When IV is available, the report includes a labeled 1SD expected range; when IV is unavailable, the report marks the IV-based range unavailable with no fabricated value.
- **SC-006**: Every completed report includes wall score, OI share, expiry weight, freshness score, put/call wall type, zone classification, and limitation notes for each wall or explains why a value is unavailable.
- **SC-007**: Missing OI, IV, basis, spot, or futures inputs produce actionable missing-data instructions in 100% of blocked analyses.
- **SC-008**: The dashboard/report view displays the selected session, references, basis, expected range, wall table, zone table, limitation notes, and research-only disclaimer for a sample completed report.
- **SC-009**: Yahoo Finance GC=F and GLD are labeled as OHLCV proxies only in every report where they are used.
- **SC-010**: Generated XAU reports and imported research datasets remain excluded from version control after a completed smoke run.

## Assumptions

- The first version uses local or manually imported gold options/futures research datasets when institutional CME/QuikStrike/COT feeds are not available.
- XAUUSD spot may be represented by a direct spot series when available or by a clearly labeled proxy reference for research comparison only.
- GC=F and GLD are acceptable OHLCV proxies for context but not sources of gold options OI, implied volatility, or XAUUSD spot execution data.
- The default wall score uses OI share, expiry weight, and freshness factor because those components are transparent and auditable.
- Expiry weighting and freshness rules may be configurable later, but the first version must expose the chosen formula and component values.
- Zone classifications are research annotations and must be combined with broader validation before any future trading work is considered.
- This feature depends on the existing provider, local file, reporting, and dashboard conventions from earlier Elpis research-platform features.
