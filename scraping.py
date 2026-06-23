"""
Web scraping, cookie extraction, and site interaction for pyanime.

Warning: This module is deprecated — prefer importing from src.providers instead.
"""
import warnings

warnings.warn(
    "scraping.py is deprecated; use 'from src.providers import ...' instead.",
    PendingDeprecationWarning,
    stacklevel=2,
)

import asyncio
import base64

_cookie_warn_count = {}
def _cookie_warn(msg):
    _cookie_warn_count[msg] = _cookie_warn_count.get(msg, 0) + 1
    if _cookie_warn_count[msg] <= 3:
        print(f"[pyanime] Warning: {msg}")
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import difflib
from urllib.parse import urlparse, quote_plus

import httpx
from bs4 import BeautifulSoup
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.live import Live

from config import get_config_dir, load_config, _config_cache, THEME, get_icon, console
from player import get_cached_players, play_with_vlc, play_with_mpv, play_with_iina, play_with_celluloid, play_with_haruna


# ─── Cookie Extraction ─────────────────────────────────────

def get_user_data_path(browser_name):
    home = os.path.expanduser("~")
    if os.name == 'nt':
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        if browser_name == "chrome":
            return os.path.join(local_app_data, r"Google\Chrome\User Data")
        elif browser_name == "edge":
            return os.path.join(local_app_data, r"Microsoft\Edge\User Data")
    elif sys.platform == "darwin":
        if browser_name == "chrome":
            return os.path.join(home, "Library/Application Support/Google/Chrome")
        elif browser_name == "edge":
            return os.path.join(home, "Library/Application Support/Microsoft Edge")
    else:
        if browser_name == "chrome":
            return os.path.join(home, ".config/google-chrome")
        elif browser_name == "edge":
            return os.path.join(home, ".config/microsoft-edge")
    return None


def get_macos_key(browser_name):
    service = "Chrome Safe Storage" if browser_name == "chrome" else "Microsoft Edge Safe Storage"
    try:
        cmd = ["security", "find-generic-password", "-w", "-s", service]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip().encode("utf-8")
    except Exception:
        try:
            import keyring
            key = keyring.get_password(service, "Chrome" if browser_name == "chrome" else "Microsoft Edge")
            if key:
                return key.encode("utf-8")
        except Exception as e:
            print(f"[pyanime] Warning: cookie query setup failed: {e}")
    return None


def get_linux_key(browser_name):
    service = "Chrome Safe Storage" if browser_name == "chrome" else "Microsoft Edge Safe Storage"
    account = "Chrome" if browser_name == "chrome" else "edge"
    try:
        cmd = ["secret-tool", "lookup", "service", service, "account", account]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            return result.stdout.strip().encode("utf-8")
    except Exception as e:
        print(f"[pyanime] Warning: cookie DB query failed: {e}")

    try:
        cmd = ["secret-tool", "lookup", "xdg:schema", "org.chromium.Chromium.SafeStorage", "password", "chrome" if browser_name == "chrome" else "edge"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            return result.stdout.strip().encode("utf-8")
    except Exception as e:
        print(f"[pyanime] Warning: cookie decryption failed: {e}")

    try:
        import keyring
        key = keyring.get_password(service, account)
        if key:
            return key.encode("utf-8")
    except Exception as e:
        print(f"[pyanime] Warning: cookie processing failed: {e}")

    return b"peanuts"


try:
    from Cryptodome.Cipher import AES as _AES
except ImportError:
    try:
        from Crypto.Cipher import AES as _AES
    except ImportError:
        _AES = None


def decrypt_cbc_cookie(encrypted_value, key):
    if not encrypted_value:
        return ""
    if not _AES:
        return ""
    if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
        ciphertext = encrypted_value[3:]
    else:
        ciphertext = encrypted_value

    try:
        cipher = _AES.new(key, _AES.MODE_CBC, iv=b' ' * 16)
        decrypted = cipher.decrypt(ciphertext)
        padding_len = decrypted[-1]
        if 1 <= padding_len <= 16:
            if all(x == padding_len for x in decrypted[-padding_len:]):
                decrypted = decrypted[:-padding_len]
        return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def get_browser_cookies(browser_name):
    user_data_path = get_user_data_path(browser_name)
    if not user_data_path or not os.path.exists(user_data_path):
        return []

    decrypted_key = None
    is_gcm = False

    if os.name == 'nt':
        local_state_path = os.path.join(user_data_path, "Local State")
        if os.path.exists(local_state_path):
            try:
                with open(local_state_path, "r", encoding="utf-8") as f:
                    local_state = json.loads(f.read())
                encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
                encrypted_key = encrypted_key[5:]
                try:
                    import win32crypt
                    decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                    is_gcm = True
                except ImportError:
                    win32crypt = None
            except Exception as e:
                print(f"[pyanime] Warning: local state decryption failed: {e}")
    elif sys.platform == "darwin":
        password = get_macos_key(browser_name)
        if password:
            import hashlib
            decrypted_key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)
            is_gcm = False
    else:
        password = get_linux_key(browser_name)
        if password:
            import hashlib
            decrypted_key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)
            is_gcm = False

    if not decrypted_key:
        return []

    cookies = {}
    profiles = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]

    try:
        for item in os.listdir(user_data_path):
            if (item.startswith("Profile") or item == "Default") and os.path.isdir(os.path.join(user_data_path, item)):
                if item not in profiles:
                    profiles.append(item)
    except Exception as e:
        print(f"[pyanime] Warning: Edge cookie extraction failed: {e}")

    try:
        import win32crypt
    except ImportError:
        win32crypt = None
    if not win32crypt:
        return list(cookies.values()) if cookies else []

    for profile in profiles:
        cookie_path = os.path.join(user_data_path, profile, "Network", "Cookies")
        if not os.path.exists(cookie_path):
            cookie_path = os.path.join(user_data_path, profile, "Cookies")
        if not os.path.exists(cookie_path):
            continue

        temp_cookie_file = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            temp_cookie_file = tmp.name
            tmp.close()
            shutil.copy2(cookie_path, temp_cookie_file)
        except Exception:
            continue

        try:
            conn = sqlite3.connect(temp_cookie_file)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, encrypted_value, host_key FROM cookies WHERE host_key LIKE '%anime3rb.com%' OR host_key LIKE '%vid3rb.com%' OR host_key LIKE '%witanime%' OR host_key LIKE '%anineko%' OR host_key LIKE '%gogoanime%' OR host_key LIKE '%hianime%' OR host_key LIKE '%9anime%'"
            )
            for name, encrypted_value, host_key in cursor.fetchall():
                try:
                    if is_gcm:
                        if encrypted_value[:3] == b'v10' or encrypted_value[:3] == b'v11':
                            nonce = encrypted_value[3:15]
                            ciphertext = encrypted_value[15:-16]
                            tag = encrypted_value[-16:]
                            cipher = _AES.new(decrypted_key, _AES.MODE_GCM, nonce=nonce)
                            value = cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
                        else:
                            if win32crypt:
                                value = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8")
                            else:
                                continue
                    else:
                        value = decrypt_cbc_cookie(encrypted_value, decrypted_key)

                    domain = host_key
                    if not domain.startswith("."):
                        domain = "." + domain

                    cookies[f"{domain}:{name}"] = {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/"
                    }
                except Exception as e:
                    _cookie_warn(f"cookie decrypt failed: {e}")
                    cookies.pop(f"{domain}:{name}", None)
            conn.close()
        except Exception as e:
            _cookie_warn(f"cookie profile failed: {e}")
        finally:
            if temp_cookie_file:
                try:
                    os.remove(temp_cookie_file)
                except Exception as e:
                    _cookie_warn(f"temp file cleanup failed: {e}")

    return list(cookies.values())


