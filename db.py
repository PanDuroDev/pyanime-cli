"""
Backward-compatible shim — delegates to src.db and src.cache.
"""
import warnings

warnings.warn(
    "db.py is deprecated; use 'from src.db import ...' or 'from src.cache import ...' instead.",
    PendingDeprecationWarning,
    stacklevel=2,
)
from src.db import *  # noqa: F401, F403
from src.cache import cache_stream_url, get_cached_stream_url, clear_stream_cache  # noqa: F401
