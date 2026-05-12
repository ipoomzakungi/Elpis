# Research: Free Public Derivatives Data Expansion

**Date**: 2026-05-12  
**Feature**: 011-free-public-derivatives-data-expansion

## Decision: Add A Focused `free_derivatives` Backend Package

Add `backend/src/free_derivatives/` for CFTC, GVZ, Deribit, processing, orchestration, and report persistence. Integrate readiness and missing-data status through existing `backend/src/data_sources/` services rather than moving existing 008/009 code.

**Rationale**: The feature has source-specific parsing and processing that is larger than a static readiness entry, but its user-facing workflow belongs under the existing data-source bootstrap surface.

**Alternatives considered**:

- Put all logic under `backend/src/data_sources/free_derivatives/`: rejected because the existing `data_sources` package already owns readiness/preflight concerns and would become too broad.
- Extend `backend/src/data_bootstrap/` only: rejected because 009 remains OHLCV/feature bootstrap focused, while this feature introduces derivatives-specific raw and processed outputs.

## Decision: Store Schemas In `backend/src/models/free_derivatives.py`

Create a new schema module for free-derivatives request, result, source, row, and artifact models. Add only the provider enum entries needed in `backend/src/models/data_sources.py`.

**Rationale**: The models are specific enough to warrant a dedicated module, while readiness provider types still belong in the existing data-source model.

**Alternatives considered**:

- Add all models to `models/data_sources.py`: rejected because that file already contains feature 008/009 onboarding models.
- Reuse 009 bootstrap result models directly: rejected because CFTC/GVZ/Deribit need different source statuses, row shapes, and artifact types.

## Decision: CFTC COT Is Weekly Broad Gold Positioning Only

Use CFTC public historical compressed reports or fixture/local import. Filter gold/COMEX-relevant rows and preserve futures-only versus futures-and-options combined categories as separate labels.

**Rationale**: CFTC COT is official and free, but it is weekly broad positioning. It cannot replace intraday XAU OI, CME strike-level options OI, or feature 006 wall construction.

**Alternatives considered**:

- Treat CFTC as a gold options OI source: rejected because it does not provide strike-level wall data.
- Merge futures-only and futures-and-options rows into one series: rejected because users must know which report category they are viewing.

## Decision: GVZ Is A Gold ETF Options Volatility Proxy

Use public GVZ daily close data where available, with fixture/local import support for tests and offline validation. Label the processed series as a GLD-options-derived volatility proxy.

**Rationale**: GVZ helps provide free volatility context when full CME gold options IV is unavailable, but it is not the CME gold options IV surface used for exact expected-range modeling.

**Alternatives considered**:

- Treat GVZ as gold IV for the XAU reaction engine: rejected because it is a proxy and must not be overclaimed.
- Require a paid volatility vendor: rejected because the feature goal is free/no-paid-vendor coverage.

## Decision: Deribit Uses Public Crypto Options Market Data Only

Normalize public Deribit option instruments and market summaries for supported crypto underlyings. Capture public IV/OI fields where available and explicitly avoid private/account/order methods.

**Rationale**: Deribit is a useful free crypto options testbed for option-wall logic, but it is not a gold/XAU source and must not require account access.

**Alternatives considered**:

- Add private Deribit authentication for richer data: rejected by v0 and user scope.
- Use Deribit as a direct XAU substitute: rejected because it is crypto options data only.

## Decision: Use Existing Data-Source Bootstrap URL Shape

Expose:

- `POST /api/v1/data-sources/bootstrap/free-derivatives`
- `GET /api/v1/data-sources/bootstrap/free-derivatives/runs`
- `GET /api/v1/data-sources/bootstrap/free-derivatives/runs/{run_id}`

Also extend existing readiness, capabilities, and missing-data endpoints.

**Rationale**: This keeps feature 011 aligned with feature 008/009 user workflows and avoids creating a parallel dashboard mental model.

**Alternatives considered**:

- Add top-level `/free-derivatives` endpoints: rejected because users already inspect data-source readiness under `/data-sources`.
- Merge into `/data-sources/bootstrap/public`: rejected because public OHLCV bootstrap and derivatives context bootstrap have different source controls and artifact outputs.

## Decision: Raw, Processed, And Report Outputs Stay Under Ignored `data/`

Persist raw artifacts under source-specific `data/raw/` folders, processed outputs under source-specific `data/processed/` folders, and run summaries under `data/reports/free_derivatives/`.

**Rationale**: This matches existing Elpis reproducibility and artifact-guard conventions while making the new source outputs easy to inspect.

**Alternatives considered**:

- Store results in a database: rejected because v0 uses local files and the feature must not add PostgreSQL or ClickHouse.
- Store generated artifacts in the spec directory: rejected because raw/processed/report data must remain ignored and untracked.

## Decision: Tests Use Mocked Responses And Local Fixtures Only

Automated tests must use CFTC/GVZ/Deribit fixtures or mocked HTTP responses and must not make live external downloads.

**Rationale**: CI must be deterministic and not depend on public endpoint availability, rate limits, or changing live data.

**Alternatives considered**:

- Run live source smoke tests in the backend suite: rejected because public availability is not deterministic and would slow validation.
- Skip integration tests: rejected because parser and orchestration boundaries are core to this feature.

## External Source Notes

- CFTC publishes public historical compressed COT reports, including futures-only and combined futures-and-options report downloads.
- FRED publishes `GVZCLS`, the CBOE Gold ETF Volatility Index close series.
- Deribit public documentation separates public market-data methods such as instruments/book summaries from private account and order methods.

These notes guide request planning only; automated validation remains fixture/mocked.