def get_preferred_cookies():
    cfg = load_config()
    pref = cfg.get("preferred_browser", "auto")
    if pref == "chrome":
        return get_browser_cookies("chrome")
    elif pref == "edge":
        return get_browser_cookies("edge")
    else:
        return get_browser_cookies("chrome") or get_browser_cookies("edge")


# ─── URL Helpers ────────────────────────────────────────────

def validate_url(url):
    if not url or not url.strip():
        return False, "URL is empty"
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https"):
        return False, "URL must start with http:// or https://"
    if not p.netloc:
        return False, "URL is missing a domain name"
    if (not p.path or p.path.strip("/") == "") and not p.query:
        return False, "URL is missing a path or query string"
    return True, ""


def extract_slug(url):
    p = urlparse(url)
    netloc = p.netloc.lower()
    path = p.path

    if "anime3rb" in netloc:
        m = re.search(r"/titles/([^/#?]+)", path)
        if m: return m.group(1)
    elif "witanime" in netloc:
        # Pattern 1: /anime/{slug}/
        m = re.search(r"/anime/([^/#?]+)", path)
        if m: return m.group(1)
        # Pattern 2: /episode/{slug}-الحلقة-{N}/
        m = re.search(r"/episode/(.+?)-[\u0600-\u06FF]+-\d+", path)
        if m: return m.group(1)
    elif "anitaku" in netloc or "gogoanime" in netloc or "anineko" in netloc:
        m = re.search(r"/watch/([^/#?]+)", path)
        if m:
            slug = m.group(1)
            slug = re.sub(r'/ep-\d+$', '', slug)
            return slug
    elif "hianime" in netloc:
        m = re.search(r"/watch/([^/#?]+)", path)
        if m: return m.group(1)
    elif "9anime" in netloc:
        m = re.search(r"/watch/([^/#?]+)", path)
        if m: return m.group(1)

    path_clean = p.path.strip("/")
    if path_clean:
        parts = path_clean.split("/")
        if parts:
            return parts[-1]
    return None


def normalize(href, base_url=None):
    if href.startswith("http"):
        return href
    if base_url:
        p = urlparse(base_url)
        scheme_netloc = f"{p.scheme}://{p.netloc}"
        if href.startswith("/"):
            return scheme_netloc + href
        else:
            return scheme_netloc + "/" + href
    return href


def select_best_stream(urls):
    if not urls:
        return None

    cfg = load_config()
    pref_quality = cfg.get("default_quality", "auto")

    if pref_quality != "auto":
        if pref_quality == "1080p":
            keywords = ["1080p", "1080", "fhd", "w1080p"]
        elif pref_quality == "720p":
            keywords = ["720p", "720", "hd"]
        elif pref_quality == "480p":
            keywords = ["480p", "480", "sd"]
        else:
            keywords = []

        for u in urls:
            if any(kw in u.lower() for kw in keywords):
                return u

    for u in urls:
        if "1080" in u.lower() or "fhd" in u.lower():
            return u
    for u in urls:
        if "master.txt" in u or "/master." in u:
            return u
    for u in urls:
        if ".m3u8" in u or any(p in u for p in ["/hls/", "/hls2/", "/hls3/", "/index.m3u8", "/playlist."]):
            return u
    for u in urls:
        if ".mp4" in u:
            return u
    return urls[0]


def _classify_stream_quality(stream_url):
    """Classify stream quality based on URL keywords."""
    u = stream_url.lower()
    if "1080p" in u or "fhd" in u or "w1080p" in u:
        return "FHD/1080p"
    if "720p" in u or "hd" in u:
        return "HD/720p"
    if "480p" in u or "sd" in u:
        return "SD/480p"
    return "Auto"


# ─── Search ─────────────────────────────────────────────────

async def search_anime3rb_async(query):
    query_enc = quote_plus(query)
    url = f"https://anime3rb.com/titles/list?q={query_enc}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
        if r.status_code != 200:
            return []
        if _is_cloudflare_challenge(r.text):
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        seen = set()
        query_lower = query.lower()
        query_words = set(query_lower.split())
        for a in soup.select("a[href*='/titles/']"):
            href = a["href"].strip()
            if "/titles/list" in href or href in seen:
                continue
            title_el = a.find("h4") or a.find("h2", class_="title-name") or a.find("h2")
            if title_el:
                title = title_el.text.strip()
            else:
                title = a.text.strip().replace("\n", " ")
            title = re.sub(r'\s+', ' ', title)
            if len(title) > 2:
                seen.add(href)
                title_lower = title.lower()
                score = 0
                if query_lower in title_lower:
                    score += 10
                for w in query_words:
                    if w in title_lower:
                        score += 3
                results.append((title, href, score))
        results.sort(key=lambda x: x[2], reverse=True)
        best_score = results[0][2] if results else 0
        if best_score >= 3:
            results = [r for r in results if r[2] > 0]
        return [(t, h) for t, h, s in results]
    except Exception:
        return []


async def search_witanime_async(query):
    query_enc = quote_plus(query)
    url = f"https://witanime.com/?search_param=animes&s={query_enc}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
        if r.status_code != 200:
            return []
        if _is_cloudflare_challenge(r.text):
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        seen = set()
        query_lower = query.lower()
        query_words = set(query_lower.split())
        for a in soup.select("a[href*='/anime/']"):
            href = a["href"].strip()
            if href in seen:
                continue
            title = a.text.strip().replace("\n", " ")
            title = re.sub(r'\s+', ' ', title)
            if len(title) > 2:
                seen.add(href)
                title_lower = title.lower()
                score = 0
                if query_lower in title_lower:
                    score += 10
                for w in query_words:
                    if w in title_lower:
                        score += 3
                results.append((title, href, score))
        results.sort(key=lambda x: x[2], reverse=True)
        best_score = results[0][2] if results else 0
        if best_score >= 3:
            results = [r for r in results if r[2] > 0]
        return [(t, h) for t, h, s in results]
    except Exception:
        return []


async def search_gogoanime_async(query):
    query_enc = quote_plus(query)
    url = f"https://anineko.to/browser?keyword={query_enc}"
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            m = re.match(r'^/watch/([^/]+)$', href)
            if m:
                title = a.text.strip().replace("\n", " ").replace("  ", " ").strip()
                title = re.sub(r'\s+', ' ', title)
                title = re.sub(r'^(TV|Movie|OVA|ONA|Special)\s*', '', title)
                title = re.sub(r'\s*CC\s*\d+\s*\d*$', '', title).strip()
                if title and title not in seen and len(title) > 2:
                    seen.add(title)
                    results.append((title, normalize(f"/watch/{m.group(1)}", base_url="https://anineko.to")))
        return results
    except Exception:
        return []


