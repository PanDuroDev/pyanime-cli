"""
TUI components for pyanime — interactive terminal UI, state machine, and widgets.
"""
import asyncio

_shared_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_shared_loop)

def _run_async(coro):
    return _shared_loop.run_until_complete(coro)

import atexit
import contextlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.parse import urlparse, quote_plus

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.live import Live
from rich.columns import Columns
from rich.text import Text
from rich.markup import escape
from rich import box as rich_box

from config import (
    APP_VERSION, THEME, console, get_icon, get_provider_name,
    get_config_dir, get_config_path, load_config, save_config,
    add_search_history, get_http_client, write_custom_config_dir,
    _config_cache,
)
from db import (
    get_db_path, init_db, migrate_json_to_sqlite,
    toggle_favorite_state, is_favorite_slug,
    add_watch_history, get_watch_history,
    save_account_token, get_account_token, remove_account,
    fetch_anime_metadata,
    fetch_anilist_user_list, fetch_mal_user_list,
    cache_stream_url, get_cached_stream_url,
    get_all_episode_progress,
    add_download_entry, get_downloads, remove_download_entry, update_download_status,
)
from player import (
    get_cached_players, clear_player_cache,
    find_vlc, find_mpv, find_iina, find_celluloid, find_haruna,
    install_player,
    play_with_vlc, play_with_mpv, play_with_iina,
    play_with_celluloid, play_with_haruna,
    _invalidate_player_cfg as invalidate_player_cfg,
)
from scraping import (
    validate_url, extract_slug, get_preferred_cookies,
    deduplicate_search_results, deduplicate_search_results_multi,
    search_providers_for_media,
    fetch_episodes_list_async, scrape_multiple_streams_async,
)
from src.providers import registry as provider_registry

if os.name == 'nt':
    try:
        import win32crypt
    except ImportError:
        win32crypt = None
    import msvcrt
else:
    import tty
    import termios
    import select
    win32crypt = None
    msvcrt = None


# ── Layout helpers (from tui_layout.py) ─────────────────────

def detect_layout_mode(width=None, height=None):
    if width is None or height is None:
        width, height = shutil.get_terminal_size()
    if height < 20 or width < 75:
        return "MINIMAL"
    return "NORMAL"


# ── Key Constants & Input Handling ─────────────────────────

KEY_UP = "up"
KEY_DOWN = "down"
KEY_ENTER = "enter"
KEY_SPACE = "space"
KEY_ESC = "esc"
KEY_CTRL_C = "ctrl_c"
KEY_A = "a"
KEY_UNKNOWN = "unknown"

_in_raw_mode = False
_raw_fd = None


