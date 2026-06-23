"""
Cache layer for pyanime — stream URL storage and retrieval.
"""

from typing import Protocol, Optional, runtime_checkable


@runtime_checkable
class StreamCache(Protocol):
    """Interface for stream URL caching operations."""

    def cache_stream_url(self, slug: str, episode: int, stream_url: str, quality: str = "", provider: int = 0) -> None:
        ...

    def get_cached_stream_url(self, slug: str, episode: int, provider: int = 0, max_age_hours: int = 24) -> Optional[dict]:
        ...

    def clear_stream_cache(self, slug: Optional[str] = None, max_age_hours: int = 24) -> None:
        ...


from src.cache.stream_cache import (
    cache_stream_url,
    get_cached_stream_url,
    clear_stream_cache,
)

__all__ = [
    "StreamCache",
    "cache_stream_url",
    "get_cached_stream_url",
    "clear_stream_cache",
]