async def search_hianime_async(query):
    query_enc = quote_plus(query)
    url = f"https://hianime.dk/search?keyword={query_enc}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        seen = set()
        for a in soup.select("a[href*='/watch/']"):
            href = a["href"].strip()
            title = a.get("title") or a.text.strip().replace("\n", " ")
            title = re.sub(r'\s+', ' ', title)
            if href not in seen and len(title) > 2:
                seen.add(href)
                results.append((title, normalize(href, base_url="https://hianime.dk")))
        return results
    except Exception:
        return []


async def search_9anime_async(query):
    query_enc = quote_plus(query)
    url = f"https://9animes-tv.me/search?keyword={query_enc}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        seen = set()
        for a in soup.select("a[href*='/watch/']"):
            href = a["href"].strip()
            title = a.get("title") or a.text.strip().replace("\n", " ")
            title = re.sub(r'\s+', ' ', title)
            if href not in seen and len(title) > 2:
                seen.add(href)
                results.append((title, normalize(href, base_url="https://9animes-tv.me")))
        return results
    except Exception:
        return []


def deduplicate_search_results(results_3rb, results_wit):
    """Merge search results from Anime3rb and WitAnime, grouping identical shows.

    Returns list of (display_title, [(provider_name, url, is_witanime_flag), ...]).
    """
    def _normalize(t):
        t = t.lower().strip()
        t = re.sub(r'[\[\]\(\)]', '', t)
        t = re.sub(r'\s+', ' ', t)
        t = re.sub(r'\s*(tv|dub|sub|movie|season\s*\d+|part\s*\d+|ova|ona)\s*$', '', t)
        return t.strip()

    unified = []
    used_wit = set()

    for title_3rb, href_3rb in results_3rb:
        norm_3rb = _normalize(title_3rb)
        providers = [("Anime3rb", href_3rb, 0)]
        best_match = None
        best_ratio = 0.0

        for i, (title_wit, href_wit) in enumerate(results_wit):
            if i in used_wit:
                continue
            norm_wit = _normalize(title_wit)
            ratio = difflib.SequenceMatcher(None, norm_3rb, norm_wit).ratio()
            if ratio > 0.6 and ratio > best_ratio:
                best_ratio = ratio
                best_match = i

        if best_match is not None:
            used_wit.add(best_match)
            providers.append(("WitAnime", results_wit[best_match][1], 1))

        display_title = title_3rb
        if best_match is not None and len(results_wit[best_match][0]) > len(title_3rb):
            display_title = results_wit[best_match][0]

        unified.append((display_title, providers))

    for i, (title_wit, href_wit) in enumerate(results_wit):
        if i not in used_wit:
            unified.append((title_wit, [("WitAnime", href_wit, 1)]))

    unified.sort(key=lambda x: -len(x[1]))
    return unified


def deduplicate_search_results_multi(provider_results):
    """Deduplicate search results across multiple providers.

    provider_results: list of (provider_name, [(title, url), ...], provider_id)
    Returns list of (display_title, [(provider_name, url, provider_id), ...]).
    Only groups items from DIFFERENT providers (never same-provider).
    """
    def _normalize(t):
        t = t.lower().strip()
        t = re.sub(r'[\[\]\(\)]', '', t)
        t = re.sub(r'\s+', ' ', t)
        t = re.sub(r'\s*(tv|dub|sub|movie|season\s*\d+|part\s*\d+|ova|ona)\s*$', '', t)
        return t.strip()

    # First pass: deduplicate WITHIN each provider (remove near-identical entries)
    deduped_provider_results = []
    for pname, results, pid in provider_results:
        seen_titles = {}
        deduped = []
        for title, url in results:
            norm = _normalize(title)
            # Check if very similar to an already-seen title in this provider
            found = False
            for seen_norm, seen_title, seen_url in seen_titles.values():
                if difflib.SequenceMatcher(None, norm, seen_norm).ratio() > 0.9:
                    found = True
                    break
            if not found:
                key = len(deduped)
                deduped.append((title, url))
                seen_titles[key] = (norm, title, url)
        deduped_provider_results.append((pname, deduped, pid))

    # Flatten with global indices for tracking
    all_items = []
    for pname, results, pid in deduped_provider_results:
        for title, url in results:
            all_items.append((title, url, pname, pid))

    groups = []
    used = set()

    for i, (title, url, pname, pid) in enumerate(all_items):
        if i in used:
            continue
        norm_i = _normalize(title)
        group = [(pname, url, pid)]
        used.add(i)
        group_pids = {pid}

        for j in range(i + 1, len(all_items)):
            if j in used:
                continue
            title_j, url_j, pname_j, pid_j = all_items[j]
            if pid_j in group_pids:
                continue  # one entry per provider per group
            norm_j = _normalize(title_j)
            ratio = difflib.SequenceMatcher(None, norm_i, norm_j).ratio()
            if ratio > 0.6:
                group.append((pname_j, url_j, pid_j))
                used.add(j)
                group_pids.add(pid_j)
                if len(title_j) > len(title):
                    title = title_j

        groups.append((title, group))

    groups.sort(key=lambda x: -len(x[1]))
    return groups


def search_providers_for_media(title):
    """Search all providers for a title.

    Returns (display_title, url, provider_id) or None.
    """
    try:
        from src.providers import registry as _reg
        providers_list = _reg.get_all()

        async def _search():
            tasks = [p.search(title) for p in providers_list]
            res = await asyncio.gather(*tasks, return_exceptions=True)
            providers = []
            for i, p in enumerate(providers_list):
                data = res[i] if isinstance(res[i], list) else []
                items = [(item["title"], item["url"]) for item in data]
                providers.append((p.provider_name, items, p.provider_id))
            deduped = deduplicate_search_results_multi(providers)
            if deduped:
                entry = deduped[0]
                pname, url, flag = entry[1][0]
                return (entry[0], url, flag)
            return None
        return asyncio.run(_search())
    except Exception:
        return None


# ─── Scraping Helpers ───────────────────────────────────────

def _is_cloudflare_challenge(html):
    if "Just a moment" not in html and "Attention Required" not in html:
        return False
    # Confirm with a second signal — the challenge script or verification meta
    if "cf-browser-verify" in html or "/cdn-cgi/challenge-platform" in html:
        return True
    return False


def _select_scraping_method(cfg=None):
    if cfg is None:
        cfg = load_config()
    return cfg.get("scraping_method", "auto")


def _get_ua():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


