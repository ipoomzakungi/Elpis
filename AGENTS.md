# AGENTS.md — Elpis AI Agent Operating Playbook

## 1. Project identity

This repository is **Elpis**, a research-first trading system project.

The project goal is to build a reliable research platform for market data, feature engineering, regime classification, strategy validation, dashboards, and later paper/live trading only after strict validation gates.

This project is not allowed to become a live trading bot prematurely.

## 2. Current phase

Default phase: **v0 Research Platform**

v0 focuses on:

- public market data ingestion
- reproducible local storage
- feature engineering
- regime classification
- dashboard visualization
- data-quality checks
- research validation

v0 does not include real order execution.

## 3. Mandatory documents to read before coding

Before changing code, the AI agent must inspect:

1. `.specify/memory/constitution.md`
2. The active feature spec under `specs/*/spec.md`
3. The active plan under `specs/*/plan.md`
4. The active tasks file under `specs/*/tasks.md`
5. Relevant data model / API contract / quickstart files

The agent must follow these documents unless explicitly instructed otherwise.

## 4. Core principles

The agent must preserve these principles:

- Research first, live trading later
- Reproducible data and calculations
- Timestamp-safe feature engineering
- Small vertical slices
- Test before commit
- Commit only stable checkpoints
- No hidden assumptions
- No strategy claims without evidence
- No real trading unless phase gates explicitly allow it

## 5. Allowed v0 stack

Allowed by default:

- Python 3.11+
- FastAPI
- Pydantic
- Pydantic Settings
- Polars
- DuckDB
- Parquet
- PyArrow
- httpx
- Next.js
- TypeScript
- Tailwind CSS
- lightweight-charts
- Recharts
- Public market data APIs
- Yahoo Finance / yfinance for non-execution research data
- CSV or local file import for research datasets

## 6. Forbidden in v0 unless explicitly approved

Do not add:

- Live trading
- Private exchange API keys
- Real order execution
- Wallet/private-key handling
- Leverage execution
- Real position management
- Rust execution engine
- ClickHouse
- PostgreSQL
- Kafka
- Redpanda
- NATS
- Kubernetes
- ML model training pipeline
- Broker/exchange private account access

These may be added only in later phases after the constitution/spec is updated.

## 7. Data-source rules

The project must support a data-provider architecture.

Data sources should be modular, not hardcoded into strategy logic.

Preferred abstraction:

```text
DataProvider
    fetch_ohlcv()
    fetch_open_interest()
    fetch_funding_rate()
    fetch_metadata()
```

Initial providers:

BinanceProvider:
    crypto OHLCV
    crypto funding
    crypto open interest baseline

YahooFinanceProvider:
    stocks / ETFs / indices / long-history OHLCV
    macro proxy assets
    ML baseline datasets
    not used for crypto OI or funding

LocalFileProvider:
    CSV / Parquet imported datasets
    vendor exports
    manual research data

Future providers:

BybitProvider:
    better crypto OI history than Binance official baseline

OKXProvider:
    additional crypto venue validation

KaikoProvider:
    normalized institutional crypto derivatives history

TardisProvider:
    raw exchange-native replay and long historical archive

CMEProvider:
    XAU/USD gold futures/options OI research

Important:

Yahoo Finance is useful for long-history OHLCV research.
Yahoo Finance must not be treated as a source for crypto OI/funding.
Binance official OI is acceptable for v0 prototype but not enough for serious multi-year OI research.
Data source limitations must be shown in the dashboard or documentation.
8. Work style

The agent must work in small batches.

Preferred cycle:

1. Read documents
2. Check current repo status
3. Pick the smallest next task
4. Implement only that task
5. Run relevant checks
6. Fix failures
7. Summarize changes
8. Commit only if checks pass
9. Push only if remote is configured and accessible

The agent must not do a large rewrite unless explicitly asked.

9. Required command checks
Always check repo state first
git status
git branch --show-current
git remote -v
Backend checks

Run when backend changes:

cd backend
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"

If API behavior changed, also run:

uvicorn src.main:app --host 0.0.0.0 --port 8000

Then verify:

http://localhost:8000/health
http://localhost:8000/docs
Frontend checks

Run when frontend changes:

cd frontend
npm install
npm run build

If UI behavior changed, also run:

npm run dev

Then verify:

http://localhost:3000
Full smoke test

Run after integration changes:

