# Tasks: QuikStrike Local Highcharts Extractor

**Input**: `specs/012-quikstrike-local-highcharts-extractor/`

## Phase 1 - First Vertical Slice: Setup And Fixture Parser Foundation

- [x] T001 Create `backend/src/quikstrike/__init__.py`
- [x] T002 Create `backend/src/models/quikstrike.py`
- [x] T003 Add QuikStrike view, series, extraction, mapping, artifact, and report enums
- [x] T004 Add strict schemas for DOM metadata, points, series snapshots, Highcharts snapshots, normalized rows, extraction results, and conversion results
- [x] T005 Add secret/session field rejection for QuikStrike schemas and parser inputs
- [x] T006 Implement `backend/src/quikstrike/highcharts_reader.py` for synthetic Highcharts-like chart objects
- [x] T007 Implement `backend/src/quikstrike/dom_metadata.py` for synthetic header/selector text parsing
- [x] T008 Add unit tests for QuikStrike schemas and secret-field rejection
- [x] T009 Add unit tests for Highcharts Put/Call/Vol Settle/Ranges parsing
- [x] T010 Add unit tests for DOM metadata parsing
- [x] T011 Add explicit generated-artifact guard coverage for QuikStrike raw, processed, and report paths

## Phase 2 - Remaining Feature Work

- [x] T012 Implement normalized row builder and view coverage validation in `backend/src/quikstrike/extraction.py`
- [x] T013 Implement strike mapping confidence validation in `backend/src/quikstrike/extraction.py`
- [x] T014 Implement XAU Vol-OI compatible conversion in `backend/src/quikstrike/conversion.py`
- [x] T015 Implement QuikStrike report-store persistence in `backend/src/quikstrike/report_store.py`
- [ ] T016 Add optional local API routes in `backend/src/api/routes/quikstrike.py`
- [ ] T017 Add optional dashboard/status panel if needed
- [ ] T018 Add local browser adapter skeleton without credential/session persistence
- [ ] T019 Add integration tests with synthetic Highcharts plus DOM fixtures
- [ ] T020 Add API contract tests if routes are implemented
- [ ] T021 Run final backend, frontend, artifact guard, smoke, and forbidden-scope validation