async def _fetch_episodes_list_httpx(url, is_witanime, active_cookies=None):
    slug = extract_slug(url)
    if not slug:
        return None, "Cannot extract slug from URL."
    try:
        cookies_dict = {}
        if active_cookies:
            for c in active_cookies:
                cookies_dict[c.get("name")] = c.get("value")
        headers = {
            "User-Agent": _get_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers, cookies=cookies_dict)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        html = r.text
        if _is_cloudflare_challenge(html):
            return None, "Cloudflare challenge detected"
        soup = BeautifulSoup(html, "lxml")
        eps = []
        if is_witanime == 1:
            cards = soup.find_all("div", class_="episodes-card")
            for idx, card in enumerate(cards):
                title_anchor = card.find("h3").find("a") if card.find("h3") else None
                if not title_anchor or not title_anchor.get("onclick"):
                    continue
                onclick = title_anchor["onclick"]
                try:
                    m = re.search(r"'([A-Za-z0-9+/=]+)'", onclick)
                    if not m:
                        continue
                    ep_url = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                text = title_anchor.text.strip()
                m = re.search(r'\d+', text)
                ep_num = int(m.group(0)) if m else (idx + 1)
                eps.append({"episode": ep_num, "page_url": ep_url})
        elif is_witanime == 0:
            seen = set()
            for a in soup.find_all("a", href=True):
                h = a["href"].strip()
                m = re.search(rf"/episode/{re.escape(slug)}/(\d+)", h)
                n = int(m.group(1)) if m else None
                if n is not None and h not in seen:
                    seen.add(h)
                    eps.append({"episode": n, "page_url": normalize(h, base_url=url)})
        elif is_witanime == 2:
            # Anineko: episode grid with links like /watch/{slug}/ep-{num}
            for ep_div in soup.find_all("a", class_="nv-info-episode-main"):
                ep_href = (ep_div.get("href") or "").strip()
                m = re.search(r'/ep-(\d+)$', ep_href)
                if m:
                    ep_num = int(m.group(1))
                    # Ensure /watch/ link, not /download/
                    if "/download/" in ep_href:
                        ep_href = ep_href.replace("/download/", "/watch/")
                    eps.append({"episode": ep_num, "page_url": normalize(ep_href, base_url=url)})
            if not eps:
                for a in soup.find_all("a", href=True):
                    h = a["href"].strip()
                    m = re.search(r'/ep-(\d+)$', h)
                    if m and "/watch/" in h:
                        ep_num = int(m.group(1))
                        eps.append({"episode": ep_num, "page_url": normalize(h, base_url=url)})
        elif is_witanime == 3:
            # HiAnime: load dynamically from API, then fallback to page scrape
            anime_id = None
            # Extract slug for building episode URLs
            slug = extract_slug(url)
            m = re.search(r'data-id\s*=\s*["\'](\d+)["\']', html)
            if m:
                anime_id = m.group(1)
            if not anime_id:
                m = re.search(r'let\s+id\s*=\s*(\d+)', html)
                if m:
                    anime_id = m.group(1)
            if not anime_id:
                m = re.search(r'/watch/[^/]+-(\d+)', url)
                if m:
                    anime_id = m.group(1)
            if not anime_id:
                script_tag = soup.find("script", text=re.compile(r'anime_id'))
                if not script_tag:
                    script_tag = soup.find("script", text=re.compile(r'"id"'))
                if script_tag and script_tag.string:
                    m = re.search(r'anime_id\s*=\s*["\']?(\d+)["\']?', script_tag.string)
                    if m:
                        anime_id = m.group(1)
            if anime_id:
                api_url = f"https://hianime.dk/ajax/episode/list/{anime_id}"
                async with httpx.AsyncClient(timeout=15.0) as c2:
                    ar = await c2.get(api_url, headers=headers)
                if ar.status_code == 200:
                    data = ar.json()
                    html_str = data.get("result", "")
                    if html_str:
                        ep_soup = BeautifulSoup(str(html_str), "lxml")
                        for a in ep_soup.select("a.ssl-item.ep-item, a[class*='ep-item']"):
                            ep_num_text = a.text.strip()
                            m = re.search(r'(\d+)', ep_num_text)
                            if m:
                                ep_num = int(m.group(1))
                                if slug:
                                    ep_page_url = normalize(f"/watch/{slug}/ep-{ep_num}", base_url="https://hianime.dk")
                                else:
                                    ep_page_url = normalize(a.get("href", "#"), base_url="https://hianime.dk")
                                eps.append({"episode": ep_num, "page_url": ep_page_url})
            # Fallback: scrape from page using specific episode-item selectors
            if not eps:
                seen = set()
                for a in soup.select("a.ssl-item.ep-item, a[class*='ep-item'], div[class*='ep-item'] a"):
                    h = a.get("href", "").strip()
                    ep_num_text = a.text.strip()
                    m = re.search(r'(\d+)', ep_num_text)
                    if m:
                        ep_num = int(m.group(1))
                        if h and h != "#" and h not in seen:
                            seen.add(h)
                            eps.append({"episode": ep_num, "page_url": normalize(h, base_url=url)})
        elif is_witanime == 4:
            # 9Anime: look for episode links
            seen = set()
            for a in soup.find_all("a", href=True):
                h = a["href"].strip()
                if "/watch/" in h and slug in h:
                    ep_text = a.text.strip()
                    m = re.search(r'(\d+)', ep_text)
                    if m and h not in seen:
                        seen.add(h)
                        eps.append({"episode": int(m.group(1)), "page_url": normalize(h, base_url=url)})
        if not eps:
            return None, "No episodes found via httpx"
        eps.sort(key=lambda x: x["episode"])
        return eps, None
    except Exception as e:
        return None, str(e)


