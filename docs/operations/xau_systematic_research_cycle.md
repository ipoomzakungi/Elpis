# XAU Systematic Research Cycle

## Purpose

This is a local, research-only orchestrator for aligning CME/QuikStrike structure with
traded-side XAUUSD/GO price context. It prepares a repeatable twice-daily research pack
for manual or AI review.

It does not create live trades, paper orders, alerts, position sizing, or buy/sell signals.
Every output keeps `research_only=true` and `signal_allowed=false`.

## Architecture

```text
QuikStrike Vol2Vol + Matrix
        -> XAU QuikStrike Fusion
        -> XAU Vol-OI report
        -> CME futures-side structure

Traded-side bars
        -> latest XAUUSD/GO reference
        -> session open
        -> ATR/RV
        -> candle acceptance/rejection

GC reference + XAUUSD/GO reference
        -> basis = GC futures - XAUUSD/GO spot
        -> mapped traded-side levels

All aligned sources
        -> Source Alignment Report
        -> AI Research Pack JSON/Markdown
```

## Data-Source Roles

- CME OI Matrix provides structural walls only.
- OI change and volume provide freshness/activation context only.
- Vol2Vol/IV provides expected range, SD bands, and volatility regime.
- GC/CME strikes and SD levels are futures-side and must be basis-adjusted before use on XAUUSD/GO.
- Session open, ATR/RV, and candle state come from traded-side bars.
- Missing basis, bars, session open, ATR/RV, or candle state blocks action promotion.

## Twice-Daily Workflow

Example 10:00 Asia/Bangkok run:

```bash
python scripts/run_xau_systematic_research_cycle.py --cycle-label 10am --cycle-time 10:00 --cme-source-mode api_only --price-provider dukascopy_node --dukascopy-node-command-template "npx dukascopy-node -i {symbol} -from {from_iso} -to {to_iso} -t {timeframe} -f csv -o {output_path}" --timezone Asia/Bangkok
```

Example 19:00 Asia/Bangkok run:

```bash
python scripts/run_xau_systematic_research_cycle.py --cycle-label 7pm --cycle-time 19:00 --cme-source-mode api_only --price-provider dukascopy_node --dukascopy-node-command-template "npx dukascopy-node -i {symbol} -from {from_iso} -to {to_iso} -t {timeframe} -f csv -o {output_path}" --timezone Asia/Bangkok
```

Fallback local test run:

```bash
python scripts/run_xau_systematic_research_cycle.py --cycle-label manual --cme-source-mode latest_existing --price-provider latest_local_import --timezone Asia/Bangkok
```

## Dukascopy-Node

The orchestrator accepts a command template and fills:

- `{symbol}`
- `{from_iso}`
- `{to_iso}`
- `{timeframe}`
- `{output_path}`

The command is optional and external. The Python code does not import or install Node packages.
If the command fails, the run continues with provider status `unavailable` and a blocked or
partial readiness result.

Expected normalized columns are:

```text
timestamp,open,high,low,close,volume
```

Bid/ask OHLC columns are converted to mid OHLC for research context.

## Readiness

- `blocked`: required context is missing, such as no fusion report, no price bars, no basis,
  or no latest traded price.
- `partial`: CME and price context exist, but session open, ATR/RV, candle state, IV/range,
  or volume/OI freshness is incomplete.
- `ready_for_shadow_review`: all required context exists and is fresh enough for later
  shadow-review logic.

`ready_for_shadow_review` is still not a signal.

## Output

Outputs are saved under:

```text
backend/data/reports/xau_systematic_research/{cycle_id}/
```

Files:

- `cycle.json`
- `source_manifest.json`
- `aligned_state.json`
- `ai_research_pack.json`
- `ai_research_pack.md`
- `ai_handoff_context.md`
- `metadata.json`

## Why This Is Not Live Trading

This feature only aligns research data and writes local reports. It does not connect to
brokers, place orders, send paper-trading instructions, calculate position size, or claim
profitability. OI is treated as a structural map only.

## Next Feature

Next feature after this:

```text
031-xau-shadow-signal-decision-engine
```
