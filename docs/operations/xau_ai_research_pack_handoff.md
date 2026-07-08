# XAU AI Research Pack Handoff

## Where Packs Are Saved

Each systematic research cycle writes an output folder under:

```text
backend/data/reports/xau_systematic_research/{cycle_id}/
```

The main AI-readable files are:

- `ai_research_pack.json`
- `ai_research_pack.md`
- `ai_handoff_context.md`

## Which File To Paste

Paste this file to another AI or reviewer:

```text
ai_handoff_context.md
```

It contains the concise research summary, source status, mapped levels, readiness, and
explicit guardrails.

## What Another AI Should Infer

The other AI may inspect:

- whether CME and price data were available and fresh
- whether basis was available and how mapped levels were calculated
- which futures-side walls were mapped to traded-side levels
- whether session open, ATR/RV, and candle state are present
- why the cycle is blocked, partial, or ready for shadow review

## What Another AI Must Not Infer

The pack must not be treated as:

- a buy/sell signal
- entry, stop, or target advice
- position sizing
- live or paper-trading readiness
- proof that a strategy is profitable

The pack is research-only and not a trade signal. Every generated object must keep
`research_only=true` and `signal_allowed=false`.