async def _scrape_one_stream_httpx(ep_item, is_witanime, active_cookies=None):
    ep_num = ep_item["episode"]
    url = ep_item["page_url"]
    cookies_dict = {}
    if active_cookies:
        for c in active_cookies:
            cookies_dict[c.get("name")] = c.get("value")
    headers = {
        "User-Agent": _get_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers, cookies=cookies_dict)
        if r.status_code != 200:
            return None
        html = r.text
        if _is_cloudflare_challenge(html):
            return None
        resolved = None
        if is_witanime == 1:
            soup = BeautifulSoup(html, "lxml")
            server_links = soup.find_all("a", class_="server-link")
            candidates = []
            for srv in server_links:
                onclick = srv.get("onclick", "")
                if not onclick:
                    continue
                try:
                    m = re.search(r"'([A-Za-z0-9+/=]+)'", onclick)
                    if not m:
                        continue
                    embed_url = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if not embed_url.startswith("http"):
                    continue
                try:
                    embed_headers = {**headers, "Referer": url}
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c2:
                        er = await c2.get(embed_url, headers=embed_headers)
                    if er.status_code == 200:
                        ehtml = er.text
                        found = None
                        patterns = [
                            r'<video[^>]*src=["\']([^"\']+)["\']',
                            r'<source[^>]*src=["\']([^"\']+\.(?:mp4|m3u8))["\']',
                            r'video_url\s*[=:]\s*["\']([^"\']+)["\']',
                            r'file:\s*["\']([^"\']+)["\']',
                        ]
                        for pat in patterns:
                            m = re.search(pat, ehtml)
                            if m:
                                found = m.group(1)
                                break
                        if not found:
                            m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', ehtml)
                            if m:
                                found = m.group(1)
                        if found:
                            candidates.append(found)
                except Exception:
                    continue
            resolved = select_best_stream(candidates) if candidates else None
        elif is_witanime == 0:
            soup = BeautifulSoup(html, "lxml")
            iframe = soup.find("iframe", src=re.compile(r"(vid3rb\.com|player)"))
            if iframe:
                player_url = iframe.get("src")
                if player_url:
                    if not player_url.startswith("http"):
                        from urllib.parse import urljoin
                        player_url = urljoin(url, player_url)
                    try:
                        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c2:
                            pr = await c2.get(player_url, headers=headers)
                        if pr.status_code == 200:
                            phtml = pr.text
                            m = re.search(r'(?:var|let|const)\s+video_sources\s*=\s*(\[\s*\{[\s\S]*?\}\s*\])\s*;', phtml)
                            if m:
                                sources = json.loads(m.group(1))
                                cfg = load_config()
                                pref_q = cfg.get("default_quality", "auto")
                                if pref_q == "720p":
                                    q_order = ["720p", "1080p", "480p"]
                                elif pref_q == "480p":
                                    q_order = ["480p", "720p", "1080p"]
                                else:
                                    q_order = ["1080p", "720p", "480p"]
                                for q in q_order:
                                    for s in sources:
                                        if s.get("label") == q and s.get("src") and not s.get("premium"):
                                            resolved = s["src"]
                                            break
                                    if resolved:
                                        break
                            if not resolved:
                                m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', phtml)
                                if m:
                                    resolved = m.group(1)
                    except Exception:
                        pass
        elif is_witanime == 2:
            # Anineko: extract embed URLs from data-video attributes, then resolve
            soup = BeautifulSoup(html, "lxml")
            embed_urls = []
            for el in soup.find_all(attrs={"data-video": True}):
                url_candidate = el.get("data-video", "").strip()
                if url_candidate.startswith("http"):
                    embed_urls.append(url_candidate)
            # Try iframe as fallback
            if not embed_urls:
                for iframe in soup.find_all("iframe", src=True):
                    src = iframe["src"].strip()
                    if src.startswith("http"):
                        embed_urls.append(src)
            # Resolve each embed URL
            headers["Referer"] = url
            for embed_url in embed_urls:
                try:
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as c2:
                        er = await c2.get(embed_url, headers=headers)
                    if er.status_code == 200:
                        ehtml = er.text
                        patterns = [
                            r'<video[^>]*src=["\']([^"\']+)["\']',
                            r'<source[^>]*src=["\']([^"\']+\.(?:mp4|m3u8))["\']',
                            r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)',
                            r'file:\s*["\']([^"\']+)["\']',
                            r'src:\s*["\']([^"\']+)["\']',
                        ]
                        for pat in patterns:
                            m = re.search(pat, ehtml)
                            if m:
                                resolved = m.group(1)
                                break
                        if resolved:
                            break
                except Exception:
                    continue
        elif is_witanime == 3:
            # HiAnime: try direct video sources, AJAX API, or iframe extraction
            soup = BeautifulSoup(html, "lxml")
            # Try direct video/stream URL patterns
            m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', html)
            if m:
                resolved = m.group(1)
            # Try iframe
            if not resolved:
                for iframe in soup.find_all("iframe", src=True):
                    iframe_src = iframe["src"]
                    if iframe_src.startswith("http"):
                        try:
                            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c2:
                                ir = await c2.get(iframe_src, headers=headers)
                            if ir.status_code == 200:
                                ihtml = ir.text
                                m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', ihtml)
                                if m:
                                    resolved = m.group(1)
                        except Exception:
                            pass
                    if resolved:
                        break
        elif is_witanime == 4:
            # 9Anime: look for video source
            soup = BeautifulSoup(html, "lxml")
            # Try direct sources
            m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', html)
            if m:
                resolved = m.group(1)
            if not resolved:
                for iframe in soup.find_all("iframe", src=True):
                    iframe_src = iframe["src"]
                    if iframe_src.startswith("http"):
                        try:
                            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c2:
                                ir = await c2.get(iframe_src, headers=headers)
                            if ir.status_code == 200:
                                ihtml = ir.text
                                m = re.search(r'(https?://[^"\'<>]+\.(?:mp4|m3u8)[^"\'<>]*)', ihtml)
                                if m:
                                    resolved = m.group(1)
                        except Exception:
                            pass
                    if resolved:
                        break
    except Exception as e:
        print(f"[pyanime] Warning: stream scrape failed: {e}")
    return resolved


# ─── Playwright Scraping Engine ─────────────────────────────

