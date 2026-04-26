from typing import Any


class ProviderError(Exception):
    """Base class for structured provider-layer failures."""

    code = "PROVIDER_ERROR"
    status_code = 400

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class ProviderNotFoundError(ProviderError):
    """Raised when a provider name is not registered."""

    code = "PROVIDER_NOT_FOUND"
    status_code = 404

    def __init__(self, provider: str):
        super().__init__(f"Provider '{provider}' is not registered")


class UnsupportedCapabilityError(ProviderError):
    """Raised when a provider cannot supply a requested data type."""

    code = "UNSUPPORTED_CAPABILITY"
    status_code = 400

    def __init__(self, provider: str, data_type: str, reason: str):
        super().__init__(
            f"Provider '{provider}' does not support {data_type}",
            details=[{"provider": provider, "data_type": data_type, "reason": reason}],
        )


class ProviderValidationError(ProviderError):
    """Raised when provider request validation fails."""

    code = "VALIDATION_ERROR"
    status_code = 400


class ProviderUnavailableError(ProviderError):
    """Raised when an upstream provider is temporarily unavailable."""

    code = "PROVIDER_UNAVAILABLE"
    status_code = 503


class LocalFileValidationError(ProviderError):
    """Raised when a local file cannot be treated as research data."""

    code = "LOCAL_FILE_VALIDATION_FAILED"
    status_code = 400
