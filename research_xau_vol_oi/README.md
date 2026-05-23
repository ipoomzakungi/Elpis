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
- `data_recovery_audit.py`: read-only transcript corpus, Codex session, and
  market-data coverage audit.
- `basis_mapper.py`: futures-to-spot basis and spot-equivalent strike mapping.
- `expected_move.py`: IV-derived 1SD/2SD/3SD expected move and sigma position.
- `oi_wall_engine.py`: OI wall aggregation and transparent wall scoring.
- `volatility_engine.py`: RV, VRP, IV/RV regime, and SD-only baseline fields.
- `zone_classifier.py`: deterministic no-trade, wall, fade, break, pin, and squeeze labels.
- `backtest.py`: event backtest, controls, grouped metrics, and walk-forward splits.
- `guru_review_queue.py`: human review queue for noisy transcript rule extraction.
- `guru_episode_dataset.py`: timestamp-safe guru statement, visible-data, and outcome episodes.
- `guru_full_context_review.py`: full-context review pack and context/map/filter/trade-rule taxonomy.
- `guru_monte_carlo_validation.py`: post-review Monte Carlo, placebo, filter, and market-map diagnostics.
- `gold_baseline_lab.py`: gold trend, IV/range, wall-reaction, staged CME/guru uplift lab.
- `cme_history_normalizer.py`: read-only QuikStrike/CME history normalizer for daily strike-expiry and session panels.
- `market_map_proof_pack.py`: market-map, no-trade filter, expiry pin, and acceptance-control proof pack.
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
- `outputs/transcript_corpus_manifest.csv`
- `outputs/transcript_corpus_manifest.md`
- `outputs/market_data_coverage_manifest.csv`
- `outputs/market_data_coverage_report.md`
- `outputs/transcript_market_coverage_alignment.csv`
- `outputs/transcript_market_coverage_alignment.md`
- `outputs/codex_session_search_report.md`
- `outputs/source_recovery_action_plan.md`
- `outputs/privacy_path_audit_report.md`
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
- `outputs/guru_full_context_review_pack.csv`
- `outputs/guru_full_context_review_pack.md`
- `outputs/guru_full_context_review_suggestions.csv`
- `outputs/guru_full_context_review_decisions_template.csv`
- `outputs/guru_logic_classification_summary.csv`
- `outputs/guru_filter_value_report.csv`
- `outputs/guru_market_map_validation.csv`
- `outputs/guru_full_context_review_report.md`
- `outputs/guru_monte_carlo_validation.csv`
- `outputs/guru_monte_carlo_report.md`
- `outputs/gold_baseline_metrics.csv`
- `outputs/gold_ablation_report.md`
- `outputs/charts/gold_baseline_vs_uplift.svg`
- `outputs/cme_daily_strike_expiry_panel.parquet`
- `outputs/cme_session_regime_panel.parquet`
- `outputs/cme_history_coverage_report.csv`
- `outputs/cme_history_missing_field_report.csv`
- `outputs/cme_history_duplicate_conflict_report.csv`
- `outputs/market_map_precision_report.csv`
- `outputs/filter_avoided_pnl_report.csv`
- `outputs/expiry_pin_test_report.csv`
- `outputs/proof_pack.md`
- `outputs/charts/*.svg`
- `outputs/research_report.md`

`outputs/` is ignored by git because these files are generated research artifacts.

## Data Recovery Audit

Run the full pipeline to regenerate the data recovery outputs:

```powershell
python -m research_xau_vol_oi.report
```

By default, the audit searches only project-local roots and redacts paths in
outputs. External transcript folders, private source-identifying patterns, and
Codex/session searches are local-only configuration:

```toml
[recovery]
search_roots = ["D:/private/transcripts"]
transcript_roots = ["D:/private/transcripts/corpus"]
keyword_patterns = ["private corpus pattern"]
include_codex_roots = true
redact_paths = true
local_debug = false
```

Save this as `.xau_local_sources.toml`. It is ignored by git.

Environment-variable equivalents are also supported:

- `XAU_RECOVERY_SEARCH_ROOTS`
- `XAU_TRANSCRIPT_ROOTS`
- `XAU_RECOVERY_KEYWORDS`
- `XAU_INCLUDE_CODEX_ROOTS`
- `XAU_RECOVERY_LOCAL_DEBUG`
- `XAU_RECOVERY_REDACT_PATHS`

Interpretation:

- `FULL_CORPUS` rows are inferred from configured roots/keywords or large
  transcript-file counts.
- `WEEK_SUBSET` rows are inferred from small, narrow-date transcript sets.
- Transcript dates with no matching CME OI, IV, and futures/basis data are
  logic-extraction only.
- Transcript dates with price data but no CME options coverage can support only
  price-only outcome checks.
- Full Vol-OI validation requires transcript + price + CME OI + IV +
  futures/basis on the same date.

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
2. Open `outputs/guru_full_context_review_pack.md` for transcript context around each extracted episode.
3. Fill `outputs/guru_full_context_review_decisions_template.csv`.
4. Use `APPROVE_CONTEXT`, `APPROVE_MARKET_MAP`, `APPROVE_FILTER`, or `APPROVE_TRADE_RULE` only when the excerpt/context supports that class.
5. Rerun `python -m research_xau_vol_oi.report`.
6. Check approved-only validation before making any transcript-rule research claim.

Legacy episode review is still available:

1. Fill `outputs/guru_episode_review_decisions_template.csv`.
2. Rerun `python -m research_xau_vol_oi.report`.
3. Check approved-only validation before making any transcript-rule research claim.

The generated `guru_llm_review_suggestions.csv` file is a blind, deterministic
review aid only. It uses no future outcome fields and still requires human
approval before any approved-only validation.

The generated `guru_full_context_review_suggestions.csv` file is broader: it
may suggest context, market-map, filter, or trade-rule candidates. These are
review classes only; future outcomes are used only in the separate filter,
market-map, and Monte Carlo validation reports after suggestions are frozen.
