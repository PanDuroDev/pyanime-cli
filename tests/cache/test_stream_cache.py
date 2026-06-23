import os
import sqlite3
import time
import pytest


@pytest.fixture
def in_memory_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stream_cache (
            slug TEXT,
            episode INTEGER,
            stream_url TEXT,
            fetched_at REAL,
            quality TEXT DEFAULT '',
            PRIMARY KEY (slug, episode)
        )
    """)
    conn.commit()

    original_cwd = os.getcwd()

    def mock_cache_stream_url(slug, episode, stream_url, quality="", provider=0):
        slug_key = f"{slug}_{provider}"
        cursor.execute(
            "INSERT OR REPLACE INTO stream_cache (slug, episode, stream_url, fetched_at, quality) VALUES (?, ?, ?, ?, ?)",
            (slug_key, episode, stream_url, time.time(), quality)
        )
        conn.commit()

    def mock_get_cached_stream_url(slug, episode, provider=0, max_age_hours=24):
        slug_key = f"{slug}_{provider}"
        cursor.execute(
            "SELECT stream_url, fetched_at, quality FROM stream_cache WHERE slug = ? AND episode = ?",
            (slug_key, episode)
        )
        row = cursor.fetchone()
        if row:
            fetched_at = row[1]
            if time.time() - fetched_at < max_age_hours * 3600:
                return {"stream_url": row[0], "quality": row[2]}
        return None

    def mock_clear_stream_cache(slug=None, max_age_hours=24):
        if slug:
            cursor.execute("DELETE FROM stream_cache WHERE slug = ? AND fetched_at < ?",
                          (slug, time.time() - max_age_hours * 3600))
        else:
            cursor.execute("DELETE FROM stream_cache WHERE fetched_at < ?",
                          (time.time() - max_age_hours * 3600,))
        conn.commit()

    return {
        "conn": conn,
        "cursor": cursor,
        "cache_stream_url": mock_cache_stream_url,
        "get_cached_stream_url": mock_get_cached_stream_url,
        "clear_stream_cache": mock_clear_stream_cache,
    }


class TestStreamCacheSetAndGet:
    def test_cache_set_and_retrieve(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://stream.example/playlist.m3u8", quality="1080p")
        result = api["get_cached_stream_url"]("naruto", 1)
        assert result is not None
        assert result["stream_url"] == "https://stream.example/playlist.m3u8"
        assert result["quality"] == "1080p"

    def test_cache_different_episodes(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/ep1.m3u8")
        api["cache_stream_url"]("naruto", 2, "https://example.com/ep2.m3u8")
        r1 = api["get_cached_stream_url"]("naruto", 1)
        r2 = api["get_cached_stream_url"]("naruto", 2)
        assert r1["stream_url"] == "https://example.com/ep1.m3u8"
        assert r2["stream_url"] == "https://example.com/ep2.m3u8"

    def test_cache_different_shows(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/naruto.m3u8")
        api["cache_stream_url"]("one-piece", 1, "https://example.com/onepiece.m3u8")
        naruto = api["get_cached_stream_url"]("naruto", 1)
        onepiece = api["get_cached_stream_url"]("one-piece", 1)
        assert naruto["stream_url"] != onepiece["stream_url"]

    def test_cache_provider_scoping(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://provider0.example/stream", provider=0)
        api["cache_stream_url"]("naruto", 1, "https://provider1.example/stream", provider=1)
        r0 = api["get_cached_stream_url"]("naruto", 1, provider=0)
        r1 = api["get_cached_stream_url"]("naruto", 1, provider=1)
        assert r0["stream_url"] != r1["stream_url"]


class TestStreamCacheMiss:
    def test_cache_miss_returns_none(self, in_memory_db):
        api = in_memory_db
        result = api["get_cached_stream_url"]("nonexistent", 1)
        assert result is None

    def test_cache_miss_wrong_episode(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/stream")
        result = api["get_cached_stream_url"]("naruto", 2)
        assert result is None

    def test_cache_miss_wrong_slug(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/stream")
        result = api["get_cached_stream_url"]("one-piece", 1)
        assert result is None


class TestStreamCacheExpiration:
    def test_cache_expires_after_max_age(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/stream")
        result = api["get_cached_stream_url"]("naruto", 1, max_age_hours=0)
        assert result is None

    def test_cache_valid_within_max_age(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/stream")
        result = api["get_cached_stream_url"]("naruto", 1, max_age_hours=24)
        assert result is not None

    def test_cache_default_max_age(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/stream")
        result = api["get_cached_stream_url"]("naruto", 1)
        assert result is not None


class TestStreamCacheClear:
    def test_clear_all_cache(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/naruto.m3u8")
        api["cache_stream_url"]("one-piece", 1, "https://example.com/onepiece.m3u8")
        api["clear_stream_cache"](max_age_hours=-1)
        r1 = api["get_cached_stream_url"]("naruto", 1)
        r2 = api["get_cached_stream_url"]("one-piece", 1)
        assert r1 is None
        assert r2 is None

    def test_clear_cache_by_slug(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/naruto.m3u8")
        api["cache_stream_url"]("one-piece", 1, "https://example.com/onepiece.m3u8")
        api["clear_stream_cache"](slug="naruto_0", max_age_hours=-1)
        r1 = api["get_cached_stream_url"]("naruto", 1)
        r2 = api["get_cached_stream_url"]("one-piece", 1)
        assert r1 is None
        assert r2 is not None

    def test_clear_cache_only_old_entries(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/old.m3u8")
        time.sleep(0.01)
        api["cache_stream_url"]("naruto", 2, "https://example.com/new.m3u8")
        api["clear_stream_cache"](max_age_hours=0)
        r1 = api["get_cached_stream_url"]("naruto", 1, max_age_hours=0)
        r2 = api["get_cached_stream_url"]("naruto", 2, max_age_hours=0)
        assert r1 is None
        assert r2 is None


class TestStreamCacheUpdate:
    def test_cache_update_overwrites(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/old.m3u8")
        api["cache_stream_url"]("naruto", 1, "https://example.com/new.m3u8")
        result = api["get_cached_stream_url"]("naruto", 1)
        assert result["stream_url"] == "https://example.com/new.m3u8"

    def test_cache_update_refreshes_timestamp(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "https://example.com/old.m3u8")
        time.sleep(0.01)
        api["cache_stream_url"]("naruto", 1, "https://example.com/new.m3u8")
        result = api["get_cached_stream_url"]("naruto", 1, max_age_hours=0)
        assert result is None


class TestStreamCacheEdgeCases:
    def test_cache_empty_string_url(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("naruto", 1, "")
        result = api["get_cached_stream_url"]("naruto", 1)
        assert result is not None
        assert result["stream_url"] == ""

    def test_cache_special_chars_in_slug(self, in_memory_db):
        api = in_memory_db
        api["cache_stream_url"]("shingeki-no-kyojin", 1, "https://example.com/aot.m3u8")
        result = api["get_cached_stream_url"]("shingeki-no-kyojin", 1)
        assert result is not None

    def test_cache_special_chars_in_url(self, in_memory_db):
        api = in_memory_db
        url = "https://example.com/stream?token=abc123&expires=9999999999"
        api["cache_stream_url"]("naruto", 1, url)
        result = api["get_cached_stream_url"]("naruto", 1)
        assert result is not None
        assert result["stream_url"] == url

    def test_cache_many_entries(self, in_memory_db):
        api = in_memory_db
        for i in range(100):
            api["cache_stream_url"]("naruto", i, f"https://example.com/ep{i}.m3u8")
        for i in range(100):
            result = api["get_cached_stream_url"]("naruto", i)
            assert result is not None
            assert f"/ep{i}.m3u8" in result["stream_url"]
