# XAUUSD Dukascopy Data Pipeline

Local research workflow for XAUUSD 1-minute Dukascopy data. It downloads bid
and ask CSV files, cleans them into UTC Parquet, validates data quality, and
runs a simple research-only strategy backtest and parameter optimization.

This is not a live trading, paper trading, broker, order execution, or strategy
profitability system.

This pipeline uses the unofficial open-source `dukascopy-node` package for
research only. The package is not affiliated with or endorsed by Dukascopy Bank
SA. Dukascopy Bank SA also lists `dukascopy-node.app` among domains not
controlled by Dukascopy Group, so treat the project documentation as third-party
package documentation. Do not provide personal information, trading credentials,
cookies, tokens, broker details, or private account data to third-party sites or
tools.

## Dukascopy CSV Format

The current `dukascopy-node` CSV output is expected to contain:

```text
timestamp,open,high,low,close,volume
1612137600000,1.21225,1.21363,1.2056,1.20676,165569.8187
```

Volume may be absent depending on CLI flags. Timestamps default to Unix
milliseconds in UTC; `--date-format iso` can emit ISO UTC strings. The cleaner
accepts both formats and common column aliases such as `datetime`, `time`,
`bid_open`, `ask_open`, `Open`, `High`, `Low`, and `Close`.

## Install

Install Node.js 18+ and Python 3.11+.

```powershell
cd data_pipeline
npm install
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install -r requirements.txt
```

## Download Data

Recommended resumable PowerShell download:

```powershell
cd data_pipeline
powershell -ExecutionPolicy Bypass -File scripts/download_xauusd_dukascopy_monthly.ps1 -Install
```

The monthly downloader writes resumable chunks under:

```text
data/raw/dukascopy/monthly/
```

Then it combines them into the default cleaner inputs:

```text
data/raw/dukascopy/xauusd_m1_bid_2024_to_now.csv
data/raw/dukascopy/xauusd_m1_ask_2024_to_now.csv
```

If it stops partway through, rerun the same command. Existing non-empty monthly
files are skipped unless you pass `-Force`.

Single-range PowerShell download:

```powershell
cd data_pipeline
powershell -ExecutionPolicy Bypass -File scripts/download_xauusd_dukascopy.ps1 -Install
```

The script runs:

```powershell
npx dukascopy-node -i xauusd -from 2024-01-01 -to now -t m1 -p bid -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_bid_2024_to_now.csv
npx dukascopy-node -i xauusd -from 2024-01-01 -to now -t m1 -p ask -f csv -dir ./data/raw/dukascopy -fn xauusd_m1_ask_2024_to_now.csv
```

Some `dukascopy-node` versions append the format extension to `-fn`, producing
names like `xauusd_m1_bid_2024_to_now.csv.csv`. The wrapper scripts rename
those files back to the expected `.csv` names, and the Python cleaner also
falls back to reading `.csv.csv` when a requested `.csv` path is not present.

Bash:

```bash
cd data_pipeline
bash scripts/download_xauusd_dukascopy_monthly.sh --install
```

## Clean Data

```powershell
python src/clean_xauusd.py
```

Output:

```text
data/processed/xauusd_m1_2024_to_now.parquet
data/reports/clean_summary.json
```

The cleaner sorts timestamps, removes duplicate timestamps, joins bid and ask,
creates mid OHLC, calculates `spread_close` and `spread_points`, and reports
missing one-minute ranges.

## Validate Data

```powershell
python src/validate_xauusd.py
```

Reports:

```text
data/reports/missing_minutes.json
data/reports/duplicate_rows.json
data/reports/spread_summary.json
data/reports/date_range_summary.json
```

The validator reports first and last timestamp, total candles, missing candle
count, duplicate timestamps, average and max spread, and suspicious candles
where OHLC values are internally inconsistent.

## Resample

```powershell
python src/resample_xauusd.py --timeframe m15
python src/resample_xauusd.py --timeframe h1
```

## Run One Backtest

