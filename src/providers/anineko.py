from scraping import (
    search_gogoanime_async, _fetch_episodes_list_httpx,
    _scrape_one_stream_httpx, fetch_episodes_list_async,
)

PROVIDER_ID = 2
PROVIDER_NAME = "Anineko"


class AninekoProvider:
    provider_id = PROVIDER_ID
    provider_name = PROVIDER_NAME

    async def search(self, query: str) -> list[dict]:
        results = await search_gogoanime_async(query)
        return [{"title": t, "url": u} for t, u in results]

    async def fetch_episodes(self, url: str) -> list[dict]:
        eps, err = await _fetch_episodes_list_httpx(url, 2)
        if eps is not None:
            return eps
        eps, err = await fetch_episodes_list_async(url, 2)
        return eps or []

    async def resolve_stream(self, episode_url: str) -> dict | None:
        stream = await _scrape_one_stream_httpx({"episode": 0, "page_url": episode_url}, 2)
        if stream:
            quality = "Auto"
            if "1080p" in stream.lower() or "fhd" in stream.lower():
                quality = "FHD/1080p"
            elif "720p" in stream.lower() or "hd" in stream.lower():
                quality = "HD/720p"
            elif "480p" in stream.lower():
                quality = "SD/480p"
            return {"url": stream, "quality": quality}
        return None

    async def resolve_stream_with_cookies(self, episode_url: str, cookies: list) -> dict | None:
        stream = await _scrape_one_stream_httpx({"episode": 0, "page_url": episode_url}, 2, cookies)
        if stream:
            quality = "Auto"
            if "1080p" in stream.lower() or "fhd" in stream.lower():
                quality = "FHD/1080p"
            elif "720p" in stream.lower() or "hd" in stream.lower():
                quality = "HD/720p"
            elif "480p" in stream.lower():
                quality = "SD/480p"
            return {"url": stream, "quality": quality}
        return None


def _register_provider(reg):
    reg.register(AninekoProvider())
