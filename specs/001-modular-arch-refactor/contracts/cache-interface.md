# Cache Layer Interface Contract

## Purpose

Defines how the caching layer stores and retrieves resolved stream URLs. The cache is a standalone module with no dependency on provider or playback internals.

## Interface

```python
class StreamCache(Protocol):
    """Contract for stream URL caching."""

    async def get(
        self, slug: str, episode: int, provider_id: int
    ) -> Optional[dict]:
        """Retrieve a cached stream URL.
        Returns {url: str, quality: str, fetched_at: float} or None.
        """

    async def set(
        self, slug: str, episode: int, stream_url: str,
        quality: str, provider_id: int
    ) -> None:
        """Store a resolved stream URL."""

    async def invalidate(
        self, slug: str, episode: int = None, provider_id: int = None
    ) -> None:
        """Remove cache entries. If episode is None, clears all for slug."""

    async def prune(self, max_age_hours: int = 24) -> int:
        """Remove entries older than max_age_hours. Returns count removed."""
```

## Cache Behavior

- Cache is read-through: resolve_stream checks cache before scraping
- Cache is write-through: resolved URLs are stored immediately
- Default TTL: 24 hours (configurable)
- Cache key: `{slug}_{provider_id}:{episode}`
- Underlying storage: SQLite `stream_cache` table (existing schema)
