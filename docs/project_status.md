# Elpis Project Status

**Updated**: 2026-06-08
**Current branch**: `codex/xau-vol-oi-research-pipeline`
**Current phase**: v0 Research Platform

Elpis is still a research-first trading system. The current code can create
research candidate labels, but it is not a systematic trading execution system
and must not be promoted to live trading, paper trading, alerts, broker access,
orders, position sizing, or PnL logic.

## Current Result

Feature 025 is implemented as a backend local XAU Walk-Forward Range Desk
Research Runner. It creates scheduled research snapshots, resolves native CME
SD from saved `range_bands.json` sidecars or fixture inputs, maps futures levels
to traded levels with Diff/Basis, creates research-only initial/recovery order
templates, optionally simulates outcomes from local OHLCV bars, persists local
history artifacts, and exposes API/CLI access.

Feature 024B is implemented as a backend local XAU Data Capability Audit. It
reads saved CME/QuikStrike and XAU artifacts and reports which fields are
source-backed, partial, unavailable, or blocked. It still avoids entries,
alerts, PnL, position sizing, paper trading, and live execution.

Feature 024A is implemented as a backend local XAU Range Desk / Diff-SD
planner. It maps futures-side CME SD and OI levels into traded-instrument
planning levels.

Feature 023 is implemented as a backend local XAU candidate forward-outcomes
layer on top of the Feature 021/022 candidate workflow.

Feature 021 remains the research-only 2SD-3SD XAU SD/OI mean-reversion
candidate classifier. It supports:

- `long_reversion_candidate`
- `short_reversion_candidate`
- `no_trade`
- `breakout_risk`

Feature 022 now wraps the existing local CME/XAU pieces into one daily workflow:

- load a local XAU bundle or latest existing structural map
- apply manual/static GC, traded reference, and session-open inputs
- record provider statuses and a basis snapshot
- build or read the persisted daily structural map
- run Feature 021 candidate classification
- persist candidate sidecars beside the map
- persist a workbench run artifact
- expose local API endpoints for run/latest/run-detail/map/candidate review
- expose a local CLI script for fixture/local-bundle/latest-existing runs

Every output remains:

```text
signal_allowed = false
research_only = true
```

Feature 023 attaches local price-bar forward outcome labels to saved Feature
021/022 candidate sets. It supports:

- 30m, 1h, 4h, session-close, and next-day outcome windows
- local CSV, JSON, and Parquet price bars
- short/long MFE and MAE
- target 1/2/3 hits
- stop-reference hits
- returned-to-1SD flags
- 2SD, 3SD, 3.5SD, next-wall, and breakout-continuation flags
- missing and partial price-bar coverage states
- persisted local outcome artifacts
- local API and CLI access

Feature 023 still does not implement PnL, entries, alerts, broker execution,
position sizing, paper trading, live trading, or strategy profitability claims.

Feature 024A adds the missing manual Range Desk bridge:

- `diff_points = future_reference_price - traded_reference_price`
- `traded_offset = traded_reference_price - future_reference_price`
- `mapped_traded_level = futures_level + traded_offset`
- mapped future SD table
- mapped traded SD table
- mapped OI wall levels
- no-trade zone inside 1SD
- 2SD-3SD upper/lower research stretch zones
- planning-only target/invalidation references

Feature 024B adds a read-only data capability audit for saved local artifacts:

- OI and OI change availability
- intraday-volume qualification, including partial volume states
- volatility, DTE, and future-reference availability
- native SD and SD range availability
- delta and gamma availability when present in local XAU source rows
- GEX possibility only when source-backed gamma and OI are both available
- explicit unavailable or blocked statuses for missing fields

Default no-signal behavior remains explicit:

```text
Feature 021 is research-only; signal generation is disabled.
Feature 022 is a research-only daily workbench; signal generation is disabled.
Feature 023 is research-only; candidate outcome labels are not trading signals.
Feature 024A is research-only; Range Desk plans are not trading signals.
Feature 024B is research-only; capability audit rows are not trading signals.
Feature 025 is research-only; walk-forward order templates and outcomes are not trading signals.
```

## Latest XAU Smoke Validation

Validated on 2026-06-07 against existing local CME/QuikStrike XAU artifacts.
This validation did not use the BTC/Binance quickstart path. Current testing is
focused on XAU/CME local artifacts. Yahoo Finance is not the active XAU source
for this daily workbench slice.

Local XAU API inventory:

- XAU Vol-OI reports: 49
- XAU reaction reports: 47
- QuikStrike Vol2Vol reports: 53
- QuikStrike Matrix reports: 46
- XAU QuikStrike fusion reports: 44
- Forward journal entries: 38

