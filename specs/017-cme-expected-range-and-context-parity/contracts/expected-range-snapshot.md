# Contract: Expected Range Snapshot

**Feature**: 017-cme-expected-range-and-context-parity

This contract documents the local research payload shape for expected-range context. It is not a broker, exchange, execution, or live-trading contract.

## CME-Native Snapshot

```json
{
  "source_report_id": "vol2vol_20260604",
  "source_view": "QUIKOPTIONS VOL2VOL",
  "capture_timestamp": "2026-06-04T12:00:00Z",
  "official_release_ts": "2026-06-04T10:00:00Z",
  "source_status": "final",
  "product": "Gold",
  "option_product_code": "OG|GC",
  "futures_symbol": "GC",
  "expiration_code": "OG1M6",
  "expiry_date": "2026-06-05",
  "reference_futures_price": 4549.2,
  "report_level_iv": 0.2508,
  "vol_settle": 0.2508,
  "fractional_dte": 3.47,
  "cme_numeric_1sd": 111.3,
  "cme_numeric_2sd": 222.6,
  "cme_numeric_3sd": 333.9,
  "upper_1sd": 4660.5,
  "lower_1sd": 4437.9,
  "upper_2sd": 4771.8,
  "lower_2sd": 4326.6,
  "upper_3sd": 4883.1,
  "lower_3sd": 4215.3,
  "range_source": "cme_native",
  "extraction_quality": "complete",
  "limitations": []
}
```

## IV-Derived Snapshot

```json
{
  "source_report_id": "vol2vol_20260604",
  "source_view": "QUIKOPTIONS VOL2VOL",
  "capture_timestamp": "2026-06-04T12:00:00Z",
  "source_status": "unknown",
  "product": "Gold",
  "option_product_code": "OG|GC",
  "reference_futures_price": 4549.2,
  "report_level_iv": 0.2508,
  "fractional_dte": 3.47,
  "range_source": "derived_from_iv",
  "extraction_quality": "complete",
  "limitations": [
    "CME-native numeric SD bands were unavailable; expected range was derived from report-level IV, futures reference price, and fractional DTE."
  ]
}
```

## Contract Rules

- Native numeric values are source-of-truth when complete.
- IV-derived values must be labeled as fallback.
- `range_label` alone must not populate numeric band fields.
- Missing basis must not produce spot-equivalent levels.
- Blank/null Matrix cells remain blank/null.
- Payloads must not include cookies, tokens, headers, HAR files, screenshots, credentials, private URLs, endpoint replay material, broker fields, wallet fields, order fields, or execution fields.
