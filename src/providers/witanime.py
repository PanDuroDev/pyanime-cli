from scraping import (
    search_witanime_async, _fetch_episodes_list_httpx,
    _scrape_one_stream_httpx, _scrape_one_stream_playwright,
    fetch_episodes_list_async, _classify_stream_quality,
)

PROVIDER_ID = 1
PROVIDER_NAME = "WitAnime"


class WitAnimeProvider:
    provider_id = PROVIDER_ID
    provider_name = PROVIDER_NAME

    async def search(self, query: str) -> list[dict]:
        results = await search_witanime_async(query)
        return [{"title": t, "url": u} for t, u in results]

    async def fetch_episodes(self, url: str) -> list[dict]:
        eps, err = await _fetch_episodes_list_httpx(url, 1)
        if eps is not None:
            return eps
        eps, err = await fetch_episodes_list_async(url, 1)
        return eps or []

    async def fetch_episodes_with_cookies(self, url: str, cookies: list) -> list[dict]:
        eps, err = await _fetch_episodes_list_httpx(url, 1, cookies)
        if eps is not None:
            return eps
        eps, err = await fetch_episodes_list_async(url, 1, cookies)
        return eps or []

    async def _resolve(self, episode_url: str, cookies=None):
        stream = await _scrape_one_stream_httpx({"episode": 0, "page_url": episode_url}, 1, cookies)
        if stream:
            return {"url": stream, "quality": _classify_stream_quality(stream)}
        stream = await _scrape_one_stream_playwright({"episode": 0, "page_url": episode_url}, 1, cookies)
        if stream:
            return {"url": stream, "quality": _classify_stream_quality(stream)}
        return None

    async def resolve_stream(self, episode_url: str) -> dict | None:
        return await self._resolve(episode_url)

    async def resolve_stream_with_cookies(self, episode_url: str, cookies: list) -> dict | None:
        return await self._resolve(episode_url, cookies)


def _register_provider(reg):
    reg.register(WitAnimeProvider())
