# Implementation Plan: Public Data Bootstrapper

**Branch**: `009-public-data-bootstrapper` | **Date**: 2026-05-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/009-public-data-bootstrapper/spec.md`

## Summary

Add a research-only public data bootstrap workflow that downloads no-key Binance crypto data and Yahoo OHLCV proxy data, writes raw and processed artifacts under ignored local data paths, records source limitations, and exposes bootstrap run status through the existing data-source onboarding surface. The implementation will add a focused `backend/src/data_bootstrap/` module, reuse provider/client and feature-processing conventions, keep XAU options OI as a local import workflow, and avoid all trading, execution, private credential, paid-vendor, and forbidden v0 technology scope.

## Technical Context

**Language/Version**: Python 3.11+ for backend data and orchestration; TypeScript with Next.js for dashboard updates
**Primary Dependencies**: FastAPI, Pydantic, Polars, Parquet/PyArrow, existing provider layer, existing Binance public client/provider behavior, existing Yahoo Finance provider behavior, existing feature engine, existing data-source preflight service
**Storage**: Local ignored file artifacts under `data/raw/`, `data/processed/`, and `data/reports/`; no database server
**Testing**: pytest for backend unit, integration, and contract tests; frontend production build for UI/type checks; existing artifact guard script
**Target Platform**: Local research workstation and CI on Windows/Linux-compatible Python and Node environments
**Project Type**: Web application with FastAPI backend, local research files, and Next.js dashboard
**Performance Goals**: Default bootstrap planning completes immediately; mocked integration runs complete in the normal backend test suite; real public downloads preserve per-asset progress and partial results rather than failing the whole run
**Constraints**: Research-only, public/no-key data only, no secret exposure, no generated artifact commits, no external downloads during automated tests, no live/paper/shadow trading, no broker/wallet/order execution, no forbidden v0 technologies
**Scale/Scope**: Default assets are BTCUSDT, ETHUSDT, SOLUSDT, SPY, QQQ, GLD, and GC=F; optional assets are BNBUSDT, XRPUSDT, DOGEUSDT, and BTC-USD; timeframes are crypto 15m/1h/1d and Yahoo 1d

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Research-First Architecture**: PASS. The feature prepares reproducible research data and reports only; it does not add execution behavior.
- **Language Split**: PASS. Python remains the backend research/orchestration language; TypeScript remains UI-only; no Rust is introduced.
- **Frontend Stack**: PASS. Dashboard work stays in the existing Next.js/TypeScript/Tailwind app.
- **Backend Stack**: PASS. FastAPI and Pydantic schemas remain the API boundary; Polars and Parquet remain data-processing and file-output primitives.
- **Data Processing**: PASS. Processed feature files must be timestamp-safe, provider-labeled, and compatible with existing preflight checks.
- **Storage v0**: PASS. Raw data, processed features, and reports stay under local `data/` paths using Parquet/JSON/Markdown where appropriate.
- **Event Architecture v0**: PASS. No Kafka, Redpanda, NATS, Kubernetes, microservice split, or streaming platform is introduced.
- **Data-Source Principle**: PASS. Public official/provider-backed data is used first; Yahoo remains OHLCV-only; XAU options OI remains local import.
- **Live Trading Principle**: PASS. No live, paper, shadow, broker, wallet, account, or order-execution behavior is introduced.

No constitution violations require complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/009-public-data-bootstrapper/
+-- plan.md
+-- research.md
+-- data-model.md
+-- quickstart.md
+-- contracts/
|   +-- api.md
+-- tasks.md
```

### Source Code (repository root)

```text
backend/
+-- src/
|   +-- data_bootstrap/
|   |   +-- __init__.py
|   |   +-- binance_public.py
|   |   +-- yahoo_public.py
|   |   +-- processing.py
|   |   +-- orchestration.py
|   |   +-- report_store.py
|   +-- models/
|   |   +-- data_bootstrap.py
|   +-- api/
|       +-- routes/
|           +-- data_bootstrap.py or data_sources.py
+-- tests/
    +-- unit/
    |   +-- test_data_bootstrap_binance.py
    |   +-- test_data_bootstrap_yahoo.py
    |   +-- test_data_bootstrap_processing.py
    +-- integration/
    |   +-- test_data_bootstrap_flow.py
    +-- contract/
        +-- test_data_sources_api_contracts.py

frontend/
+-- src/
    +-- app/
    |   +-- data-sources/
    |       +-- page.tsx
    +-- services/
    |   +-- api.ts
    +-- types/
        +-- index.ts
```

**Structure Decision**: Use a focused backend `data_bootstrap` package for new public bootstrap responsibilities. Keep the public URL shape under `/api/v1/data-sources/bootstrap/...` so feature 008 dashboard and preflight flows remain the user-facing data-source surface. If existing 008 bootstrap code remains in `src/data_sources/bootstrap.py`, migrate or wrap it so `src/data_bootstrap` is canonical and `data_sources` only integrates/routes.

## Complexity Tracking

No constitution or architecture violations are introduced.
