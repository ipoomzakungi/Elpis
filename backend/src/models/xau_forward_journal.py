from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.models.backtest import StrictModel, _normalize_guardrail_key

SAFE_XAU_FORWARD_JOURNAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING = (
    "XAU forward journal entries are local-only research annotations."
)
XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION = (
    "This journal builds forward evidence from saved snapshots and is not a historical "
    "QuikStrike strike-level backtest."
)

FORBIDDEN_XAU_FORWARD_JOURNAL_FIELDS = {
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

FORBIDDEN_XAU_FORWARD_JOURNAL_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"__VIEWSTATE", re.IGNORECASE),
    re.compile(r"__EVENTVALIDATION", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:", re.IGNORECASE),
    re.compile(r"\bCookie\s*:", re.IGNORECASE),
    re.compile(r"\bSet-Cookie\s*:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
)

FORBIDDEN_XAU_FORWARD_JOURNAL_CLAIM_VALUE_PATTERNS = (
    re.compile(r"\bprofit(?:able|ability)\b", re.IGNORECASE),
    re.compile(r"\bpredict(?:s|ive|ion)?\b", re.IGNORECASE),
    re.compile(r"\bsafe to trade\b", re.IGNORECASE),
    re.compile(r"\blive[- ]?ready\b", re.IGNORECASE),
    re.compile(r"\bexecute order\b", re.IGNORECASE),
    re.compile(r"\bplace order\b", re.IGNORECASE),
)

ALLOWED_XAU_FORWARD_JOURNAL_ARTIFACT_PREFIXES = (
    "data/reports/xau_forward_journal/",
    "backend/data/reports/xau_forward_journal/",
)


class XauForwardJournalSourceType(StrEnum):
    QUIKSTRIKE_VOL2VOL = "quikstrike_vol2vol"
    QUIKSTRIKE_MATRIX = "quikstrike_matrix"
    XAU_QUIKSTRIKE_FUSION = "xau_quikstrike_fusion"
    XAU_VOL_OI = "xau_vol_oi"
    XAU_REACTION = "xau_reaction"


class XauForwardJournalEntryStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"


class XauForwardOutcomeWindow(StrEnum):
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    SESSION_CLOSE = "session_close"
    NEXT_DAY = "next_day"


class XauForwardOutcomeLabel(StrEnum):
    WALL_HELD = "wall_held"
    WALL_REJECTED = "wall_rejected"
    WALL_ACCEPTED_BREAK = "wall_accepted_break"
    MOVED_TO_NEXT_WALL = "moved_to_next_wall"
    REVERSED_BEFORE_TARGET = "reversed_before_target"
    STAYED_INSIDE_RANGE = "stayed_inside_range"
    NO_TRADE_WAS_CORRECT = "no_trade_was_correct"
    INCONCLUSIVE = "inconclusive"
    PENDING = "pending"


class XauForwardOutcomeStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class XauForwardArtifactType(StrEnum):
    METADATA = "metadata"
    ENTRY_JSON = "entry_json"
    OUTCOMES_JSON = "outcomes_json"
    REPORT_JSON = "report_json"
    REPORT_MARKDOWN = "report_markdown"
    PRICE_COVERAGE_JSON = "price_coverage_json"
    PRICE_UPDATE_REPORT_JSON = "price_update_report_json"
    PRICE_UPDATE_REPORT_MARKDOWN = "price_update_report_markdown"


class XauForwardArtifactFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class XauForwardPriceSourceLabel(StrEnum):
    TRUE_XAUUSD_SPOT = "true_xauusd_spot"
    GC_FUTURES = "gc_futures"
    YAHOO_GC_F_PROXY = "yahoo_gc_f_proxy"
    GLD_ETF_PROXY = "gld_etf_proxy"
    LOCAL_CSV = "local_csv"
    LOCAL_PARQUET = "local_parquet"
    UNKNOWN_PROXY = "unknown_proxy"


class XauForwardPriceCoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    INVALID = "invalid"
    BLOCKED = "blocked"


class XauForwardPriceDirection(StrEnum):
    UP_FROM_SNAPSHOT = "up_from_snapshot"
    DOWN_FROM_SNAPSHOT = "down_from_snapshot"
    FLAT_FROM_SNAPSHOT = "flat_from_snapshot"
    UNAVAILABLE = "unavailable"


def validate_xau_forward_journal_safe_id(value: str, field_name: str = "id") -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    if not SAFE_XAU_FORWARD_JOURNAL_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, underscores, or hyphens"
        )
    return cleaned