class RawModeContext:
    def __enter__(self):
        global _in_raw_mode, _raw_fd
        if os.name != 'nt' and sys.stdin.isatty():
            try:
                self.fd = sys.stdin.fileno()
                self.old_settings = termios.tcgetattr(self.fd)

                new_settings = termios.tcgetattr(self.fd)
                new_settings[0] &= ~(termios.BRKINT | termios.ICRNL | termios.INPCK | termios.ISTRIP | termios.IXON)
                new_settings[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
                new_settings[6][termios.VMIN] = 1
                new_settings[6][termios.VTIME] = 0

                termios.tcsetattr(self.fd, termios.TCSADRAIN, new_settings)
                _in_raw_mode = True
                _raw_fd = self.fd
            except Exception:
                self.fd = None
                self.old_settings = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _in_raw_mode, _raw_fd
        if os.name != 'nt' and getattr(self, 'fd', None) is not None and getattr(self, 'old_settings', None) is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass
            _in_raw_mode = False
            _raw_fd = None


def read_key():
    if os.name == 'nt':
        try:
            ch = msvcrt.getwch()
            if ch in ('\x00', '\xe0'):
                ch += msvcrt.getwch()
            if ch == '\xe0H': return KEY_UP
            if ch == '\xe0P': return KEY_DOWN
            if ch in ('\r', '\n'): return KEY_ENTER
            if ch == ' ': return KEY_SPACE
            if ch in ('\x08', '\x7f'): return '\x08'
            if ch == '\x1b': return KEY_ESC
            if ch == '\x03': return KEY_CTRL_C
            if ch in ('a', 'A'): return KEY_A
            if len(ch) == 1:
                return ch
            return KEY_UNKNOWN
        except Exception:
            return KEY_UNKNOWN
    else:
        if not sys.stdin.isatty():
            try:
                ch = sys.stdin.read(1)
                if not ch:
                    return KEY_ESC
                if ch in ('\r', '\n'): return KEY_ENTER
                if ch == ' ': return KEY_SPACE
                if ch in ('a', 'A'): return KEY_A
                return ch
            except Exception:
                return KEY_ESC

        if _in_raw_mode and _raw_fd is not None:
            try:
                b = os.read(_raw_fd, 1)
                if not b:
                    return KEY_ESC
                if b == b'\x1b':
                    r, _, _ = select.select([_raw_fd], [], [], 0.05)
                    if r:
                        extra = os.read(_raw_fd, 2)
                        if extra == b'[A': return KEY_UP
                        if extra == b'[B': return KEY_DOWN
                    return KEY_ESC
                if b in (b'\r', b'\n'): return KEY_ENTER
                if b == b' ': return KEY_SPACE
                if b == b'\x03': return KEY_CTRL_C
                if b in (b'a', b'A'): return KEY_A
                return b.decode('utf-8', errors='ignore')
            except Exception:
                return KEY_UNKNOWN
        else:
            try:
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
            except Exception:
                try:
                    ch = sys.stdin.read(1)
                    if not ch: return KEY_ESC
                    return ch
                except Exception:
                    return KEY_UNKNOWN

            try:
                new_settings = termios.tcgetattr(fd)
                new_settings[0] &= ~(termios.BRKINT | termios.ICRNL | termios.INPCK | termios.ISTRIP | termios.IXON)
                new_settings[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
                new_settings[6][termios.VMIN] = 1
                new_settings[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSADRAIN, new_settings)

                r, _, _ = select.select([fd], [], [])
                if not r:
                    return KEY_UNKNOWN
                b = os.read(fd, 1)
                if not b:
                    return KEY_ESC
                if b == b'\x1b':
                    r, _, _ = select.select([fd], [], [], 0.05)
                    if r:
                        extra = os.read(fd, 2)
                        if extra == b'[A': return KEY_UP
                        if extra == b'[B': return KEY_DOWN
                    return KEY_ESC
                if b in (b'\r', b'\n'): return KEY_ENTER
                if b == b' ': return KEY_SPACE
                if b == b'\x03': return KEY_CTRL_C
                if b in (b'a', b'A'): return KEY_A
                return b.decode('utf-8', errors='ignore')
            except Exception:
                return KEY_UNKNOWN
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass


def flush_input_buffer():
    if os.name == 'nt':
        try:
            while msvcrt.kbhit():
                msvcrt.getwch()
        except Exception:
            pass
    else:
        try:
            import select as sel_mod
            while sel_mod.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        except Exception:
            pass


# ── Terminal Control ───────────────────────────────────────

def clear_screen():
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def enter_alt_screen():
    if sys.stdout.isatty():
        sys.stdout.write("\033[?1049h")
        sys.stdout.flush()


def exit_alt_screen():
    if sys.stdout.isatty():
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()


def set_terminal_title(title):
    if sys.stdout.isatty():
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()


def prompt_input(prompt_text):
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    try:
        val = console.input(prompt_text).strip()
        return val
    except (KeyboardInterrupt, EOFError):
        return None
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()


# ── Print Helpers ──────────────────────────────────────────

def print_info(msg):
    console.print(f"[bold {THEME['primary']}]" + get_icon("info") + f"[/bold {THEME['primary']}] [{THEME['fg']}]{msg}[/{THEME['fg']}]")


def print_ok(msg):
    console.print(f"[bold {THEME['success']}]" + get_icon("check") + f"[/bold {THEME['success']}] [{THEME['fg']}]{msg}[/{THEME['fg']}]")


def print_warn(msg):
    console.print(f"[bold {THEME['warning']}]" + get_icon("warning") + f"[/bold {THEME['warning']}] [{THEME['fg']}]{msg}[/{THEME['fg']}]")


def print_fail(msg):
    console.print(f"[bold {THEME['error']}]" + get_icon("cross") + f"[/bold {THEME['error']}] [{THEME['fg']}]{msg}[/{THEME['fg']}]")


def print_hotkey_guide(player_name):
    title = f" [bold {THEME['primary']}]{player_name} Keyboard Controls / Shortcuts[/bold {THEME['primary']}] "

    table = Table(box=None, show_header=True, header_style=f"bold {THEME['accent']}", pad_edge=False)
    table.add_column("Action", style=f"bold {THEME['fg']}")
    table.add_column("Hotkey / Shortcut", style=f"bold {THEME['success']}")

    if player_name == "MPV":
        table.add_row("Play / Pause", "SPACE")
        table.add_row("Seek Back / Forward (5s)", "LEFT / RIGHT")
        table.add_row("Seek Back / Forward (1m)", "UP / DOWN")
        table.add_row("Adjust Volume", "9 / 0")
        table.add_row("Toggle Fullscreen", "F")
        table.add_row("Exit Player", "Q")
    else:
        table.add_row("Play / Pause", "SPACE")
        table.add_row("Seek Back / Forward", "ALT + LEFT / RIGHT")
        table.add_row("Adjust Volume", "CTRL + UP / DOWN")
        table.add_row("Toggle Fullscreen", "F")
        table.add_row("Exit Player", "Q / ESC")

    panel = Panel(
        table,
        title=title,
        border_style=THEME['border'],
        box=rich_box.ROUNDED,
        padding=(1, 2),
        expand=False
    )
    console.print(panel)


# ── Centered Helpers ──────────────────────────────────────

def _centered_message(msg, level="info"):
    icon_map = {"info": "info", "ok": "check", "warn": "warning", "error": "cross"}
    color_map = {"info": THEME['primary'], "ok": THEME['success'], "warn": THEME['warning'], "error": THEME['error']}
    icon = get_icon(icon_map.get(level, "info"))
    color = color_map.get(level, THEME['fg'])

    w, h = shutil.get_terminal_size()
    panel = Panel(
        Group(Text(f"{icon} {msg}", style=color, justify="center"), Text("")),
        box=rich_box.ROUNDED,
        border_style=THEME['border'],
        padding=(1, 3),
    )
    padding_top = max(0, (h - 8) // 2)
    console.clear()
    console.print(Group(
        Text("\n" * padding_top),
        panel,
        Text(""),
        Text("Press any key to continue...", style=THEME['dim'], justify="center"),
    ))
    read_key()


def _centered_prompt(prompt_text):
    if sys.stdout.isatty():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    try:
        w, h = shutil.get_terminal_size()
        panel = Panel(
            Text(f"{get_icon('settings')} {prompt_text}", style=THEME['fg'], justify="center"),
            box=rich_box.ROUNDED,
            border_style=THEME['border'],
            padding=(1, 3),
        )
        padding_top = max(0, (h - 8) // 2)
        console.clear()
        console.print(Group(
            Text("\n" * padding_top),
            panel,
            Text(""),
            Text("Type your answer and press Enter (Esc to cancel):", style=THEME['dim'], justify="center"),
        ))
        val = console.input(f"[bold {THEME['accent']}]\u276f[/bold {THEME['accent']}] ").strip()
        return val
    except (KeyboardInterrupt, EOFError):
        return None
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()


@contextlib.contextmanager
def _centered_status(text, spinner="dots", icon="search"):
    spinner_renderable = Spinner(spinner, text="", style=THEME['primary'])
    icon_map = {"search": get_icon("search"), "watch": get_icon("watch_history")}
    prefix = icon_map.get(icon, "")

    def _make():
        ts = shutil.get_terminal_size()
        return Align(
            Panel(
                Group(Text(f"{prefix} {text}", style=THEME['primary'], justify="center"), Text(""), spinner_renderable),
                box=rich_box.ROUNDED,
                border_style=THEME['border'],
                padding=(1, 3),
            ),
            align="center",
            vertical="middle",
            height=ts.lines
        )

    with Live(_make(), refresh_per_second=10, transient=True) as live:
        yield live


# ── Interactive Widgets ────────────────────────────────────

UPDATE_CHECK_URL = "https://raw.githubusercontent.com/anomalyco/pyanime/main/VERSION"
_update_cache = {"latest": None, "checked": False}


def check_for_update(current_version):
    if _update_cache["checked"]:
        latest = _update_cache["latest"]
        if latest is None:
            return None
        return latest, latest != current_version

    _update_cache["checked"] = True
    try:
        resp = get_http_client().get(UPDATE_CHECK_URL, timeout=5.0)
        if resp.status_code == 200:
            latest = resp.text.strip()
            _update_cache["latest"] = latest
            return latest, latest != current_version
    except Exception:
        pass
    return None


TRACK_DEFAULTS = {"audio_id": None, "sub_id": None, "audio_lang": None, "sub_lang": None}


def _show_track_selector(track_info=None):
    if track_info is None:
        track_info = dict(TRACK_DEFAULTS)

    while True:
        table = Table(box=rich_box.ROUNDED, show_header=True, header_style=f"bold {THEME['accent']}", border_style=THEME['border'])
        table.add_column("Track Type", style=f"bold {THEME['fg']}")
        table.add_column("Setting", style=THEME['fg'])
        table.add_column("Action Key", style=THEME['dim'])

        table.add_row(
            "Audio Track",
            f"[{THEME['accent']}]{track_info['audio_lang'] or 'Default'}[/{THEME['accent']}] (ID: {track_info['audio_id'] or 'auto'})",
            "[bold]a[/bold] to set, [bold]A[/bold] to clear"
        )
        table.add_row(
            "Subtitle Track",
            f"[{THEME['accent']}]{track_info['sub_lang'] or 'None'}[/{THEME['accent']}] (ID: {track_info['sub_id'] or 'off'})",
            "[bold]s[/bold] to set, [bold]S[/bold] to clear"
        )
        table.add_row(
            "",
            "[dim]Available tracks are detected from your stream.\nManual IDs: --aid=N (MPV) / :audio-track=N (VLC)[/dim]",
            ""
        )

        panel = Panel(
            table,
            title="[bold]Audio / Subtitle Tracks[/bold]",
            border_style=THEME['border'],
            box=rich_box.ROUNDED,
            padding=(1, 2)
        )
        w, h = shutil.get_terminal_size()
        hotkey_bar = Text("a=Set audio ID  s=Set sub ID  A=Clear audio  S=Clear sub  Enter=Done  Esc=Cancel", style=THEME['dim'], justify="center")
        console.clear()
        console.print(Align(Group(panel, Text(""), hotkey_bar), align="center", vertical="middle", height=h))
        key = read_key()
        if key in (KEY_ENTER,):
            return track_info
        if key in (KEY_ESC, KEY_CTRL_C):
            return None
        if key == 'a':
            console.print(f"\n[{THEME['accent']}]Enter audio track ID (or leave empty for auto):[/{THEME['accent']}] ", end="")
            raw = _simple_read_line()
            if raw:
                try:
                    track_info["audio_id"] = int(raw)
                    track_info["audio_lang"] = f"Track {raw}"
                except ValueError:
                    pass
        elif key == 'A':
            track_info["audio_id"] = None
            track_info["audio_lang"] = None
        elif key == 's':
            console.print(f"\n[{THEME['accent']}]Enter subtitle track ID (or leave empty for off):[/{THEME['accent']}] ", end="")
            raw = _simple_read_line()
            if raw:
                try:
                    track_info["sub_id"] = int(raw)
                    track_info["sub_lang"] = f"Track {raw}"
                except ValueError:
                    pass
        elif key == 'S':
            track_info["sub_id"] = None
            track_info["sub_lang"] = None


def _simple_read_line():
    buf = []
    while True:
        k = read_key()
        if k == KEY_ENTER:
            return "".join(buf)
        if k in (KEY_ESC, KEY_CTRL_C):
            return None
        if k in ('\x08', '\x7f'):
            if buf:
                buf.pop()
        elif isinstance(k, str) and k.isprintable():
            buf.append(k)


def get_context_panel(context_type, selected_idx, options, metadata=None):
    if not metadata:
        metadata = {}

    title_text = "Information"

    players = get_cached_players()
    vlc_ok = players.get("vlc") is not None
    mpv_ok = players.get("mpv") is not None
    iina_ok = players.get("iina") is not None
    celluloid_ok = players.get("celluloid") is not None
    haruna_ok = players.get("haruna") is not None

    if context_type == "main_menu":
        title_text = "System Status & Info"
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column("Key", style=f"bold {THEME['fg']}")
        table.add_column("Val", style=THEME['success'])

        player_status = "MPV" if mpv_ok else ("VLC" if vlc_ok else "None")
        pref_player = metadata.get("pref_player", "auto").upper()

        table.add_row(f"{get_icon('play')}Preferred Player", f"{pref_player} (Active: {player_status})")
        table.add_row(f"{get_icon('settings')}Quality", metadata.get("default_quality", "auto").upper())
        table.add_row(f"{get_icon('direct_url')}Cookie Browser", metadata.get("pref_browser", "auto").upper())
        table.add_row(f"{get_icon('favorite_on')}Library Size", f"{metadata.get('favorites_count', 0)} show(s)")

        al_linked = "[green]Linked[/green]" if metadata.get("anilist_linked") else "[dim]Not Linked[/dim]"
        mal_linked = "[green]Linked[/green]" if metadata.get("mal_linked") else "[dim]Not Linked[/dim]"
        table.add_row(f"{get_icon('watch_history')}AniList Sync", al_linked)
        table.add_row(f"{get_icon('watch_history')}MyAnimeList Sync", mal_linked)

        desc = ""
        if selected_idx == 0:
            desc = "Search for anime series across multiple streaming sources (Anime3rb, WitAnime, Anineko, HiAnime) in real-time."
        elif selected_idx == 1:
            desc = "Directly play an anime URL from any supported source (Anime3rb, WitAnime, Anineko, HiAnime) without performing a search."
        elif selected_idx == 2:
            desc = "Browse your bookmarked library of shows, view history, and resume playing."
        elif selected_idx == 3:
            desc = "Configure preferred video players, stream quality, cookie sync browsers, and account integrations."
        elif selected_idx == 4:
            desc = "Close the application and exit back to the shell."

        update_row = metadata.get("update_info")
        if update_row:
            latest_ver, is_newer = update_row
            if is_newer:
                update_msg = f"[bold {THEME['warning']}]Update available: {latest_ver}[/bold {THEME['warning']}]"
            else:
                update_msg = f"[dim {THEME['dim']}]Up to date ({latest_ver})[/dim {THEME['dim']}]"
            table.add_row(f"{get_icon('warning')}Version", update_msg)

        desc_esc = escape(desc)
        renderables = [
            Text("━━━ SYSTEM DIAGNOSTICS ━━━", style=f"bold {THEME['accent']}"),
            Text(""),
            table,
            Text(""),
            Text("━━━ DESCRIPTION ━━━", style=f"bold {THEME['accent']}"),
            Text(f"\n{desc_esc}\n", style=THEME['fg']),
            Text("━━━ QUICK CONTROLS ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 [bold {THEME['primary']}]\u2191 / \u2193[/bold {THEME['primary']}]   : Move cursor\n  \u2022 [bold {THEME['primary']}]ENTER[/bold {THEME['primary']}]   : Select option\n  \u2022 [bold {THEME['primary']}]ESC[/bold {THEME['primary']}]     : Go back / Exit\n", style=THEME['fg'])
        ]

    elif context_type == "settings":
        title_text = "Configuration Help"
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column("Player", style=f"bold {THEME['fg']}")
        table.add_column("Status", style=THEME['success'])

        table.add_row("MPV Player", "[green]Installed[/green]" if mpv_ok else "[red]Not Found[/red]")
        table.add_row("VLC Player", "[green]Installed[/green]" if vlc_ok else "[red]Not Found[/red]")
        if sys.platform == "darwin":
            table.add_row("IINA Player", "[green]Installed[/green]" if iina_ok else "[red]Not Found[/red]")
        else:
            table.add_row("Celluloid", "[green]Installed[/green]" if celluloid_ok else "[red]Not Found[/red]")
            table.add_row("Haruna", "[green]Installed[/green]" if haruna_ok else "[red]Not Found[/red]")
        table.add_row("Config Path", f"[dim]{get_config_dir()}[/dim]")

        desc = ""
        option_title = options[selected_idx] if selected_idx < len(options) else ""
        if "Preferred Player" in option_title:
            desc = "Choose your preferred video player. MPV is strongly recommended as it supports embedding and progress tracking. VLC is used as a fallback."
        elif "Default Video Quality" in option_title:
            desc = "Select your default streaming quality. If 'auto' is selected, the highest resolution available on the server will be selected."
        elif "Cookie Sync Browser" in option_title:
            desc = "Select which browser to extract cookies from (Chrome or Edge). Cookies are required to bypass Cloudflare Turnstile protection on WitAnime/Anime3rb."
        elif "History Tracking" in option_title:
            desc = "Toggle local watch history tracking. If disabled, watched episodes and watch progress won't be saved in the database."
        elif "Auto Fullscreen" in option_title:
            desc = "Automatically open the player in fullscreen mode upon launch."
        elif "Custom Player Args" in option_title:
            desc = "Specify additional command line arguments to pass directly to the player executable (e.g. `--volume=80` or `--ontop`)."
        elif "Nerd Font Icons" in option_title:
            desc = "Toggle Nerd Font icons support. If your terminal font supports Nerd Fonts, this enables modern high-resolution icons instead of standard Unicode."
        elif "Config" in option_title and "Directory" in option_title:
            desc = "Change the directory path where config.json and pyanime.db are stored. Existing data is moved automatically to the new location."
        elif "Accounts Integration" in option_title:
            desc = "Link and manage MyAnimeList (MAL) or AniList accounts to sync your watch progress dynamically."
        elif "Clear Search History" in option_title:
            desc = "Delete all recent search queries cached in your local config.json file."
        elif "Clear All Watch History" in option_title:
            desc = "Warning: This will permanently delete all local bookmarks, watched episode lists, watch progress, and linked accounts from the database."
        elif "Scraping Method" in option_title:
            desc = "Choose how episodes are scraped: 'Auto' tries httpx first and falls back to Playwright if needed; 'Playwright Only' always uses Playwright (Chromium); 'httpx Only' uses only httpx without launching a browser."
        elif "Go Back" in option_title:
            desc = "Return to the main menu."

        desc_esc = escape(desc)
        renderables = [
            Text("━━━ PLAYER DIAGNOSTICS ━━━", style=f"bold {THEME['accent']}"),
            Text(""),
            table,
            Text(""),
            Text("━━━ SETTING HELP ━━━", style=f"bold {THEME['accent']}"),
            Text(f"\n{desc_esc}\n", style=THEME['fg'])
        ]

    elif context_type == "search_results":
        title_text = "Search Details"
        query = metadata.get("search_query", "")
        search_entries = metadata.get("search_entries", [])

        selected_item = search_entries[selected_idx] if selected_idx < len(search_entries) else None
        if selected_item:
            sel_title = selected_item.get("title", "")
            sel_provider = selected_item.get("provider_name", "Unknown")
            sel_url = selected_item.get("url", "")
        else:
            sel_title = ""
            sel_provider = "Unknown"
            sel_url = ""

        query_esc = escape(query)
        title_esc = escape(sel_title)
        url_esc = escape(sel_url)

        renderables = [
            Text("━━━ SEARCH CONTEXT ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 [bold {THEME['primary']}]Active Query[/bold {THEME['primary']}] : '{query_esc}'\n  \u2022 [bold {THEME['primary']}]Total Results[/bold {THEME['primary']}]: {len(options)} item(s) found\n", style=THEME['fg']),
            Text("━━━ SELECTED ITEM ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 [bold {THEME['primary']}]Title[/bold {THEME['primary']}]        : {title_esc}\n  \u2022 [bold {THEME['primary']}]Provider[/bold {THEME['primary']}]     : {sel_provider}\n  \u2022 [bold {THEME['primary']}]URL[/bold {THEME['primary']}]         : {url_esc}\n", style=THEME['fg']),
            Text("━━━ INSTRUCTIONS ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 Press [bold {THEME['success']}]ENTER[/bold {THEME['success']}] to load this anime's episode list.\n  \u2022 Press [bold {THEME['warning']}]ESC[/bold {THEME['warning']}] to return to the search input screen.\n", style=THEME['fg'])
        ]

    elif context_type == "favorites":
        title_text = "Bookmark Details"
        selected_opt = options[selected_idx] if selected_idx < len(options) else ""
        show_slug = metadata.get("fav_slugs", [])[selected_idx] if selected_idx < len(metadata.get("fav_slugs", [])) else None

        title_esc = escape(selected_opt)
        info_text_markup = f"\n  \u2022 [bold {THEME['primary']}]Title[/bold {THEME['primary']}]        : {title_esc}\n"
        if show_slug:
            hist = get_watch_history(show_slug)
            last_ep = hist.get("last_watched", 0)
            watched_eps = len(hist.get("watched", []))
            info_text_markup += f"  \u2022 [bold {THEME['primary']}]Last Watched[/bold {THEME['primary']}]   : Episode {last_ep if last_ep > 0 else 'None'}\n"
            info_text_markup += f"  \u2022 [bold {THEME['primary']}]Watched Count[/bold {THEME['primary']}]  : {watched_eps} episode(s)\n"

        renderables = [
            Text("━━━ LIBRARY STATS ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 [bold {THEME['primary']}]Total Bookmarks[/bold {THEME['primary']}] : {len(options)} show(s)\n", style=THEME['fg']),
            Text("━━━ SELECTED BOOKMARK ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(info_text_markup, style=THEME['fg']),
            Text("━━━ INSTRUCTIONS ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(f"\n  \u2022 Press [bold {THEME['success']}]ENTER[/bold {THEME['success']}] to open this show's episodes list.\n  \u2022 Press [bold {THEME['warning']}]ESC[/bold {THEME['warning']}] to return to the main menu.\n", style=THEME['fg'])
        ]

    elif context_type == "episode_selection":
        title_text = "Episode Selection & Controls"
        anime_title = metadata.get("anime_title", "Anime Show")
        provider = metadata.get("provider", "Unknown")
        player_name = metadata.get("player_name", "MPV")
        anime_meta = metadata.get("anime_metadata")

        anime_title_esc = escape(anime_title)
        provider_esc = escape(provider)

        meta_lines = []
        if anime_meta:
            synopsis = anime_meta.get("synopsis")
            if synopsis:
                synopsis_clean = re.sub(r'<[^>]+>', '', synopsis)
                if len(synopsis_clean) > 180:
                    w, _ = shutil.get_terminal_size()
                    max_chars = max(80, w * 2)
                    synopsis_clean = synopsis_clean[:max_chars] + "..."
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Synopsis[/bold {THEME['primary']}]    : {escape(synopsis_clean)}")
            genres = anime_meta.get("genres", [])
            if genres:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Genres[/bold {THEME['primary']}]      : {', '.join(genres[:5])}")
            score = anime_meta.get("average_score")
            if score:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Rating[/bold {THEME['primary']}]       : {score}%")
            ep_count = anime_meta.get("episodes")
            if ep_count:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Episodes[/bold {THEME['primary']}]    : {ep_count}")
            studios = anime_meta.get("studios", [])
            if studios:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Studio[/bold {THEME['primary']}]      : {', '.join(studios[:2])}")
            season = anime_meta.get("season")
            season_year = anime_meta.get("season_year")
            if season and season_year:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Season[/bold {THEME['primary']}]      : {season.title()} {season_year}")
            elif season_year:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Year[/bold {THEME['primary']}]        : {season_year}")
            status_val = anime_meta.get("status")
            if status_val:
                meta_lines.append(f"  \u2022 [bold {THEME['primary']}]Status[/bold {THEME['primary']}]      : {status_val.replace('_', ' ').title()}")

        show_meta_markup = f"\n  \u2022 [bold {THEME['primary']}]Title[/bold {THEME['primary']}]        : {anime_title_esc}\n  \u2022 [bold {THEME['primary']}]Provider[/bold {THEME['primary']}]     : {provider_esc}\n"
        if meta_lines:
            show_meta_markup += "\n" + "\n".join(meta_lines) + "\n"

        renderables = [
            Text("━━━ SHOW METADATA ━━━", style=f"bold {THEME['accent']}"),
            Text.from_markup(show_meta_markup, style=THEME['fg']),
        ]

    return Panel(
        Group(*renderables),
        title=f"[bold {THEME['primary']}] {title_text} [/bold {THEME['primary']}]",
        border_style=THEME['border'],
        box=rich_box.ROUNDED,
        padding=(1, 1),
        expand=True
    )


def _show_help_panel(help_items, title="Keyboard Shortcuts"):
    table = Table(show_header=True, header_style=f"bold {THEME['accent']}", border_style=THEME['border'], box=rich_box.ROUNDED)
    table.add_column("Key", style=f"bold {THEME['primary']}")
    table.add_column("Action", style=THEME['fg'])
    for key, action in help_items:
        table.add_row(key, action)
    panel = Panel(table, title=f"[bold {THEME['primary']}] {title} [/bold {THEME['primary']}]", border_style=THEME['border'], padding=(1, 2))
    console.print(panel)
    console.print(f"[dim {THEME['dim']}]Press any key to dismiss...[/dim {THEME['dim']}]")
    read_key()


def interactive_select(options, title="Select Option", context_type=None, metadata=None,
                       player_name=None, active_player=None, pref_player=None, icons=None,
                       top_renderable=None):
    if not options:
        return -1, None

    flush_input_buffer()
    mapped_order = list(range(len(options)))
    filter_text = ""
    sort_mode = 0
    _get_display = lambda: [options[i] for i in mapped_order]
    selected_idx = 0
    scroll_offset = 0
    _, term_height = shutil.get_terminal_size()
    max_visible = max(5, min(20, term_height - 12))

    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    _right_panel_cache = {}
    _last_size = None
    _filter_active = False
    _filter_buf = ""

    def _rebuild_order():
        nonlocal mapped_order, selected_idx
        base = list(range(len(options)))
        if sort_mode == 1:
            base.sort(key=lambda i: options[i].lower())
        elif sort_mode == 2:
            base.sort(key=lambda i: options[i].lower(), reverse=True)
        if filter_text:
            base = [i for i in base if filter_text.lower() in options[i].lower()]
        mapped_order = base
        if selected_idx >= len(mapped_order):
            selected_idx = max(0, len(mapped_order) - 1)

    def _update_right_cache():
        _right_panel_cache.clear()

    _show_details = False
    _anim_old_scroll = 0
    _anim_start = 0.0
    _ANIM_DURATION = 0.3
    _anim_active = False

    try:
        def make_panel():
            nonlocal scroll_offset, selected_idx, _filter_active, _filter_buf
            nonlocal _right_panel_cache, _last_size, _show_details
            nonlocal _anim_old_scroll, _anim_start, _anim_active

            current_size = shutil.get_terminal_size()
            if _last_size != (current_size.columns, current_size.lines):
                _last_size = (current_size.columns, current_size.lines)
                _right_panel_cache.clear()

            display = _get_display()
            if not display:
                display = ["[dim](no matches)[/dim]"]
            if selected_idx >= len(display):
                selected_idx = max(0, len(display) - 1)
            if selected_idx < scroll_offset:
                scroll_offset = selected_idx
            elif selected_idx >= scroll_offset + max_visible:
                scroll_offset = selected_idx - max_visible + 1

            render_scroll = scroll_offset
            if _anim_active:
                elapsed = time.monotonic() - _anim_start
                if elapsed >= _ANIM_DURATION:
                    _anim_active = False
                else:
                    progress = elapsed / _ANIM_DURATION
                    eased = 1.0 - (1.0 - progress) ** 3
                    render_scroll = int(round(_anim_old_scroll + (scroll_offset - _anim_old_scroll) * eased))

            table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))

            if render_scroll > 0:
                table.add_row(f"[dim {THEME['dim']}]    {get_icon('arrow_up')}more items above[/dim {THEME['dim']}]")
            else:
                table.add_row("")

            visible_options = display[render_scroll : render_scroll + max_visible]
            for idx_rel, opt in enumerate(visible_options):
                idx_abs = render_scroll + idx_rel
                num_label = f"{idx_abs + 1}."
                if idx_abs == selected_idx:
                    table.add_row(f"  [bold {THEME['accent']}]{get_icon('bullet')}[/bold {THEME['accent']}][bold {THEME['select_fg']} on {THEME['select_bg']}] {num_label} {opt} [/bold {THEME['select_fg']} on {THEME['select_bg']}]")
                else:
                    table.add_row(f"    [{THEME['fg']}]{num_label}[/{THEME['fg']}] [{THEME['fg']}]{opt}[/{THEME['fg']}]")

            total = len(display) if display != ["[dim](no matches)[/dim]"] else 0
            if render_scroll + max_visible < total:
                table.add_row(f"[dim {THEME['dim']}]    {get_icon('arrow_down')}more items below[/dim {THEME['dim']}]")
            else:
                table.add_row("")

            if _filter_active:
                buf_text = escape(_filter_buf) if _filter_buf else ""
                table.add_row(f"  [{THEME['accent']}]Filter: {buf_text}\u2588[/{THEME['accent']}]")

            filter_indicator = ""
            if filter_text:
                filter_indicator = f"  [{THEME['accent']}]/ {escape(filter_text)}[/{THEME['accent']}]"
            sort_labels = ["", " [A-Z]", " [Z-A]"]
            page_info = f"({selected_idx + 1}/{total}){filter_indicator}{sort_labels[sort_mode]}"
            if _filter_active:
                buf_text = escape(_filter_buf) if _filter_buf else "..."
                subtitle = f"[{THEME['accent']}]  Filter: {buf_text}\u2588  (Esc=Abort  Enter=Apply)[/{THEME['accent']}]"
            else:
                player_info = ""
                if player_name and active_player:
                    player_info = f" | {icons.get('check', '')} {player_name} ({active_player})" if icons else f" | {player_name}"
                detail_label = "d=Details" if context_type else ""
                subtitle = f"\u2191\u2193 Navigate  \u23ce Select  {detail_label}  Esc Back  /=Filter  s=Sort{player_info}  {page_info}"

            left_panel = Panel(
                table,
                title=f"[bold {THEME['primary']}] {title} [/bold {THEME['primary']}] [dim]{APP_VERSION}[/dim]",
                subtitle=f"[{THEME['fg']}]{subtitle}[/{THEME['fg']}]",
                border_style=THEME['border'],
                box=rich_box.ROUNDED,
                expand=True,
                padding=(1, 2)
            )

            width, height = current_size.columns, current_size.lines
            mode = detect_layout_mode(width, height)

            body_parts = []
            if top_renderable:
                body_parts.append(top_renderable)

            show_right = context_type and _show_details and mode != "MINIMAL" and width >= 80
            if show_right:
                orig_idx = mapped_order[selected_idx] if selected_idx < len(mapped_order) else 0
                if orig_idx not in _right_panel_cache:
                    _right_panel_cache[orig_idx] = get_context_panel(context_type, orig_idx, options, metadata)
                right_panel = _right_panel_cache[orig_idx]
                grid = Table.grid(expand=True)
                grid.add_column(ratio=40)
                grid.add_column(ratio=60)
                grid.add_row(left_panel, right_panel)
                body_parts.append(grid)
            else:
                body_parts.append(Align.center(left_panel))

            body = Group(*body_parts) if len(body_parts) > 1 else body_parts[0]
            return Align(body, align="center", vertical="middle", height=current_size.lines)

        with RawModeContext():
            with Live(None, refresh_per_second=20, transient=False) as live:
                live.update(make_panel())
                while True:
                    key = read_key()

                    if _filter_active:
                        if key == KEY_ENTER:
                            _filter_active = False
                            filter_text = _filter_buf
                            _filter_buf = ""
                            _rebuild_order()
                            _update_right_cache()
                            selected_idx = 0
                        elif key in (KEY_ESC, KEY_CTRL_C):
                            _filter_active = False
                            _filter_buf = ""
                        elif key in ('\x08', '\x7f'):
                            _filter_buf = _filter_buf[:-1]
                        elif isinstance(key, str) and key.isprintable():
                            _filter_buf += key
                        live.update(make_panel())
                        continue

                    display = _get_display()
                    if key == KEY_UP:
                        if display:
                            _anim_old_scroll = scroll_offset
                            _anim_start = time.monotonic()
                            _anim_active = True
                            selected_idx = (selected_idx - 1) % len(display)
                        live.update(make_panel())
                    elif key == KEY_DOWN:
                        if display:
                            _anim_old_scroll = scroll_offset
                            _anim_start = time.monotonic()
                            _anim_active = True
                            selected_idx = (selected_idx + 1) % len(display)
                        live.update(make_panel())
                    elif key in ('d', 'D'):
                        if context_type:
                            _show_details = not _show_details
                            live.update(make_panel())
                    elif key == '/':
                        _filter_active = True
                        _filter_buf = ""
                        live.update(make_panel())
                    elif key in ('s', 'S'):
                        sort_mode = (sort_mode + 1) % 3
                        _rebuild_order()
                        _update_right_cache()
                        selected_idx = 0
                        live.update(make_panel())
                    elif key in ('?', 'h', 'H'):
                        _show_help_panel([
                            ("\u2191 / \u2193", "Navigate list"),
                            ("Enter", "Select item"),
                            ("d", "Toggle details panel"),
                            ("Esc", "Go back / Clear filter"),
                            ("/", "Filter results by text"),
                            ("s", "Cycle sort order"),
                            ("g / G", "Go to first / last"),
                        ], "Navigation Help")
                        live.update(make_panel())
                    elif key == KEY_ENTER:
                        if mapped_order and selected_idx < len(mapped_order):
                            return mapped_order[selected_idx], options[mapped_order[selected_idx]]
                        return -1, None
                    elif key in (KEY_ESC, KEY_CTRL_C):
                        if filter_text:
                            filter_text = ""
                            _rebuild_order()
                            _update_right_cache()
                            selected_idx = 0
                            live.update(make_panel())
                        else:
                            return -1, None
                    elif key in ('g', 'G'):
                        if display:
                            _anim_old_scroll = scroll_offset
                            _anim_start = time.monotonic()
                            _anim_active = True
                            selected_idx = 0 if key == 'g' else len(display) - 1
                        live.update(make_panel())
                    elif key == KEY_UNKNOWN:
                        pass
                    else:
                        if display:
                            selected_idx = (selected_idx + 1) % len(display)
                        live.update(make_panel())
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()


def interactive_checklist(options, title="Select Episodes", default_start_idx=0, is_favorite=False, on_toggle_favorite=None,
                          context_type=None, metadata=None,
                          player_name=None, active_player=None, pref_player=None, icons=None,
                          preselected_indices=None):
    if not options:
        return []

    flush_input_buffer()
    selected_idx = default_start_idx
    scroll_offset = 0
    _, term_height = shutil.get_terminal_size()
    max_visible = max(5, min(20, term_height - 12))
    checked = [False] * len(options)
    if preselected_indices:
        for idx in preselected_indices:
            if 0 <= idx < len(options):
                checked[idx] = True
    PAGE_SIZE = 50
    _notify = ""
    _input_active = False
    _input_buf = ""
    if len(checked) > 0 and not any(checked):
        checked[selected_idx] = True

    _right_panel_cache = {}
    _last_size = None
    _show_details = False

    if sys.stdout.isatty():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    def _scroll_to(idx):
        nonlocal scroll_offset
        selected_idx = max(0, min(idx, len(options) - 1))
        if selected_idx < scroll_offset:
            scroll_offset = selected_idx
        elif selected_idx >= scroll_offset + max_visible:
            scroll_offset = selected_idx - max_visible + 1
        return selected_idx

    _anim_old_scroll = 0
    _anim_start = 0.0
    _ANIM_DURATION = 0.3
    _anim_active = False

    try:
        def make_panel():
            nonlocal scroll_offset, _notify, _input_active, _input_buf
            nonlocal _right_panel_cache, _last_size, _show_details
            nonlocal _anim_old_scroll, _anim_start, _anim_active
            if selected_idx < scroll_offset:
                scroll_offset = selected_idx
            elif selected_idx >= scroll_offset + max_visible:
                scroll_offset = selected_idx - max_visible + 1

            current_size = shutil.get_terminal_size()
            if _last_size != (current_size.columns, current_size.lines):
                _last_size = (current_size.columns, current_size.lines)
                _right_panel_cache.clear()

            width, height = current_size.columns, current_size.lines
            mode = detect_layout_mode(width, height)

            render_scroll = scroll_offset
            if _anim_active:
                elapsed = time.monotonic() - _anim_start
                if elapsed >= _ANIM_DURATION:
                    _anim_active = False
                else:
                    progress = elapsed / _ANIM_DURATION
                    eased = 1.0 - (1.0 - progress) ** 3
                    render_scroll = int(round(_anim_old_scroll + (scroll_offset - _anim_old_scroll) * eased))

            table = Table(box=None, show_header=False, pad_edge=False)

            if render_scroll > 0:
                table.add_row(f"[dim {THEME['dim']}]  {get_icon('arrow_up')}more items above[/dim {THEME['dim']}]")
            else:
                table.add_row("")

            visible_options = options[render_scroll : render_scroll + max_visible]
            for idx_rel, opt in enumerate(visible_options):
                idx_abs = render_scroll + idx_rel
                box = get_icon("check") if checked[idx_abs] else get_icon("cross")
                color = THEME["checked"] if checked[idx_abs] else THEME["unchecked"]
                opt_text = f"{box}{opt}"

                if idx_abs == selected_idx:
                    table.add_row(f"[bold {THEME['primary']}]{get_icon('bullet')}[/bold {THEME['primary']}] [bold {THEME['select_fg']} on {THEME['select_bg']}]{opt_text}[/bold {THEME['select_fg']} on {THEME['select_bg']}]")
                else:
                    table.add_row(f"  [{color}]{opt_text}[/{color}]")

            if render_scroll + max_visible < len(options):
                table.add_row(f"[dim {THEME['dim']}]  {get_icon('arrow_down')}more items below[/dim {THEME['dim']}]")
            else:
                table.add_row("")

            if _input_active:
                buf_text = escape(_input_buf) if _input_buf else ""
                table.add_row(f"  [{THEME['accent']}]Jump: {buf_text}\u2588[/{THEME['accent']}]")

            if _notify:
                table.add_row(f"[bold {THEME['warning']}]  {_notify}[/bold {THEME['warning']}]")
                _notify = ""
            table.add_row("")

            sel_count = sum(checked)
            total_pages = (len(options) + PAGE_SIZE - 1) // PAGE_SIZE
            current_page = selected_idx // PAGE_SIZE + 1
            page_info = f"(p.{current_page}/{total_pages} ep.{selected_idx + 1}/{len(options)}) [{sel_count} selected]"

            fav_icon = f" [bold {THEME['error']}]{get_icon('favorite_on')}[/bold {THEME['error']}]" if is_favorite else f" [{THEME['dim']}]{get_icon('favorite_off')}[/{THEME['dim']}]"

            drag_label = "[bold yellow]\u25b6 drag[/bold yellow]" if _in_drag() else "SPACE+\u2195=drag"
            player_info = ""
            if player_name and active_player:
                player_info = f" | {icons.get('check', '')} {player_name} ({active_player})" if icons else f" | {player_name}"
            subtitle = f"SPACE=toggle  {drag_label}  d=Details  A=all  F=fav  J=jump  []=page  Enter=confirm  Esc=back{player_info}"

            left_panel = Panel(
                table,
                title=f"[bold {THEME['primary']}] {title}{fav_icon}[/bold {THEME['primary']}] [dim]{APP_VERSION}[/dim]",
                subtitle=f"[{THEME['fg']}]{subtitle}  {page_info}[/{THEME['fg']}]",
                border_style=THEME['border'],
                box=rich_box.ROUNDED,
                expand=True,
                padding=(1, 2)
            )

            show_right = context_type and _show_details and mode != "MINIMAL" and width >= 80
            if show_right:
                if selected_idx not in _right_panel_cache:
                    _right_panel_cache[selected_idx] = get_context_panel(context_type, selected_idx, options, metadata)
                right_panel = _right_panel_cache[selected_idx]
                grid = Table.grid(expand=True)
                grid.add_column(ratio=40)
                grid.add_column(ratio=60)
                grid.add_row(left_panel, right_panel)
                return Align(grid, align="center", vertical="middle", height=current_size.lines)

            return Align(Align.center(left_panel), align="center", vertical="middle", height=current_size.lines)

        _last_drag_time = 0.0
        _DRAG_WINDOW = 0.5

        def _in_drag():
            return time.time() - _last_drag_time < _DRAG_WINDOW

        with RawModeContext():
            with Live(None, refresh_per_second=20, transient=False) as live:
                live.update(make_panel())
                while True:
                    key = read_key()

                    # ── Input mode (jump-to-episode) ───────────
                    if _input_active:
                        if key == KEY_ENTER:
                            _input_active = False
                            buf = _input_buf
                            _input_buf = ""
                            if buf:
                                try:
                                    ep_num = int(buf) - 1
                                    if 0 <= ep_num < len(options):
                                        selected_idx = ep_num
                                    else:
                                        _notify = f"Episode {buf} out of range (1-{len(options)})"
                                except ValueError:
                                    _notify = f"Invalid: '{buf}'"
                        elif key in (KEY_ESC, KEY_CTRL_C):
                            _input_active = False
                            _input_buf = ""
                        elif key in ('\x08', '\x7f'):
                            _input_buf = _input_buf[:-1]
                        elif isinstance(key, str) and key.isdigit():
                            _input_buf += key
                        live.update(make_panel())
                        continue

                    now = time.time()
                    is_dragging = _in_drag()

                    if key == KEY_UP:
                        _anim_old_scroll = scroll_offset
                        _anim_start = time.monotonic()
                        _anim_active = True
                        selected_idx = (selected_idx - 1) % len(options)
                        if is_dragging:
                            checked[selected_idx] = not checked[selected_idx]
                            _last_drag_time = now
                        live.update(make_panel())
                    elif key == KEY_DOWN:
                        _anim_old_scroll = scroll_offset
                        _anim_start = time.monotonic()
                        _anim_active = True
                        selected_idx = (selected_idx + 1) % len(options)
                        if is_dragging:
                            checked[selected_idx] = not checked[selected_idx]
                            _last_drag_time = now
                        live.update(make_panel())
                    elif key in ('d', 'D'):
                        if context_type:
                            _show_details = not _show_details
                            live.update(make_panel())
                    elif key == KEY_SPACE:
                        checked[selected_idx] = not checked[selected_idx]
                        _last_drag_time = now
                        live.update(make_panel())
                    elif key == KEY_A:
                        all_checked = all(checked)
                        checked = [not all_checked] * len(options)
                        live.update(make_panel())
                    elif key in ('f', 'F'):
                        if on_toggle_favorite:
                            is_favorite = on_toggle_favorite()
                            live.update(make_panel())
                    elif key == '[':
                        _anim_old_scroll = scroll_offset
                        _anim_start = time.monotonic()
                        _anim_active = True
                        selected_idx = max(0, selected_idx - PAGE_SIZE)
                        live.update(make_panel())
                    elif key == ']':
                        _anim_old_scroll = scroll_offset
                        _anim_start = time.monotonic()
                        _anim_active = True
                        selected_idx = min(len(options) - 1, selected_idx + PAGE_SIZE)
                        live.update(make_panel())
                    elif key in ('g', 'G'):
                        _anim_old_scroll = scroll_offset
                        _anim_start = time.monotonic()
                        _anim_active = True
                        selected_idx = 0 if key == 'g' else len(options) - 1
                        live.update(make_panel())
                    elif key in ('j', 'J'):
                        _input_active = True
                        _input_buf = ""
                        live.update(make_panel())
                    elif key in ('?', 'h', 'H'):
                        _show_help_panel([
                            ("\u2191 / \u2193", "Navigate list"),
                            ("d", "Toggle details panel"),
                            ("Space", "Toggle episode (hold then \u2191\u2193 = drag)"),
                            ("A", "Select / deselect all"),
                            ("F", "Toggle bookmark / favorite"),
                            ("J", "Jump to episode number"),
                            ("[ / ]", "Page up / down (50 episodes)"),
                            ("g / G", "Go to first / last"),
                            ("Enter", "Scrape & play selected"),
                            ("Esc", "Go back"),
                        ], "Episode Selection Help")
                        live.update(make_panel())
                    elif key == KEY_ENTER:
                        return [idx for idx, val in enumerate(checked) if val]
                    elif key in (KEY_ESC, KEY_CTRL_C):
                        return None
                    elif key == KEY_UNKNOWN:
                        pass
    finally:
        if sys.stdout.isatty():
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()


# ── State Machine Handlers ─────────────────────────────────

def _handle_main_menu(current, stack, ctx):
    platforms = [
        f"{get_icon('search')}Search Anime",
        f"{get_icon('direct_url')}Enter URL Directly",
        f"{get_icon('favorite_on')}Favorites / Library",
        f"{get_icon('settings')}Settings / Configuration",
        f"{get_icon('exit')}Exit"
    ]
    fav_count = 0
    try:
        conn = sqlite3.connect(get_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM favorites")
        fav_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"[pyanime] Warning: favorites count DB query failed: {e}")
    update_info = check_for_update(APP_VERSION)
    menu_metadata = {
        "pref_player": ctx["cfg"].get("preferred_player", "auto"),
        "default_quality": ctx["cfg"].get("default_quality", "auto"),
        "pref_browser": ctx["cfg"].get("preferred_browser", "auto"),
        "favorites_count": fav_count,
        "anilist_linked": get_account_token("anilist") is not None,
        "mal_linked": get_account_token("myanimelist") is not None,
        "update_info": update_info,
    }
    choice_idx, choice_opt = interactive_select(
        platforms, "Main Menu", context_type="main_menu", metadata=menu_metadata,
        player_name=ctx["player_name"], active_player=ctx["active_player"],
        pref_player=ctx["pref_player"], icons=ctx["layout_icons"]
    )
    if choice_idx == 4 or choice_idx == -1:
        return False
    if choice_idx == 0:
        stack.append({"state": "SEARCH_INPUT"})
    elif choice_idx == 1:
        stack.append({"state": "URL_INPUT"})
    elif choice_idx == 2:
        stack.append({"state": "FAVORITES"})
    elif choice_idx == 3:
        stack.append({"state": "SETTINGS"})
    return True


def _handle_search_input(current, stack, ctx):
    cfg = ctx["cfg"]
    search_hist = cfg.get("search_history", [])
    query = None
    if search_hist:
        hist_opts = ["[New Search Query]"] + search_hist
        sel_idx, sel_opt = interactive_select(hist_opts, "Recent Searches")
        if sel_idx == -1:
            stack.pop()
            return True
        if sel_idx == 0:
            query = _centered_prompt("Enter search query")
        else:
            query = sel_opt
    else:
        query = _centered_prompt("Enter search query")
    if not query:
        stack.pop()
        return True
    add_search_history(query)
    enabled = [i for i in cfg.get("enabled_sources", [0, 1]) if i <= 1]
    active_providers = [p for p in provider_registry.get_all() if p.provider_id in enabled]
    source_names = [p.provider_name for p in active_providers]
    with _centered_status(f"Searching {', '.join(source_names)}...", icon="search"):
        try:
            from src.providers import search_all_providers as _search_all
            from src.config import PROVIDER_IDS as _PID
            raw = _run_async(_search_all(query, enabled))
            search_results = []
            seen = set()
            for pid, items in raw.items():
                pname = _PID.get(pid, f"Provider {pid}")
                for item in items:
                    title = item.get("title", "?")
                    url = item.get("url", "")
                    key = (pid, url)
                    if key not in seen:
                        seen.add(key)
                        search_results.append({
                            "title": title,
                            "url": url,
                            "provider_id": pid,
                            "provider_name": pname,
                        })
        except KeyboardInterrupt:
            search_results = []
            print_warn("Search cancelled by user.")
            time.sleep(1.0)
    if not search_results:
        _centered_message("No search results found.", level="warn")
        return True
    stack.append({
        "state": "SEARCH_RESULTS",
        "query": query,
        "search_results": search_results,
    })
    return True


def _try_open_episodes(stack, anime_url, is_witanime, slug, title_text, came_from_search, active_cookies):
    with _centered_status("Loading episodes list...", icon="watch"):
        try:
            eps, err = _run_async(fetch_episodes_list_async(anime_url, is_witanime, active_cookies))
        except KeyboardInterrupt:
            eps, err = [], "Action cancelled."
        except Exception as exc:
                eps, err = [], str(exc)
    if err:
        hint = ""
        err_lower = err.lower()
        if "timeout" in err_lower or "connect" in err_lower or "connection" in err_lower:
            hint = " (check your internet connection or try again later)"
        elif "cloudflare" in err_lower or "just a moment" in err_lower:
            hint = " (site is behind Cloudflare — try disabling IPv6 or using a different network)"
        elif "404" in err_lower or "not found" in err_lower:
            hint = " (anime page not found — it may have been removed or the URL is incorrect)"
        _centered_message(f"Error fetching episodes: {err}{hint}", level="error")
        return False
    if not eps:
        _centered_message("No episodes found.", level="warn")
        return False
    metadata = fetch_anime_metadata(title_text)
    stack.append({
        "state": "EPISODE_SELECTION",
        "eps": eps, "slug": slug, "anime_url": anime_url,
        "is_witanime": is_witanime, "title": title_text,
        "came_from_search": came_from_search, "auto_play": False,
        "anime_metadata": metadata
    })
    return True


def _browse_platform_list(token, fetch_func, platform_name, stack):
    with _centered_status(f"Fetching {platform_name} watch list...", icon="watch"):
        media_list = fetch_func(token)
    if not media_list:
        _centered_message(f"No entries found on {platform_name}.", level="warn")
        return False
    options = [entry["title"] for entry in media_list]
    idx, opt = interactive_select(options, f"{platform_name} Watch List")
    if idx == -1:
        return False
    selected = media_list[idx]
    title = selected["title"]
    console.print(f"\n[bold {THEME['primary']}]Searching providers for '{title}'...[/bold {THEME['primary']}]")
    result = search_providers_for_media(title)
    if not result:
        _centered_message(f"Could not find '{title}' on any supported provider.", level="warn")
        return False
    display_title, anime_url, is_witanime = result
    slug = extract_slug(anime_url)
    if not slug:
        _centered_message("Could not extract slug from URL.", level="warn")
        return False
    active_cookies = get_preferred_cookies()
    _try_open_episodes(stack, anime_url, is_witanime, slug, display_title, True, active_cookies)
    return True


def _handle_search_results(current, stack, ctx):
    query = current["query"]
    search_results = current["search_results"]
    options = [f"[{r['provider_name']}] {r['title']}" for r in search_results]
    results_metadata = {"search_query": query, "search_entries": search_results}
    sel_idx, sel_opt = interactive_select(
        options, f"Results for '{query}'", context_type="search_results",
        metadata=results_metadata, player_name=ctx["player_name"],
        active_player=ctx["active_player"], pref_player=ctx["pref_player"],
        icons=ctx["layout_icons"]
    )
    if sel_idx == -1:
        stack.pop()
        return True
    selected = search_results[sel_idx]
    title_text = selected["title"]
    anime_url = selected["url"]
    is_witanime = selected["provider_id"]
    chosen_name = selected["provider_name"]

    slug = extract_slug(anime_url)
    if not slug:
        slug = anime_url.strip("/").split("/")[-1] if anime_url.strip("/") else None
    if not slug:
        _centered_message(f"Could not extract slug from URL: {anime_url}.", level="error")
        return True
    print_info(f"[{chosen_name}] Target: {slug}")
    with _centered_status("Syncing cookies from browser profiles...", icon="watch"):
        active_cookies = get_preferred_cookies()
    if active_cookies:
        print_ok(f"Synced {len(active_cookies)} cookies. Bypassing Turnstile.")
    else:
        print_warn("No cookies synced. Using clean session.")
    _try_open_episodes(stack, anime_url, is_witanime, slug, title_text, True, active_cookies)
    return True


def _handle_url_input(current, stack, ctx):
    anime_url = current.get("prefilled_url") or _centered_prompt("Enter Anime URL (or press Enter/Esc to go back)")
    if not anime_url:
        stack.pop()
        return True
    valid, err_msg = validate_url(anime_url)
    if not valid:
        _centered_message(f"Invalid URL: {err_msg}.", level="error")
        return True
    anime_url = anime_url.strip()
    p = urlparse(anime_url)
    is_witanime = 1 if "witanime" in p.netloc else 2 if "anitaku" in p.netloc or "gogoanime" in p.netloc or "anineko" in p.netloc else 0

    if 'search_param=animes' in p.query:
        from urllib.parse import parse_qs
        params = parse_qs(p.query)
        search_query = params.get('s', [None])[0]
        if search_query:
            print_info(f"Search URL detected \u2014 query: {search_query}")
            add_search_history(search_query)
            with _centered_status("Searching...", icon="search"):
                try:
                    cfg_s = load_config()
                    enabled = [i for i in cfg_s.get("enabled_sources", [0, 1]) if i <= 1]
                    from src.providers import search_all_providers as _search_all
                    from src.config import PROVIDER_IDS as _PID
                    raw = _run_async(_search_all(search_query, enabled))
                    search_results = []
                    seen = set()
                    for pid, items in raw.items():
                        pname = _PID.get(pid, f"Provider {pid}")
                        for item in items:
                            title = item.get("title", "?")
                            url = item.get("url", "")
                            key = (pid, url)
                            if key not in seen:
                                seen.add(key)
                                search_results.append({
                                    "title": title,
                                    "url": url,
                                    "provider_id": pid,
                                    "provider_name": pname,
                                })
                except KeyboardInterrupt:
                    search_results = []
                    print_warn("Search cancelled.")
                    time.sleep(1.0)
            if not search_results:
                _centered_message("No results found.", level="warn")
                return True
            stack.append({"state": "SEARCH_RESULTS", "query": search_query, "search_results": search_results})
            return True
        else:
            query = _centered_prompt("Enter search query")
            if not query:
                return True
            current["prefilled_url"] = anime_url.split('?')[0] + f'?search_param=animes&s={quote_plus(query)}'
            return _handle_url_input(current, stack, ctx)

    direct_ep = None
    slug = None

    m = re.search(r'/episode/(.+)-[\u0600-\u06FF]+-(\d+)(?:/|$)', p.path)
    if m:
        direct_ep = int(m.group(2))
        slug = m.group(1).rstrip('-')
    if direct_ep is None:
        m = re.search(r'/episode[-\s]?(\d+)(?:/|$)', p.path)
        if m:
            direct_ep = int(m.group(1))
    if direct_ep is None and '/episode/' in p.path:
        nums = re.findall(r'/(\d+)/', p.path + '/')
        if nums:
            direct_ep = int(nums[-1])

    if direct_ep is not None:
        if slug is None:
            path_parts = p.path.strip("/").split("/")
            for part in path_parts:
                if part and not re.match(r'^\d+$', part) and part != "episode" and part != "anime" and "episode" not in part.lower():
                    slug = part
                    break
            if not slug:
                slug = path_parts[-2] if len(path_parts) >= 2 else path_parts[-1]
        if not slug:
            _centered_message(f"Could not extract slug from URL: {anime_url}.", level="error")
            return True
        print_info(f"Direct episode URL detected \u2014 Episode {direct_ep}")
        with _centered_status("Syncing cookies...", icon="watch"):
            active_cookies = get_preferred_cookies()
        if active_cookies:
            print_ok(f"Synced {len(active_cookies)} cookies.")
        else:
            print_warn("No cookies synced. Using clean session.")
        title_text = slug.replace('-', ' ').title()
        metadata = fetch_anime_metadata(title_text)
        single_eps = [{"episode": direct_ep, "page_url": anime_url}]
        stack.append({
            "state": "EPISODE_SELECTION",
            "eps": single_eps, "slug": slug, "anime_url": anime_url,
            "is_witanime": is_witanime, "title": title_text,
            "came_from_search": False, "auto_play": True,
            "anime_metadata": metadata
        })
        return True

    slug = extract_slug(anime_url)
    if slug:
        print_info(f"Target Anime Slug: {slug}")
    with _centered_status("Syncing cookies from browser profiles...", icon="watch"):
        active_cookies = get_preferred_cookies()
    if active_cookies:
        print_ok(f"Synced {len(active_cookies)} cookies. Bypassing Turnstile.")
    else:
        print_warn("No cookies synced. Using clean session.")
    title_text = slug.replace('-', ' ').title()
    _try_open_episodes(stack, anime_url, is_witanime, slug, title_text, False, active_cookies)
    return True

    _centered_message(f"Could not recognize URL format: {anime_url}.", level="error")
    return True


def _handle_favorites(current, stack, ctx):
    db_path = get_db_path()
    favs = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT slug, title, url, is_witanime FROM favorites")
        for row in cursor.fetchall():
            favs.append({"slug": row[0], "title": row[1], "url": row[2], "is_witanime": int(row[3])})
        conn.close()
    except Exception as e:
        print(f"[pyanime] Warning: favorites DB query failed: {e}")
    if not favs:
        _centered_message("No favorites bookmarked yet.", level="warn")
        stack.pop()
        return True
    fav_slugs = [f["slug"] for f in favs]
    favorites_metadata = {"fav_slugs": fav_slugs}
    options = [f"{f['title']} ({get_provider_name(f.get('is_witanime', 0))})" for f in favs]
    sel_idx, sel_opt = interactive_select(
        options, "Bookmarked Anime", context_type="favorites", metadata=favorites_metadata,
        player_name=ctx["player_name"], active_player=ctx["active_player"],
        pref_player=ctx["pref_player"], icons=ctx["layout_icons"]
    )
    if sel_idx == -1:
        stack.pop()
        return True
    selected_fav = favs[sel_idx]
    anime_url = selected_fav["url"]
    is_witanime = int(selected_fav.get("is_witanime", 0))
    slug = selected_fav["slug"]
    print_info(f"Target Anime Slug: {slug}")
    with _centered_status("Syncing cookies...", icon="watch"):
        active_cookies = get_preferred_cookies()
    _try_open_episodes(stack, anime_url, is_witanime, slug, selected_fav["title"], False, active_cookies)
    return True


def _handle_settings(current, stack, ctx):
    cfg = ctx["cfg"]
    current_player = cfg.get("preferred_player", "auto")
    current_quality = cfg.get("default_quality", "auto")
    current_browser = cfg.get("preferred_browser", "auto")
    history_enabled = cfg.get("history_tracking", True)
    fullscreen_enabled = cfg.get("fullscreen", True)
    player_args = cfg.get("custom_player_args", "")
    vlc = ctx["vlc"]; mpv = ctx["mpv"]; iina = ctx["iina"]
    celluloid = ctx["celluloid"]; haruna = ctx["haruna"]

    while True:
        cat_opts = [
            "Player & Playback",
            "Search & Sources",
            "Data & Sync",
            "Appearance",
            "Download Manager (Offline Preparation)",
            "Config / Data Directory",
            "About pyanime",
            "Go Back"
        ]
        cat_idx, _ = interactive_select(cat_opts, "Settings",
            player_name=ctx["player_name"], active_player=ctx["active_player"],
            pref_player=ctx["pref_player"], icons=ctx["layout_icons"])
        if cat_idx == -1 or cat_idx == 7:
            stack.pop()
            return True

        if cat_idx == 0:
            _settings_player(cfg)
        elif cat_idx == 1:
            _settings_search_sources(cfg)
        elif cat_idx == 2:
            if _settings_data_sync(cfg, stack):
                return True
        elif cat_idx == 3:
            _settings_appearance(cfg)
        elif cat_idx == 4:
            stack.append({"state": "DOWNLOAD_MANAGER"})
            return True
        elif cat_idx == 5:
            _settings_config_dir(cfg)
        elif cat_idx == 6:
            _settings_about(ctx)

    return True


def _settings_player(cfg):
    from config import _config_cache
    history_enabled = cfg.get("history_tracking", True)
    fullscreen_enabled = cfg.get("fullscreen", False)
    player_args = cfg.get("custom_player_args", "")
    current_player = cfg.get("preferred_player", "auto")
    current_quality = cfg.get("default_quality", "auto")

    while True:
        opts = [
            f"Preferred Player       (Current: {current_player.upper()})",
            f"Default Video Quality  (Current: {current_quality.upper()})",
            f"Auto Fullscreen        (Current: {'ENABLED' if fullscreen_enabled else 'DISABLED'})",
            f"Custom Player Args     (Current: '{player_args if player_args else 'None'}')",
            "Go Back"
        ]
        sel_idx, sel_opt = interactive_select(opts, "Player & Playback")
        if sel_idx == -1 or sel_idx == 4:
            break
        if sel_idx == 0:
            players = ["auto", "vlc", "mpv", "iina", "celluloid", "haruna"]
            p_idx, p_opt = interactive_select(players, "Select Preferred Player")
            if p_idx != -1:
                cfg["preferred_player"] = p_opt
                save_config(cfg)
                invalidate_player_cfg()
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Preferred player set to: {p_opt.upper()}[/bold {THEME['success']}]")
                is_missing = False
                if p_opt == "mpv" and not find_mpv(): is_missing = True
                elif p_opt == "vlc" and not find_vlc(): is_missing = True
                elif p_opt == "iina" and not find_iina(): is_missing = True
                elif p_opt == "celluloid" and not find_celluloid(): is_missing = True
                elif p_opt == "haruna" and not find_haruna(): is_missing = True
                if is_missing:
                    console.print(f"\n[bold {THEME['warning']}]" + get_icon("warning") + f"{p_opt.upper()} is not installed on your system.[/bold {THEME['warning']}]")
                    c_idx, _ = interactive_select([f"Yes, install {p_opt.upper()} now", "No, install it manually later"], f"Would you like to install {p_opt.upper()}?")
                    if c_idx == 0:
                        install_player(p_opt)
                time.sleep(1.0)
        elif sel_idx == 1:
            qualities = ["auto", "1080p", "720p", "480p", "360p"]
            q_idx, q_opt = interactive_select(qualities, "Select Default Quality")
            if q_idx != -1:
                cfg["default_quality"] = q_opt
                save_config(cfg)
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Default quality set to: {q_opt.upper()}[/bold {THEME['success']}]")
                time.sleep(1.0)
        elif sel_idx == 2:
            cfg["fullscreen"] = not fullscreen_enabled
            save_config(cfg)
            invalidate_player_cfg()
            status_str = "ENABLED" if not fullscreen_enabled else "DISABLED"
            console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Auto Fullscreen set to: {status_str}[/bold {THEME['success']}]")
            time.sleep(1.0)
            fullscreen_enabled = cfg.get("fullscreen", False)
        elif sel_idx == 3:
            new_args = _centered_prompt("Enter custom player arguments (e.g. --fs --volume=80). Leave empty to clear.")
            if new_args is not None:
                cfg["custom_player_args"] = new_args.strip()
                save_config(cfg)
                invalidate_player_cfg()
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + "Custom player arguments updated![/bold {THEME['success']}]")
                time.sleep(1.0)
                player_args = cfg.get("custom_player_args", "")


def _settings_search_sources(cfg):
    while True:
        scrap_method = cfg.get("scraping_method", "auto")
        enabled = [i for i in cfg.get("enabled_sources", [0, 1]) if i <= 1]
        method_labels = {"auto": "Auto (httpx -> Playwright)", "playwright_only": "Playwright Only", "alternative_only": "httpx Only"}
        opts = [
            f"Search Sources         (Current: {len(enabled)}/3 enabled)",
            f"Scraping Method        (Current: {scrap_method.upper()})",
            "Clear Search History",
            "Go Back"
        ]
        sel_idx, _ = interactive_select(opts, "Search & Sources")
        if sel_idx == -1 or sel_idx == 3:
            break
        if sel_idx == 0:
            provider_options = [
                "[0] Anime3rb", "[1] WitAnime",
                "[2] Anineko - (x) Under Development",
            ]
            current_enabled = [i for i in cfg.get("enabled_sources", [0, 1]) if i <= 1]
            selected = interactive_checklist(
                provider_options, "Toggle Search Sources (space to toggle, Enter to confirm)",
                preselected_indices=current_enabled
            )
            if selected is not None:
                selected = [i for i in selected if i != 2]
                cfg["enabled_sources"] = selected
                save_config(cfg)
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Search sources updated ({len(selected)}/3 enabled)![/bold {THEME['success']}]")
                time.sleep(1.0)
        elif sel_idx == 1:
            methods = ["auto", "playwright_only", "alternative_only"]
            m_labels = {"auto": "Auto (httpx -> Playwright)", "playwright_only": "Playwright Only", "alternative_only": "httpx Only"}
            m_idx, m_opt = interactive_select([m_labels[m] for m in methods], "Select Scraping Method")
            if m_idx != -1:
                cfg["scraping_method"] = methods[m_idx]
                save_config(cfg)
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Scraping method set to: {m_labels[methods[m_idx]]}[/bold {THEME['success']}]")
                time.sleep(1.0)
        elif sel_idx == 2:
            cfg["search_history"] = []
            save_config(cfg)
            console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + "Search history cleared![/bold {THEME['success']}]")
            time.sleep(1.0)


def _settings_data_sync(cfg, stack):
    while True:
        history_enabled = cfg.get("history_tracking", True)
        current_browser = cfg.get("preferred_browser", "auto")
        opts = [
            f"Cookie Sync Browser    (Current: {current_browser.upper()})",
            f"History Tracking       (Current: {'ENABLED' if history_enabled else 'DISABLED'})",
            "Accounts Integration (AniList / MyAnimeList)",
            "Clear All Watch History & Bookmarks",
            "Export Watch History / Progress",
            "Go Back"
        ]
        sel_idx, sel_opt = interactive_select(opts, "Data & Sync")
        if sel_idx == -1 or sel_idx == 5:
            break
        if sel_idx == 0:
            browsers = ["auto", "chrome", "edge"]
            b_idx, b_opt = interactive_select(browsers, "Select Preferred Cookie Browser")
            if b_idx != -1:
                cfg["preferred_browser"] = b_opt
                save_config(cfg)
                console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Preferred browser for cookies set to: {b_opt.upper()}[/bold {THEME['success']}]")
                time.sleep(1.0)
        elif sel_idx == 1:
            cfg["history_tracking"] = not history_enabled
            save_config(cfg)
            status_str = "ENABLED" if not history_enabled else "DISABLED"
            console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Watch history tracking set to: {status_str}[/bold {THEME['success']}]")
            time.sleep(1.0)
        elif sel_idx == 2:
            while True:
                anilist_info = get_account_token("anilist")
                mal_info = get_account_token("myanimelist")
                al_linked = anilist_info is not None
                mal_linked = mal_info is not None
                al_s = f"[bold green]Linked[/bold green]" if al_linked else "[dim]Not Linked[/dim]"
                mal_s = f"[bold green]Linked[/bold green]" if mal_linked else "[dim]Not Linked[/dim]"
                acc_opts = [
                    f"Link AniList Account       (Status: {al_s})",
                    f"Link MyAnimeList Account   (Status: {mal_s})",
                    "Unlink AniList Account" if al_linked else "Unlink AniList Account (Disabled)",
                    "Unlink MyAnimeList Account" if mal_linked else "Unlink MyAnimeList Account (Disabled)",
                    "Browse AniList Watch List",
                    "Browse MyAnimeList Watch List",
                    "Go Back"
                ]
                sub_idx, _ = interactive_select(acc_opts, "Accounts Integration")
                if sub_idx == -1 or sub_idx == 6:
                    break
                if sub_idx == 0:
                    try:
                        link_anilist_flow()
                    except Exception:
                        _centered_message("AniList account linking is not yet implemented.\nCheck back in a future update.", "info")
                elif sub_idx == 1:
                    try:
                        link_myanimelist_flow()
                    except Exception:
                        _centered_message("MyAnimeList account linking is not yet implemented.\nCheck back in a future update.", "info")
                elif sub_idx == 2:
                    if al_linked:
                        remove_account("anilist")
                        console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + "Unlinked AniList account.[/bold {THEME['success']}]")
                        time.sleep(1.0)
                elif sub_idx == 3:
                    if mal_linked:
                        remove_account("myanimelist")
                        console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + "Unlinked MyAnimeList account.[/bold {THEME['success']}]")
                        time.sleep(1.0)
                elif sub_idx == 4:
                    if not al_linked:
                        _centered_message("AniList account not linked. Link it first.", level="warn")
                        continue
                    if _browse_platform_list(anilist_info["token"], fetch_anilist_user_list, "AniList", stack):
                        return True
                elif sub_idx == 5:
                    if not mal_linked:
                        _centered_message("MyAnimeList account not linked. Link it first.", level="warn")
                        continue
                    if _browse_platform_list(mal_info["token"], fetch_mal_user_list, "MyAnimeList", stack):
                        return True
        elif sel_idx == 3:
            try:
                conn = sqlite3.connect(get_db_path())
                cursor = conn.cursor()
                cursor.execute("DELETE FROM favorites")
                cursor.execute("DELETE FROM shows")
                cursor.execute("DELETE FROM watched_episodes")
                cursor.execute("DELETE FROM episode_progress")
                cursor.execute("DELETE FROM accounts")
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[pyanime] Warning: DB cleanup failed: {e}")
            cfg["history"] = {}
            cfg["favorites"] = []
            save_config(cfg)
            console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + "Watch history, bookmarks, and linked accounts cleared![/bold {THEME['success']}]")
            time.sleep(1.0)
        elif sel_idx == 4:
            _handle_export()
            break

    return False


