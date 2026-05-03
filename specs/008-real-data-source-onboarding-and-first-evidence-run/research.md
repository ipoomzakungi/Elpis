# Phase 0 Research: Real Data-Source Onboarding And First Evidence Run

## Decision 1: Use `backend/src/data_sources/`

**Decision**: Implement the feature under `backend/src/data_sources/` with schemas in `backend/src/models/data_sources.py` and API routes in `backend/src/api/routes/data_sources.py`.

**Rationale**: The public workflow and endpoint names are data-source oriented. The module is focused on readiness, capability labeling, preflight, and first-run delegation rather than generic provider implementation.

**Alternatives considered**:

- `backend/src/data_onboarding/`: accurate but less aligned with endpoint names.
- Extend `backend/src/providers/`: rejected because providers fetch data, while this feature inspects readiness and orchestrates evidence.
- Extend `backend/src/research_execution/`: rejected for foundation services because readiness and capability matrix concerns should remain reusable before execution.

## Decision 2: Static Capability Matrix With Provider Metadata Enrichment

**Decision**: Store the canonical capability matrix in `backend/src/data_sources/capabilities.py`, optionally enriching public provider rows with metadata from the feature 002 provider registry.

**Rationale**: Optional vendor capabilities and unsupported-source rules are product constraints, not live provider calls. A static matrix is deterministic and easy to test. Provider metadata enrichment keeps Binance/Yahoo/local provider details aligned without making onboarding depend on external downloads.

**Alternatives considered**:

- Dynamic probing of all providers: rejected because readiness must be fast, deterministic, and no-key by default.
- Hardcode capabilities directly in API routes: rejected because unit tests and frontend reuse need a central service.

## Decision 3: Presence-Only Optional Key Detection

**Decision**: Detect optional paid provider configuration through a fixed environment variable allowlist and return only configured/missing booleans.

**Rationale**: The feature must support optional research vendor keys without leaking secrets. Returning variable names and boolean presence is enough for onboarding.

**Rejected behavior**:

- Returning secret values, prefixes, suffixes, hashes, or masked strings.
- Accepting private trading, broker, wallet, or execution key categories.
- Requiring paid keys for the MVP workflow.

## Decision 4: Public/Local MVP Remains Non-Blocking Without Paid Vendors

**Decision**: Missing Kaiko, Tardis, CoinGlass, CryptoQuant, and CME/QuikStrike optional provider keys are reported as unavailable but do not fail the public/local MVP preflight.

**Rationale**: The first evidence workflow must be usable with Binance public data, Yahoo OHLCV/proxy data, and local XAU files. Optional vendor absence should produce limitations and next actions, not a hard failure.

## Decision 5: First Evidence Run Delegates To Feature 007

**Decision**: `backend/src/data_sources/first_run.py` translates onboarding preflight state into a `ResearchExecutionRunRequest` and delegates to `ResearchExecutionOrchestrator`.

**Rationale**: Feature 007 already owns evidence workflow orchestration, final evidence summaries, and report persistence. This feature should not duplicate strategy, validation, or evidence logic.

**Boundary**:

- Data-source module checks readiness and constructs a request.
- Research execution module runs or records crypto, proxy, and XAU workflows.
- Report stores remain under existing ignored report paths.

## Decision 6: XAU Local File Checks Reuse Feature 006 Validation

**Decision**: XAU local file readiness uses the existing XAU options OI import validation rules from feature 006 where possible.

**Rationale**: Feature 006 already defines required columns, optional columns, parsing behavior, and missing-data instructions for gold options OI CSV/Parquet imports. Reuse prevents divergent schema rules.

## Decision 7: Dashboard Route Is `/data-sources`

**Decision**: Add a new dashboard page at `/data-sources`.

**Rationale**: `/evidence` already shows completed research execution outputs. The new page is an operating checklist before and during the first evidence run: readiness, capability matrix, optional key presence, missing-data actions, and first-run status.

**Alternative considered**:

- Extend `/evidence`: rejected because it would mix report inspection with data-source onboarding and create a crowded surface.

## Decision 8: Generated Artifacts Stay Under Existing Ignored Paths

**Decision**: Do not introduce a new artifact root. First-run outputs should reference existing `data/reports/research_execution` artifacts or store minimal first-run wrapper metadata under ignored `data/reports`.

**Rationale**: Existing `.gitignore` and artifact guard already protect `data/reports`, `data/raw`, `data/processed`, `.env*`, Parquet, DuckDB, `.next`, `.venv`, and `node_modules`.

## Decision 9: Unsupported Capability Labels Are First-Class Outputs

**Decision**: Responses include unsupported capability labels for Yahoo proxy requests, optional vendor gaps, and forbidden credential categories.

**Rationale**: Silent omission would make real research unsafe. The dashboard and API must explain that Yahoo Finance is OHLCV/proxy-only and not a source for crypto OI, funding, gold options OI, futures OI, IV, or XAUUSD execution data.

## Decision 10: Smoke Tests May Use Synthetic Fixtures Only As Test Inputs

**Decision**: Automated and local smoke tests may create ignored synthetic processed feature and XAU local files, but final real research runs must use real public/local data.

**Rationale**: Tests need deterministic fixtures. The feature must not substitute synthetic data for real evidence.
