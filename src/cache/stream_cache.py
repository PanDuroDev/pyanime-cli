"""
Stream cache implementation — SQLite-backed storage for resolved stream URLs.
"""

import os
import sqlite3
import time

from config import get_config_dir

# Bump this when URL format changes to invalidate all old caches
CACHE_VERSION = 2


def _cache_key(slug, provider):
    return f"{slug}_{provider}_v{CACHE_VERSION}"


def cache_stream_url(slug, episode, stream_url, quality="", provider=0):
    slug_key = _cache_key(slug, provider)
    db_path = os.path.join(get_config_dir(), "pyanime.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO stream_cache (slug, episode, stream_url, fetched_at, quality) VALUES (?, ?, ?, ?, ?)",
            (slug_key, episode, stream_url, time.time(), quality)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_cached_stream_url(slug, episode, provider=0, max_age_hours=24):
    slug_key = _cache_key(slug, provider)
    db_path = os.path.join(get_config_dir(), "pyanime.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stream_url, fetched_at, quality FROM stream_cache WHERE slug = ? AND episode = ?",
            (slug_key, episode)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            fetched_at = row[1]
            if time.time() - fetched_at < max_age_hours * 3600:
                return {"stream_url": row[0], "quality": row[2]}
    except Exception:
        pass
    return None


def clear_stream_cache(slug=None, max_age_hours=24):
    db_path = os.path.join(get_config_dir(), "pyanime.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if slug:
            cursor.execute("DELETE FROM stream_cache WHERE slug = ? AND fetched_at < ?", (slug, time.time() - max_age_hours * 3600))
        else:
            cursor.execute("DELETE FROM stream_cache WHERE fetched_at < ?", (time.time() - max_age_hours * 3600))
        conn.commit()
        conn.close()
    except Exception:
        pass
