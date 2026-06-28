# Research: XAU Candidate Forward Outcomes

## Decision: Use Feature 021 Candidate Sets As The Immutable Input

**Rationale**: Feature 021 already defines candidate ids, side, target references, stop references, SD bands, context states, and no-signal guardrails. Outcome runs should attach evidence to that candidate contract instead of mutating the structural map or workbench output.

**Alternatives considered**:

- Recompute candidates from maps during outcome runs: rejected because it would make evidence dependent on current classifier behavior rather than the saved candidate artifact.
- Store outcomes inside `candidates.json`: rejected because it would rewrite the candidate snapshot.

## Decision: Use Local OHLCV Files And Static Fixtures First

**Rationale**: The user explicitly noted current testing is XAU-focused and not using BTC. Local CSV/JSON/Parquet files support reproducible XAU research without network access or Yahoo dependence.

**Alternatives considered**:

- Add yfinance now: rejected because tests must not require network and Yahoo is not the active XAU source for this slice.
- Add broker or exchange private price providers: rejected by v0 guardrails.

## Decision: Conservative Missing And Partial Coverage

**Rationale**: Missing bars must not become invented evidence. Partial bars can provide visible OHLC facts, but the coverage status and limitations must state that the window is incomplete.

**Alternatives considered**:

- Drop partial windows: rejected because available OHLC may still help researchers inspect data gaps.
- Fill gaps from nearby candles: rejected because it fabricates price evidence.

## Decision: Label Outcomes, Not Trades Or PnL

**Rationale**: The course hypothesis needs forward evidence before claims. The first useful measurement is whether target, stop, 1SD, 3SD, or 3.5SD references were touched.

**Alternatives considered**:

- Add PnL and position sizing: rejected as premature and explicitly forbidden.
- Add alerts for target/stop hits: rejected because alerts are outside this research-only evidence layer.