def _settings_appearance(cfg):
    while True:
        use_nerd = cfg.get("nerd_fonts", False)
        opts = [
            f"Nerd Font Icons        (Current: {'ENABLED' if use_nerd else 'DISABLED'})",
            "Go Back"
        ]
        sel_idx, _ = interactive_select(opts, "Appearance")
        if sel_idx == -1 or sel_idx == 1:
            break
        if sel_idx == 0:
            cfg["nerd_fonts"] = not use_nerd
            save_config(cfg)
            status_str = "ENABLED" if not use_nerd else "DISABLED"
            console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Nerd Font Icons support set to: {status_str}[/bold {THEME['success']}]")
            time.sleep(1.0)


def _settings_config_dir(cfg):
    new_path = _centered_prompt(f"New config directory path (Current: {get_config_dir()}). Existing data will be moved automatically. Leave empty to keep current.")
    if new_path and new_path.strip():
        expanded = os.path.expanduser(new_path.strip())
        abs_path = os.path.abspath(expanded)
        if os.path.isdir(abs_path) or not os.path.exists(abs_path):
            old_dir = get_config_dir()
            if abs_path != old_dir:
                write_custom_config_dir(abs_path)
                os.makedirs(abs_path, exist_ok=True)
                old_cfg = os.path.join(old_dir, "config.json")
                new_cfg = os.path.join(abs_path, "config.json")
                if os.path.exists(old_cfg) and not os.path.exists(new_cfg):
                    try:
                        import shutil
                        shutil.move(old_cfg, new_cfg)
                    except Exception as e:
                        print(f"[pyanime] Warning: config migration failed: {e}")
                    old_db = os.path.join(old_dir, "pyanime.db")
                    new_db = os.path.join(abs_path, "pyanime.db")
                    if os.path.exists(old_db) and not os.path.exists(new_db):
                        try:
                            import shutil
                            shutil.move(old_db, new_db)
                        except Exception as e:
                            print(f"[pyanime] Warning: DB migration failed: {e}")
                        console.print(f"\n[bold {THEME['success']}]" + get_icon("check") + f"Config directory changed to: {abs_path}[/bold {THEME['success']}]")
        else:
            console.print(f"\n[bold {THEME['error']}]" + get_icon("cross") + f"Invalid path: '{abs_path}' is not a directory.[/bold {THEME['error']}]")
    else:
        console.print(f"\n[dim {THEME['dim']}]Config directory unchanged.[/dim {THEME['dim']}]")
    time.sleep(1.5)