def ensure_no_forbidden_xau_forward_journal_content(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = _normalize_guardrail_key(str(key))
            if normalized_key in FORBIDDEN_XAU_FORWARD_JOURNAL_FIELDS:
                location = f"{path}.{key}" if path else str(key)
                raise ValueError(
                    f"forbidden sensitive/session field for XAU forward journal: {location}"
                )
            next_path = f"{path}.{key}" if path else str(key)
            ensure_no_forbidden_xau_forward_journal_content(item, next_path)
        return

    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            ensure_no_forbidden_xau_forward_journal_content(item, f"{path}[{index}]")
        return

    if isinstance(value, str):
        for pattern in FORBIDDEN_XAU_FORWARD_JOURNAL_SENSITIVE_VALUE_PATTERNS:
            if pattern.search(value):
                location = path or "value"
                raise ValueError(
                    f"forbidden sensitive/session or unsupported claim value for "
                    f"XAU forward journal: {location}"
                )
        for pattern in FORBIDDEN_XAU_FORWARD_JOURNAL_CLAIM_VALUE_PATTERNS:
            if pattern.search(value) and not _is_research_only_disclaimer(value):
                location = path or "value"
                raise ValueError(
                    f"forbidden sensitive/session or unsupported claim value for "
                    f"XAU forward journal: {location}"
                )


def _is_research_only_disclaimer(value: str) -> bool:
    lowered = value.lower()
    has_research_context = "research" in lowered or "annotation" in lowered
    has_negation = any(
        phrase in lowered
        for phrase in (
            "do not imply",
            "does not imply",
            "not imply",
            "not a ",
            "not action",
            "not instruction",
        )
    )
    return has_research_context and has_negation


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_required_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("text field is required")
    return cleaned


def _normalize_text_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)
    return normalized


def _normalize_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class XauForwardJournalBaseModel(StrictModel):
    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_or_session_fields(cls, value: Any) -> Any:
        ensure_no_forbidden_xau_forward_journal_content(value)
        return value


class XauForwardJournalNote(XauForwardJournalBaseModel):
    note_id: str | None = None
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "manual"

    @model_validator(mode="before")
    @classmethod
    def coerce_string_note(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        return value

    @field_validator("note_id", mode="before")
    @classmethod
    def validate_optional_note_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "note_id")

    @field_validator("text", "source")
    @classmethod
    def normalize_required_text_fields(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)


