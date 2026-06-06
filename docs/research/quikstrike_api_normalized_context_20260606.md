# QuikStrike API-Normalized XAU Data Context

Created: 2026-06-06
Purpose: handoff context for a research model that needs to understand what the
Elpis QuikStrike API-only pipeline can fetch and normalize for XAU/Gold options.

This document is sanitized. It intentionally excludes credentials, cookies,
headers, request bodies, response bodies, SAML values, viewstate values, HAR,
screenshots, and private full URLs.

## Current Proven State

We proved that Elpis can fetch QuikStrike Gold (OG|GC) data without opening a
browser by using:

1. HTTP login through CME SSO.
2. SAML handoff to QuikStrike.
3. Disclaimer acceptance.
4. ASP.NET WebForms postbacks for navigation/view changes.
5. Full selected-page GET after each postback.
6. In-memory extraction from safe page data.
7. Persistence into local research artifacts.

The API-only command is:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_daily_xau_quikstrike_snapshot.ps1 -ApiOnly
```

Latest normalized run:

- Digest id: `quikstrike_webforms_normalized_20260606_134625`
- Run timestamp: `2026-06-06T20:46:25+07:00`
- Vol2Vol report id: `quikstrike_api_20260606_134625`
- Matrix report id: `quikstrike_matrix_api_20260606_134625`

Important calendar caveat:

- This run was on Saturday, 2026-06-06.
- Saturday/Sunday are non-trading days, so QuikStrike may return the latest
  available prior trading data rather than fresh weekend market data.
- The Matrix title observed in the run includes prior-business-day comparison
  context such as `Open Interest Change Matrix (6/4/2026 vs 6/3/2026)`.
- Treat this run as a successful API/data-shape proof and a latest-available
  snapshot, not as proof of live weekend data freshness.

## Main Artifacts

Combined digest:

```text
data/reports/quikstrike_webforms_normalized/quikstrike_webforms_normalized_20260606_134625/digest.json
```

Vol2Vol normalized report:

```text
backend/data/reports/quikstrike/quikstrike_api_20260606_134625/report.json
backend/data/reports/quikstrike/quikstrike_api_20260606_134625/normalized_rows.json
backend/data/reports/quikstrike/quikstrike_api_20260606_134625/conversion_rows.json
```

Matrix normalized report:

```text
backend/data/reports/quikstrike_matrix/quikstrike_matrix_api_20260606_134625/report.json
backend/data/raw/quikstrike_matrix/quikstrike_matrix_api_20260606_134625_normalized_rows.json
backend/data/processed/quikstrike_matrix/quikstrike_matrix_api_20260606_134625_xau_vol_oi_input.csv
```

## Views Fetched

API-only normalized fetch completed all requested views:

- `intraday_volume`
- `eod_volume`
- `open_interest`
- `oi_change`
- `churn`
- `open_interest_matrix`
- `oi_change_matrix`
- `volume_matrix`
- `settlements`
- `futures_volume_oi`

## Vol2Vol Data Coverage

Source surface: `QUIKOPTIONS VOL2VOL`
Product: `Gold (OG|GC)`
Primary option expiration in this run: `OG2M6`
Future reference price observed: `4365.3`
DTE observed: about `6.15`

Rows:

- Total normalized rows: `300`
- Conversion rows: `60`
- Views: `5`
- Rows per view:
  - `intraday_volume`: `60`
  - `eod_volume`: `60`
  - `open_interest`: `60`
  - `oi_change`: `60`
  - `churn`: `60`
- Each Vol2Vol view contains put/call rows by strike.

Fields available in Vol2Vol normalized rows:

- `capture_timestamp`
- `product`
- `option_product_code`
- `futures_symbol`
- `expiration_code`
- `dte`
- `future_reference_price`
- `view_type`
- `strike`
- `strike_id`
- `option_type`
- `value`
- `value_type`
- `vol_settle`
- `range_label`
- `sigma_label`
- `source_view`
- `strike_mapping_confidence`
- `extraction_warnings`
- `extraction_limitations`

Vol2Vol value meanings:

- For `view_type = intraday_volume`, `value` is intraday option volume.
- For `view_type = eod_volume`, `value` is end-of-day volume.
- For `view_type = open_interest`, `value` is open interest.
- For `view_type = oi_change`, `value` is open interest change.
- For `view_type = churn`, `value` is churn / OI-change-to-volume style metric.
- `vol_settle` is the per-strike volatility/vol-settle curve value when present.
- `range_label` is the expected-range bucket label from the chart payload.

Vol2Vol range and volatility notes:

- Rows with `vol_settle`: `280` of `300`.
- Rows with `range_label`: `300` of `300`.
- `range_label` distribution:
  - `1`: `100` rows
  - `2`: `110` rows
  - `3`: `90` rows
- `sigma_label` is currently null in persisted rows.
- We therefore have range-bucket context, but not a separate clean SD summary
  table in this artifact.

Vol2Vol status:

- Report status is `partial`.
- This is because strike mapping confidence is `partial`, not because rows are
  missing.
- The existing validator considers the numeric chart x-values plausible Gold
  strikes but not fully cross-checked against visible strike labels.
- `StrikeId` is preserved as internal QuikStrike metadata and is not used as the
  strike.

Example Vol2Vol row shape:

```json
{
  "view_type": "intraday_volume",
  "strike": 4000.0,
  "option_type": "call",
  "value": 0.0,
  "value_type": "intraday_volume",
  "vol_settle": 0.36357951771223895,
  "range_label": "3",
  "sigma_label": null,
  "expiration_code": "OG2M6",
  "dte": 6.15,
  "future_reference_price": 4365.3
}
```

## Matrix Data Coverage

Source surface: `OPEN INTEREST Matrix`
Product: `Gold (OG|GC)`

Rows:

- Matrix normalized rows: `1674`
- Matrix conversion rows: `319`
- Matrix row status:
  - `available`: `524`
  - `blank`: `1150`
- Matrix views:
  - `open_interest_matrix`: `558`
  - `oi_change_matrix`: `558`
  - `volume_matrix`: `558`

Matrix conversion coverage:

- Conversion rows: `319`
- Rows with `open_interest`: `319`
- Rows with `oi_change`: `93`
- Rows with `volume`: `112`
- Expiries present:
  - `OG2M6`
  - `OGN6`
  - `OGQ6`
  - `OGU6`
  - `OGV6`
  - `OGX6`
  - `OGZ6`
  - `OGG7`
  - `OGH7`
- Strike range in conversion rows: `4495` to `4645`

Fields available in Matrix normalized rows:

- `capture_timestamp`
- `product`
- `option_product_code`
- `futures_symbol`
- `source_menu`
- `view_type`
- `strike`
- `expiration`
- `dte`
- `future_reference_price`
- `option_type`
- `value`
- `value_type`
- `cell_state`
- `table_row_label`
- `table_column_label`
- `extraction_warnings`
- `extraction_limitations`

Matrix value meanings:

- For `view_type = open_interest_matrix`, `value` is open interest.
- For `view_type = oi_change_matrix`, `value` is open interest change.
- For `view_type = volume_matrix`, `value` is option volume.
- `cell_state = available` means numeric cell was parsed.
- `cell_state = blank` means the table cell was blank and was preserved as blank,
  not coerced to zero.

Example Matrix row shape:

```json
{
  "view_type": "open_interest_matrix",
  "strike": 4495.0,
  "expiration": "OGN6",
  "dte": 19.0,
  "futures_symbol": "GCQ6",
  "future_reference_price": 4365.3,
  "option_type": "call",
  "value": 53.0,
  "value_type": "open_interest",
  "cell_state": "available",
  "table_column_label": "GCQ6 4365.3 OGN6 19 DTE C"
}
```

## Supplemental Views

The API-only pipeline also fetches:

- `settlements`
- `futures_volume_oi`

Current handling:

- These are stored as supplemental table digests in the combined digest.
- They are not yet converted into the main XAU Vol-OI strike-row schema.
- They are useful as supporting context and for future parser work.

Supplemental table counts in latest digest:

- `settlements`: `5` table digests
- `futures_volume_oi`: `2` table digests

## Data We Have Now

The current normalized dataset is enough for research models to inspect:

- Per-strike call/put intraday volume.
- Per-strike call/put end-of-day volume.
- Per-strike call/put open interest.
- Per-strike call/put open interest change.
- Per-strike call/put churn.
- Per-strike vol-settle curve values where present.
- Per-strike expected-range bucket labels.
- Cross-expiry matrix open interest.
- Cross-expiry matrix OI change.
- Cross-expiry matrix volume.
- Blank/unavailable cells preserved explicitly.
- Supplemental settlement and futures volume/OI table context.

## Data Not Yet Fully Normalized

The following are fetched or partially represented, but not yet converted into a
final clean research table:

- Standalone SD band summary such as `1SD +/- value`, `2SD +/- value`, upper and
  lower boundaries, and percent range.
- `settlements` rows as a typed settlement schema.
- `futures_volume_oi` rows as a typed futures-volume/OI schema.
- A single fused, fully de-duplicated table that combines Vol2Vol and Matrix
  values into one row per `(expiration, strike, option_type)`.

## Safety And Research Limits

This is research-only data ingestion.

The artifacts do not imply:

- buy/sell signals
- trade entries
- alerts
- PnL
- prediction proof
- live-readiness
- broker/exchange account access
- order execution

Limitations preserved in artifacts:

- QuikStrike extraction is local-only and research-only.
- Only sanitized visible metadata, chart settings, and HTML table cells are
  processed.
- No credentials, cookies, headers, request bodies, response bodies, viewstate,
  SAML, HAR, screenshots, or private full URLs are persisted.
- Missing/blank matrix cells are preserved as blank/null and are not treated as
  zero.
- Weekend runs should be treated as latest-available vendor data, not fresh
  weekend market updates.

## Recommended Next Research Use

For another research model, start with:

1. `digest.json` to understand which views completed and where artifacts live.
2. Vol2Vol `normalized_rows.json` for per-strike single-expiry chart data.
3. Matrix `normalized_rows.json` for cross-expiry heatmap values.
4. Matrix `xau_vol_oi_input.csv` for easier spreadsheet/DataFrame loading.

Use Matrix conversion rows for multi-expiry OI/OI-change/volume research.
Use Vol2Vol rows for same-expiry chart-derived volume, OI, churn, volatility,
and range-bucket context.