def _settings_about(ctx):
    players = get_cached_players()
    vlc_ok = players.get("vlc") is not None
    mpv_ok = players.get("mpv") is not None
    iina_ok = players.get("iina") is not None
    celluloid_ok = players.get("celluloid") is not None
    haruna_ok = players.get("haruna") is not None

    _ = os.name
    anilist_token = get_account_token("anilist")
    mal_token = get_account_token("myanimelist")

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("Key", style=f"bold {THEME['fg']}")
    table.add_column("Val", style=THEME['success'])

    table.add_row("Version", f"pyanime {APP_VERSION}")
    table.add_row("Config Path", get_config_dir())
    table.add_row("DB Path", get_db_path())
    table.add_row("Active Player", f"{ctx['player_name']} ({ctx['active_player'] or 'None'})")
    table.add_row("Theme", THEME.get('name', 'Catppuccin Mocha'))
    table.add_row("MPV", "[green]Installed[/green]" if mpv_ok else "[red]Not Found[/red]")
    table.add_row("VLC", "[green]Installed[/green]" if vlc_ok else "[red]Not Found[/red]")
    if sys.platform == "darwin":
        table.add_row("IINA", "[green]Installed[/green]" if iina_ok else "[red]Not Found[/red]")
    else:
        table.add_row("Celluloid", "[green]Installed[/green]" if celluloid_ok else "[red]Not Found[/red]")
        table.add_row("Haruna", "[green]Installed[/green]" if haruna_ok else "[red]Not Found[/red]")
    table.add_row("AniList", "[green]Linked[/green]" if anilist_token else "[dim]Not Linked[/dim]")
    table.add_row("MyAnimeList", "[green]Linked[/green]" if mal_token else "[dim]Not Linked[/dim]")
    table.add_row("Platform", sys.platform)
    table.add_row("Python", sys.version.split()[0])

    panel = Panel(
        Group(
            Text("pyanime", style=f"bold {THEME['primary']}", justify="center"),
            Text("Anime Streaming Terminal CLI", style=f"{THEME['fg']}", justify="center"),
            Text(""),
            table,
        ),
        title="[bold] About pyanime [/bold]",
        border_style=THEME['border'],
        box=rich_box.ROUNDED,
        padding=(1, 2),
    )
    console.clear()
    console.print(panel)
    console.print(f"\n[{THEME['dim']}]Press any key to go back...[/{THEME['dim']}]")
    read_key()


