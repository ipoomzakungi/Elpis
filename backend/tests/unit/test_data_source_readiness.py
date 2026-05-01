from src.data_sources.readiness import (
    OPTIONAL_PROVIDER_ENV_VARS,
    data_source_readiness,
    env_var_configured,
    provider_statuses,
)
from src.models.data_sources import (
    DataSourceProviderStatus,
    DataSourceProviderType,
    DataSourceReadinessStatus,
)
from tests.helpers.test_data_source_data import find_provider, optional_vendor_environment


def test_optional_paid_provider_key_missing_and_present_status():
    missing_statuses = provider_statuses(environ={})
    missing_kaiko = find_provider(missing_statuses, DataSourceProviderType.KAIKO_OPTIONAL)

    assert missing_kaiko.status == DataSourceReadinessStatus.UNAVAILABLE_OPTIONAL
    assert missing_kaiko.configured is False
    assert missing_kaiko.env_var_name == OPTIONAL_PROVIDER_ENV_VARS[
        DataSourceProviderType.KAIKO_OPTIONAL
    ]
    assert missing_kaiko.secret_value_returned is False
    assert missing_kaiko.missing_actions
    assert missing_kaiko.missing_actions[0].blocking is False

    present_statuses = provider_statuses(environ=optional_vendor_environment("secret-123"))
    present_kaiko = find_provider(present_statuses, DataSourceProviderType.KAIKO_OPTIONAL)
    present_tardis = find_provider(present_statuses, DataSourceProviderType.TARDIS_OPTIONAL)

    assert present_kaiko.status == DataSourceReadinessStatus.CONFIGURED
    assert present_kaiko.configured is True
    assert present_kaiko.missing_actions == []
    assert present_tardis.status == DataSourceReadinessStatus.UNAVAILABLE_OPTIONAL


def test_public_sources_are_ready_without_keys():
    statuses = provider_statuses(environ={})
    binance = find_provider(statuses, DataSourceProviderType.BINANCE_PUBLIC)
    yahoo = find_provider(statuses, DataSourceProviderType.YAHOO_FINANCE)
    local = find_provider(statuses, DataSourceProviderType.LOCAL_FILE)

    assert binance.status == DataSourceReadinessStatus.READY
    assert yahoo.status == DataSourceReadinessStatus.READY
    assert local.status == DataSourceReadinessStatus.READY
    assert binance.configured is True
    assert yahoo.configured is True
    assert local.configured is True


def test_readiness_payload_never_returns_secret_values():
    secret = "very-sensitive-research-key-value"
    readiness = data_source_readiness(environ=optional_vendor_environment(secret))
    payload = readiness.model_dump_json()

    assert secret not in payload
    assert "secret_value_returned" in payload
    assert all(status.secret_value_returned is False for status in readiness.provider_statuses)
    assert DataSourceProviderType.TARDIS_OPTIONAL in readiness.optional_sources_missing


def test_secret_value_return_flag_is_rejected():
    status = find_provider(provider_statuses(environ={}), DataSourceProviderType.BINANCE_PUBLIC)

    try:
        DataSourceProviderStatus.model_validate(
            {**status.model_dump(mode="python"), "secret_value_returned": True}
        )
    except ValueError as exc:
        assert "secret values must never be returned" in str(exc)
    else:
        raise AssertionError("secret_value_returned=True should be rejected")


def test_env_var_configured_treats_blank_as_missing():
    assert env_var_configured("KAIKO_API_KEY", {"KAIKO_API_KEY": "abc"}) is True
    assert env_var_configured("KAIKO_API_KEY", {"KAIKO_API_KEY": "   "}) is False
    assert env_var_configured("KAIKO_API_KEY", {}) is False
