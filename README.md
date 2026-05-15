# Elpis

Research-first market data and XAU options research platform. v0 is local
research only: data ingestion, reports, dashboards, validation, and journal
outcome updates. Do not add live trading, paper trading, broker integration,
credential storage, endpoint replay, paid vendors, Rust, ClickHouse,
PostgreSQL, Kafka, Kubernetes, or ML training.

## Current XAU Workflow

The local daily QuikStrike runner captures:

- QuikStrike Vol2Vol
- QuikStrike Matrix
- XAU QuikStrike Fusion
- XAU Vol-OI
- XAU Reaction
- XAU Forward Journal `daily_snapshot`

Run from repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_xau_quikstrike_snapshot.ps1
```

The script opens or reuses a local CDP browser, then automates QuikStrike
product/view navigation after manual CME login. It does not save or print
cookies, tokens, headers, HAR, screenshots, viewstate, private URLs, or
credentials.

CME/QuikStrike content may lag the user's local midnight and update closer to
local noon. The daily runner fingerprints sanitized Vol2Vol, Matrix, and Fusion
content before creating a Forward Journal entry. If the latest previous entry
for the same product, expiration, and capture window has identical content, the
runner returns `duplicate_content` and references the previous `journal_id`
instead of creating a duplicate journal entry. Rerun after CME updates, or pass
`-ForceCreate` only when a manual research override is intentional.

## Local Runner Config

On first run the wrapper creates this ignored workspace config:

```text
.quikstrike-runner.local.env
```

It stores only non-secret settings such as CDP port, browser, wait time, and
the browser profile path. The browser profile itself must stay outside the
repo because it contains browser cache/session material. The wrapper rejects
repo-local profile paths.

Default profile:

```text
%LOCALAPPDATA%\Elpis\quikstrike-browser-profile
```

## Forward Journal Outcomes

Forward Journal entries are created with pending outcome windows:

- `30m`
- `1h`
- `4h`
- `session_close`
- `next_day`

Pending means later OHLC candle data has not yet been attached. It is not a
QuikStrike extraction failure. Outcome updates must use real local/public OHLC
coverage only: complete candles update observed metrics, partial candles become
inconclusive, and missing candles remain pending.

## Validation

Useful checks:

```powershell
cd backend
python -c "from src.main import app; print('backend import ok')"
cd ..
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
git status
```

Generated reports live under ignored `data/` or `backend/data/` paths and must
not be committed.
