"""
Database infrastructure for pyanime — favorites, watch history, accounts, progress.
"""

import json
import os
import re
import sqlite3
import threading
import time

import httpx

from config import get_config_dir, get_config_path, load_config, get_http_client


def get_db_path():
    return os.path.join(get_config_dir(), "pyanime.db")


def init_db():
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                slug TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                is_witanime INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shows (
                slug TEXT PRIMARY KEY,
                last_watched INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watched_episodes (
                slug TEXT,
                episode INTEGER,
                PRIMARY KEY (slug, episode)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                slug TEXT,
                episode INTEGER,
                stream_url TEXT,
                quality TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                file_path TEXT DEFAULT '',
                added_at REAL,
                downloaded_at REAL,
                PRIMARY KEY (slug, episode)
            )
        """)
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episode_progress (
                slug TEXT,
                episode INTEGER,
                time_pos REAL,
                duration REAL,
                PRIMARY KEY (slug, episode)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                platform TEXT PRIMARY KEY,
                token TEXT,
                client_id TEXT,
                refresh_token TEXT,
                expires_at REAL
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[pyanime] Warning: DB init failed: {e}")


def migrate_json_to_sqlite():
    p = get_config_path()
    if not os.path.exists(p):
        return
    try:
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        migrated = False
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if "favorites" in cfg and cfg["favorites"]:
            for fav in cfg["favorites"]:
                slug = fav.get("slug")
                title = fav.get("title")
                url = fav.get("url")
                is_witanime = int(fav.get("is_witanime", 0))
                if slug:
                    cursor.execute(
                        "INSERT OR IGNORE INTO favorites (slug, title, url, is_witanime) VALUES (?, ?, ?, ?)",
                        (slug, title, url, is_witanime)
                    )
            del cfg["favorites"]
            migrated = True

        if "history" in cfg and cfg["history"]:
            for slug, hist_item in cfg["history"].items():
                last_watched = hist_item.get("last_watched", 0)
                cursor.execute(
                    "INSERT OR REPLACE INTO shows (slug, last_watched) VALUES (?, ?)",
                    (slug, last_watched)
                )
                watched = hist_item.get("watched", [])
                for ep in watched:
                    cursor.execute(
                        "INSERT OR IGNORE INTO watched_episodes (slug, episode) VALUES (?, ?)",
                        (slug, ep)
                    )
            del cfg["history"]
            migrated = True

        if migrated:
            conn.commit()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
        conn.close()
    except Exception as e:
        print(f"[pyanime] Warning: config migration failed: {e}")


def save_episode_progress(slug, ep, time_pos, duration):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO episode_progress (slug, episode, time_pos, duration) VALUES (?, ?, ?, ?)",
            (slug, ep, time_pos, duration)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_episode_progress(slug, ep):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT time_pos, duration FROM episode_progress WHERE slug = ? AND episode = ?",
            (slug, ep)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"time_pos": row[0], "duration": row[1]}
    except Exception:
        pass
    return None


def toggle_favorite_state(title, url, is_witanime, slug):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE slug = ?", (slug,))
        exists = cursor.fetchone() is not None
        if exists:
            cursor.execute("DELETE FROM favorites WHERE slug = ?", (slug,))
            ret = False
        else:
            cursor.execute(
                "INSERT INTO favorites (slug, title, url, is_witanime) VALUES (?, ?, ?, ?)",
                (slug, title, url, int(is_witanime))
            )
            ret = True
        conn.commit()
        conn.close()
        return ret
    except Exception:
        return False


def is_favorite_slug(slug):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM favorites WHERE slug = ?", (slug,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except Exception:
        return False


def get_all_episode_progress(slug):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT episode, time_pos, duration FROM episode_progress WHERE slug = ?",
            (slug,)
        )
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"time_pos": r[1], "duration": r[2]} for r in rows}
    except Exception:
        return {}


def add_download_entry(slug, episode, stream_url, quality=""):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO downloads (slug, episode, stream_url, quality, status, added_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (slug, episode, stream_url, quality, time.time())
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_downloads(slug=None):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if slug:
            cursor.execute(
                "SELECT slug, episode, stream_url, quality, status, file_path, added_at, downloaded_at FROM downloads WHERE slug = ? ORDER BY episode",
                (slug,)
            )
        else:
            cursor.execute(
                "SELECT slug, episode, stream_url, quality, status, file_path, added_at, downloaded_at FROM downloads ORDER BY added_at DESC"
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "slug": r[0], "episode": r[1], "stream_url": r[2],
                "quality": r[3], "status": r[4], "file_path": r[5],
                "added_at": r[6], "downloaded_at": r[7]
            }
            for r in rows
        ]
    except Exception:
        return []


def remove_download_entry(slug, episode):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM downloads WHERE slug = ? AND episode = ?", (slug, episode))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def update_download_status(slug, episode, status, file_path=""):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE downloads SET status = ?, file_path = ?, downloaded_at = ? WHERE slug = ? AND episode = ?",
            (status, file_path, time.time() if status == "completed" else None, slug, episode)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def add_watch_history(slug, episode_num, anime_title=None, provider=0):
    cfg = load_config()
    if not cfg.get("history_tracking", True):
        return
    slug_key = f"{slug}_{provider}"
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO shows (slug, last_watched) VALUES (?, ?)", (slug_key, episode_num))
        cursor.execute("INSERT OR IGNORE INTO watched_episodes (slug, episode) VALUES (?, ?)", (slug_key, episode_num))
        conn.commit()
        conn.close()
    except Exception:
        pass

    sync_watch_progress_bg(slug, anime_title, episode_num)


def get_watch_history(slug, provider=0):
    slug_key = f"{slug}_{provider}"
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT last_watched FROM shows WHERE slug = ?", (slug_key,))
        row = cursor.fetchone()
        last_watched = row[0] if row else 0

        cursor.execute("SELECT episode FROM watched_episodes WHERE slug = ?", (slug_key,))
        watched = [r[0] for r in cursor.fetchall()]
        conn.close()
        return {"last_watched": last_watched, "watched": watched}
    except Exception:
        return {"last_watched": 0, "watched": []}


def save_account_token(platform, token, client_id=None, refresh_token=None, expires_in=None):
    db_path = get_db_path()
    expires_at = time.time() + expires_in if expires_in else None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO accounts (platform, token, client_id, refresh_token, expires_at) VALUES (?, ?, ?, ?, ?)",
            (platform, token, client_id, refresh_token, expires_at)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_account_token(platform):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT token, client_id, refresh_token, expires_at FROM accounts WHERE platform = ?", (platform,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "token": row[0],
                "client_id": row[1],
                "refresh_token": row[2],
                "expires_at": row[3]
            }
    except Exception:
        pass
    return None


def remove_account(platform):
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE platform = ?", (platform,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def refresh_mal_token(client_id, refresh_token):
    token_url = "https://myanimelist.net/v1/oauth2/token"
    payload = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    try:
        response = get_http_client().post(token_url, data=payload)
        if response.status_code == 200:
            data = response.json()
            access_token = data["access_token"]
            new_refresh = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 2419200)
            save_account_token("myanimelist", access_token, client_id, new_refresh, expires_in)
            return access_token
    except Exception:
        pass
    return None


def clean_slug_for_search(slug):
    cleaned = slug.lower()
    cleaned = re.sub(r'-(?:sub|dub|arabic|season|ep|episode|uncut|tv).*$', '', cleaned)
    cleaned = cleaned.replace('-', ' ').strip()
    return cleaned


def sync_to_anilist(token, anime_title, episode_num):
    url = "https://graphql.anilist.co"
    query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        id
        title {
          romaji
          english
          native
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    try:
        response = get_http_client().post(url, json={"query": query, "variables": {"search": anime_title}}, headers=headers)
        if response.status_code != 200:
            return False, f"HTTP Error {response.status_code}"
        data = response.json()
        media = data.get("data", {}).get("Media")
        if not media:
            return False, "Anime not found on AniList"
        media_id = media["id"]

        mutation = """
        mutation ($mediaId: Int, $progress: Int, $status: MediaListStatus) {
          SaveMediaListEntry (mediaId: $mediaId, progress: $progress, status: $status) {
            id
            progress
            status
          }
        }
        """
        variables = {
            "mediaId": media_id,
            "progress": episode_num,
            "status": "CURRENT"
        }
        resp2 = get_http_client().post(url, json={"query": mutation, "variables": variables}, headers=headers)
        if resp2.status_code != 200:
            return False, f"Mutation Error {resp2.status_code}"
        return True, "Success"
    except Exception as e:
        return False, str(e)


def sync_to_myanimelist(token, anime_title, episode_num):
    headers = {
        "Authorization": f"Bearer {token}"
    }
    try:
        search_url = "https://api.myanimelist.net/v2/anime"
        params = {"q": anime_title, "limit": 1}
        response = get_http_client().get(search_url, params=params, headers=headers)
        if response.status_code != 200:
            return False, f"Search HTTP Error {response.status_code}"
        data = response.json()
        nodes = data.get("data", [])
        if not nodes:
            return False, "Anime not found on MyAnimeList"
        anime_id = nodes[0]["node"]["id"]

        update_url = f"https://api.myanimelist.net/v2/anime/{anime_id}/my_list_status"
        payload = {
            "status": "watching",
            "num_watched_episodes": episode_num
        }
        resp2 = get_http_client().put(update_url, data=payload, headers=headers)
        if resp2.status_code != 200:
            return False, f"Update HTTP Error {resp2.status_code}"
        return True, "Success"
    except Exception as e:
        return False, str(e)


def sync_watch_progress_bg(slug, anime_title, episode_num):
    def worker():
        anilist_acc = get_account_token("anilist")
        if anilist_acc:
            token = anilist_acc["token"]
            search_term = clean_slug_for_search(slug)
            success, msg = sync_to_anilist(token, search_term, episode_num)
            if not success and anime_title:
                sync_to_anilist(token, anime_title, episode_num)

        mal_acc = get_account_token("myanimelist")
        if mal_acc:
            token = mal_acc["token"]
            client_id = mal_acc["client_id"]
            refresh_token = mal_acc["refresh_token"]
            expires_at = mal_acc["expires_at"]

            if expires_at and time.time() > expires_at:
                if client_id and refresh_token:
                    new_token = refresh_mal_token(client_id, refresh_token)
                    if new_token:
                        token = new_token

            search_term = clean_slug_for_search(slug)
            success, msg = sync_to_myanimelist(token, search_term, episode_num)
            if not success and anime_title:
                sync_to_myanimelist(token, anime_title, episode_num)

    threading.Thread(target=worker, daemon=True).start()


_metadata_cache = {}

def fetch_anime_metadata(search_term):
    key = search_term.lower().strip()
    if key in _metadata_cache:
        return _metadata_cache[key]

    url = "https://graphql.anilist.co"
    query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        id
        title { romaji english native }
        description
        genres
        averageScore
        episodes
        studios { nodes { name } }
        season
        seasonYear
        status
        format
        coverImage { large }
      }
    }
    """
    try:
        response = get_http_client().post(url, json={"query": query, "variables": {"search": search_term}})
        if response.status_code != 200:
            _metadata_cache[key] = None
            return None
        data = response.json()
        media = data.get("data", {}).get("Media")
        if not media:
            _metadata_cache[key] = None
            return None

        studios = [s["name"] for s in media.get("studios", {}).get("nodes", []) if s.get("name")]

        result = {
            "synopsis": media.get("description"),
            "genres": media.get("genres", []),
            "average_score": media.get("averageScore"),
            "episodes": media.get("episodes"),
            "studios": studios,
            "season": media.get("season"),
            "season_year": media.get("seasonYear"),
            "status": media.get("status"),
            "format": media.get("format"),
            "cover_image": media.get("coverImage", {}).get("large"),
            "title_romaji": media.get("title", {}).get("romaji"),
            "title_english": media.get("title", {}).get("english"),
        }
        _metadata_cache[key] = result
        return result
    except Exception:
        _metadata_cache[key] = None
        return None


def fetch_anilist_user_list(token, status_filter=None):
    url = "https://graphql.anilist.co"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    viewer_query = """
    query { Viewer { id name } }
    """
    try:
        resp = get_http_client().post(url, json={"query": viewer_query}, headers=headers)
        if resp.status_code != 200:
            return []
        viewer_data = resp.json()
        user_id = viewer_data.get("data", {}).get("Viewer", {}).get("id")
        if not user_id:
            return []
    except Exception:
        return []

    list_query = """
    query ($userId: Int, $type: MediaType) {
      MediaListCollection(userId: $userId, type: $type) {
        lists {
          entries {
            media {
              id
              title { romaji english }
              coverImage { large }
            }
            progress
            status
          }
        }
      }
    }
    """
    try:
        resp = get_http_client().post(url, json={
            "query": list_query,
            "variables": {"userId": user_id, "type": "ANIME"}
        }, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
        lists = data.get("data", {}).get("MediaListCollection", {}).get("lists", [])
        results = []
        for lst in lists:
            for entry in lst.get("entries", []):
                media = entry.get("media", {})
                title = media.get("title", {})
                display_title = title.get("english") or title.get("romaji") or "Unknown"
                status = entry.get("status")
                if status_filter and status != status_filter:
                    continue
                results.append({
                    "title": display_title,
                    "media_id": media.get("id"),
                    "progress": entry.get("progress", 0),
                    "status": status,
                    "cover_url": media.get("coverImage", {}).get("large"),
                    "title_romaji": title.get("romaji"),
                })
        return results
    except Exception:
        return []


def fetch_mal_user_list(token, status_filter=None):
    headers = {
        "Authorization": f"Bearer {token}"
    }
    params = {
        "fields": "list_status,node{title,main_picture}",
        "limit": 1000
    }
    if status_filter:
        params["status"] = status_filter

    url = "https://api.myanimelist.net/v2/users/@me/animelist"
    try:
        resp = get_http_client().get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("data", []):
            node = item.get("node", {})
            list_status = item.get("list_status", {})
            results.append({
                "title": node.get("title", "Unknown"),
                "media_id": node.get("id"),
                "progress": list_status.get("num_episodes_watched", 0),
                "status": list_status.get("status"),
                "cover_url": node.get("main_picture", {}).get("large"),
                "title_romaji": None,
            })
        return results
    except Exception:
        return []
