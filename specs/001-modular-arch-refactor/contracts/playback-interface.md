# Playback Control Interface Contract

## Purpose

Defines how the playback layer discovers, launches, and tracks external video players. The playback layer has no dependency on provider or UI internals.

## Discovery Contract

```python
def discover_players() -> dict:
    """Scan system for available video players.
    Returns {player_name: executable_path} for each found player.
    Keys: "vlc", "mpv", "iina", "celluloid", "haruna"
    """

def find_player(name: str) -> Optional[str]:
    """Find a specific player by name. Returns path or None."""

def install_player(name: str) -> bool:
    """Attempt auto-install of a player via system package manager.
    Returns True if installed successfully.
    """
```

## Launch Contract

```python
def play(
    stream_urls: List[str],
    player: str = "mpv",
    fullscreen: bool = True,
    slug: str = None,
    episode: int = None,
    extra_args: List[str] = None
) -> bool:
    """Launch external player with stream URLs.
    Returns True if player launched successfully.
    """

def play_with_vlc(stream_urls: List[str], **kwargs) -> bool: ...
def play_with_mpv(stream_urls: List[str], slug: str = None, episode: int = None, **kwargs) -> bool: ...
def play_with_iina(stream_urls: List[str], **kwargs) -> bool: ...
def play_with_celluloid(stream_urls: List[str], **kwargs) -> bool: ...
def play_with_haruna(stream_urls: List[str], **kwargs) -> bool: ...
```

## Progress Tracking Contract

```python
def start_progress_tracking(slug: str, episode: int, player_ipc_path: str) -> None:
    """Begin polling MPV IPC socket for playback progress.
    Runs in a daemon thread. Saves progress every 2 seconds.
    Automatically marks episode complete at >95% duration.
    """
```
