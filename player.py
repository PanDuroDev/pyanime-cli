"""
Player discovery, caching, installation, and launching for pyanime.
Backward-compatible shim — delegates to src.playback.
"""
import warnings

warnings.warn(
    "player.py is deprecated; use 'from src.playback import ...' instead.",
    PendingDeprecationWarning,
    stacklevel=2,
)
from src.playback.discovery import (
    _get_player_cfg,
    _invalidate_player_cfg,
    get_cached_players,
    clear_player_cache,
    refresh_system_path,
    find_vlc,
    find_mpv,
    find_iina,
    find_celluloid,
    find_haruna,
    install_player,
)
from src.playback.launch import (
    play_with_vlc,
    play_with_mpv,
    play_with_iina,
    play_with_celluloid,
    play_with_haruna,
)
from src.playback.progress import (
    poll_mpv_progress,
)