def _handle_episode_selection(current, stack, ctx):
    eps = current["eps"]
    slug = current["slug"]
    anime_url = current["anime_url"]
    is_witanime = current["is_witanime"]
    anime_title = current.get("title", slug)
    active_player = ctx["active_player"]
    player_name = ctx["player_name"]
    pref_player = ctx["pref_player"]
    vlc = ctx["vlc"]; mpv = ctx["mpv"]; iina = ctx["iina"]
    celluloid = ctx["celluloid"]; haruna = ctx["haruna"]

    history_data = get_watch_history(slug, provider=is_witanime)
    last_watched = history_data.get("last_watched", 0)
    watched_list = history_data.get("watched", [])
    last_watched_idx = next((i for i, x in enumerate(eps) if x['episode'] == last_watched), -1)
    default_idx = 0
    if last_watched_idx != -1:
        default_idx = last_watched_idx + 1 if last_watched_idx + 1 < len(eps) else last_watched_idx
    progress_data = get_all_episode_progress(slug)
    ep_options = []
    for x in eps:
        ep_num = x['episode']
        prog = progress_data.get(ep_num)
        bar_str = ""
        if prog and prog.get("duration", 0) > 0:
            pct = prog["time_pos"] / prog["duration"]
            pct = min(max(pct, 0), 1)
            filled = int(pct * 10)
            empty = 10 - filled
            bar_str = f" [dim {THEME['dim']}][[/dim {THEME['dim']}]{'█' * filled}{'░' * empty}[dim {THEME['dim']}]][/dim {THEME['dim']}] [bold {THEME['accent']}]{int(pct * 100)}%[/bold {THEME['accent']}]"
        if ep_num in watched_list:
            ep_options.append(f"Episode {ep_num}{bar_str} [dim {THEME['dim']}](watched {get_icon('check').strip()})[/dim {THEME['dim']}]")
        else:
            ep_options.append(f"Episode {ep_num}{bar_str}")
    fav_status = is_favorite_slug(slug)

    def on_toggle_fav():
        return toggle_favorite_state(anime_title, anime_url, is_witanime, slug)

    if current.get("auto_play", False) and len(eps) == 1:
        selected_indices = [0]
    else:
        ep_metadata = {
            "anime_title": anime_title,
            "provider": get_provider_name(is_witanime),
            "player_name": player_name,
            "anime_metadata": current.get("anime_metadata")
        }
        selected_indices = interactive_checklist(
            ep_options, title=f"Select episodes ({slug})",
            default_start_idx=default_idx, is_favorite=fav_status,
            on_toggle_favorite=on_toggle_fav, context_type="episode_selection",
            metadata=ep_metadata, player_name=player_name,
            active_player=active_player, pref_player=pref_player,
            icons=ctx["layout_icons"]
        )
    if not selected_indices:
        stack.pop()
        return True

    eps_to_scrape = [eps[i] for i in selected_indices]
    ep_numbers = [ep["episode"] for ep in eps_to_scrape]

    uncached = []
    cached_urls = {}
    for ep in eps_to_scrape:
        ep_num = ep["episode"]
        cached = get_cached_stream_url(slug, ep_num, provider=is_witanime)
        if cached:
            cached_urls[ep_num] = cached["stream_url"]
        else:
            uncached.append(ep)

    if cached_urls:
        console.print(f"[{THEME['success']}]{get_icon('check')} {len(cached_urls)} episode(s) loaded from stream cache.[/{THEME['success']}]")

    if uncached:
        console.print(f"[bold {THEME['primary']}]{get_icon('watch_history')}Scraping stream URLs for {len(uncached)} episodes...[/bold {THEME['primary']}]")
        active_cookies = get_preferred_cookies()
        try:
            results = _run_async(scrape_multiple_streams_async(uncached, is_witanime, active_cookies))
        except KeyboardInterrupt:
            _centered_message("Scraping cancelled by user.", level="warn")
            return True
        except Exception as exc:
            _centered_message(f"Scraping engine error: {exc}.", level="error")
            return True
        for ep in uncached:
            ep_num = ep["episode"]
            u_str = results.get(ep_num)
            if u_str:
                cache_stream_url(slug, ep_num, u_str, provider=is_witanime)
                cached_urls[ep_num] = u_str

    stream_urls = []
    for ep in eps_to_scrape:
        ep_num = ep["episode"]
        u_str = cached_urls.get(ep_num)
        if u_str:
            stream_urls.append(u_str)
    if not stream_urls:
        _centered_message("No stream URLs resolved (site may be blocking playback or episodes may be expired).", level="error")
        return True

    if not active_player:
        target_to_install = pref_player if pref_player in ("mpv", "vlc", "iina", "celluloid", "haruna") else "mpv"
        console.print(f"\n[bold {THEME['warning']}]{get_icon('warning')}Preferred player {target_to_install.upper()} is not installed on your system.[/bold {THEME['warning']}]")
        console.print(f"[bold {THEME['primary']}]{get_icon('watch_history')}Automatically downloading and installing {target_to_install.upper()} now...[/bold {THEME['primary']}]")
        time.sleep(1.0)
        success_install = install_player(target_to_install)
        if success_install:
            clear_player_cache()
            nv = find_vlc(); nm = find_mpv(); ni = find_iina()
            nc = find_celluloid(); nh = find_haruna()
            if target_to_install == "mpv" and nm: active_player, player_name = nm, "MPV"
            elif target_to_install == "vlc" and nv: active_player, player_name = nv, "VLC"
            elif target_to_install == "iina" and ni: active_player, player_name = ni, "IINA"
            elif target_to_install == "celluloid" and nc: active_player, player_name = nc, "Celluloid"
            elif target_to_install == "haruna" and nh: active_player, player_name = nh, "Haruna"
        if not active_player:
            for p_name, find_func, display_name in [
                ("mpv", find_mpv, "MPV"), ("vlc", find_vlc, "VLC"),
                ("iina", find_iina, "IINA"), ("celluloid", find_celluloid, "Celluloid"),
                ("haruna", find_haruna, "Haruna"),
            ]:
                p_path = find_func()
                if p_path:
                    console.print(f"\n[bold {THEME['warning']}]{get_icon('warning')}{target_to_install.upper()} installation failed. Falling back to {display_name}.[/bold {THEME['warning']}]")
                    active_player = p_path
                    player_name = display_name
                    time.sleep(2.0)
                    break
        if not active_player:
            default_fallback = "mpv"
            if sys.platform == "darwin":
                default_fallback = "iina"
            console.print(f"\n[bold {THEME['primary']}]{get_icon('watch_history')}Trying to install {default_fallback.upper()} as fallback...[/bold {THEME['primary']}]")
            if install_player(default_fallback):
                nv = find_vlc(); nm = find_mpv(); ni = find_iina()
                nc = find_celluloid(); nh = find_haruna()
                p_path = find_iina() if default_fallback == "iina" else find_mpv()
                if p_path:
                    active_player = p_path
                    player_name = default_fallback.upper()
        if not active_player:
            console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Player installation failed and no fallback player is available.[/bold {THEME['error']}]")
            choice = ["Show Streaming Links Only", "Go Back"]
            c_idx, _ = interactive_select(choice, "How would you like to proceed?")
            if c_idx == 1 or c_idx == -1:
                return True

    track_info = dict(TRACK_DEFAULTS)
    if active_player:
        console.print(f"\n[{THEME['dim']}]Press [bold]T[/bold] for tracks, [bold]D[/bold] to queue for download, or [bold]Enter[/bold] to play...[/{THEME['dim']}]")
        key = read_key()
        if key in ('t', 'T'):
            result = _show_track_selector(track_info)
            if result is not None:
                track_info = result
        elif key in ('d', 'D'):
            for ep in eps_to_scrape:
                ep_num = ep["episode"]
                u_str = cached_urls.get(ep_num)
                if u_str:
                    add_download_entry(slug, ep_num, u_str)
            _centered_message(f"{len(eps_to_scrape)} episode(s) queued for download.\nAccess 'Download Manager' in Settings to manage.", level="ok")
            return True
        elif key in (KEY_ESC, KEY_CTRL_C):
            return True

        print_hotkey_guide(player_name)
        track_args = []
        if player_name == "MPV":
            if track_info["audio_id"] is not None:
                track_args.append(f"--aid={track_info['audio_id']}")
            if track_info["sub_id"] is not None:
                track_args.append(f"--sid={track_info['sub_id']}")
            else:
                track_args.append("--sid=no")
        elif player_name == "VLC":
            if track_info["audio_id"] is not None:
                track_args.append(f":audio-track={track_info['audio_id']}")
            if track_info["sub_id"] is not None:
                track_args.append(f":sub-track={track_info['sub_id']}")
        console.print(f"\n[bold {THEME['success']}]{get_icon('play')}Launching {player_name} with {len(stream_urls)} stream(s)...[/bold {THEME['success']}]")
        if player_name == "MPV":
            launch_success = play_with_mpv(stream_urls, slug=slug, ep=eps_to_scrape[0]["episode"], extra_args=track_args)
        elif player_name == "VLC":
            launch_success = play_with_vlc(stream_urls)
        elif player_name == "IINA":
            launch_success = play_with_iina(stream_urls)
        elif player_name == "Celluloid":
            launch_success = play_with_celluloid(stream_urls)
        elif player_name == "Haruna":
            launch_success = play_with_haruna(stream_urls)
        if launch_success:
            for ep_num in ep_numbers:
                add_watch_history(slug, ep_num, anime_title, provider=is_witanime)
            console.print(f"[bold {THEME['success']}]{get_icon('check')}Playback started! {len(stream_urls)} episode(s) queued in {player_name}.[/bold {THEME['success']}]")
        else:
            console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Failed to launch {player_name}. Showing links instead:[/bold {THEME['error']}]")
            for i, s_url in enumerate(stream_urls):
                console.print(f"  [bold {THEME['fg']}]{i + 1}.[/bold {THEME['fg']}] [{THEME['accent']}]{s_url}[/{THEME['accent']}]")
    else:
        console.print(f"\n[bold {THEME['primary']}]\u2550\u2550\u2550 Streaming Links \u2550\u2550\u2550[/bold {THEME['primary']}]")
        for i, s_url in enumerate(stream_urls):
            console.print(f"  [bold {THEME['fg']}]{i + 1}.[/bold {THEME['fg']}] [{THEME['accent']}]{s_url}[/{THEME['accent']}]")

    _centered_message("Done. Returning to episode selection.", level="info")
    return True


