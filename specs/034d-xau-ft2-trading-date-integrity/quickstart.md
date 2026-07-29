# Quickstart: XAU FT2 Trading-Date And Execution Integrity

From `backend`:

```powershell
python scripts/run_xau_ft2_integrity.py `
  --session-date-from 2026-05-31 `
  --session-date-to 2026-07-27 `
  --as-of-date 2026-07-29 `
  --supersedes-run-dir data/reports/xau_ft2_candidate/xau_ft2_candidate_20260728T170205236747
```

The integrity run writes a new report directory and never overwrites Feature
034C artifacts. All outputs remain research-only and non-executable.
