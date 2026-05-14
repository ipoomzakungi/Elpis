# Research: XAU Forward Journal Outcome Price Updater

**Date**: 2026-05-14
**Feature**: 016-xau-forward-journal-outcome-price-updater

## Decision 1: Extend Existing Forward Journal Package

**Decision**: Add price-outcome behavior inside `backend/src/xau_forward_journal/` rather than creating a new top-level XAU package.

**Rationale**: The feature updates saved Forward Journal outcome windows and must preserve feature 015 snapshot immutability, report-store paths, conservative outcome rules, and API grouping. Keeping the slice inside the existing package limits scope and avoids duplicating journal persistence behavior.

**Alternatives considered**:

- Create a new `xau_price_outcomes` package. Rejected because it would duplicate journal loading, artifact paths, and conflict handling.
- Add behavior to XAU Vol-OI or reaction packages. Rejected because those packages create snapshot inputs, while this feature updates journal outcomes after the snapshot.

## Decision 2: Use Polars For OHLC File Loading

**Decision**: Use Polars to read and normalize local CSV/Parquet OHLC candles and existing public OHLC output files.

**Rationale**: The constitution requires Polars as the primary DataFrame engine. The existing backend already depends on Polars and PyArrow, and other research workflows use Parquet files under ignored local data paths.

**Alternatives considered**:

- Use pandas. Rejected because Polars is the project default and no compatibility need requires pandas here.
- Parse CSV manually. Rejected because timestamp/schema validation is safer through structured data-frame operations.

## Decision 3: Treat Coverage As A First-Class Result

**Decision**: Compute and return a per-window coverage summary before and during outcome updates.

**Rationale**: The feature must never fabricate missing candles. A coverage result lets the researcher see complete, partial, and missing windows explicitly and explains why a window is completed, inconclusive, or still pending.

**Alternatives considered**:

- Update only windows with candles and silently ignore the rest. Rejected because missing data would be too easy to overlook.
- Reject the whole request when any window is missing. Rejected because researchers may legitimately have complete 30m/1h data while longer windows remain pending.

## Decision 4: Conservative Window Status Rules

**Decision**: Use `pending` for windows with no usable candles, `inconclusive` for partial windows, and completed outcome observations only for fully covered windows.

**Rationale**: The project’s research policy prioritizes data integrity over convenience. Partial coverage cannot support a completed outcome label, and missing coverage must remain visible.

**Alternatives considered**:

- Fill partial windows with available candles and mark them completed. Rejected because this would overstate evidence.
- Interpolate or forward-fill missing candles. Rejected because it fabricates data.

## Decision 5: Source Labeling Is Required For Every Result

**Decision**: Every coverage and update response must include one required source label: `true_xauusd_spot`, `gc_futures`, `yahoo_gc_f_proxy`, `gld_etf_proxy`, `local_csv`, `local_parquet`, or `unknown_proxy`.

**Rationale**: The user explicitly requires source labeling. The project already treats Yahoo GC=F and GLD as OHLCV proxies only, not true XAUUSD spot. Local files may contain spot or proxy data, so they must be labeled by source/file type and limitations.

**Alternatives considered**:

- Infer spot/proxy status only from symbol. Rejected because local files may contain custom or vendor-derived data with ambiguous meaning.
- Allow free-form labels. Rejected because downstream dashboard and tests need deterministic limitation behavior.

## Decision 6: Proxy Limitation Notes Are Attached Near Outcomes

**Decision**: Attach proxy limitations to coverage summaries, update reports, outcome notes/limitations, and dashboard display.

**Rationale**: A researcher needs to see immediately whether outcomes came from true XAUUSD spot, GC futures, Yahoo GC=F, GLD, local files, or unknown proxy data. Proxy outcomes are useful research observations but must not be mistaken for true spot candles.

**Alternatives considered**:

- Put proxy notes only in report footnotes. Rejected because dashboard users could miss the limitation.
- Block all proxy sources. Rejected because GC futures, GC=F, and GLD are allowed research proxies when clearly labeled.

## Decision 7: Persist Price Updates Under Existing Journal Artifact Root

**Decision**: Store price-update reports under `data/reports/xau_forward_journal/<journal_id>/price_updates/`.

**Rationale**: Feature 015 already stores journal artifacts under the ignored journal report root. Keeping price updates under the same entry directory preserves traceability and stays covered by the generated artifact guard.

**Alternatives considered**:

- Store price update reports in a separate report root. Rejected because it would split evidence for one journal entry across unrelated directories.
- Store only in `outcomes.json`. Rejected because the required output includes coverage summary, missing checklist, proxy notes, and report artifacts.

## Decision 8: Add Two Local Research Endpoints

**Decision**: Add `POST /api/v1/xau/forward-journal/entries/{journal_id}/outcomes/from-price-data` and `GET /api/v1/xau/forward-journal/entries/{journal_id}/price-coverage`.

**Rationale**: The user explicitly requested both interfaces. The first mutates only outcome state; the second reads coverage state without needing raw file inspection.

**Alternatives considered**:

- Extend the existing `/outcomes` endpoint only. Rejected because manual outcome label updates and price-derived outcome updates have different inputs and validation rules.
- Make coverage a query parameter on update. Rejected because coverage inspection should be possible without writing updated outcomes.

## Decision 9: Dashboard Remains Inspection-Only

**Decision**: Extend `/xau-vol-oi` Forward Journal panel to display coverage and updated outcome information, without adding trading controls or execution language.

**Rationale**: The project is in v0 Research Platform. The dashboard should help researchers review evidence and limitations, not trigger trades or imply prediction.

**Alternatives considered**:

- Add dashboard controls for running updates. Deferred because the current success criteria require display/build behavior, while backend/API contract validation covers update mechanics.
- Create a new page. Rejected because feature 015 already placed Forward Journal review in `/xau-vol-oi`.

## Decision 10: Tests Use Synthetic Fixtures Only

**Decision**: Automated tests must use synthetic journal entries and synthetic OHLC candles; they must not perform real external downloads.

**Rationale**: Tests should be deterministic, offline-capable, and free of paid/private data dependencies. This matches existing public-data and Forward Journal test patterns.

**Alternatives considered**:

- Call Yahoo Finance during tests. Rejected because network availability and source data can change.
- Use generated report artifacts as tracked fixtures. Rejected because generated data must remain ignored and untracked.