class XauForwardSourceReportRef(XauForwardJournalBaseModel):
    source_type: XauForwardJournalSourceType
    report_id: str
    source_kind: str = "operational"
    status: str = "available"
    created_at: datetime | None = None
    product: str | None = None
    expiration: str | None = None
    expiration_code: str | None = None
    row_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "report_id")

    @field_validator("created_at")
    @classmethod
    def normalize_optional_created_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator(
        "source_kind",
        "status",
        "product",
        "expiration",
        "expiration_code",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @field_validator("artifact_paths")
    @classmethod
    def normalize_artifact_paths(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = value.replace("\\", "/").strip()
            if not cleaned:
                continue
            if ".." in cleaned.split("/"):
                raise ValueError("source artifact path must not contain parent traversal")
            normalized.append(cleaned)
        return list(dict.fromkeys(normalized))


class XauForwardSnapshotContext(XauForwardJournalBaseModel):
    snapshot_time: datetime
    capture_window: str = "daily_snapshot"
    capture_session: str | None = None
    product: str | None = None
    expiration: str | None = None
    expiration_code: str | None = None
    spot_price_at_snapshot: float | None = Field(default=None, gt=0)
    futures_price_at_snapshot: float | None = Field(default=None, gt=0)
    basis: float | None = None
    session_open_price: float | None = Field(default=None, gt=0)
    event_news_flag: str | bool | None = None
    missing_context: list[str] = Field(default_factory=list)
    notes: list[XauForwardJournalNote] = Field(default_factory=list)

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator(
        "capture_session",
        "product",
        "expiration",
        "expiration_code",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("capture_window")
    @classmethod
    def validate_capture_window(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "capture_window")

    @field_validator("missing_context")
    @classmethod
    def normalize_missing_context(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardWallSummary(XauForwardJournalBaseModel):
    summary_id: str
    wall_type: str
    source_report_id: str
    strike: float = Field(gt=0)
    expiration: str | None = None
    expiration_code: str | None = None
    option_type: str | None = None
    open_interest: float | None = None
    oi_change: float | None = None
    volume: float | None = None
    wall_score: float | None = None
    rank: int = Field(gt=0)
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("summary_id", "source_report_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "wall_summary_id")

    @field_validator(
        "wall_type",
        "expiration",
        "expiration_code",
        "option_type",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def require_wall_value(self) -> XauForwardWallSummary:
        if all(
            value is None
            for value in (self.open_interest, self.oi_change, self.volume, self.wall_score)
        ):
            raise ValueError("wall summary requires at least one value")
        return self


class XauForwardReactionSummary(XauForwardJournalBaseModel):
    reaction_id: str
    source_report_id: str
    wall_id: str | None = None
    zone_id: str | None = None
    reaction_label: str
    confidence_label: str | None = None
    no_trade_reasons: list[str] = Field(default_factory=list)
    bounded_risk_annotation_count: int = Field(default=0, ge=0)
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("reaction_id", "source_report_id")
    @classmethod
    def validate_required_ids(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "reaction_id")

    @field_validator("wall_id", "zone_id", mode="before")
    @classmethod
    def validate_optional_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "source_row_id")

    @field_validator("reaction_label", "confidence_label", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("no_trade_reasons", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardMissingContextItem(XauForwardJournalBaseModel):
    context_key: str
    status: str
    severity: str = "warning"
    message: str
    source_report_ids: list[str] = Field(default_factory=list)
    blocks_outcome_label: bool = False
    blocks_reaction_review: bool = False

    @field_validator("context_key", "status", "severity", "message")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("source_report_ids")
    @classmethod
    def validate_source_report_ids(cls, values: list[str]) -> list[str]:
        return [
            validate_xau_forward_journal_safe_id(value, "source_report_id")
            for value in _normalize_text_list(values)
        ]


class XauForwardOutcomeObservation(XauForwardJournalBaseModel):
    window: XauForwardOutcomeWindow
    status: XauForwardOutcomeStatus = XauForwardOutcomeStatus.PENDING
    label: XauForwardOutcomeLabel = XauForwardOutcomeLabel.PENDING
    observation_start: datetime | None = None
    observation_end: datetime | None = None
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float | None = Field(default=None, gt=0)
    range: float | None = Field(default=None, ge=0)
    direction: XauForwardPriceDirection | None = None
    price_source_label: XauForwardPriceSourceLabel | None = None
    price_source_symbol: str | None = None
    coverage_status: XauForwardPriceCoverageStatus | None = None
    coverage_reason: str | None = None
    price_update_id: str | None = None
    reference_wall_id: str | None = None
    reference_wall_level: float | None = Field(default=None, gt=0)
    next_wall_reference: str | None = None
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("observation_start", "observation_end", "updated_at")
    @classmethod
    def normalize_optional_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator("reference_wall_id", "next_wall_reference", "price_update_id", mode="before")
    @classmethod
    def validate_optional_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "outcome_reference_id")

    @field_validator("price_source_symbol", "coverage_reason", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_observation_shape(self) -> XauForwardOutcomeObservation:
        if (
            self.observation_start is not None
            and self.observation_end is not None
            and self.observation_end <= self.observation_start
        ):
            raise ValueError("observation_end must be after observation_start")
        if None not in (self.open, self.high, self.low, self.close):
            high = self.high or 0
            low = self.low or 0
            open_price = self.open or 0
            close_price = self.close or 0
            if high < low or high < open_price or high < close_price:
                raise ValueError("high must be greater than or equal to open, low, and close")
            if low > open_price or low > close_price:
                raise ValueError("low must be less than or equal to open and close")
        return self


class XauForwardPriceDataRequestBase(XauForwardJournalBaseModel):
    source_label: XauForwardPriceSourceLabel
    source_symbol: str | None = None
    ohlc_path: str
    timestamp_column: str = "timestamp"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    timezone: str = "UTC"
    research_only_acknowledged: bool

    @field_validator(
        "source_symbol",
        "timestamp_column",
        "open_column",
        "high_column",
        "low_column",
        "close_column",
        "timezone",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator(
        "timestamp_column",
        "open_column",
        "high_column",
        "low_column",
        "close_column",
        "timezone",
    )
    @classmethod
    def require_text_fields(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("column and timezone fields are required")
        return _normalize_required_text(value)

    @field_validator("ohlc_path")
    @classmethod
    def validate_ohlc_path(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").strip()
        if not cleaned:
            raise ValueError("ohlc_path is required")
        if cleaned.startswith(("http://", "https://")):
            raise ValueError("ohlc_path must be a local research file path")
        if ".." in cleaned.split("/"):
            raise ValueError("ohlc_path must not contain parent traversal")
        return cleaned

    @model_validator(mode="after")
    def require_research_acknowledgement(self) -> XauForwardPriceDataRequestBase:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauForwardPriceDataUpdateRequest(XauForwardPriceDataRequestBase):
    update_note: str | None = None
    persist_report: bool = True

    @field_validator("update_note", mode="before")
    @classmethod
    def normalize_update_note(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class XauForwardPriceCoverageRequest(XauForwardPriceDataRequestBase):
    pass


class XauForwardOhlcCandle(XauForwardJournalBaseModel):
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float | None = Field(default=None, ge=0)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @model_validator(mode="after")
    def validate_ohlc_shape(self) -> XauForwardOhlcCandle:
        if self.high < self.low or self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close")
        return self


class XauForwardPriceSource(XauForwardJournalBaseModel):
    source_label: XauForwardPriceSourceLabel
    source_symbol: str | None = None
    source_path: str
    format: str
    row_count: int = Field(ge=0)
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("source_symbol", "format", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("source_path")
    @classmethod
    def normalize_source_path(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").strip()
        if not cleaned:
            raise ValueError("source_path is required")
        if ".." in cleaned.split("/"):
            raise ValueError("source_path must not contain parent traversal")
        return cleaned

    @field_validator("first_timestamp", "last_timestamp")
    @classmethod
    def normalize_optional_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardOutcomeWindowRange(XauForwardJournalBaseModel):
    window: XauForwardOutcomeWindow
    required_start: datetime
    required_end: datetime
    boundary_basis: str
    limitations: list[str] = Field(default_factory=list)

    @field_validator("required_start", "required_end")
    @classmethod
    def normalize_datetimes(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("boundary_basis")
    @classmethod
    def normalize_boundary_basis(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_range(self) -> XauForwardOutcomeWindowRange:
        if self.required_end <= self.required_start:
            raise ValueError("required_end must be after required_start")
        return self


class XauForwardPriceCoverageWindow(XauForwardJournalBaseModel):
    window: XauForwardOutcomeWindow
    status: XauForwardPriceCoverageStatus
    required_start: datetime
    required_end: datetime
    observed_start: datetime | None = None
    observed_end: datetime | None = None
    candle_count: int = Field(default=0, ge=0)
    gap_count: int = Field(default=0, ge=0)
    missing_reason: str | None = None
    partial_reason: str | None = None
    source_label: XauForwardPriceSourceLabel
    source_symbol: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @field_validator("required_start", "required_end", "observed_start", "observed_end")
    @classmethod
    def normalize_optional_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator("missing_reason", "partial_reason", "source_symbol", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardPriceOutcomeMetrics(XauForwardJournalBaseModel):
    window: XauForwardOutcomeWindow
    status: XauForwardOutcomeStatus
    label: XauForwardOutcomeLabel
    observation_start: datetime | None = None
    observation_end: datetime | None = None
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float | None = Field(default=None, gt=0)
    range: float | None = Field(default=None, ge=0)
    snapshot_price: float | None = Field(default=None, gt=0)
    direction: XauForwardPriceDirection = XauForwardPriceDirection.UNAVAILABLE
    source_label: XauForwardPriceSourceLabel
    source_symbol: str | None = None
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("observation_start", "observation_end")
    @classmethod
    def normalize_optional_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_aware_datetime(value)

    @field_validator("source_symbol", mode="before")
    @classmethod
    def normalize_source_symbol(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardMissingCandleItem(XauForwardJournalBaseModel):
    window: XauForwardOutcomeWindow
    required_start: datetime
    required_end: datetime
    status: XauForwardPriceCoverageStatus
    message: str
    action: str

    @field_validator("required_start", "required_end")
    @classmethod
    def normalize_datetimes(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("message", "action")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        return _normalize_required_text(value)


class XauForwardPriceCoverageSummary(XauForwardJournalBaseModel):
    journal_id: str
    snapshot_time: datetime
    source: XauForwardPriceSource
    windows: list[XauForwardPriceCoverageWindow]
    complete_windows: list[XauForwardOutcomeWindow] = Field(default_factory=list)
    partial_windows: list[XauForwardOutcomeWindow] = Field(default_factory=list)
    missing_windows: list[XauForwardOutcomeWindow] = Field(default_factory=list)
    missing_candle_checklist: list[XauForwardMissingCandleItem] = Field(default_factory=list)
    proxy_limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: ["Price coverage is local-only research metadata."]
    )

    @field_validator("journal_id")
    @classmethod
    def validate_journal_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "journal_id")

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("proxy_limitations", "warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardPriceOutcomeUpdateReport(XauForwardJournalBaseModel):
    update_id: str
    journal_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: XauForwardPriceSource
    coverage_summary: XauForwardPriceCoverageSummary
    updated_outcomes: list[XauForwardOutcomeObservation]
    missing_candle_checklist: list[XauForwardMissingCandleItem] = Field(default_factory=list)
    proxy_limitations: list[str] = Field(default_factory=list)
    artifacts: list[XauForwardJournalArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [
            "This research-only annotation does not imply profitability, prediction, "
            "safety, live readiness, or any execution instruction."
        ]
    )

    @field_validator("update_id", "journal_id")
    @classmethod
    def validate_ids(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "price_update_id")

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("proxy_limitations", "warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardPriceCoverageResponse(XauForwardJournalBaseModel):
    journal_id: str
    coverage: XauForwardPriceCoverageSummary
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [
            "This research-only annotation does not imply profitability, prediction, "
            "safety, live readiness, or any execution instruction."
        ]
    )

    @field_validator("journal_id")
    @classmethod
    def validate_journal_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "journal_id")

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardPriceOutcomeUpdateResponse(XauForwardJournalBaseModel):
    journal_id: str
    update_report: XauForwardPriceOutcomeUpdateReport
    outcomes: list[XauForwardOutcomeObservation]
    coverage: XauForwardPriceCoverageSummary
    artifacts: list[XauForwardJournalArtifact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [
            "This research-only annotation does not imply profitability, prediction, "
            "safety, live readiness, or any execution instruction."
        ]
    )

    @field_validator("journal_id")
    @classmethod
    def validate_journal_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "journal_id")

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardJournalArtifact(XauForwardJournalBaseModel):
    artifact_type: XauForwardArtifactType
    path: str
    format: XauForwardArtifactFormat
    rows: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    limitations: list[str] = Field(default_factory=list)

    @field_validator("path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").strip()
        if not cleaned:
            raise ValueError("artifact path is required")
        if ".." in cleaned.split("/"):
            raise ValueError("artifact path must not contain parent traversal")
        if not any(
            cleaned.startswith(prefix) for prefix in ALLOWED_XAU_FORWARD_JOURNAL_ARTIFACT_PREFIXES
        ):
            raise ValueError("artifact path must remain under xau_forward_journal reports")
        return cleaned

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("limitations")
    @classmethod
    def normalize_limitations(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)


class XauForwardJournalCreateRequest(XauForwardJournalBaseModel):
    snapshot_time: datetime
    capture_window: str = "daily_snapshot"
    capture_session: str | None = None
    vol2vol_report_id: str
    matrix_report_id: str
    fusion_report_id: str
    xau_vol_oi_report_id: str
    xau_reaction_report_id: str
    spot_price_at_snapshot: float | None = Field(default=None, gt=0)
    futures_price_at_snapshot: float | None = Field(default=None, gt=0)
    basis: float | None = None
    session_open_price: float | None = Field(default=None, gt=0)
    event_news_flag: str | bool | None = None
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    persist_report: bool = True
    force_create: bool = False
    research_only_acknowledged: bool

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("capture_window")
    @classmethod
    def validate_capture_window(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "capture_window")

    @field_validator("capture_session", mode="before")
    @classmethod
    def normalize_capture_session(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "capture_session")

    @field_validator(
        "vol2vol_report_id",
        "matrix_report_id",
        "fusion_report_id",
        "xau_vol_oi_report_id",
        "xau_reaction_report_id",
    )
    @classmethod
    def validate_report_ids(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "source_report_id")

    @model_validator(mode="after")
    def require_research_acknowledgement(self) -> XauForwardJournalCreateRequest:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauForwardOutcomeUpdateRequest(XauForwardJournalBaseModel):
    outcomes: list[XauForwardOutcomeObservation]
    update_note: str | None = None
    research_only_acknowledged: bool

    @field_validator("outcomes")
    @classmethod
    def require_outcomes(
        cls,
        values: list[XauForwardOutcomeObservation],
    ) -> list[XauForwardOutcomeObservation]:
        if not values:
            raise ValueError("at least one outcome window is required")
        return values

    @field_validator("update_note", mode="before")
    @classmethod
    def normalize_update_note(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def require_research_acknowledgement(self) -> XauForwardOutcomeUpdateRequest:
        if not self.research_only_acknowledged:
            raise ValueError("research_only_acknowledged must be true")
        return self


class XauForwardJournalEntry(XauForwardJournalBaseModel):
    journal_id: str
    snapshot_key: str
    source_kind: str = "operational"
    status: XauForwardJournalEntryStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot: XauForwardSnapshotContext
    source_reports: list[XauForwardSourceReportRef]
    content_fingerprint: str | None = None
    content_fingerprint_components: dict[str, str] = Field(default_factory=dict)
    top_oi_walls: list[XauForwardWallSummary] = Field(default_factory=list)
    top_oi_change_walls: list[XauForwardWallSummary] = Field(default_factory=list)
    top_volume_walls: list[XauForwardWallSummary] = Field(default_factory=list)
    reaction_summaries: list[XauForwardReactionSummary] = Field(default_factory=list)
    missing_context: list[XauForwardMissingContextItem] = Field(default_factory=list)
    outcomes: list[XauForwardOutcomeObservation] = Field(default_factory=list)
    notes: list[XauForwardJournalNote] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(
        default_factory=lambda: [XAU_FORWARD_JOURNAL_FORWARD_ONLY_LIMITATION]
    )
    research_only_warnings: list[str] = Field(
        default_factory=lambda: [XAU_FORWARD_JOURNAL_RESEARCH_ONLY_WARNING]
    )
    artifacts: list[XauForwardJournalArtifact] = Field(default_factory=list)

    @field_validator("journal_id", "snapshot_key")
    @classmethod
    def validate_journal_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "journal_id")

    @field_validator("content_fingerprint")
    @classmethod
    def validate_content_fingerprint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "content_fingerprint")

    @field_validator("content_fingerprint_components")
    @classmethod
    def validate_content_fingerprint_components(cls, values: dict[str, str]) -> dict[str, str]:
        return {
            validate_xau_forward_journal_safe_id(key, "content_fingerprint_component"): (
                validate_xau_forward_journal_safe_id(value, "content_fingerprint")
            )
            for key, value in values.items()
        }

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("warnings", "limitations", "research_only_warnings")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)

    @model_validator(mode="after")
    def validate_entry_state(self) -> XauForwardJournalEntry:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be greater than or equal to created_at")
        if self.status == XauForwardJournalEntryStatus.COMPLETED:
            if not self.source_reports:
                raise ValueError("completed journal entry requires source reports")
            if not self.limitations:
                raise ValueError("completed journal entry requires source limitations")
        if self.status == XauForwardJournalEntryStatus.BLOCKED and not self.warnings:
            raise ValueError("blocked journal entry requires a warning")
        return self


class XauForwardJournalSummary(XauForwardJournalBaseModel):
    journal_id: str
    snapshot_key: str
    source_kind: str = "operational"
    status: XauForwardJournalEntryStatus
    snapshot_time: datetime
    capture_window: str = "daily_snapshot"
    capture_session: str | None = None
    product: str | None = None
    expiration: str | None = None
    expiration_code: str | None = None
    fusion_report_id: str | None = None
    xau_vol_oi_report_id: str | None = None
    xau_reaction_report_id: str | None = None
    outcome_status: XauForwardOutcomeStatus = XauForwardOutcomeStatus.PENDING
    completed_outcome_count: int = Field(default=0, ge=0)
    pending_outcome_count: int = Field(default=0, ge=0)
    no_trade_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)

    @field_validator(
        "journal_id",
        "snapshot_key",
        "fusion_report_id",
        "xau_vol_oi_report_id",
        "xau_reaction_report_id",
    )
    @classmethod
    def validate_optional_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_xau_forward_journal_safe_id(value, "report_id")

    @field_validator("snapshot_time")
    @classmethod
    def normalize_snapshot_time(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator(
        "capture_session",
        "product",
        "expiration",
        "expiration_code",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("capture_window")
    @classmethod
    def validate_capture_window(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "capture_window")


class XauForwardJournalListResponse(XauForwardJournalBaseModel):
    entries: list[XauForwardJournalSummary] = Field(default_factory=list)


class XauForwardOutcomeResponse(XauForwardJournalBaseModel):
    journal_id: str
    outcomes: list[XauForwardOutcomeObservation]
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("journal_id")
    @classmethod
    def validate_journal_id(cls, value: str) -> str:
        return validate_xau_forward_journal_safe_id(value, "journal_id")

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_aware_datetime(value)

    @field_validator("warnings", "limitations")
    @classmethod
    def normalize_text_lists(cls, values: list[str]) -> list[str]:
        return _normalize_text_list(values)