Latest local report sample:

```text
XAU Vol-OI report: xau_vol_oi_20260606_105123_412747
Status: partial
Source rows: 60
Accepted rows: 60
Walls: 30
Zones: 30

XAU reaction report: xau_reaction_20260606_105123_xau_vol_oi_20260606_105123_412747
Status: completed
Reaction rows: 30
Risk-plan rows: 0

XAU fusion report: xau_quikstrike_fusion_20260606_105122_data_20260606_daily_snapshot
Status: partial
Fusion rows: 1938
Missing-context items: 7

Forward journal: xau_forward_journal_data_20260606_fetched_20260606_daily_snapshot_og2m6_391488594201
Data date: 2026-06-06
Outcome windows: 5 pending
```

Rendered dashboard validation:

- `/xau-vol-oi` loads successfully.
- The page displays the research-only notice, QuikStrike, Matrix, Fusion,
  Forward Journal, Reaction Report, Basis Snapshot, Expected Range, Walls,
  Zones, and No-Trade Reasons sections.
- No frontend error text was visible in the rendered page.

Operational fix from this smoke:

- Some ignored local XAU report artifacts were generated by older schemas.
- XAU Vol-OI and XAU reaction list endpoints now skip unreadable legacy
  metadata in list views instead of returning a 500 for the whole dashboard.
- Direct reads of invalid legacy report IDs still fail normally; the fix only
  keeps list/dashboard views usable with mixed old and current local artifacts.

## What Exists Now

### Project Guardrails

- Research-first v0 platform guardrails are documented in `AGENTS.md` and the
  constitution.
- Live trading, paper trading, broker execution, private exchange keys, real
  order execution, leverage, real position management, Rust execution engines,
  ClickHouse, PostgreSQL, Kafka, Kubernetes, and ML training remain forbidden in
  v0 unless the constitution/spec is explicitly updated.
- A narrow local read-only research credential exception exists only for market
  data ingestion such as CME/QuikStrike-style sources, with strict no-secret
  handling.

### Course Doctrine

- The course doctrine index exists at
  `docs/course_source/COURSE_DOCTRINE_INDEX.md`.
- It locks the rule that OI is a structural map, not a buy/sell signal.
- IV and SD are expected-move/risk boundaries, not guaranteed reversals.
- OI change and intraday flow are activation/freshness context.
- CME GC strikes and SD bands must be basis-adjusted before XAU/GO use.
- Missing basis, expected range, open context, stale data, or candle context
  means `NO_TRADE`, `WAIT`, or `signal_allowed=false`.

### CME And QuikStrike Foundation

- The local QuikStrike/WebForms path exists.
- The daily runner can capture Vol2Vol, Matrix, XAU QuikStrike Fusion, XAU
  Vol-OI, XAU Reaction, and XAU Forward Journal daily snapshot artifacts.
- API-only credential handling exists for approved read-only research data.
- Generated reports and data remain ignored and must not be committed.

### Expected Range And Structural Map Layers

- Feature 017 handles CME expected-range parity and blocks fake numeric SD
  creation from range labels.
- Feature 018 creates a daily structural map with basis, expected range, OI
  walls, session context, readiness, and no-signal reasons.
- Feature 019 persists daily structural map artifacts.
- Feature 020A reads local bundle-shaped XAU artifacts and persists maps while
  preserving missing context.
- Feature 021 consumes those maps and labels research candidates without
  creating signals.
- Feature 022 orchestrates local XAU workbench runs and persists map, candidate,
  and workbench artifacts for API review.
- Feature 023 consumes saved candidate sets plus local OHLCV bars and persists
  candidate outcome evidence for forward windows without PnL or execution.
- Feature 024A consumes manual/research future reference, traded reference,
  future-side SD levels, optional session open, and optional OI walls, then
  returns mapped traded levels for practical chart review without execution
  semantics.
- Feature 024B consumes saved local Vol2Vol, Matrix, Fusion, and XAU Vol-OI
  artifacts, then returns capability evidence for data readiness without
  signal, prediction, execution, or PnL semantics.

## What Feature 021 Means

Feature 021 means the system can label one timestamp as a research candidate or
blocked/no-trade state. It does not prove that the strategy works.

Example research-only interpretation:

```text
Price between upper 2SD and upper 3SD
+ rejection confirmation
+ IV not expanding
+ flow not confirming breakout
= short_reversion_candidate
```

Breakout context blocks mean-reversion interpretation:

```text
Price beyond 3SD
+ IV expanding
+ flow-through-wall
+ candle acceptance
= breakout_risk
```