def _handle_export():
    formats = ["JSON (.json)", "CSV (.csv)"]
    f_idx, f_opt = interactive_select(formats, "Export Format")
    if f_idx == -1:
        return

    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT slug, last_watched FROM shows ORDER BY slug")
        shows = cursor.fetchall()

        cursor.execute("SELECT slug, episode FROM watched_episodes ORDER BY slug, episode")
        watched = cursor.fetchall()

        cursor.execute("SELECT slug, episode, time_pos, duration FROM episode_progress ORDER BY slug, episode")
        progress = cursor.fetchall()

        conn.close()
    except Exception as e:
        _centered_message(f"Database read error: {e}", level="error")
        return

    data = {
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": APP_VERSION,
        "shows": {slug: {"last_watched": lw} for slug, lw in shows},
        "watched_episodes": {slug: [] for slug, _ in shows},
        "episode_progress": {},
    }

    for slug, ep in watched:
        data["watched_episodes"].setdefault(slug, []).append(ep)

    for slug, ep, tp, dur in progress:
        data["episode_progress"].setdefault(slug, []).append({"episode": ep, "time_pos": tp, "duration": dur})

    export_dir = get_config_dir()
    ts = time.strftime("%Y%m%d_%H%M%S")
    if f_idx == 0:
        fpath = os.path.join(export_dir, f"pyanime_export_{ts}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _centered_message(f"Exported to: {fpath}", level="ok")
        return
    else:
        import csv
        fpath = os.path.join(export_dir, f"pyanime_export_{ts}.csv")
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["slug", "field", "episode", "value"])
            for slug, lw in shows:
                writer.writerow([slug, "last_watched", "", lw])
            for slug, ep in watched:
                writer.writerow([slug, "watched", ep, ""])
            for slug, ep, tp, dur in progress:
                writer.writerow([slug, "progress", ep, f"{tp}/{dur}"])
        _centered_message(f"Exported to: {fpath}", level="ok")


