# XAU/USD Vol-OI Research Pipeline

Research-only pipeline for testing XAU/USD range, wall, breakout, fade, pin,
squeeze, and no-trade labels from:

- Yahoo or XAU/GC OHLCV price data
- CME/QuikStrike-style gold futures/options OI data
- transcript-derived deterministic rules

It does not connect to brokers, place orders, manage positions, optimize for
Sharpe, or claim that a signal is tradable.

## Modules

- `config.py`: thresholds, labels, and column aliases.
- `data_loader.py`: data inventory plus CSV, Parquet, Excel, and transcript loaders.
- `basis_mapper.py`: futures-to-spot basis and spot-equivalent strike mapping.
- `expected_move.py`: IV-derived 1SD/2SD/3SD expected move and sigma position.
- `oi_wall_engine.py`: OI wall aggregation and transparent wall scoring.
- `volatility_engine.py`: RV, VRP, IV/RV regime, and SD-only baseline fields.
- `zone_classifier.py`: deterministic no-trade, wall, fade, break, pin, and squeeze labels.
- `backtest.py`: event backtest, controls, grouped metrics, and walk-forward splits.
- `guru_review_queue.py`: human review queue for noisy transcript rule extraction.
- `guru_episode_dataset.py`: timestamp-safe guru statement, visible-data, and outcome episodes.
- `report.py`: pipeline runner, output files, SVG charts, and Markdown report.

## Run

From the repository root:

```powershell
python -m research_xau_vol_oi.report
```

Optional explicit inputs:

```powershell
python -m research_xau_vol_oi.report `
  --price data/raw/yahoo/gc=f_15m_ohlcv_20260513_20260521.parquet `
  --options backend/data/raw/xau/quikstrike_20260513_101537_xau_vol_oi_input.csv `
  --output-dir outputs
```

## Outputs

The runner writes:

- `outputs/xau_feature_table.parquet`
- `outputs/signal_events.csv`
- `outputs/backtest_summary.csv`
- `outputs/backtest_trades.csv`
- `outputs/walk_forward_validation.csv`
- `outputs/oi_walls.csv`
- `outputs/data_inventory.csv`
- `outputs/guru_rule_review_queue.csv`
- `outputs/guru_rule_review_decisions_template.csv`
- `outputs/guru_rule_review_report.md`
- `outputs/guru_decision_episodes.csv`
- `outputs/guru_episode_outcomes.csv`
- `outputs/guru_episode_rule_performance.csv`
- `outputs/guru_episode_review_dashboard.html`
- `outputs/guru_episode_review_decisions_template.csv`
- `outputs/guru_episode_review_guide.md`
- `outputs/guru_episode_report.md`
- `outputs/guru_llm_review_suggestions.csv`
- `outputs/guru_llm_review_final_suggestions.csv`
- `outputs/guru_llm_review_audit.md`
- `outputs/guru_monte_carlo_validation.csv`
- `outputs/guru_monte_carlo_report.md`
- `outputs/charts/*.svg`
- `outputs/research_report.md`

`outputs/` is ignored by git because these files are generated research artifacts.

## Guardrails

- 1SD and 2SD are range context, not automatic buy/sell rules.
- OI walls are level evidence, not standalone entries.
- Breakout confirmation requires close beyond the wall plus next-bar hold.
- Missing IV, missing basis, stale/bad data, or no nearby wall returns no-trade labels.
- Walk-forward validation separates formation and test windows and checks that wall
  timestamps are not later than event timestamps.
- Extracted transcript rules are research features only. Approved-only uplift requires
  human review decisions; unreviewed rules are preview-only and cannot support a
  predictive claim.
- Guru episode outcomes separate visible snapshot data from future evaluation windows;
  future rows never become episode inputs.

## Guru Episode Review

1. Open `outputs/guru_episode_review_dashboard.html`.
2. Fill `outputs/guru_episode_review_decisions_template.csv`.
3. Rerun `python -m research_xau_vol_oi.report`.
4. Check approved-only validation before making any transcript-rule research claim.

The generated `guru_llm_review_suggestions.csv` file is a blind, deterministic
review aid only. It uses no future outcome fields and still requires human
approval before any approved-only validation.
