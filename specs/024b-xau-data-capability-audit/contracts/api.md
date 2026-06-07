# API Contract: XAU Data Capability Audit

All endpoints are local research-only endpoints mounted under `/api/v1`.

Every successful response includes:

- `research_only=true`
- `signal_allowed=false`
- `no_signal_reasons`
- `limitations`

## POST /api/v1/research/xau/data-capability-audit/run

Runs a read-only audit of saved local XAU CME/QuikStrike artifacts.

```json
{
  "max_reports_per_source": 1,
  "research_only_acknowledged": true
}
```

Optional request fields:

- `reports_dir`
- `vol2vol_report_ids`
- `matrix_report_ids`
- `fusion_report_ids`
- `xau_vol_oi_report_ids`
- `max_reports_per_source`
- `research_only_acknowledged`

Response model: `XauDataCapabilityAuditResult`.

Key response fields:

- `readiness`
- `source_reports`
- `capabilities`
- `missing_capabilities`
- `blocked_capabilities`
- `limitations`
- `research_only`
- `signal_allowed`

Capability result shape:

```json
{
  "capability": "has_gamma",
  "status": "unavailable",
  "source_count": 0,
  "row_count": 60,
  "non_null_count": 0,
  "evidence": [
    {
      "source_type": "xau_vol_oi",
      "report_id": "xau_vol_oi_example",
      "field_names": ["gamma"],
      "row_count": 60,
      "non_null_count": 0,
      "sample_values": []
    }
  ],
  "limitations": ["No audited artifact exposes has_gamma."]
}
```

## Forbidden Behavior

The API does not expose buy/sell signals, alerts, order instructions, position
sizing, PnL, broker access, paper trading, live trading, automatic trade
placement, or strategy profitability claims.
