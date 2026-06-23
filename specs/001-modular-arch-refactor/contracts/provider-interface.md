# Source Provider Interface Contract

## Purpose

Defines the contract every stream source provider must implement. Providers are discovered through a registry and invoked by the orchestrator layer.

## Interface

```python
from typing import Protocol, List, Optional

class SourceProvider(Protocol):
    """Contract for anime streaming source providers."""

    provider_id: int
    provider_name: str

    async def search(self, query: str) -> List[dict]:
        """Search for anime titles.
        Returns list of {title: str, url: str}.
        """

    async def fetch_episodes(self, url: str) -> List[dict]:
        """Fetch episode list for an anime page.
        Returns list of {episode: int, page_url: str}.
        """

    async def resolve_stream(self, episode_url: str) -> Optional[dict]:
        """Resolve a playable stream URL from an episode page.
        Returns {url: str, quality: str} or None if resolution fails.
        """

    async def resolve_stream_with_cookies(
        self, episode_url: str, cookies: list
    ) -> Optional[dict]:
        """Same as resolve_stream but with browser cookies for bypass.
        Returns {url: str, quality: str} or None.
        """
```

## Error Contract

| Error Scenario | Behavior |
|---------------|----------|
| Network failure (timeout, DNS) | Return empty list from search/fetch; None from resolve |
| Cloudflare challenge | Return empty list — indicates cookies or Playwright needed |
| Invalid URL | Return empty list |
| Unexpected parse error | Return empty list (log internally, never crash) |

## Registration

Providers are registered in a singleton `ProviderRegistry`:

- Registry is populated at import time from `src/providers/__init__.py`
- Each provider is instantiated and stored by `provider_id`
- Orchestrator queries all providers for search, deduplicates results
- Stream resolution targets a specific provider by ID
