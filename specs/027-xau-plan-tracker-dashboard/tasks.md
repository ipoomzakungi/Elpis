# Tasks: XAU Plan Tracker Dashboard

## Phase 1: Speckit Artifacts

- [X] T001 Create Feature 027 specification.
- [X] T002 Create Feature 027 implementation plan.
- [X] T003 Create Feature 027 data model notes.
- [X] T004 Create Feature 027 API contract notes.
- [X] T005 Create Feature 027 quickstart.
- [X] T006 Create Feature 027 requirements checklist.

## Phase 2: Frontend Dashboard

- [X] T007 Add `/xau-plan-tracker` app route page.
- [X] T008 Load latest run and run/snapshot/order bundle.
- [X] T009 Add run lookup by run_id for replay/review.
- [X] T010 Display snapshot cards (10:10/18:10) with mapped plan levels.
- [X] T011 Display order outcome table with PnL/DD and near-miss diagnostics.
- [X] T012 Add source-quality and limitations panel.
- [X] T013 Add research-only notice and safe empty/error states.
- [X] T014 Add nav link to Header.

## Phase 3: Documentation

- [X] T015 Update active feature pointer to Feature 027.
- [X] T016 Update project status and next-milestone notes.

## Guardrails

- No live trading, alerts, broker execution, position sizing, or account-level behavior.
- No synthetic signal generation; every output remains `research_only=true` and `signal_allowed=false`.
