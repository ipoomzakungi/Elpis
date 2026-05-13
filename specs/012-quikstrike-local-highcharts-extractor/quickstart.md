# Quickstart: QuikStrike Local Highcharts Extractor

**Date**: 2026-05-13
**Feature**: 012-quikstrike-local-highcharts-extractor

This quickstart describes the validation path after implementation. The feature is local-only and research-only. It must not add live trading, paper trading, shadow trading, private keys, broker integration, real execution, credential storage, cookie/session storage, HAR capture, screenshot OCR, ASP.NET endpoint replay, paid vendors, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML training.

## 1. Verify Existing Checks

From `backend/`:

```powershell
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/unit/test_quikstrike_*.py -v
python -m pytest tests/integration/test_quikstrike_*.py -v
python -m pytest tests/contract/test_quikstrike_api_contracts.py -v
python -m pytest tests/ -q
```

From `frontend/` if dashboard or API client files changed:

```powershell
npm install
npm run build
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## 2. Fixture-Based Extraction Validation

Automated tests must use synthetic sanitized fixtures only. Fixtures should mimic the shape of Highcharts and DOM metadata without containing real cookies, headers, viewstate values, HAR files, screenshots, private full URLs, or real QuikStrike chart payloads.

Fixture coverage should include:

- `intraday_volume` with Put, Call, Vol Settle, and Ranges
- `eod_volume` with Put, Call, Vol Settle, and Ranges
- `open_interest` with Put, Call, Vol Settle, and Ranges
- `oi_change` with Put, Call, Vol Settle, and Ranges
- `churn` with Put, Call, Vol Settle, and Ranges
- missing Vol Settle
- missing Ranges
- missing Put series
- missing Call series
- high-confidence strike mapping
- partial strike mapping
- conflicting strike mapping
- forbidden secret/session field names

Expected behavior:

- Supported view types produce normalized rows.
- Put and Call rows remain separated.
- DTE and future reference price parse from sanitized DOM metadata.
- Vol Settle and range context are preserved when available.
- Partial/conflicting strike mapping blocks XAU Vol-OI conversion.
- Forbidden secret/session fields are rejected.

## 3. Optional Local Browser Shape Smoke

Only run this manually with a user-controlled authenticated browser session.

Manual steps:

1. Open QuikStrike locally.
2. Log in manually.
3. Navigate manually to `QUIKOPTIONS VOL2VOL`.
4. Use the product dropdown manually to choose `Metals -> Precious Metals -> Gold (OG|GC)`.
5. Visit the supported views:
   - `Volume -> Intraday`
   - `Volume -> EOD`
   - `Open Interest -> OI`
   - `Open Interest -> OI Change`
   - `Open Interest -> Churn`
6. Run only the local shape validation/extraction command provided by the implementation.

Expected behavior:

- The extractor reads sanitized visible DOM metadata.
- The extractor reads sanitized Highcharts series and points.
- No cookies, tokens, headers, viewstate values, HAR files, screenshots, private full URLs, or credential material are written.
- If the browser is not on Gold Vol2Vol, extraction is blocked with manual navigation instructions.

## 4. Start Backend For API Smoke

From `backend/`:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## 5. Run Sanitized API Smoke If Routes Are Implemented

Create a fixture payload under the OS temp directory, not in the repository. The payload should include sanitized DOM metadata and synthetic Highcharts-like series for at least one supported view.

Call:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/quikstrike/extractions" `
  -ContentType "application/json" `
  -Body $body
```

Expected response includes:

- `extraction_id`
- extraction `status`
- completed or partial views
- row counts
- Put/Call counts
- strike mapping confidence
- conversion eligibility
- warnings
- limitations
- research-only warnings
- generated local artifact paths

Then call:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/quikstrike/extractions"
Invoke-RestMethod "http://localhost:8000/api/v1/quikstrike/extractions/{extraction_id}"
Invoke-RestMethod "http://localhost:8000/api/v1/quikstrike/extractions/{extraction_id}/rows"
Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/quikstrike/extractions/{extraction_id}/convert-xau-vol-oi"
```

Confirm missing extraction ids return structured `NOT_FOUND` errors and uncertain strike mapping returns structured `CONVERSION_BLOCKED` errors.

## 6. Inspect Generated Artifacts

Generated artifacts should appear only under ignored paths:

```text
data/raw/quikstrike/
data/processed/quikstrike/
data/reports/quikstrike/
```

They must remain ignored by git and must not contain:

- cookies
- tokens
- headers
- authorization values
- viewstate values
- HAR files
- screenshots
- private full URLs
- credentials
- account/order/wallet fields

## 7. Dashboard Check If UI Is Implemented

From `frontend/`:

```powershell
npm run dev
```

Open one or both pages, depending on implementation:

```text
http://localhost:3000/data-sources
http://localhost:3000/xau-vol-oi
```

Verify the page shows:

- local QuikStrike extraction readiness
- latest extraction status
- supported view coverage
- row counts
- missing view warnings
- strike mapping confidence
- conversion eligibility
- generated local file paths
- local-only and research-only disclaimer

Confirm no browser console errors if browser smoke tooling is available.

## 8. Forbidden Scope Review

Before marking implementation complete:

```powershell
rg -n -i "live trading|paper trading|shadow trading|private key|private-key|broker|order execution|real execution|wallet|cookie|session token|authorization header|viewstate|har|screenshot ocr|endpoint replay|paid vendor|rust|clickhouse|postgresql|postgres|kafka|redpanda|nats|kubernetes|sklearn|tensorflow|torch|ml training|buy signal|sell signal|profitable|profitability|predictive|safe to trade|live ready|live-readiness" backend/src frontend/src backend/pyproject.toml frontend/package.json .github/workflows/validation.yml
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected result:

- Any matches are guardrail/disclaimer text only.
- No live trading, paper trading, shadow trading, private keys, broker integration, real execution, wallet handling, credential storage, cookie/session storage, HAR capture, screenshot OCR, endpoint replay, paid vendors, Rust execution engine, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell execution behavior, or prohibited claims were introduced.
- No generated raw, processed, report, local browser profile, HAR, screenshot, or fixture data is tracked.
