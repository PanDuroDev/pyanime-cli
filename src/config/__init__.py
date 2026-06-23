"""
Configuration management for pyanime.
Handles config file paths, read/write, caching, theme, and icon helpers.
"""

import json
import os

import httpx
from rich.console import Console
from rich import box as rich_box

console = Console()

_http_client = None
def get_http_client():
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=15.0, follow_redirects=True)
    return _http_client

APP_VERSION = "1.0.0"

THEME = {
    "fg": "#E2E8F0",
    "dim": "#7C8BA1",
    "border": "#6C63FF",
    "primary": "#A78BFA",
    "accent": "#C084FC",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "error": "#FB7185",
    "select_bg": "#312E81",
    "select_fg": "#E0E7FF",
    "checked": "#4ADE80",
    "unchecked": "#475569",
    "gradient1": "#C084FC",
    "gradient2": "#818CF8",
    "gradient3": "#6366F1",
    "gradient4": "#4F46E5",
    "gradient5": "#4338CA",
    "separator": "#1E293B",
    "box": rich_box.ROUNDED,
    "box_simple": rich_box.SIMPLE,
    "box_minimal": rich_box.MINIMAL,
}

_config_cache = None
_nerd_fonts_enabled = False


def get_config_path_pointer():
    return os.path.join(os.path.expanduser("~"), ".pyanime_config_path")


def read_custom_config_dir():
    ptr = get_config_path_pointer()
    try:
        with open(ptr, "r", encoding="utf-8") as f:
            path = f.read().strip()
            if path and os.path.isabs(path):
                return path
    except Exception:
        pass
    return None


def write_custom_config_dir(path):
    ptr = get_config_path_pointer()
    try:
        with open(ptr, "w", encoding="utf-8") as f:
            f.write(path.strip())
    except Exception:
        pass


def get_default_config_dir():
    home = os.path.expanduser("~")
    if os.name == 'nt':
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "pyanime")
        else:
            return os.path.join(home, ".config", "pyanime")
    else:
        return os.path.join(home, ".config", "pyanime")


def get_config_dir():
    custom = read_custom_config_dir()
    if custom:
        os.makedirs(custom, exist_ok=True)
        return custom
    path = get_default_config_dir()
    os.makedirs(path, exist_ok=True)
    return path


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def load_config():
    global _config_cache, _nerd_fonts_enabled
    if _config_cache is not None:
        return _config_cache
    p = get_config_path()
    default_cfg = {
        "preferred_player": "auto",
        "default_quality": "auto",
        "preferred_browser": "auto",
        "history_tracking": True,
        "fullscreen": True,
        "custom_player_args": "",
        "nerd_fonts": False,
        "scraping_method": "auto",
        "enabled_sources": [0, 1],
        "search_history": [],
        "favorites": [],
        "history": {}
    }
    if not os.path.exists(p):
        _config_cache = default_cfg
        _nerd_fonts_enabled = default_cfg["nerd_fonts"]
        return _config_cache
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k, v in default_cfg.items():
                if k not in cfg:
                    cfg[k] = v
            _config_cache = cfg
            _nerd_fonts_enabled = cfg.get("nerd_fonts", False)
            return _config_cache
    except Exception:
        _config_cache = default_cfg
        _nerd_fonts_enabled = default_cfg["nerd_fonts"]
        return _config_cache


def save_config(cfg):
    global _config_cache, _nerd_fonts_enabled
    _config_cache = cfg
    _nerd_fonts_enabled = cfg.get("nerd_fonts", False)
    p = get_config_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[pyanime] Warning: could not save config: {e}")


def add_search_history(query):
    cfg = load_config()
    hist = cfg.get("search_history", [])
    if query in hist:
        hist.remove(query)
    hist.insert(0, query)
    cfg["search_history"] = hist[:5]
    save_config(cfg)


def get_icon(name):
    use_nerd = _nerd_fonts_enabled
    nerd_icons = {
        "search": " ",
        "favorite_on": " ",
        "favorite_off": " ",
        "direct_url": " ",
        "settings": " ",
        "exit": " ",
        "play": " ",
        "watch_history": " ",
        "check": " ",
        "cross": " ",
        "warning": " ",
        "info": " ",
        "bullet": " ",
        "arrow_up": " ",
        "arrow_down": " ",
        "folder": " ",
        "sparkle": "✦ "
    }
    unicode_icons = {
        "search": "⚲ ",
        "favorite_on": "★ ",
        "favorite_off": "☆ ",
        "direct_url": "🔗 ",
        "settings": "⚙ ",
        "exit": "⏻ ",
        "play": "▶ ",
        "watch_history": "⏳ ",
        "check": "✔ ",
        "cross": "✘ ",
        "warning": "⚠ ",
        "info": "ℹ ",
        "bullet": "❯ ",
        "arrow_up": "▲ ",
        "arrow_down": "▼ ",
        "folder": "📁 ",
        "sparkle": "✦ "
    }
    return nerd_icons[name] if use_nerd else unicode_icons[name]


PROVIDER_IDS = {
    0: "Anime3rb",
    1: "WitAnime",
    2: "Anineko",
}

def get_provider_name(val):
    return PROVIDER_IDS.get(int(val), "Unknown")

def get_provider_id(name):
    for k, v in PROVIDER_IDS.items():
        if v == name:
            return k
    return 0
