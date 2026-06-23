import asyncio
import time
from typing import Any, Optional, Protocol
from urllib.parse import urlparse

_search_cache: dict[tuple[str, tuple[int, ...]], tuple[float, dict[int, list[dict[str, Any]]]]] = {}
_SEARCH_CACHE_TTL = 300  # 5 minutes


class SourceProvider(Protocol):
    provider_id: int
    provider_name: str

    async def search(self, query: str) -> list[dict[str, Any]]:
        ...

    async def fetch_episodes(self, url: str) -> list[dict[str, Any]]:
        ...

    async def resolve_stream(self, episode_url: str) -> Optional[dict[str, Any]]:
        ...

    async def resolve_stream_with_cookies(
        self, episode_url: str, cookies: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[int, SourceProvider] = {}

    def register(self, provider: SourceProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: int) -> Optional[SourceProvider]:
        return self._providers.get(provider_id)

    def get_all(self) -> list[SourceProvider]:
        return list(self._providers.values())


registry = ProviderRegistry()


async def search_all_providers(
    query: str,
    provider_ids: list[int] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """Search providers, returning results keyed by provider_id (no cross-provider dedup).
    Results are cached in-memory for 5 minutes per (query, provider_ids) key.

    Returns {provider_id: [{"title": str, "url": str}, ...]}
    """
    providers = registry.get_all()
    if provider_ids is not None:
        providers = [p for p in providers if p.provider_id in provider_ids]

    if not providers:
        return {}

    cache_key = (query, tuple(sorted(p.provider_id for p in providers)))
    now = time.time()

    cached = _search_cache.get(cache_key)
    if cached and (now - cached[0]) < _SEARCH_CACHE_TTL:
        return cached[1]

    tasks = [p.search(query) for p in providers]
    res = await asyncio.gather(*tasks, return_exceptions=True)

    results: dict[int, list[dict[str, Any]]] = {}
    for i, p in enumerate(providers):
        data = res[i]
        if isinstance(data, list):
            results[p.provider_id] = data
        else:
            import sys as _sys
            print(f"[pyanime] Warning: {p.provider_name} search error: {data}", file=_sys.stderr)
            results[p.provider_id] = []

    _search_cache[cache_key] = (now, results)
    return results


def detect_provider(url: str) -> Optional["SourceProvider"]:
    """Detect which provider handles a given URL based on domain patterns."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    domain_map: dict[str, list[str]] = {
        "anime3rb": ["anime3rb.com", "anime3rb"],
        "witanime": ["witanime"],
        "anineko": ["anineko.to", "anineko", "anitaku", "gogoanime"],
    }

    for p in registry.get_all():
        pname = p.provider_name.lower()
        if pname in domain_map:
            for domain_pattern in domain_map[pname]:
                if domain_pattern in netloc:
                    return p
    return None


def _load_providers() -> None:
    from src.providers import anime3rb, witanime, anineko
    for mod in (anime3rb, witanime, anineko):
        mod._register_provider(registry)


_load_providers()
