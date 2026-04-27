from src.backtest.report_store import ReportStore
from src.models.backtest import (
    ValidationConcentrationResponse,
    ValidationRun,
    ValidationRunListResponse,
    ValidationRunRequest,
    ValidationSensitivityResponse,
    ValidationStressResponse,
    ValidationWalkForwardResponse,
)


class ValidationExecutionNotImplementedError(NotImplementedError):
    """Raised while validation execution is still a scaffold."""


class ValidationReportService:
    def __init__(self, report_store: ReportStore | None = None):
        self.report_store = report_store or ReportStore()

    def run(self, request: ValidationRunRequest) -> ValidationRun:
        raise ValidationExecutionNotImplementedError(
            "Validation report execution is implemented in later validation-depth tasks."
        )

    def list_runs(self) -> ValidationRunListResponse:
        return ValidationRunListResponse(runs=self.report_store.list_validation_run_summaries())

    def read_run(self, validation_run_id: str) -> ValidationRun:
        return self.report_store.read_validation_run(validation_run_id)

    def read_stress_results(self, validation_run_id: str) -> ValidationStressResponse:
        run = self.read_run(validation_run_id)
        return ValidationStressResponse(
            validation_run_id=validation_run_id,
            data=run.stress_results,
        )

    def read_sensitivity_results(self, validation_run_id: str) -> ValidationSensitivityResponse:
        run = self.read_run(validation_run_id)
        return ValidationSensitivityResponse(
            validation_run_id=validation_run_id,
            data=run.sensitivity_results,
        )

    def read_walk_forward_results(self, validation_run_id: str) -> ValidationWalkForwardResponse:
        run = self.read_run(validation_run_id)
        return ValidationWalkForwardResponse(
            validation_run_id=validation_run_id,
            data=run.walk_forward_results,
        )

    def read_concentration_results(self, validation_run_id: str) -> ValidationConcentrationResponse:
        run = self.read_run(validation_run_id)
        return ValidationConcentrationResponse(
            validation_run_id=validation_run_id,
            regime_coverage=run.regime_coverage,
            concentration_report=run.concentration_report,
        )