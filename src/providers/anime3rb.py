from scraping import (
    search_anime3rb_async, _fetch_episodes_list_httpx,
    _scrape_one_stream_httpx, _scrape_one_stream_playwright,
    fetch_episodes_list_async, _classify_stream_quality,
)

PROVIDER_ID = 0
PROVIDER_NAME = "Anime3rb"


class Anime3rbProvider:
    provider_id = PROVIDER_ID
    provider_name = PROVIDER_NAME

    async def search(self, query: str) -> list[dict]:
        results = await search_anime3rb_async(query)
        return [{"title": t, "url": u} for t, u in results]

    async def fetch_episodes(self, url: str) -> list[dict]:
        eps, err = await _fetch_episodes_list_httpx(url, 0)
        if eps is not None:
            return eps
        eps, err = await fetch_episodes_list_async(url, 0)
        return eps or []

    async def _resolve(self, episode_url: str, cookies=None):
        stream = await _scrape_one_stream_httpx({"episode": 0, "page_url": episode_url}, 0, cookies)
        if stream:
            return {"url": stream, "quality": _classify_stream_quality(stream)}
        stream = await _scrape_one_stream_playwright({"episode": 0, "page_url": episode_url}, 0, cookies)
        if stream:
            return {"url": stream, "quality": _classify_stream_quality(stream)}
        return None

    async def resolve_stream(self, episode_url: str) -> dict | None:
        return await self._resolve(episode_url)

    async def resolve_stream_with_cookies(self, episode_url: str, cookies: list) -> dict | None:
        return await self._resolve(episode_url, cookies)


def _register_provider(reg):
    reg.register(Anime3rbProvider())
