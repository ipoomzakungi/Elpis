# Quickstart: Real Multi-Asset Research Report

**Date**: 2026-04-30  
**Feature**: 005-real-multi-asset-research-report

This quickstart describes the expected validation path after implementation. It uses real processed feature files when available and must not rely on synthetic data for the final research report.

## 1. Verify Existing Checks

From `backend/`:

```powershell
pip install -e ".[dev]"
python -c "from src.main import app; print('backend import ok')"
python -m pytest tests/ -q
```

From `frontend/`:

```powershell
npm install
npm run build
```

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

## 2. Prepare Real Processed Features

The research workflow expects processed feature files to already exist.

Minimum successful crypto target:

```text
BTCUSDT 15m processed features
```

Minimum successful Yahoo/proxy target when available:

```text
SPY or GC=F processed OHLCV features
```

If files are missing, run the existing provider download and feature processing workflow before starting a real multi-asset research run. Do not use synthetic data as a substitute for final research output.

## 3. Start Backend

From `backend/`:

```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Verify:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## 4. Run a Multi-Asset Research Report

Submit a grouped research request:

```powershell
$body = @{
  assets = @(
    @{
      symbol = "BTCUSDT"
      provider = "binance"
      asset_class = "crypto"
      timeframe = "15m"
      enabled = $true
      required_feature_groups = @("ohlcv", "regime", "oi", "funding", "volume_confirmation")
    },
    @{
      symbol = "SPY"
      provider = "yahoo_finance"
      asset_class = "equity_proxy"
      timeframe = "1d"
      enabled = $true
      required_feature_groups = @("ohlcv", "regime")
    }
  )
  base_assumptions = @{
    initial_equity = 10000
    fee_rate = 0.0004
    slippage_rate = 0.0002
    risk_per_trade = 0.01
    allow_short = $true
  }
  strategy_set = @{
    include_grid_range = $true
    include_breakout = $true
    baselines = @("buy_hold", "price_breakout", "no_trade")
  }
  validation_config = @{
    stress_profiles = @("normal", "high_fee", "high_slippage", "worst_reasonable_cost")
    sensitivity_grid = @{
      grid_entry_threshold = @(0.1, 0.15, 0.2)
      atr_stop_buffer = @(0.75, 1.0, 1.25)
      breakout_risk_reward_multiple = @(1.5, 2.0, 2.5)
      fee_slippage_profile = @("normal", "high_fee")
    }
    walk_forward = @{
      split_count = 3
      minimum_rows_per_split = 20
    }
  }
  report_format = "both"
} | ConvertTo-Json -Depth 20

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/v1/research/runs" `
  -ContentType "application/json" `
  -Body $body
```

Expected behavior:

- Assets with processed features complete.
- Assets without processed features are marked blocked with clear instructions.
- Yahoo Finance/proxy assets are labeled OHLCV-only.
- Gold proxies state that GC=F and GLD do not provide gold options OI, futures OI, or XAU/USD spot execution data.
- The response includes research-only warnings and no profitability or live-readiness claims.

## 5. Inspect Saved Reports

List reports:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/research/runs"
```

Read report:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/research/runs/{research_run_id}"
```

Read sections:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/research/runs/{research_run_id}/assets"
Invoke-RestMethod "http://localhost:8000/api/v1/research/runs/{research_run_id}/comparison"
Invoke-RestMethod "http://localhost:8000/api/v1/research/runs/{research_run_id}/validation"
```

Generated report artifacts should appear under:

```text
data/reports/{research_run_id}/
```

They must remain ignored by git.

## 6. Start Dashboard

From `frontend/`:

```powershell
npm run dev
```

Open:

```text
http://localhost:3000/research
```

Verify the page shows:

- research run selector
- asset-level summary table
- capability badges
- missing-data warnings
- strategy-vs-baseline comparison
- stress survival by asset
- walk-forward stability by asset
- regime coverage by asset
- concentration warnings by asset
- source limitation notes
- research-only disclaimer

Dashboard smoke checklist:

- Selector can switch between saved grouped research runs without a page reload.
- Status summary shows total, completed, and blocked asset counts for the selected run.
- Blocked assets remain visible with actionable download/process instructions.
- Yahoo Finance and gold proxy assets show OHLCV-only or proxy limitation notes where applicable.
- Strategy comparison, stress, walk-forward, regime coverage, and concentration sections render empty states or persisted rows without runtime errors.
- Header navigation includes a Research Reports link to `/research`.
- The page does not claim profitability, predictive power, safety, or live readiness.

## 7. Guardrail Review

Before committing implementation:

```powershell
rg -n -i "live trading|paper trading|shadow trading|private key|api_key|broker|order execution|wallet|rust|clickhouse|postgres|kafka|kubernetes|sklearn|tensorflow|torch" backend/src frontend/src backend/pyproject.toml frontend/package.json .github/workflows/validation.yml
powershell -ExecutionPolicy Bypass -File scripts/check_generated_artifacts.ps1
```

Expected result:

- No forbidden dependency or infrastructure additions.
- Any source hits are guardrail/disclaimer text only.
- No generated report or data artifacts are tracked.