Edit `configs/strategy_config.yaml`, then run:

```powershell
python src/backtest_engine.py --config configs/strategy_config.yaml
```

Outputs:

```text
data/reports/trades.csv
data/reports/equity_curve.csv
data/reports/summary.json
```

The engine uses next-bar-open entries, supports long and short trades, applies
configured spread, commission, and slippage assumptions, and supports ATR-based
stop loss and take profit. If stop loss and take profit are both reachable in
one candle, the conservative stop-first assumption is used.

## Optimize Parameters

```powershell
python src/optimize_strategy.py --config configs/optimization_config.yaml
```

Outputs:

```text
data/reports/optimization_results.csv
data/reports/top_20_configs.csv
data/reports/best_config.yaml
```

The optimizer splits data by UTC timestamp:

```text
Train:      2024-01-01 to 2024-12-31
Validation: 2025-01-01 to 2025-12-31
Test:       2026-01-01 to now
```

Ranking is based on validation score with penalties for too few trades, high
drawdown, train/validation instability, and robustness failures. The selected
config must work on both train and validation, and the test result is checked
for collapse rather than used for direct fitting.

`optimize_strategy.py` runs a hard data-quality gate before evaluating any
parameters. By default it requires the validation reports from
`python src/validate_xauusd.py` and stops if missing minutes, duplicate
timestamps, suspicious OHLC rows, max spread, or average spread exceed the
thresholds in `configs/optimization_config.yaml`.

The default gate is strict:

```yaml
data_quality_gate:
  enabled: true
  missing_minutes_max: 0
  duplicate_timestamps_max: 0
  suspicious_candles_max: 0
  max_spread_points: 300
  average_spread_points_max: 50
```

If the gate fails, fix or document the data issue before optimization. Do not
optimize on broken or unexplained data.

The example grid is large. `optimization.max_configs` defaults to `2000` for a
deterministic local pass. Set it to `null` or pass `--max-configs 0` for an
exhaustive grid.

## Optimize TradingView Strategy Inputs

For the strategy in `Tradingview - Copy.pine`, use the local Python
approximation:

```powershell
python src/tradingview_optimizer.py --config configs/tradingview_optimizer_config.yaml --iterations 250 --workers 0
```

`--workers 0` uses CPU count minus one. Use `--workers 1` for deterministic
single-process debugging, or set a fixed number such as `--workers 8` if you
want to reserve more CPU for other work.

Default input:

```text
data/processed/xauusd_m15_2024_to_now.parquet
data/processed/xauusd_m30_2024_to_now.parquet
data/processed/xauusd_h1_2024_to_now.parquet
data/processed/xauusd_h2_2024_to_now.parquet
```

Outputs:

```text
data/reports/tradingview_optimizer/top_results.csv
data/reports/tradingview_optimizer/all_results.csv
data/reports/tradingview_optimizer/fee_attribution.csv
data/reports/tradingview_optimizer/sleeve_comparison.csv
data/reports/tradingview_optimizer/top_by_validation_pnl_all.csv
data/reports/tradingview_optimizer/top_by_test_pnl_all.csv
data/reports/tradingview_optimizer/top_by_avg_net_trade_all.csv
data/reports/tradingview_optimizer/top_positive_validation_rejected.csv
data/reports/tradingview_optimizer/top_low_frequency_candidates.csv
data/reports/tradingview_optimizer/top_target_frequency_candidates.csv
data/reports/tradingview_optimizer/research_summary.md
data/reports/tradingview_optimizer/best_presets.json
data/reports/tradingview_optimizer/pine_input_preset.md
data/reports/tradingview_optimizer/<timeframe>/top_results.csv
data/reports/tradingview_optimizer/<timeframe>/all_results.csv
```

The optimizer approximates Donchian breakouts, SD mean reversion, score
thresholds, Bybit/MEXC/custom fee models, slippage, spread, funding, optional
impact and volatility-slippage assumptions, TP1, runner, stops, dynamic
no-play zones, risk-based sizing, and time exits. It uses walk-forward
train/validation/test splits and rejects validation configs outside the
configured trade-frequency, profit-factor, average-win/loss, and
commission-drag thresholds.

