# Data Model: XAU Daily Research Workbench

## XauDailyWorkbenchRunRequest

Input model for one local daily research run.

- `session_date`: Optional date filter or local bundle session date.
- `expiration_code`: Optional CME option expiration code.
- `traded_instrument`: Chart/instrument under review, default `XAUUSD`.
- `cme_source`: `local_bundle`, `latest_existing`, or `api_only`.
- `input_dir`: Local bundle folder for `local_bundle`.
- `gc_reference_price`: Optional GC/futures reference.
- `traded_reference_price`: Optional XAU/GO/traded chart reference.
- `session_open_price`: Optional session open.
- `manual_basis`: Optional explicit basis.
- `price_provider`: Static fixture by default; Yahoo fallback is named but not network-enabled in this slice.
- `output_root`: Optional local reports root.
- `map_id`: Optional map id override for fixture or repeatable local runs.
- `run_candidates`: Whether to run Feature 021.
- `research_only_acknowledged`: Must remain true.

## XauDailyWorkbenchRunResult

Output model for a persisted workbench run.

- `run_id`
- `created_at`
- `cme_source`
- `traded_instrument`
- `session_date`
- `expiration_code`
- `map_id`
- `candidate_set_id`
- `readiness`: `completed`, `partial`, or `blocked`
- `missing_inputs`
- `no_signal_reasons`
- `artifact_paths`
- `map_metadata`
- `daily_map`
- `candidate_set`
- `candidate_metadata`
- `research_only=true`
- `signal_allowed=false`

## XauDailyWorkbenchCandidateMetadata

Metadata sidecar stored beside candidate artifacts.

- `candidate_set_id`
- `map_id`
- `created_at`
- `candidate_count`
- `readiness`
- `missing_inputs`
- `no_signal_reasons`
- `research_only=true`
- `signal_allowed=false`

## Providers

- `CmeDataSource`: Loads or creates a structural map.
- `FuturesPriceProvider`: Supplies a GC/futures reference.
- `TradedPriceProvider`: Supplies a traded chart reference.
- `SessionOpenProvider`: Supplies session open context.

Implemented providers:

- `LocalBundleSource`
- `LatestExistingXauArtifactSource`
- `ApiOnlyCmeSource` as blocked/unconfigured
- `StaticFixturePriceProvider`

## Artifacts

Workbench run:

```text
data/reports/xau_daily_workbench/{run_id}/workbench.json
data/reports/xau_daily_workbench/{run_id}/workbench.md
```

Candidate sidecars:

```text
data/reports/xau_daily_structural_map/{map_id}/candidates.json
data/reports/xau_daily_structural_map/{map_id}/candidates.md
data/reports/xau_daily_structural_map/{map_id}/candidate_metadata.json
```
