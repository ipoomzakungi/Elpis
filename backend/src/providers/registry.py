from collections.abc import Iterable, Mapping

from src.models.providers import ProviderInfo
from src.providers.base import DataProvider
from src.providers.errors import ProviderNotFoundError


class ProviderRegistry:
    """Static v0 registry for research data providers."""

    def __init__(
        self, providers: Iterable[DataProvider] | Mapping[str, DataProvider] | None = None
    ):
        self._providers: dict[str, DataProvider] = {}
        if providers is None:
            return

        if isinstance(providers, Mapping):
            for name, provider in providers.items():
                self.register(provider, name=name)
            return

        for provider in providers:
            self.register(provider)

    def register(self, provider: DataProvider, name: str | None = None) -> None:
        """Register or replace a provider by canonical lowercase name."""
        provider_name = self._normalize_name(name or provider.name)
        self._providers[provider_name] = provider

    def list_providers(self) -> list[ProviderInfo]:
        """Return metadata for all registered providers sorted by provider name."""
        return [self._providers[name].get_provider_info() for name in sorted(self._providers)]

    def get_provider(self, name: str) -> DataProvider:
        """Resolve a provider by name or raise a structured not-found error."""
        provider_name = self._normalize_name(name)
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise ProviderNotFoundError(name) from exc

    def get_provider_info(self, name: str) -> ProviderInfo:
        """Resolve provider metadata by provider name."""
        return self.get_provider(name).get_provider_info()

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()


def create_default_provider_registry() -> ProviderRegistry:
    """Create the static v0 provider registry."""
    from src.providers.binance_provider import BinanceProvider
    from src.providers.local_file_provider import LocalFileProvider
    from src.providers.yahoo_finance_provider import YahooFinanceProvider

    return ProviderRegistry([BinanceProvider(), YahooFinanceProvider(), LocalFileProvider()])
