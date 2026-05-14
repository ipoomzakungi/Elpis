from __future__ import annotations

import re
from datetime import date as dt_date
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel, _normalize_guardrail_key

SAFE_XAU_FUSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
XAU_FUSION_RESEARCH_ONLY_WARNING = (
    "XAU QuikStrike fusion outputs are local-only research artifacts, not execution inputs."
)

FORBIDDEN_XAU_FUSION_FIELDS = {
    "account",
    "accountid",
    "apikey",
    "apisecret",
    "authorization",
    "authorizationheader",
    "bearer",
    "broker",
    "browserprofile",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "endpointreplay",
    "eventvalidation",
    "fullurl",
    "har",
    "harfile",
    "header",
    "headers",
    "order",
    "orderid",
    "password",
    "private",
    "privatekey",
    "privateurl",
    "profilepath",
    "requestheader",
    "requestheaders",
    "responsebody",
    "screenshot",
    "screenshotpath",
    "secret",
    "secretkey",
    "session",
    "sessionid",
    "sessiontoken",
    "setcookie",
    "token",
    "url",
    "username",
    "viewstate",
    "wallet",
    "walletaddress",
}

FORBIDDEN_XAU_FUSION_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"__VIEWSTATE", re.IGNORECASE),
    re.compile(r"__EVENTVALIDATION", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
    re.compile(r"\bCookie\s*:", re.IGNORECASE),
    re.compile(r"\bSet-Cookie\s*:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
)

ALLOWED_XAU_FUSION_ARTIFACT_PREFIXES = (
    "data/reports/xau_quikstrike_fusion/",
    "backend/data/reports/xau_quikstrike_fusion/",
)


class XauFusionSourceType(StrEnum):
    VOL2VOL = "vol2vol"
    MATRIX = "matrix"
    FUSED = "fused"


class XauFusionMatchStatus(StrEnum):
    MATCHED = "matched"
    VOL2VOL_ONLY = "vol2vol_only"
    MATRIX_ONLY = "matrix_only"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class XauFusionAgreementStatus(StrEnum):
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    UNAVAILABLE = "unavailable"
    NOT_COMPARABLE = "not_comparable"


class XauFusionContextStatus(StrEnum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class XauFusionReportStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class XauFusionArtifactType(StrEnum):
    METADATA = "metadata"
    FUSED_ROWS_JSON = "fused_rows_json"
    FUSED_ROWS_PARQUET = "fused_rows_parquet"
    XAU_VOL_OI_INPUT_CSV = "xau_vol_oi_input_csv"
    XAU_VOL_OI_INPUT_PARQUET = "xau_vol_oi_input_parquet"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"


class XauFusionArtifactFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    MARKDOWN = "markdown"


def validate_xau_fusion_safe_id(value: str, field_name: str = "id") -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    if not SAFE_XAU_FUSION_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, underscores, or hyphens"
        )
    return cleaned


def ensure_no_forbidden_xau_fusion_content(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = _normalize_guardrail_key(str(key))
            if normalized_key in FORBIDDEN_XAU_FUSION_FIELDS:
                location = f"{path}.{key}" if path else str(key)
                raise ValueError(f"forbidden sensitive/session field for XAU fusion: {location}")
            next_path = f"{path}.{key}" if path else str(key)
            ensure_no_forbidden_xau_fusion_content(item, next_path)
        return

    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            ensure_no_forbidden_xau_fusion_content(item, f"{path}[{index}]")
        return

    if isinstance(value, str):
        for pattern in FORBIDDEN_XAU_FUSION_VALUE_PATTERNS:
            if pattern.search(value):
                location = path or "value"
                raise ValueError(f"forbidden sensitive/session value for XAU fusion: {location}")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_text_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    return normalized


class XauFusionBaseModel(StrictModel):
    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_or_session_fields(cls, value: Any) -> Any:
        ensure_no_forbidden_xau_fusion_content(value)
        return value


class XauQuikStrikeFusionRequest(XauFusionBaseModel):
    vol2vol_report_id: str
    matrix_report_id: str
    xauusd_spot_reference: float | None = Field(default=None, gt=0)
    gc_futures_reference: float | None = Field(default=None, gt=0)
    session_open_price: float | None = Field(default=None, gt=0)
    realized_volatility: float | None = Field(default=None, gt=0)
    candle_context: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    create_xau_vol_oi_report: bool = False
    create_xau_reaction_report: bool = False
    run_label: str | None = None
    persist_report: bool = True
    research_only_acknowledged: bool

    @field_validator("vol2vol_report_id", "matrix_report_id")
    @classmethod
    def validate_report_ids(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "source_report_id")

    @field_validator("run_label", mode="before")
    @classmethod
    def normalize_optional_run_label(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_research_acknowledgement(self) -> XauQuikStrikeFusionRequest:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauQuikStrikeSourceRef(XauFusionBaseModel):
    source_type: XauFusionSourceType
    report_id: str
    status: str = "available"
    product: str | None = None
    option_product_code: str | None = None
    row_count: int = Field(default=0, ge=0)
    conversion_status: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)

    @field_validator("source_type")
    @classmethod
    def source_ref_must_be_external(cls, value: XauFusionSourceType) -> XauFusionSourceType:
        if value == XauFusionSourceType.FUSED:
            raise ValueError("source reference must point to vol2vol or matrix output")
        return value

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "report_id")

    @field_validator(
        "status",
        "product",
        "option_product_code",
        "conversion_status",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("warnings", "limitations", "artifact_paths")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauFusionMatchKey(XauFusionBaseModel):
    strike: float = Field(gt=0)
    expiration: str | None = None
    expiration_code: str | None = None
    expiration_key: str | None = None
    option_type: str
    value_type: str

    @field_validator("expiration", "expiration_code", "expiration_key", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("option_type", "value_type")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("match key field is required")
        return cleaned

    @model_validator(mode="after")
    def require_expiration_reference(self) -> XauFusionMatchKey:
        if self.expiration_key is None:
            self.expiration_key = self.expiration or self.expiration_code
        if self.expiration_key is None:
            raise ValueError("expiration, expiration_code, or expiration_key is required")
        return self


class XauFusionSourceValue(XauFusionBaseModel):
    source_type: XauFusionSourceType
    source_report_id: str
    source_row_id: str | None = None
    value: float | None = None
    value_type: str
    source_view: str | None = None
    strike: float | None = Field(default=None, gt=0)
    expiration: str | None = None
    expiration_code: str | None = None
    option_type: str | None = None
    future_reference_price: float | None = Field(default=None, gt=0)
    dte: float | None = Field(default=None, ge=0)
    vol_settle: float | None = None
    range_label: str | None = None
    sigma_label: str | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("source_type")
    @classmethod
    def source_value_must_be_external(cls, value: XauFusionSourceType) -> XauFusionSourceType:
        if value == XauFusionSourceType.FUSED:
            raise ValueError("source value must point to vol2vol or matrix output")
        return value

    @field_validator("source_report_id")
    @classmethod
    def validate_source_report_id(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "source_report_id")

    @field_validator("source_row_id", mode="before")
    @classmethod
    def validate_optional_source_row_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_fusion_safe_id(value, "source_row_id")

    @field_validator(
        "value_type",
        "source_view",
        "expiration",
        "expiration_code",
        "option_type",
        "range_label",
        "sigma_label",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauFusionCoverageSummary(XauFusionBaseModel):
    matched_key_count: int = Field(ge=0)
    vol2vol_only_key_count: int = Field(ge=0)
    matrix_only_key_count: int = Field(ge=0)
    conflict_key_count: int = Field(ge=0)
    blocked_key_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    option_type_count: int = Field(ge=0)
    value_type_count: int = Field(ge=0)


class XauFusionRow(XauFusionBaseModel):
    fusion_row_id: str
    fusion_report_id: str
    match_key: XauFusionMatchKey
    source_type: XauFusionSourceType = XauFusionSourceType.FUSED
    match_status: XauFusionMatchStatus
    agreement_status: XauFusionAgreementStatus = XauFusionAgreementStatus.UNAVAILABLE
    vol2vol_value: XauFusionSourceValue | None = None
    matrix_value: XauFusionSourceValue | None = None
    basis_points: float | None = None
    spot_equivalent_level: float | None = Field(default=None, gt=0)
    source_agreement_notes: list[str] = Field(default_factory=list)
    missing_context_notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("fusion_row_id", "fusion_report_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "fusion id")

    @field_validator(
        "source_agreement_notes",
        "missing_context_notes",
        "warnings",
        "limitations",
    )
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_source_presence(self) -> XauFusionRow:
        if self.source_type == XauFusionSourceType.FUSED:
            if self.vol2vol_value is None or self.matrix_value is None:
                raise ValueError("fused row requires both Vol2Vol and Matrix source values")
        elif self.source_type == XauFusionSourceType.VOL2VOL and self.vol2vol_value is None:
            raise ValueError("vol2vol row requires vol2vol_value")
        elif self.source_type == XauFusionSourceType.MATRIX and self.matrix_value is None:
            raise ValueError("matrix row requires matrix_value")

        if (
            self.match_status == XauFusionMatchStatus.BLOCKED
            and not self.warnings
            and not self.missing_context_notes
        ):
            raise ValueError("blocked fusion rows require a warning or missing-context note")
        return self


class XauFusionMissingContextItem(XauFusionBaseModel):
    context_key: str
    status: XauFusionContextStatus
    severity: str = "warning"
    blocks_fusion: bool = False
    blocks_reaction_confidence: bool = False
    message: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("context_key", "severity", "message")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("missing-context text fields are required")
        return cleaned

    @field_validator("source_refs")
    @classmethod
    def normalize_source_refs(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauFusionBasisState(XauFusionBaseModel):
    status: XauFusionContextStatus
    xauusd_spot_reference: float | None = Field(default=None, gt=0)
    gc_futures_reference: float | None = Field(default=None, gt=0)
    basis_points: float | None = None
    calculation_note: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @field_validator("calculation_note", mode="before")
    @classmethod
    def normalize_optional_note(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("warnings")
    @classmethod
    def normalize_warnings(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_available_basis_fields(self) -> XauFusionBasisState:
        if self.status == XauFusionContextStatus.AVAILABLE:
            if self.xauusd_spot_reference is None or self.gc_futures_reference is None:
                raise ValueError("available basis requires spot and futures references")
            if self.basis_points is None:
                raise ValueError("available basis requires basis_points")
        return self


class XauFusionContextSummary(XauFusionBaseModel):
    basis_status: XauFusionContextStatus
    iv_range_status: XauFusionContextStatus
    open_regime_status: XauFusionContextStatus
    candle_acceptance_status: XauFusionContextStatus
    realized_volatility_status: XauFusionContextStatus
    source_agreement_status: XauFusionContextStatus
    missing_context: list[XauFusionMissingContextItem] = Field(default_factory=list)


class XauFusionVolOiInputRow(XauFusionBaseModel):
    date: dt_date | None = None
    timestamp: datetime | None = None
    expiry: str | None = None
    expiration_code: str | None = None
    strike: float = Field(gt=0)
    spot_equivalent_strike: float | None = Field(default=None, gt=0)
    option_type: str
    open_interest: float | None = None
    oi_change: float | None = None
    volume: float | None = None
    intraday_volume: float | None = None
    eod_volume: float | None = None
    churn: float | None = None
    implied_volatility: float | None = None
    underlying_futures_price: float | None = Field(default=None, gt=0)
    source: str = "xau_quikstrike_fusion"
    source_report_ids: list[str]
    source_agreement_status: XauFusionAgreementStatus
    limitations: list[str] = Field(default_factory=list)

    @field_validator("expiry", "expiration_code", "option_type", "source", mode="before")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("source_report_ids")
    @classmethod
    def validate_source_report_ids(cls, values: list[str]) -> list[str]:
        return [validate_xau_fusion_safe_id(value, "source_report_id") for value in values]

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_conversion_requirements(self) -> XauFusionVolOiInputRow:
        if self.expiry is None and self.expiration_code is None:
            raise ValueError("expiry or expiration_code is required")
        value_fields = (
            self.open_interest,
            self.oi_change,
            self.volume,
            self.intraday_volume,
            self.eod_volume,
            self.churn,
            self.implied_volatility,
        )
        if all(value is None for value in value_fields):
            raise ValueError("at least one XAU Vol-OI value field is required")
        if not self.option_type:
            raise ValueError("option_type is required")
        return self


class XauFusionDownstreamResult(XauFusionBaseModel):
    xau_vol_oi_report_id: str | None = None
    xau_reaction_report_id: str | None = None
    xau_report_status: str | None = None
    reaction_report_status: str | None = None
    reaction_row_count: int | None = Field(default=None, ge=0)
    no_trade_count: int | None = Field(default=None, ge=0)
    all_reactions_no_trade: bool | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("xau_vol_oi_report_id", "xau_reaction_report_id", mode="before")
    @classmethod
    def validate_optional_report_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_fusion_safe_id(value, "report_id")

    @field_validator("xau_report_status", "reaction_report_status", mode="before")
    @classmethod
    def normalize_optional_status(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauFusionArtifact(XauFusionBaseModel):
    artifact_type: XauFusionArtifactType
    path: str
    format: XauFusionArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").strip()
        if not cleaned:
            raise ValueError("artifact path is required")
        if ".." in cleaned.split("/"):
            raise ValueError("artifact path must not contain parent traversal")
        if not any(cleaned.startswith(prefix) for prefix in ALLOWED_XAU_FUSION_ARTIFACT_PREFIXES):
            raise ValueError("artifact path must remain under xau_quikstrike_fusion reports")
        return cleaned

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauQuikStrikeFusionSummary(XauFusionBaseModel):
    report_id: str
    source_kind: str = "operational"
    status: XauFusionReportStatus
    created_at: datetime = Field(default_factory=datetime.utcnow)
    vol2vol_report_id: str
    matrix_report_id: str
    fused_row_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    expiration_count: int = Field(ge=0)
    basis_status: XauFusionContextStatus = XauFusionContextStatus.UNAVAILABLE
    iv_range_status: XauFusionContextStatus = XauFusionContextStatus.UNAVAILABLE
    open_regime_status: XauFusionContextStatus = XauFusionContextStatus.UNAVAILABLE
    candle_acceptance_status: XauFusionContextStatus = XauFusionContextStatus.UNAVAILABLE
    xau_vol_oi_report_id: str | None = None
    xau_reaction_report_id: str | None = None
    all_reactions_no_trade: bool | None = None
    warning_count: int = Field(default=0, ge=0)

    @field_validator(
        "report_id",
        "vol2vol_report_id",
        "matrix_report_id",
        "xau_vol_oi_report_id",
        "xau_reaction_report_id",
    )
    @classmethod
    def validate_optional_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_fusion_safe_id(value, "report_id")


class XauQuikStrikeFusionReport(XauFusionBaseModel):
    report_id: str
    source_kind: str = "operational"
    status: XauFusionReportStatus
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    request: XauQuikStrikeFusionRequest | None = None
    vol2vol_source: XauQuikStrikeSourceRef
    matrix_source: XauQuikStrikeSourceRef
    coverage: XauFusionCoverageSummary | None = None
    context_summary: XauFusionContextSummary | None = None
    basis_state: XauFusionBasisState | None = None
    fused_row_count: int = Field(ge=0)
    xau_vol_oi_input_row_count: int = Field(default=0, ge=0)
    fused_rows: list[XauFusionRow] = Field(default_factory=list)
    downstream_result: XauFusionDownstreamResult | None = None
    artifacts: list[XauFusionArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: [XAU_FUSION_RESEARCH_ONLY_WARNING])
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [XAU_FUSION_RESEARCH_ONLY_WARNING]
    )

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "report_id")

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_report_state(self) -> XauQuikStrikeFusionReport:
        if self.status == XauFusionReportStatus.COMPLETED and self.fused_row_count == 0:
            raise ValueError("completed fusion report requires fused rows")
        missing_context = self.context_summary.missing_context if self.context_summary else []
        if (
            self.status == XauFusionReportStatus.BLOCKED
            and not self.warnings
            and not missing_context
        ):
            raise ValueError("blocked fusion report requires a warning or missing-context reason")
        return self


class XauQuikStrikeFusionListResponse(XauFusionBaseModel):
    reports: list[XauQuikStrikeFusionSummary]


class XauFusionRowsResponse(XauFusionBaseModel):
    report_id: str
    rows: list[XauFusionRow]

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "report_id")


class XauFusionMissingContextResponse(XauFusionBaseModel):
    report_id: str
    missing_context: list[XauFusionMissingContextItem]

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_xau_fusion_safe_id(value, "report_id")
