# XAU Candidate Validation v2

Feature 032B evaluates only the candidate rules frozen before the validation
period. It is a historical research workflow and cannot submit orders.

## Acceptance rules

A session is appended only when all of these conditions pass:

- the requested date is after `2026-07-16`;
- Vol2Vol returns the exact requested `sessionDate`;
- `collection_meta.complete` is explicitly `true`;
- Dukascopy XAUUSD has all 1,020 M1 bars from 07:00 through 23:59 Bangkok;
- the frozen manifest and C1/C2 candidate hashes match.

Incomplete, substituted, pre-cutoff, and duplicate sessions fail closed. C3 is
descriptive only and BO0 is monitor-only.

## Run a completed session

From `backend`:

```powershell
python scripts/run_xau_candidate_validation_v2.py `
  --session-date 2026-07-17
```

Add `--resolve-ambiguous-with-ticks --tick-data-file <path>` to resolve only
same-minute ambiguous outcomes when timestamped finer data is locally available.
The original M1 status is retained. Missing or inconclusive finer data leaves the
outcome ambiguous.

Validation journals are stored under:

```text
data/reports/xau_candidate_validation/v2/
```

The JSONL streams are append-only. A correction must be represented by a new
superseding record; existing rows are not edited.

## Review schedule

The runner creates immutable review checkpoints at 10, 20, and 30 accepted
validation sessions. Calibration results remain separate from validation-v2.
Subgroup results are descriptive and cannot alter the frozen candidates.
