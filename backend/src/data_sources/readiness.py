"""Readiness detection for public, local, and optional research data sources."""

import os
from collections.abc import Mapping
from datetime import UTC, datetime

from src.data_sources.capabilities import capability_matrix
from src.data_sources.missing_data import optional_vendor_key_action
from src.models.data_sources import (
    DataSourceCapability,
    DataSourceProviderStatus,
    DataSourceProviderType,
    DataSourceReadiness,
    DataSourceReadinessStatus,
    DataSourceTier,
)

OPTIONAL_PROVIDER_ENV_VARS: dict[DataSourceProviderType, str] = {
    DataSourceProviderType.KAIKO_OPTIONAL: "KAIKO_API_KEY",
    DataSourceProviderType.TARDIS_OPTIONAL: "TARDIS_API_KEY",
    DataSourceProviderType.COINGLASS_OPTIONAL: "COINGLASS_API_KEY",
    DataSourceProviderType.CRYPTOQUANT_OPTIONAL: "CRYPTOQUANT_API_KEY",
    DataSourceProviderType.CME_QUIKSTRIKE_LOCAL_OR_OPTIONAL: "CME_QUIKSTRIKE_API_KEY",
}

RESEARCH_ONLY_WARNING = (
    "Data-source onboarding is research-only and does not enable live, paper, "
    "shadow, broker, wallet, or order execution workflows."
)


def env_var_configured(
    env_var_name: str,
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = environ if environ is not None else os.environ
    return bool(env.get(env_var_name, "").strip())


def provider_statuses(
    environ: Mapping[str, str] | None = None,
    capabilities: list[DataSourceCapability] | None = None,
) -> list[DataSourceProviderStatus]:
    matrix = capabilities or capability_matrix()
    statuses: list[DataSourceProviderStatus] = []
    for capability in matrix:
        env_var_name = OPTIONAL_PROVIDER_ENV_VARS.get(capability.provider_type)
        configured = _configured_from_capability(capability, env_var_name, environ)
        status = _status_from_capability(capability, configured)
        missing_actions = []
        if (
            capability.provider_type in OPTIONAL_PROVIDER_ENV_VARS
            and not configured
            and capability.is_optional
        ):
            missing_actions.append(
                optional_vendor_key_action(capability.provider_type, env_var_name or "")
            )

        statuses.append(
            DataSourceProviderStatus(
                provider_type=capability.provider_type,
                status=status,
                configured=configured,
                env_var_name=env_var_name,
                secret_value_returned=False,
                capabilities=capability,
                warnings=[],
                limitations=capability.limitations,
                missing_actions=missing_actions,
            )
        )
    return statuses


def data_source_readiness(environ: Mapping[str, str] | None = None) -> DataSourceReadiness:
    matrix = capability_matrix()
    statuses = provider_statuses(environ=environ, capabilities=matrix)
    optional_missing = [
        status.provider_type
        for status in statuses
        if status.status == DataSourceReadinessStatus.UNAVAILABLE_OPTIONAL
    ]
    forbidden = [
        status.provider_type
        for status in statuses
        if status.status == DataSourceReadinessStatus.FORBIDDEN
    ]
    return DataSourceReadiness(
        generated_at=datetime.now(UTC),
        provider_statuses=statuses,
        capability_matrix=matrix,
        public_sources_available=any(
            status.configured
            and status.capabilities.tier == DataSourceTier.TIER_0_PUBLIC_LOCAL
            for status in statuses
        ),
        optional_sources_missing=optional_missing,
        forbidden_sources_detected=forbidden,
        missing_data_actions=[
            action for status in statuses for action in status.missing_actions
        ],
        research_only_warnings=[RESEARCH_ONLY_WARNING],
    )


def _configured_from_capability(
    capability: DataSourceCapability,
    env_var_name: str | None,
    environ: Mapping[str, str] | None,
) -> bool:
    if capability.provider_type == DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING:
        return False
    if env_var_name:
        return env_var_configured(env_var_name, environ)
    return capability.tier == DataSourceTier.TIER_0_PUBLIC_LOCAL


def _status_from_capability(
    capability: DataSourceCapability,
    configured: bool,
) -> DataSourceReadinessStatus:
    if capability.provider_type == DataSourceProviderType.FORBIDDEN_PRIVATE_TRADING:
        return DataSourceReadinessStatus.FORBIDDEN
    if capability.requires_key and capability.is_optional:
        return (
            DataSourceReadinessStatus.CONFIGURED
            if configured
            else DataSourceReadinessStatus.UNAVAILABLE_OPTIONAL
        )
    if capability.requires_local_file:
        return DataSourceReadinessStatus.READY
    return DataSourceReadinessStatus.READY if configured else DataSourceReadinessStatus.MISSING
