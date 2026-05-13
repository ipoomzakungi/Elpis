# Quickstart: QuikStrike Open Interest Matrix Extractor

**Date**: 2026-05-13
**Feature**: 013-quikstrike-open-interest-matrix-extractor

## Scope

This quickstart validates the local-only, research-only matrix extraction workflow using synthetic sanitized HTML table fixtures. It does not log in to QuikStrike, replay endpoints, store credentials, store cookies, save screenshots, capture HAR files, or persist private URLs.

## Prerequisites

- Feature 012 QuikStrike Local Highcharts Extractor is already merged.
- Feature 006 XAU Vol-OI Wall Engine exists as the downstream consumer.
- No generated QuikStrike Matrix artifacts are staged.
- `data/raw/quikstrike_matrix/`, `data/processed/quikstrike_matrix/`, and `data/reports/quikstrike_matrix/` are ignored.

## Backend Validation

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_quikstrike_matrix_models.py -v
python -m pytest tests/unit/test_quikstrike_matrix_table_reader.py -v
python -m pytest tests/unit/test_quikstrike_matrix_extraction.py -v
python -m pytest tests/unit/test_quikstrike_matrix_conversion.py -v
python -m pytest tests/unit/test_quikstrike_matrix_report_store.py -v
python -m pytest tests/unit/test_quikstrike_matrix_local_browser.py -v
python -m pytest tests/integration/test_quikstrike_matrix_flow.py -v
python -m pytest tests/contract/test_quikstrike_matrix_api_contracts.py -v
python -m pytest tests/ -q
```

## Frontend Validation

Run only when frontend status panels or client types are changed.

```powershell
cd frontend
npm install
npm run build
```

## Artifact Guard

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Confirm generated matrix artifacts remain ignored and untracked:

```powershell
git status --short
```

## Fixture Smoke Flow

1. Start the backend if API routes are implemented.
2. Submit a sanitized fixture payload to `POST /api/v1/quikstrike-matrix/extractions/from-fixture` with:
   - `open_interest_matrix`
   - `oi_change_matrix`
   - `volume_matrix`
   - Gold metadata
   - strike rows
   - expiration columns
   - call/put subcolumns
   - blank cells and explicit zero cells
3. Confirm the response includes:
   - `extraction_id`
   - `status`
   - `row_count`
   - `strike_count`
   - `expiration_count`
   - `unavailable_cell_count`
   - mapping status
   - warnings
   - limitations
   - artifact references under ignored paths
4. Confirm unavailable cells are not converted to zero.
5. Confirm `GET /api/v1/quikstrike-matrix/extractions` lists the saved report.
6. Confirm `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}` returns detail.
7. Confirm `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/rows` returns normalized rows.
8. Confirm `GET /api/v1/quikstrike-matrix/extractions/{extraction_id}/conversion` returns conversion status and generated XAU Vol-OI compatible rows when mapping is valid.
9. Confirm missing extraction ids return structured `NOT_FOUND` errors.
10. Confirm invalid or secret-bearing requests return structured validation errors.

## Dashboard Smoke Flow

Run only when the optional `/xau-vol-oi` status panel is implemented.

1. Start backend and frontend.
2. Open `/xau-vol-oi`.
3. Confirm the QuikStrike Matrix status panel renders.
4. Confirm the panel shows:
   - latest extraction status
   - OI/OI Change/Volume coverage
   - row count
   - strike count
   - expiry count
   - missing-cell warnings
   - conversion status
   - generated local paths
   - local-only and research-only disclaimer
5. Confirm no browser console errors if browser smoke tooling is available.

## Local Browser Shape Smoke

This is optional and must remain user-controlled.

1. User manually logs in to QuikStrike.
2. User manually opens `OPEN INTEREST` and selects `Metals -> Precious Metals -> Gold (OG|GC)`.
3. User manually loads OI Matrix, OI Change Matrix, and Volume Matrix.
4. The local adapter, if implemented, captures sanitized visible table snapshots only.
5. Confirm the adapter does not accept or save cookies, tokens, headers, viewstate, HAR files, screenshots, credentials, private full URLs, or endpoint replay payloads.
6. Save only normalized rows and sanitized metadata under ignored matrix artifact paths.

## Forbidden-Scope Review

Before marking the feature complete, scan changed files and confirm no:

- live trading
- paper trading
- shadow trading
- private trading keys
- broker integration
- real execution
- wallet/private-key handling
- paid vendor automation
- endpoint replay
- credential/session storage
- cookie/token/header/HAR/screenshot/viewstate/private URL persistence
- Rust execution engine
- ClickHouse
- PostgreSQL
- Kafka / Redpanda / NATS
- Kubernetes
- ML model training
- profitability, predictive, safety, or live-readiness claims

## Expected Result

- Synthetic OI Matrix, OI Change Matrix, and Volume Matrix fixtures parse into normalized rows.
- Valid matrix rows convert to XAU Vol-OI compatible local input.
- Missing strike or expiration mapping blocks conversion.
- Blank and unavailable cells remain unavailable.
- Generated artifacts remain under ignored local paths.
- No secret/session data is accepted, saved, returned, staged, or committed.