def _handle_download_manager(current, stack, ctx):
    downloads = get_downloads()
    if not downloads:
        _centered_message("No downloads queued yet. Select episodes and choose 'Download' to add them.", level="warn")
        stack.pop()
        return True

    options = []
    for d in downloads:
        status_icon = get_icon("check") if d["status"] == "completed" else (get_icon("watch_history") if d["status"] == "downloading" else get_icon("cross"))
        options.append(f"Ep {d['episode']} ({d['slug']}) [{status_icon} {d['status']}]")

    idx, opt = interactive_select(options, "Download Manager")
    if idx == -1:
        stack.pop()
        return True

    selected = downloads[idx]
    if selected["status"] == "completed":
        console.print(f"\n[bold {THEME['success']}]{get_icon('check')}Already downloaded: {selected.get('file_path', 'unknown')}[/bold {THEME['success']}]")
        console.print(f"[{THEME['dim']}]Stream URL: {selected['stream_url']}[/{THEME['dim']}]")
    else:
        console.print(f"\n[bold {THEME['primary']}]Episode {selected['episode']} \u2014 Status: {selected['status']}[/bold {THEME['primary']}]")
        console.print(f"[{THEME['dim']}]Stream URL: {selected['stream_url']}[/{THEME['dim']}]")
        remove = _centered_prompt("Remove this download entry? (y/N)")
        if remove and remove.lower() == 'y':
            remove_download_entry(selected["slug"], selected["episode"])
            print_ok("Download entry removed.")

    _centered_message("Done.", level="info")
    return True