async def fetch_episodes_list_async(url, is_witanime, active_cookies=None):
    method = _select_scraping_method()
    if method in ("auto", "alternative_only"):
        eps, err = await _fetch_episodes_list_httpx(url, is_witanime, active_cookies)
        if eps is not None:
            return eps, err
        if method == "alternative_only":
            return [], err or "httpx alternative failed"
    from playwright.async_api import async_playwright

    slug = extract_slug(url)
    if not slug:
        return [], "Cannot extract slug from URL."

    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-gpu",
                    ]
                )
            except Exception as e:
                msg = str(e)
                if "executable doesn't exist" in msg.lower() or "playwright install" in msg.lower():
                    msg = "Playwright Chromium browser is not installed. Please run 'playwright install' or 'python3 -m playwright install' in your terminal."
                return [], msg

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            if active_cookies:
                try:
                    await context.add_cookies(active_cookies)
                except Exception as e:
                    _cookie_warn(f"add cookies failed: {e}")

            page = await context.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})

            try:
                await page.goto(url, wait_until="domcontentloaded")

                success = False
                extra_wait = 2.0 if is_witanime == 3 else 0.0
                await asyncio.sleep(extra_wait)
                for _ in range(35 if is_witanime == 4 else 25):
                    title = await page.title()
                    if "Just a moment" not in title and "Attention Required" not in title:
                        if is_witanime == 1:
                            if await page.locator("div.episodes-card").count() > 0:
                                success = True
                                break
                        elif is_witanime == 0:
                            if await page.locator("a[href*='/episode/']").count() > 0:
                                success = True
                                break
                        elif is_witanime == 2:
                            if await page.locator("#episode_page").count() > 0 or await page.locator("a[href*='/episode']").count() > 0:
                                success = True
                                break
                        elif is_witanime == 3:
                            if await page.locator("#episodes-content .ssl-item.ep-item").count() > 0 or await page.locator("a[href*='/watch/']").count() > 0:
                                success = True
                                break
                        elif is_witanime == 4:
                            if await page.locator("a[href*='/watch/']").count() > 0:
                                success = True
                                break
                        else:
                            success = True
                            break
                    await asyncio.sleep(1.0)

                if not success:
                    await browser.close()
                    return [], "Failed to bypass Cloudflare challenge."

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")
                eps = []

                if is_witanime == 1:
                    cards = soup.find_all("div", class_="episodes-card")
                    for idx, card in enumerate(cards):
                        title_anchor = card.find("h3").find("a") if card.find("h3") else None
                        if not title_anchor or not title_anchor.get("onclick"):
                            continue
                        onclick = title_anchor["onclick"]
                        try:
                            m = re.search(r"'([A-Za-z0-9+/=]+)'", onclick)
                            if not m:
                                continue
                            ep_url = base64.b64decode(m.group(1)).decode("utf-8", errors="ignore")
                        except Exception:
                            continue
                        text = title_anchor.text.strip()
                        m = re.search(r'\d+', text)
                        ep_num = int(m.group(0)) if m else (idx + 1)

                        eps.append({
                            "episode": ep_num,
                            "page_url": ep_url
                        })
                elif is_witanime == 0:
                    seen = set()
                    for a in soup.find_all("a", href=True):
                        h = a["href"].strip()
                        m = re.search(rf"/episode/{re.escape(slug)}/(\d+)", h)
                        n = int(m.group(1)) if m else None
                        if n is not None and h not in seen:
                            seen.add(h)
                            eps.append({
                                "episode": n,
                                "page_url": normalize(h, base_url=url)
                            })
                elif is_witanime == 2:
                    for ep_div in soup.find_all("a", class_="nv-info-episode-main"):
                        ep_href = (ep_div.get("href") or "").strip()
                        m = re.search(r'/ep-(\d+)$', ep_href)
                        if m:
                            ep_num = int(m.group(1))
                            if "/download/" in ep_href:
                                ep_href = ep_href.replace("/download/", "/watch/")
                            eps.append({"episode": ep_num, "page_url": normalize(ep_href, base_url=url)})
                    if not eps:
                        for a in soup.find_all("a", href=True):
                            h = a["href"].strip()
                            m = re.search(r'/ep-(\d+)$', h)
                            if m and "/watch/" in h:
                                ep_num = int(m.group(1))
                                eps.append({"episode": ep_num, "page_url": normalize(h, base_url=url)})
                elif is_witanime == 3:
                    seen = set()
                    for a in soup.select("a.ssl-item.ep-item, a[class*='ep-item'], div[class*='ep-item'] a"):
                        h = a.get("href", "").strip()
                        ep_num_text = a.text.strip()
                        m = re.search(r'(\d+)', ep_num_text)
                        if m:
                            ep_num = int(m.group(1))
                            if slug:
                                ep_page_url = normalize(f"/watch/{slug}/ep-{ep_num}", base_url=url)
                            elif h and h != "#" and h not in seen:
                                ep_page_url = normalize(h, base_url=url)
                            else:
                                continue
                            if ep_page_url not in seen:
                                seen.add(ep_page_url)
                                eps.append({"episode": ep_num, "page_url": ep_page_url})
                elif is_witanime == 4:
                    seen = set()
                    for a in soup.find_all("a", href=True):
                        h = a["href"].strip()
                        if "/watch/" in h and slug.replace('-', '') in h.replace('-', ''):
                            ep_text = a.text.strip()
                            m = re.search(r'(\d+)', ep_text)
                            if m and h not in seen:
                                seen.add(h)
                                eps.append({"episode": int(m.group(1)), "page_url": normalize(h, base_url=url)})

                eps.sort(key=lambda x: x["episode"])
                await browser.close()
                return eps, None
            except Exception as e:
                await browser.close()
                return [], str(e)
    except Exception as e:
        return [], str(e)


