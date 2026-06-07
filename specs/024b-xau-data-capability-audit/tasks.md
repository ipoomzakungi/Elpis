# Tasks: XAU Data Capability Audit

**Input**: Design documents from `specs/024b-xau-data-capability-audit/`
**Prerequisites**: `plan.md`, `spec.md`, `data-model.md`, `contracts/api.md`, `quickstart.md`

**Tests**: Tests are required for the audit service and API route.

## Phase 1: Setup

- [X] T001 Create Feature 024B specification in `specs/024b-xau-data-capability-audit/spec.md`
- [X] T002 Create Feature 024B implementation plan in `specs/024b-xau-data-capability-audit/plan.md`
- [X] T003 [P] Create Feature 024B data model in `specs/024b-xau-data-capability-audit/data-model.md`
- [X] T004 [P] Create Feature 024B API contract in `specs/024b-xau-data-capability-audit/contracts/api.md`
- [X] T005 [P] Create Feature 024B quickstart in `specs/024b-xau-data-capability-audit/quickstart.md`
- [X] T006 Create Feature 024B requirements checklist in `specs/024b-xau-data-capability-audit/checklists/requirements.md`

## Phase 2: Foundational Models And Audit Service

- [X] T007 Add data capability audit Pydantic models in `backend/src/models/xau_data_capability_audit.py`
- [X] T008 Add data capability audit package exports in `backend/src/xau_data_capability_audit/__init__.py`
- [X] T009 Add read-only audit service in `backend/src/xau_data_capability_audit/service.py`

## Phase 3: User Story 1 - Inventory Current Data Capabilities

- [X] T010 [P] [US1] Add fixture audit test for Vol2Vol and Matrix artifacts in `backend/tests/unit/test_xau_data_capability_audit.py`
- [X] T011 [US1] Implement Vol2Vol, Matrix, Fusion, and XAU Vol-OI source evidence mapping in `backend/src/xau_data_capability_audit/service.py`

## Phase 4: User Story 2 - Distinguish Partial And Blocked Capabilities

- [X] T012 [P] [US2] Add gamma/GEX fixture test in `backend/tests/unit/test_xau_data_capability_audit.py`
- [X] T013 [US2] Implement partial volume and blocked GEX status rules in `backend/src/xau_data_capability_audit/service.py`

## Phase 5: User Story 3 - Preserve Research-Only Guardrails

- [X] T014 [P] [US3] Add API route research-only test in `backend/tests/unit/test_xau_data_capability_audit.py`
- [X] T015 [US3] Enforce audit guardrail validation in `backend/src/models/xau_data_capability_audit.py`

## Phase 6: API And Validation

- [X] T016 Add Data Capability Audit API route in `backend/src/api/routes/xau_data_capability_audit.py`
- [X] T017 Register Data Capability Audit router in `backend/src/main.py`
- [X] T018 Update `.specify/feature.json`
- [X] T019 Update `AGENTS.md`
- [X] T020 Update `docs/project_status.md`
- [X] T021 Run focused Feature 024B tests and adjacent XAU regressions
- [X] T022 Run backend import check and ruff on touched Python files
- [X] T023 Start backend and verify `/health`, `/docs`, and `/api/v1/research/xau/data-capability-audit/run`
- [X] T024 Confirm no live trading, paper trading, broker integration, private keys, endpoint replay, Rust, ClickHouse, PostgreSQL, Kafka, Kubernetes, ML training, buy/sell live signal, alert, PnL, or execution was added

## Dependencies & Execution Order

- Setup tasks complete the feature documentation.
- Model and service tasks must precede API route registration.
- US1 is the MVP and can be verified independently with fixture reports.
- US2 depends on the core capability aggregation from US1.
- US3 can be validated through model and route tests once US1 exists.
- Validation tasks run after implementation and docs are complete.

## Parallel Opportunities

- T003, T004, and T005 can be completed in parallel.
- T010, T012, and T014 touch the same test file and should be sequenced in practice.
- Source-specific evidence mapping can be reviewed independently once the shared collector exists.

## Implementation Strategy

1. Complete the read-only capability inventory first.
2. Add partial/blocked status rules for weak or impossible fields.
3. Expose the audit through one local API endpoint.
4. Validate with focused tests, adjacent regressions, import check, ruff, and API smoke.
