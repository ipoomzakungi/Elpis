# Contract: XAU Daily Structural Map

**Feature**: 018-xau-daily-structural-map

This contract documents the local research payload shape. It is not an execution, broker, alert, order, position, or live-trading contract.

## Full-Context Map Example

```json
{
  "map_id": "xau_map_20260602_og1m6",
  "session_date": "2026-06-02",
  "created_at": "2026-06-04T12:00:00Z",
  "source_product": "Gold",
  "option_product_code": "OG|GC",
  "futures_symbol": "GC",
  "expiration_code": "OG1M6",
  "expiry_date": "2026-06-05",
  "reference_futures_price": 4549.2,
  "traded_instrument": "XAUUSD",
  "traded_reference_price": 4536.7,
  "basis": 12.5,
  "basis_source": "computed",
  "basis_mapping_available": true,
  "basis_timestamp_alignment_status": "unknown",
  "expected_range_source": "cme_native",
  "report_level_iv": 0.2508,
  "fractional_dte": 3.47,
  "lower_1sd": 4437.9,
  "upper_1sd": 4660.5,
  "lower_2sd": 4326.6,
  "upper_2sd": 4771.8,
  "lower_3sd": 4215.3,
  "upper_3sd": 4883.1,
  "session_open_price": 4538.0,
  "session_open_source": "manual_research_input",
  "session_open_available": true,
  "open_side_vs_1sd": "inside_1sd",
  "open_distance_points": -1.3,
  "wall_count": 1,
  "walls": [
    {
      "wall_id": "wall_4550_call",
      "expiry": "2026-06-05",
      "expiration_code": "OG1M6",
      "strike": 4550.0,
      "wall_type": "call",
      "open_interest": 1000.0,
      "oi_change": null,
      "volume": null,
      "wall_score": 0.42,
      "freshness_state": "confirmed",
      "spot_equivalent_level": 4537.5,
      "distance_to_traded_price": 0.8,
      "distance_to_session_open": -0.5,
      "inside_1sd": true,
      "inside_2sd": true,
      "near_expected_range_boundary": false,
      "open_side_vs_wall": "above_wall",
      "mapping_status": "mapped",
      "limitations": []
    }
  ],
  "data_quality_state": "structural_map_ready",
  "signal_allowed": false,
  "no_signal_reasons": [
    "Feature 018 is map-only; signal generation is disabled."
  ],
  "limitations": []
}
```

## Contract Rules

- `signal_allowed` is always false.
- Missing basis keeps `spot_equivalent_level`, `distance_to_traded_price`, and `distance_to_session_open` null.
- Missing expected range keeps SD fields null and expected-range membership fields null.
- Missing session open keeps session-open fields null and readiness partial.
- Blank Matrix values and unavailable optional wall metrics remain null.
- Payloads must not include cookies, tokens, headers, HAR files, screenshots, credentials, private URLs, endpoint replay material, broker fields, wallet fields, order fields, or execution fields.
