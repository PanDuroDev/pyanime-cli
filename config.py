"""
Backward-compatible shim — delegates to src.config.
"""
import warnings

warnings.warn(
    "config.py is deprecated; use 'from src.config import ...' instead.",
    PendingDeprecationWarning,
    stacklevel=2,
)
from src.config import *  # noqa: F401, F403
from src.config import _config_cache  # noqa: F401 — explicitly export private name