_STATE_HANDLERS = {
    "MAIN_MENU": _handle_main_menu,
    "SEARCH_INPUT": _handle_search_input,
    "SEARCH_RESULTS": _handle_search_results,
    "URL_INPUT": _handle_url_input,
    "FAVORITES": _handle_favorites,
    "SETTINGS": _handle_settings,
    "EPISODE_SELECTION": _handle_episode_selection,
    "DOWNLOAD_MANAGER": _handle_download_manager,
}


# ── Main Application ───────────────────────────────────────

def run_app(initial_url=None, player_override=None, quality_override=None):
    stack = [{"state": "MAIN_MENU"}]
    if initial_url:
        valid, err_msg = validate_url(initial_url)
        if valid:
            stack.append({"state": "URL_INPUT", "prefilled_url": initial_url})
        else:
            console.print(f"[bold red]Invalid URL: {err_msg}[/bold red]")

    while stack:
        cfg = load_config()
        pref_player = player_override or cfg.get("preferred_player", "auto")
        if quality_override:
            cfg["default_quality"] = quality_override

        players = get_cached_players()
        vlc = players.get("vlc"); mpv = players.get("mpv")
        iina = players.get("iina"); celluloid = players.get("celluloid"); haruna = players.get("haruna")

        active_player = None
        player_name = "None"
        if pref_player == "vlc" and vlc: active_player, player_name = vlc, "VLC"
        elif pref_player == "mpv" and mpv: active_player, player_name = mpv, "MPV"
        elif pref_player == "iina" and iina: active_player, player_name = iina, "IINA"
        elif pref_player == "celluloid" and celluloid: active_player, player_name = celluloid, "Celluloid"
        elif pref_player == "haruna" and haruna: active_player, player_name = haruna, "Haruna"
        else:
            if mpv: active_player, player_name = mpv, "MPV"
            elif vlc: active_player, player_name = vlc, "VLC"
            elif iina: active_player, player_name = iina, "IINA"
            elif celluloid: active_player, player_name = celluloid, "Celluloid"
            elif haruna: active_player, player_name = haruna, "Haruna"

        clear_screen()
        layout_icons = {
            "sparkle": get_icon('sparkle'),
            "check": get_icon('check'),
            "warning": get_icon('warning'),
        }

        current = stack[-1]
        state = current["state"]

        title_map = {
            "MAIN_MENU": "Anime CLI Player",
            "SEARCH_INPUT": "Search Input",
            "SEARCH_RESULTS": f"Search Results: {current.get('query', '')}",
            "URL_INPUT": "Direct URL Input",
            "FAVORITES": "Favorites Library",
            "SETTINGS": "Configuration Settings",
            "EPISODE_SELECTION": f"Episodes: {current.get('slug', '')}",
            "PLAYBACK": f"Playing: {current.get('slug', '')}",
        }
        set_terminal_title(title_map.get(state, "Anime CLI Player"))

        try:
            handler = _STATE_HANDLERS.get(state)
            if handler is not None:
                ctx = {
                    "cfg": cfg, "players": players,
                    "active_player": active_player, "player_name": player_name,
                    "pref_player": pref_player, "layout_icons": layout_icons,
                    "vlc": vlc, "mpv": mpv, "iina": iina,
                    "celluloid": celluloid, "haruna": haruna,
                }
                if not handler(current, stack, ctx):
                    break
        except KeyboardInterrupt:
            if len(stack) > 1:
                stack.pop()
            else:
                break
        except Exception as exc:
            console.print(f"\n[bold {THEME['error']}]{get_icon('cross')}Unexpected error: {exc}[/bold {THEME['error']}]")
            import traceback
            traceback.print_exc()
            console.print(f"[{THEME['dim']}]Press any key to continue...[/{THEME['dim']}]")
            read_key()
            if len(stack) > 1:
                stack.pop()
            else:
                break