async def scrape_one_stream_async(browser, ep_item, is_witanime, active_cookies, results_dict, status_dict):
    ep_num = ep_item["episode"]
    url = ep_item["page_url"]

    status_dict[ep_num] = {"status": "Initializing...", "color": "cyan", "quality": "-"}

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    if active_cookies:
        try:
            await context.add_cookies(active_cookies)
        except Exception as e:
            _cookie_warn(f"playwright stream scrape failed: {e}")

    page = await context.new_page()
    await page.set_viewport_size({"width": 1280, "height": 800})

    media_requests = []
    def request_handler(request):
        u = request.url.lower()
        if any(kw in u for kw in ["google", "ads", "analytics", "banner", "p.gif", "count.gif", "tracker"]):
            return

        is_stream = False
        if request.resource_type == "media":
            is_stream = True
        elif ".mp4" in u or ".m3u8" in u or "master.txt" in u:
            is_stream = True
        elif request.resource_type in ["xhr", "fetch"]:
            if any(p in u for p in ["/hls/", "/hls2/", "/hls3/", "/master.", "/playlist.", "/index.m3u8"]):
                is_stream = True

        if is_stream and not u.startswith("blob:") and not u.startswith("data:"):
            media_requests.append(request.url)

    page.on("request", request_handler)

    resolved_stream = None
    try:
        status_dict[ep_num] = {"status": "Loading page...", "color": "blue", "quality": "-"}
        await page.goto(url, wait_until="domcontentloaded")

        # Wait for Cloudflare challenge to clear if present
        for _ in range(30):
            title = await page.title()
            if "Just a moment" not in title and "Attention Required" not in title:
                break
            await asyncio.sleep(1.0)

        if is_witanime == 1:
            status_dict[ep_num] = {"status": "Selecting server...", "color": "yellow", "quality": "-"}
            await page.wait_for_selector("a.server-link", timeout=12000)
            server_links = page.locator("a.server-link")
            srv_count = await server_links.count()

            srv_items = []
            for idx in range(srv_count):
                loc = server_links.nth(idx)
                name = await loc.locator("span.ser").inner_text()
                srv_items.append({"index": idx, "name": name, "locator": loc})

            def get_priority(srv):
                name = srv["name"].lower()
                if "videa - fhd" in name or "videa-fhd" in name: return 5
                if "streamwish - fhd" in name or "streamwish-fhd" in name: return 4
                if "videa" in name: return 3
                if "streamwish" in name: return 2
                if "multi" in name: return 1
                return 0

            srv_items.sort(key=get_priority, reverse=True)

            for srv in srv_items:
                await page.evaluate("el => el.click()", await srv["locator"].element_handle())
                await asyncio.sleep(2.5)

                if media_requests:
                    resolved_stream = select_best_stream(media_requests)
                    break

                try:
                    iframe_src = await page.locator("#iframe-container iframe").get_attribute("src")
                except Exception:
                    iframe_src = None

                if iframe_src and iframe_src.startswith("http"):
                    status_dict[ep_num] = {"status": "Resolving player...", "color": "yellow", "quality": "-"}
                    player_page = await context.new_page()
                    p_media = []

                    player_page.on("request", lambda r: p_media.append(r.url) if (
                        r.resource_type == "media" or
                        ".mp4" in r.url.lower() or
                        ".m3u8" in r.url.lower() or
                        "master.txt" in r.url.lower() or
                        (r.resource_type in ["xhr", "fetch"] and any(p in r.url.lower() for p in ["/hls/", "/hls2/", "/hls3/", "/master.", "/playlist.", "/index.m3u8"]))
                    ) and not r.url.lower().startswith("blob:") and not r.url.lower().startswith("data:") else None)

                    try:
                        await player_page.goto(iframe_src, wait_until="domcontentloaded", timeout=15000)
                        await asyncio.sleep(2.0)

                        try:
                            await player_page.locator("video, .play-button, .vjs-big-play-button").first.click(timeout=5000)
                        except Exception:
                            try:
                                await player_page.mouse.click(640, 400)
                            except Exception:
                                pass
                        try:
                            await player_page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
                        except Exception as e:
                            print(f"[pyanime] Warning: player_page.evaluate failed: {e}")
                        await asyncio.sleep(3.0)

                        if p_media:
                            resolved_stream = select_best_stream(p_media)
                        else:
                            v_src = await player_page.evaluate("() => document.querySelector('video') ? document.querySelector('video').src : null")
                            if v_src and not v_src.startswith("blob:") and not v_src.startswith("data:"):
                                resolved_stream = v_src
                    except Exception as e:
                        status_dict[ep_num] = {"status": f"Embed Error: {e}", "color": "red", "quality": "-"}
                    finally:
                        try:
                            await player_page.close()
                        except Exception as e:
                            print(f"[pyanime] Warning: player_page.close failed: {e}")

                    if resolved_stream:
                        break
        elif is_witanime == 0:
            status_dict[ep_num] = {"status": "Extracting source...", "color": "yellow", "quality": "-"}

            cfg = load_config()
            pref_q = cfg.get("default_quality", "auto")
            if pref_q == "720p":
                quality_order = ["720p", "1080p", "480p"]
            elif pref_q == "480p":
                quality_order = ["480p", "720p", "1080p"]
            else:
                quality_order = ["1080p", "720p", "480p"]

            success = False
            for _ in range(10):
                frames = page.frames
                player_frame = next((f for f in frames if "vid3rb.com" in f.url or "player" in f.url), None)
                if player_frame:
                    try:
                        frame_html = await player_frame.content()
                        m = re.search(r'(?:var|let|const)\s+video_sources\s*=\s*(\[\s*\{[\s\S]*?\}\s*\])\s*;', frame_html)
                        if m:
                            sources = json.loads(m.group(1))
                            for q in quality_order:
                                for s in sources:
                                    if s.get("label") == q and s.get("src") and not s.get("premium"):
                                        resolved_stream = s["src"]
                                        success = True
                                        break
                                if success:
                                    break
                    except Exception as e:
                        print(f"[pyanime] Warning: scraper iteration failed: {e}")

                    if success:
                        break

                    if media_requests:
                        resolved_stream = media_requests[0]
                        success = True
                        break
                await asyncio.sleep(1.0)

            if not resolved_stream and media_requests:
                resolved_stream = media_requests[0]
        elif is_witanime == 2:
            # Anineko: extract data-video embed URLs, open in player page
            status_dict[ep_num] = {"status": "Finding player...", "color": "yellow", "quality": "-"}
            await asyncio.sleep(2.0)
            try:
                embed_urls = await page.evaluate("""() => {
                    const els = document.querySelectorAll('[data-video]');
                    return Array.from(els).map(el => el.getAttribute('data-video')).filter(u => u && u.startsWith('http'));
                }""")
                if not embed_urls:
                    iframe_src = await page.locator("iframe[src*='//']").first.get_attribute("src")
                    if iframe_src and iframe_src.startswith("http"):
                        embed_urls = [iframe_src]
                for embed_url in embed_urls:
                    player_page = await context.new_page()
                    try:
                        p_media = []
                        player_page.on("request", lambda r: p_media.append(r.url) if (
                            r.resource_type == "media" or ".mp4" in r.url.lower() or ".m3u8" in r.url.lower()
                        ) and not r.url.lower().startswith("blob:") and not r.url.lower().startswith("data:") else None)
                        await player_page.goto(embed_url, wait_until="load")
                        await asyncio.sleep(3.0)
                        if p_media:
                            resolved_stream = select_best_stream(p_media)
                        else:
                            v_src = await player_page.evaluate("() => document.querySelector('video') ? document.querySelector('video').src : null")
                            if v_src and not v_src.startswith("blob:") and not v_src.startswith("data:"):
                                resolved_stream = v_src
                    finally:
                        await player_page.close()
                    if resolved_stream:
                        break
            except Exception:
                if media_requests:
                    resolved_stream = select_best_stream(media_requests)
        elif is_witanime == 3:
            # HiAnime: click server buttons, extract video
            status_dict[ep_num] = {"status": "Finding servers...", "color": "yellow", "quality": "-"}
            await asyncio.sleep(3.0)
            try:
                srv_buttons = page.locator(".server-item a.btn[data-link-id], a.server-item[data-link-id], button.server-item")
                srv_count = await srv_buttons.count()
                if srv_count == 0:
                    srv_buttons = page.locator("[data-link-id]")
                    srv_count = await srv_buttons.count()
                for i in range(srv_count):
                    try:
                        await srv_buttons.nth(i).click()
                        await asyncio.sleep(3.0)
                        if media_requests:
                            resolved_stream = select_best_stream(media_requests)
                            break
                    except Exception:
                        pass
            except Exception:
                pass
            if not resolved_stream:
                try:
                    v_src = await page.evaluate("() => document.querySelector('video') ? document.querySelector('video').src : null")
                    if v_src and not v_src.startswith("blob:") and not v_src.startswith("data:"):
                        resolved_stream = v_src
                except Exception:
                    pass
            if not resolved_stream:
                try:
                    iframe = await page.locator("iframe[src*='//']").first.get_attribute("src")
                    if iframe and iframe.startswith("http"):
                        player_page = await context.new_page()
                        try:
                            await player_page.goto(iframe, wait_until="load")
                            await asyncio.sleep(3.0)
                            p_media = []
                            player_page.on("request", lambda r: p_media.append(r.url) if (
                                r.resource_type == "media" or ".mp4" in r.url.lower() or ".m3u8" in r.url.lower()
                            ) and not r.url.lower().startswith("blob:") and not r.url.lower().startswith("data:") else None)
                            await asyncio.sleep(3.0)
                            if p_media:
                                resolved_stream = select_best_stream(p_media)
                        finally:
                            await player_page.close()
                except Exception:
                    pass
        elif is_witanime == 4:
            # 9Anime: look for video source
            status_dict[ep_num] = {"status": "Extracting stream...", "color": "yellow", "quality": "-"}
            await asyncio.sleep(2.0)
            if media_requests:
                resolved_stream = select_best_stream(media_requests)
            if not resolved_stream:
                try:
                    v_src = await page.evaluate("() => document.querySelector('video') ? document.querySelector('video').src : null")
                    if v_src and not v_src.startswith("blob:") and not v_src.startswith("data:"):
                        resolved_stream = v_src
                except Exception:
                    pass
            if not resolved_stream:
                try:
                    iframe = await page.locator("iframe[src*='//']").first.get_attribute("src")
                    if iframe and iframe.startswith("http"):
                        player_page = await context.new_page()
                        try:
                            await player_page.goto(iframe, wait_until="load")
                            await asyncio.sleep(3.0)
                            p_media = []
                            player_page.on("request", lambda r: p_media.append(r.url) if (
                                r.resource_type == "media" or ".mp4" in r.url.lower() or ".m3u8" in r.url.lower()
                            ) and not r.url.lower().startswith("blob:") and not r.url.lower().startswith("data:") else None)
                            await asyncio.sleep(3.0)
                            if p_media:
                                resolved_stream = select_best_stream(p_media)
                        finally:
                            await player_page.close()
                except Exception:
                    pass

    except Exception as e:
        status_dict[ep_num] = {"status": f"Failed: {e}", "color": "red", "quality": "-"}
    finally:
        await page.close()
        await context.close()

    if resolved_stream:
        results_dict[ep_num] = resolved_stream
        quality = "FHD/1080p" if any(q in resolved_stream.lower() for q in ["1080p", "fhd", "w1080p"]) else "HD/720p" if any(q in resolved_stream.lower() for q in ["720p", "hd"]) else "SD/480p" if "480p" in resolved_stream.lower() else "Auto"
        status_dict[ep_num] = {"status": "Resolved ✔", "color": "green", "quality": quality}
    else:
        status_dict[ep_num] = {"status": "Failed ✘", "color": "red", "quality": "-"}


