# Quickstart: CME Expected Range And Context Parity

**Feature**: 017-cme-expected-range-and-context-parity
**Date**: 2026-06-04

## Scope

This feature adds research-only CME expected-range context parity. It distinguishes CME-native numeric SD bands from IV-derived fallback bands, preserves fractional DTE and source timing fields, keeps range labels non-numeric, and preserves missing basis/null Matrix semantics.

It does not run a strategy test, create alerts, connect to brokers, manage positions, store private CME session material, or claim predictive power.

## Focused Validation

Run from the repository root:

```powershell
python -m pytest research_xau_vol_oi/tests/test_systematic_engine_field_inventory.py -q
```

Run the new backend parity tests from `backend/`:

```powershell
cd backend
python -m pytest tests/unit/test_xau_expected_range_context_parity.py -q
python -c "from src.main import app; print('backend import ok')"
```

Expected results:

- Native numeric bands preserve CME-native source and upper/lower bands.
- Missing native bands with IV/reference/DTE derive 1SD, 2SD, and 3SD.
- Range-label-only context does not create numeric SD bands.
- Missing basis keeps spot-equivalent levels unavailable.
- Blank Matrix cells remain null rather than zero.
- Inventory marks the new expected-range snapshot fields as closing P0 data-parity gaps.

## Manual CME Discovery Checklist

If an authenticated CME/QuikStrike page is available later, inspect only visible page fields for:

- ATM or report-level IV
- Vol Settle
- Expected Move
- 1SD, 2SD, and 3SD numeric bands
- Delta ranges
- SD ranges
- Futures reference price
- DTE and expiration
- Source view name
- Capture timestamp

Store only sanitized visible text or structured extracted values. Do not store cookies, tokens, headers, HAR files, screenshots, private URLs, credentials, endpoint replay payloads, broker fields, wallet fields, order fields, or execution fields.

## Not Ready For Strategy Test

After Feature 017, the project is closer to daily structural map readiness but still should not run a 2SD strategy test until the next feature builds a daily structural map and no-lookahead protocol.
