# XAU Options Feature Validity and Candidate Freeze

Feature 032A audits Feature 032 without searching for additional strategies. It checks
whether options fields have real time variation, removes concurrent rolling outcomes,
replaces episode-level inference with session-clustered inference, runs matched controls,
and freezes candidate validation v2.

## Run

From `backend`:

```powershell
python scripts/run_xau_options_feature_validity_audit.py --permutations 1000
```

By default, the CLI uses the latest complete Feature 032 report and the retained raw
Vol2Vol data. A specific Feature 032 report can be supplied with `--source-report`.

## Semantics

- Source OI Change is audited separately from derived same-strike OI change.
- Repeated OI values are structural snapshots, not new directional observations.
- Intraday volume is tested for cumulative behavior before interval volume is derived.
- Negative volume resets become null within a session/series instead of false flow.
- IV slopes use actual value changes rather than repeated source values.
- Prior-session, three-session, five-session OI changes and wall persistence are retained
  as separate structural fields.

## Independence and Inference

The revised simulation permits one active position per experiment, side, series, and
configuration. Cost scenarios do not create new opportunities. Statistical inference
uses session-level means, session-block bootstrap, clustered sign permutations, and
Benjamini-Hochberg adjustment. Episode-level p-values are explicitly invalidated.

## Candidate Validation V2

Candidate rules are frozen in `config/xau_options_candidate_validation_v2.json`:

- `C1`: fixed-morning MR0 with 0.50SD target
- `C2`: rolling-30m MR0 with 0.25SD target and one-position accounting
- `C3`: fixed-morning MR2 with 0.50SD target, enabled only if matched controls pass
- `BO0_MONITOR`: fixed-morning breakout observation only

The calibration cutoff is July 16, 2026. Only completed sessions beginning July 17 may
enter validation-v2. Any rule change requires a v3 registry and new hashes.

All outputs remain `research_only=true` and `signal_allowed=false`.