1. Start backend
2. Start frontend
3. Open dashboard
4. Trigger data download
5. Confirm raw data files exist
6. Trigger feature processing
7. Confirm processed data files exist
8. Confirm dashboard displays charts/panels
9. Confirm no console/runtime errors
10. Commit rules

The agent must commit after stable checkpoints only.

Commit is allowed only when:

changed code builds
relevant import checks pass
frontend build passes if frontend changed
backend starts if backend changed
no forbidden v0 technology is introduced
no generated data files are committed
no secrets are committed

Good commit examples:

git commit -m "docs: add AI agent operating playbook"
git commit -m "fix: stabilize backend imports and frontend build"
git commit -m "feat: add data provider abstraction"
git commit -m "test: add smoke validation script"

Do not commit:

.env
.venv
node_modules
data/raw
data/processed
data/reports
*.parquet
*.duckdb
build output
secret keys
11. Push rules

Before push:

git status
git remote -v
git branch --show-current

If authentication fails:

gh auth status
gh auth login

Push:

git push -u origin <current-branch>

If push fails, do not assume the repo does not exist. Check authentication and remote URL first.

12. Testing and validation policy

A feature is not done because code exists.

A feature is done only when:

it works from the documented quickstart
it has passed relevant command checks
it has at least minimal tests or smoke validation
failure cases are handled or documented
dashboard/API behavior is manually verified where relevant
13. Research policy

The agent must not claim a strategy works without evidence.

Allowed claims:

"Implementation works"
"Data downloads"
"Features compute"
"Dashboard displays"
"Backtest result is X under assumptions Y"

Forbidden claims without evidence:

"This strategy is profitable"
"This OI signal predicts price"
"This grid is safe"
"This can be traded live"
14. Strategy development order

Default order:

1. Data ingestion
2. Data quality
3. Feature engineering
4. Visualization
5. Regime classification
6. Backtesting
7. Parameter robustness
8. Paper/shadow trading
9. Risk validation
10. Live trading gate

Do not jump directly from visualization to live trading.

15. Current recommended next milestones

After the current OI Regime Lab smoke test:

M1: Add AGENTS.md
M2: Add smoke validation script
M3: Add data provider abstraction
M4: Add YahooFinanceProvider for long-history OHLCV
M5: Add strategy/backtest module
M6: Compare Binance crypto OI regime results with Yahoo/non-crypto OHLCV baseline research
M7: Add Pine Script prototype only for visual comparison
16. Definition of done for every AI session

At the end of every session, the agent must report:

- Files changed
- Commands run
- Passed checks
- Failed checks
- Fixes made
- Remaining risks
- Suggested next task
- Commit hash if committed

---

# What to tell the new local AI session

Paste this into the new AI session:

```text
You are working on the Elpis repository.

First, read AGENTS.md if it exists.
If AGENTS.md does not exist, create it using the operating playbook I provide.

Then read:
- .specify/memory/constitution.md
- specs/001-oi-regime-lab/spec.md
- specs/001-oi-regime-lab/plan.md
- specs/001-oi-regime-lab/tasks.md
- specs/001-oi-regime-lab/quickstart.md

Current status:
- OI Regime Lab v0 skeleton exists.
- Backend import check passed.
- Backend /health passed.
- Backend /docs passed.
- Frontend build passed.
- .venv is in .gitignore.
- There was a push/authentication issue, so check git remote and GitHub auth before pushing.

Important project rule:
Do not add live trading, private API keys, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, or ML in v0.

Current goal:
Create or update AGENTS.md as a generic AI operating playbook.
Then run a functional smoke test of the existing app.

Smoke test:
1. Start backend:
   cd backend
   .\.venv\Scripts\Activate
   uvicorn src.main:app --host 0.0.0.0 --port 8000

2. Start frontend:
   cd frontend
   npm run dev

3. Open:
   http://localhost:3000

4. Click Download Data.
5. Confirm data/raw has OHLCV, OI, and funding Parquet files.
6. Click Process Features.
7. Confirm data/processed has the feature Parquet file.
8. Confirm dashboard displays:
   - price chart
   - range lines
   - open interest chart
   - funding chart
   - volume chart
   - regime panel
   - data quality panel

If the smoke test fails, fix only the root cause.
Do not redesign the architecture.

After smoke test passes:
- commit stable changes
- push if authentication works
- report files changed, commands run, results, commit hash, and remaining risks.

<!-- SPECKIT START -->
Active Speckit plan: specs/011-free-public-derivatives-data-expansion/plan.md
<!-- SPECKIT END -->