Feature 022 automates the local backend handoff from saved XAU bundle/map
artifacts to candidate sidecars. The caller still must supply or already have
source-backed traded price, GC reference, session open, and source bundle/map
context. Confirmation, IV state, and flow state are still `unavailable` in this
slice and need a later context-state engine.

Feature 023 automates the local backend handoff from saved candidate sidecars to
forward outcome artifacts. The caller still must supply local price bars, and
missing or partial bars remain explicit coverage limitations.

## Feature 022 Workbench API

Implemented local endpoints:

```text
POST /api/v1/research/xau/workbench/run
GET  /api/v1/research/xau/workbench/latest
GET  /api/v1/research/xau/workbench/runs/{run_id}
GET  /api/v1/research/xau/workbench/maps/{map_id}
GET  /api/v1/research/xau/workbench/candidates/{map_id}
```

Local script:

```text
backend/scripts/run_xau_daily_research_workbench.py
```

Persisted workbench artifacts:

```text
data/reports/xau_daily_workbench/{run_id}/workbench.json
data/reports/xau_daily_workbench/{run_id}/workbench.md
```

Persisted candidate sidecars:

```text
data/reports/xau_daily_structural_map/{map_id}/candidates.json
data/reports/xau_daily_structural_map/{map_id}/candidates.md
data/reports/xau_daily_structural_map/{map_id}/candidate_metadata.json
```

Dashboard status:

```text
backend API implemented
frontend workbench page not implemented in this slice
```

## Feature 023 Candidate Outcome API

Implemented local endpoints:

```text
POST /api/v1/research/xau/candidate-outcomes/run
GET  /api/v1/research/xau/candidate-outcomes/latest
GET  /api/v1/research/xau/candidate-outcomes/{outcome_run_id}
```

Local script:

```text
backend/scripts/run_xau_candidate_forward_outcomes.py
```

Persisted outcome artifacts:

```text
data/reports/xau_candidate_outcomes/{outcome_run_id}/outcome_metadata.json
data/reports/xau_candidate_outcomes/{outcome_run_id}/outcomes.json
data/reports/xau_candidate_outcomes/{outcome_run_id}/outcomes.md
```

The outcome labels are evidence annotations only:

```text
target_hit
stop_hit
mean_reverted
breakout_continued
unresolved
unavailable
```

## Feature 024A Range Desk API

Implemented local endpoint:

```text
POST /api/v1/research/xau/range-desk/plan
```

The request supplies future reference, traded reference, future-side SD levels,
optional session open, and optional OI wall levels. The response returns:

```text
basis_snapshot
futures_levels
traded_levels
mapped_oi_walls
zones
target_plans
missing_inputs
limitations
signal_allowed=false
research_only=true
```

The endpoint is a calculator/planner only. It does not fetch live prices,
calculate PnL, create signals, issue alerts, size positions, connect to a
broker, or place orders.

## Feature 024B Data Capability Audit API

Implemented local endpoint:

```text
POST /api/v1/research/xau/data-capability-audit/run
```

The request can use the latest saved local reports or selected report IDs for
Vol2Vol, Matrix, Fusion, and XAU Vol-OI sources. The response returns:

```text
readiness
source_reports
capabilities
missing_capabilities
blocked_capabilities
limitations
signal_allowed=false
research_only=true
```

Current audit semantics:

- Vol2Vol and Matrix can provide OI, OI change, DTE, and future reference.
- Vol2Vol can provide intraday volume and SD/range evidence when present.
- Matrix and XAU Vol-OI volume are partial unless intraday qualification is
  source-backed.
- Fusion can provide native numeric SD and volatility context from expected
  range snapshots.
- Delta and gamma are only available when local XAU source rows contain them.
- GEX possibility is blocked unless source-backed gamma and OI are both
  available.

The endpoint is an evidence inventory only. It does not fetch fresh data,
calculate PnL, create signals, issue alerts, size positions, connect to a
broker, or place orders.

## Feature 025 Walk-Forward Research API

Implemented local endpoints:

```text
POST /api/v1/research/xau/walk-forward/run
GET  /api/v1/research/xau/walk-forward/latest
GET  /api/v1/research/xau/walk-forward/runs/{run_id}
GET  /api/v1/research/xau/walk-forward/runs/{run_id}/orders
GET  /api/v1/research/xau/walk-forward/runs/{run_id}/snapshots
```

Local script:

```text
backend/scripts/run_xau_walk_forward_research.py
```

Persisted artifacts:

```text
data/reports/xau_walk_forward/{run_id}/run_metadata.json
data/reports/xau_walk_forward/{run_id}/snapshots.json
data/reports/xau_walk_forward/{run_id}/range_desk_snapshots.json
data/reports/xau_walk_forward/{run_id}/research_orders.json
data/reports/xau_walk_forward/{run_id}/simulated_outcomes.json
data/reports/xau_walk_forward/{run_id}/run.md
data/reports/xau_walk_forward/{run_id}/order_history.md
```

