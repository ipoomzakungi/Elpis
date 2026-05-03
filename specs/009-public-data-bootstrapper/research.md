# Research: Public Data Bootstrapper

## Decision 1: Focused `data_bootstrap` Package

**Decision**: Create `backend/src/data_bootstrap/` as the canonical home for public bootstrap planning, downloads, processing, orchestration, and report persistence.

**Rationale**: Feature 008 owns source readiness and first evidence run orchestration. Feature 009 is a separate data-preparation workflow and should not grow `data_sources` into a mixed readiness/download module. A focused package keeps boundaries clear while still allowing existing data-source endpoints to delegate to it.

**Alternatives considered**:

- Extend `backend/src/data_sources/bootstrap.py` directly. Rejected because the user explicitly requested `backend/src/data_bootstrap/` and the feature deserves a narrower boundary.
- Put bootstrap logic inside providers. Rejected because providers should fetch/normalize source data, while bootstrap orchestration needs reporting, path safety, preflight bridging, and partial-run behavior.

## Decision 2: Reuse Provider/Client Behavior Where Practical

**Decision**: Use existing provider-layer conventions and existing Binance/Yahoo client behavior where practical, while keeping provider-specific public endpoint details inside `binance_public.py` and `yahoo_public.py`.

**Rationale**: Feature 002 established provider abstraction and capability metadata. The bootstrapper should not hardcode provider details into feature processing, evidence orchestration, or dashboard code.

**Alternatives considered**:

- Implement a generic downloader in orchestration. Rejected because it would mix provider specifics with run aggregation.
- Add paid vendor providers for deeper history. Rejected because the feature is explicitly public/no-key and paid vendor keys are not required.

## Decision 3: Raw And Processed Output Contract

**Decision**: Write raw public downloads under `data/raw/{provider}/` and processed feature files under `data/processed/{symbol}_{timeframe}_features.parquet`.

**Rationale**: Feature 008 preflight already expects local processed features and the user specifically requires these paths. Persisted raw files allow inspection and reproducibility; processed files make first evidence runs ready without manual path edits.

**Alternatives considered**:

- Store only processed files. Rejected because raw downloads are needed for reproducibility and audit.
- Store under feature-specific report folders only. Rejected because downstream preflight checks expect `data/processed`.

## Decision 4: Processing Uses Existing Feature Conventions

**Decision**: Normalize OHLCV, optional OI, and optional funding into the existing feature-processing shape, producing enough columns for feature 008 and 007 readiness where possible.

**Rationale**: The bootstrapper should not invent strategy logic or evidence logic. It should prepare the expected feature files and let existing research and evidence systems decide readiness and research outcomes.

**Alternatives considered**:

- Create synthetic features when derivatives fields are missing. Rejected because the platform must not substitute invented data for real research inputs.
- Require OI/funding for all assets. Rejected because Yahoo is OHLCV-only and Binance public derivatives history may be limited.

## Decision 5: Source Limitation Labels Are First-Class Results

**Decision**: Store source limitations and unsupported capabilities with each asset result and in the run-level summary.

**Rationale**: Binance public OI/funding can be shallow or unavailable, Yahoo is OHLCV-only, and XAU options OI remains local import. These limitations affect research interpretation and must remain visible in API and dashboard flows.

**Alternatives considered**:

- Log warnings only. Rejected because warnings would be easy to miss and unavailable to the dashboard.
- Fail the whole bootstrap when optional derivatives fields are missing. Rejected because OHLCV assets can still prepare useful baseline/proxy data.

## Decision 6: Tests Use Mocked Public Providers

**Decision**: Automated tests must not perform real external downloads. Unit and integration tests use mocked Binance/Yahoo responses and synthetic local data.

**Rationale**: Tests must be deterministic, CI-safe, and independent of public endpoint availability, rate limits, or network conditions.

**Alternatives considered**:

- Smoke-test live public endpoints in CI. Rejected because external availability and rate limits would make CI unstable.

## Decision 7: API Stays Under Data-Source Bootstrap Paths

**Decision**: Expose public bootstrap endpoints at `/api/v1/data-sources/bootstrap/public`, `/api/v1/data-sources/bootstrap/runs`, and `/api/v1/data-sources/bootstrap/runs/{bootstrap_run_id}`.

**Rationale**: Feature 008 already made data-source onboarding the user-facing readiness surface. Keeping bootstrap under that path avoids a parallel navigation concept while allowing implementation to live in `data_bootstrap`.

**Alternatives considered**:

- Create `/api/v1/data-bootstrap/...`. Rejected because it fragments the data-source onboarding API.

## Decision 8: No Paid Keys Or Execution Credentials

**Decision**: Optional paid provider key detection can remain visible from 008, but the 009 public bootstrap workflow does not require or use paid provider keys and never accepts private trading, broker, wallet, or execution credentials.

**Rationale**: The user explicitly chose free/no-paid-vendor data only for the next data-gathering capability.

**Alternatives considered**:

- Add optional paid vendor download branches. Rejected because it violates the user's selected MVP path for this feature.