async def scrape_multiple_streams_async(ep_items, is_witanime, active_cookies):
    results = {}
    status_dict = {}
    for ep in ep_items:
        status_dict[ep["episode"]] = {"status": "Pending...", "color": "gray", "quality": "-"}

    def make_scraping_table():
        table = Table(box=None, show_header=True, border_style=THEME['border'])
        table.add_column("Episode", justify="center", style=f"bold {THEME['primary']}")
        table.add_column("Status", justify="left")
        table.add_column("Quality", justify="center", style=f"bold {THEME['success']}")

        color_map = {
            "gray": THEME['dim'],
            "cyan": THEME['primary'],
            "blue": THEME['accent'],
            "yellow": THEME['warning'],
            "green": THEME['success'],
            "red": THEME['error'],
        }

        for ep_num in sorted(status_dict.keys()):
            info = status_dict[ep_num]
            raw_color = info["color"]
            theme_color = color_map.get(raw_color, THEME['fg'])
            status_text = f"[{theme_color}]{info['status']}[/{theme_color}]"
            table.add_row(f"Episode {ep_num}", status_text, info["quality"])

        resolved_count = sum(1 for info in status_dict.values() if "Resolved" in info["status"])
        failed_count = sum(1 for info in status_dict.values() if "Failed" in info["status"])
        total_count = len(status_dict)
        done_count = resolved_count + failed_count

        pct = int((done_count / total_count) * 100) if total_count > 0 else 0
        bar_len = 20
        filled_len = int(bar_len * done_count // total_count) if total_count > 0 else 0
        bar = "█" * filled_len + "░" * (bar_len - filled_len)

        progress_text = f"\n[bold {THEME['accent']}]Progress:[/bold {THEME['accent']}] [bold {THEME['success']}]{bar}[/bold {THEME['success']}] {pct}%\n"
        progress_text += f"[bold {THEME['success']}]{get_icon('check')}Scraped:[/bold {THEME['success']}] {resolved_count} | [bold {THEME['error']}]{get_icon('cross')}Failed:[/bold {THEME['error']}] {failed_count} | [bold {THEME['primary']}]Total:[/bold {THEME['primary']}] {total_count}"

        progress_panel = Panel(
            progress_text,
            title=f"[bold {THEME['primary']}]Scraping Overview[/bold {THEME['primary']}]",
            border_style=THEME['border'],
            expand=False
        )

        w, h = shutil.get_terminal_size()
        return Align(
            Align.center(Columns([
                Panel(table, title=f"[bold {THEME['primary']}]Task Progress[/bold {THEME['primary']}]", border_style=THEME['border'], expand=False),
                progress_panel
            ])),
            vertical="middle",
            height=h
        )

    method = _select_scraping_method()
    need_playwright = []
    for ep in ep_items:
        en = ep["episode"]
        status_dict[en] = {"status": "Trying httpx...", "color": "cyan", "quality": "-"}
        if method == "playwright_only":
            need_playwright.append(ep)
            status_dict[en] = {"status": "Pending...", "color": "gray", "quality": "-"}
        else:
            stream = await _scrape_one_stream_httpx(ep, is_witanime, active_cookies)
            if stream:
                results[en] = stream
                quality = "FHD/1080p" if any(q in stream.lower() for q in ["1080p", "fhd", "w1080p"]) else "HD/720p" if any(q in stream.lower() for q in ["720p", "hd"]) else "SD/480p" if "480p" in stream.lower() else "Auto"
                status_dict[en] = {"status": "Resolved ✔", "color": "green", "quality": quality}
            else:
                need_playwright.append(ep)
                status_dict[en] = {"status": "Pending...", "color": "gray", "quality": "-"}

    if need_playwright:
        if method == "alternative_only":
            for ep in need_playwright:
                status_dict[ep["episode"]] = {"status": "Failed ✘", "color": "red", "quality": "-"}
        else:
            from playwright.async_api import async_playwright
            try:
                async with async_playwright() as p:
                    try:
                        browser = await p.chromium.launch(
                            headless=True,
                            args=[
                                "--disable-blink-features=AutomationControlled",
                                "--no-sandbox",
                                "--disable-gpu",
                            ]
                        )
                    except Exception as e:
                        msg = str(e)
                        if "executable doesn't exist" in msg.lower() or "playwright install" in msg.lower():
                            msg = "Playwright Chromium browser is not installed. Please run 'playwright install' or 'python3 -m playwright install' in your terminal."
                        for ep in need_playwright:
                            status_dict[ep["episode"]] = {"status": f"Failed: {msg}", "color": "red", "quality": "-"}
                        return results

                    tasks = []
                    for ep in need_playwright:
                        tasks.append(scrape_one_stream_async(browser, ep, is_witanime, active_cookies, results, status_dict))

                    with Live(make_scraping_table(), refresh_per_second=5, transient=False) as live:
                        async def update_display():
                            while True:
                                await asyncio.sleep(1.0)
                                live.update(make_scraping_table())

                        display_task = asyncio.create_task(update_display())
                        try:
                            await asyncio.gather(*tasks)
                        finally:
                            display_task.cancel()
                            try:
                                await display_task
                            except asyncio.CancelledError:
                                pass
                        live.update(make_scraping_table())

                    await browser.close()
            except Exception as e:
                for ep in need_playwright:
                    status_dict[ep["episode"]] = {"status": f"Failed: {e}", "color": "red", "quality": "-"}
    return results


async def _scrape_one_stream_playwright(ep_item, is_witanime, active_cookies=None):
    """Playwright fallback for single-stream scraping. Returns stream URL or None."""
    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-gpu",
                ]
            )
            results = {}
            status = {}
            await scrape_one_stream_async(browser, ep_item, is_witanime, active_cookies, results, status)
            await browser.close()
            ep_num = ep_item["episode"]
            return results.get(ep_num)
    except Exception:
        return None