Feature 025 uses native CME SD when available, but does not treat `range_label`
as numeric SD. Yahoo Finance support is optional and labeled
`research_fallback`; manual and fixture prices are the tested paths. Recovery
sizing is simulated only and is blocked when risk inputs are missing or
configured caps are exceeded. Every output remains:

```text
signal_allowed = false
research_only = true
```

## Missing Before Systematic Trading

- Frontend workbench page for the new Feature 022 API.
- API-only CME fetch path integration for the workbench after source readiness
  and credential handling are validated.
- Weekday fresh-data runs and freshness validation.
- Automatic traded-price, GC reference, and XAU/GO/broker-side reference
  providers.
- Frontend display and persistence for Range Desk and Data Capability Audit
  results.
- Frontend page for Feature 025 walk-forward Range Desk history.
- Source-backed automatic price-provider validation beyond manual/fixture and
  optional Yahoo fallback.
- Fresh source-provider coverage for fields still unavailable in the audit,
  especially Vol Chg, Future Chg, delta ranges, gamma, and GEX prerequisites.
- Automatic candle reaction classification:
  `rejection`, `close_back_inside`, `acceptance`, `neutral`, `unavailable`.
- Automatic IV state detection:
  `stable`, `compressing`, `expanding`, `unavailable`.
- Automatic flow-through-wall detection from volume, OI change, and price
  behavior near walls.
- Gamma/GEX regime estimation only if source-backed Greeks are available.
- Aggregated outcome statistics by regime, IV state, flow state, OI freshness,
  wall proximity, and session context.
- Shadow/paper research journal after historical and forward evidence exists.
- Live execution gate, risk sizing, broker integration, and order handling.

## Milestones

| Milestone | Status | Notes |
| --- | --- | --- |
| M0 Doctrine lock | Done | Course/source guardrails are documented. |
| M1 CME data extraction proof | Mostly done | Needs weekday fresh-data run and freshness validation. |
| M2 Expected range / SD parity | Done enough for research | Native numeric SD samples should continue to be collected. |
| M3 Basis-adjusted structural map | Mostly done | Needs automatic traded-price/reference providers. |
| M4 Structural map persistence | Done | Map artifacts are persisted locally. |
| M5 Real bundle adapter | Done, data-dependent | Needs real bundle files and map verification. |
| M6 Candidate research classifier | Done | Feature 021, research-only. |
| M7 Daily workbench API | Backend done | Feature 022, local bundle/latest-existing sources, candidate sidecars. |
| M7B Local workbench dashboard | Not done | Needs frontend page wired to Feature 022 API. |
| M8 Range Desk / Diff-SD planner | Backend done | Feature 024A maps CME future levels to traded chart levels. |
| M9 Data capability audit | Backend done | Feature 024B audits saved local artifacts for SD, Vol Chg, Future Chg, delta, gamma, GEX prerequisites. |
| M9B Walk-forward Range Desk runner | Backend done | Feature 025 creates scheduled research snapshots, order templates, and simulated outcomes. |
| M10 Candle / IV / flow state engine | Not done | Turns raw data into candidate context states. |
| M11 Forward outcome labels | Done | Feature 023 attaches local OHLCV outcome evidence to candidates. |
| M12 Research backtest | Not done | Required before any strategy claim. |
| M13 Dashboard / decision console | Partly planned | Should show data freshness, map, candidates, and no-trade reasons. |
| M14 Paper/shadow mode | Not done | Not allowed until research gates are satisfied. |
| M15 Live trading gate | Not allowed | Requires historical, forward, paper, and risk validation first. |

## Next Recommended Feature

Create Feature 024C:

```text
024c-xau-range-desk-audit-ui-persistence
```

Purpose:

```text
Persist and display Range Desk plans and Data Capability Audit output in the
local research dashboard without signals, alerts, PnL, or execution semantics.
```

Then create Feature 026:

```text
026-xau-reaction-state-engine
```

Purpose:

```text
Automatically compute confirmation_state, iv_state, and flow_state from
source-backed price bars, IV context, volume, OI change, and wall interaction.
```

Then create Feature 027:

```text
027-xau-outcome-statistics-backtest
```

Purpose:

```text
Aggregate outcome labels by regime, IV state, flow state, OI freshness, wall
proximity, and session context before any strategy claim.
```

## Current System Stage

```text
research candidate generation plus forward outcome evidence
```

Not:

```text
systematic trading execution
```