The default config explores M15, M30, H1, and H2. It samples strategy mode,
long/short permissions, strictness preset, grid/Donchian lengths, regime
thresholds, RSI/MACD/EMA lengths, ATR stop behavior, TP quantities, TP/runner
levels, MR TP2, breakeven behavior, dynamic no-play behavior, and
fee-multiple gates. The default research config now searches a lower-turnover
range instead of forcing 500+ trades/year, because high-frequency candidates
can look useful before costs while failing after realistic execution costs.

Robustness checks are enabled by default. Each candidate is evaluated with the
base fee model and an additional worst-case taker/slippage/funding scenario.
Ranking is driven mainly by validation net P&L, profit factor, win/loss
quality, drawdown, commission drag, and worst-fee validation performance. Keep
the Pine inputs shown in `pine_input_preset.md` aligned before pasting one of
the candidate parameter blocks back into TradingView.

These presets are candidates to paste back into Pine and re-test in
TradingView. They are not proof of profitability, predictive power, safety, or
live readiness.

## Optimize Legacy TradingView Strategy Inputs

For the older strategy in `Tradingview.pine`, use the legacy Python
approximation:

```powershell
python src/tradingview_legacy_optimizer.py --config configs/tradingview_legacy_optimizer_config.yaml --iterations 250 --workers 0
```

The legacy optimizer writes the same visibility-first sorted reports as the
newer optimizer: every sampled candidate is evaluated across
train/validation/test, written to `all_results.csv`, and then labeled with gate
flags and reject reasons. The sorted report files include
`top_by_validation_pnl_all.csv`, `top_by_test_pnl_all.csv`,
`top_by_avg_net_trade_all.csv`, `top_positive_validation_rejected.csv`,
`top_low_frequency_candidates.csv`, `top_target_frequency_candidates.csv`, and
`research_summary.md`.

## Diagnose TradingView Strategy Edge

Run fee and engine-slice diagnostics to separate signal edge from execution
cost:

```powershell
python src/tradingview_diagnostics.py --config configs/tradingview_optimizer_config.yaml --iterations 30 --workers 12
```

The diagnostics compare:

```text
Fee profiles: zero cost, Bybit maker+taker, Bybit taker+taker, MEXC low cost, worst-case taker
Strategy slices: auto, MR only, breakout only, long-breakout only, long only, short only
Timeframes: M15, M30, H1, H2
```

Outputs:

```text
data/reports/tradingview_diagnostics/summary.csv
data/reports/tradingview_diagnostics/timeframe_summary.csv
data/reports/tradingview_diagnostics/all_results.csv
data/reports/tradingview_diagnostics/top_results.csv
data/reports/tradingview_diagnostics/cases/<fee>__<slice>/all_results.csv
```

Use this before deeper optimization. If zero-cost works but real-fee cases
fail, the strategy has gross signal edge but not enough edge after execution
costs. If MR-only or short-only fail even at zero cost, those engines should
not be tuned blindly.

## Backtest SMC Pine Prototype

For the lightweight `smc.pine` strategy, run the local Python approximation:

```powershell
python src/smc_pine_backtest.py --config configs/smc_pine_backtest_config.yaml
```

Outputs:

```text
data/reports/smc_pine_backtest/all_results.csv
data/reports/smc_pine_backtest/top_results.csv
data/reports/smc_pine_backtest/research_summary.md
data/reports/smc_pine_backtest/pine_input_preset.md
data/reports/smc_pine_backtest/best_config.yaml
```

The SMC approximation uses confirmed swing pivots, next-bar-open entries,
risk-based sizing, configured spread/slippage, stop-first ambiguous candles,
and train/validation/test splits. Use its presets as research candidates only,
then re-test the same inputs in TradingView on the matching timeframe.
