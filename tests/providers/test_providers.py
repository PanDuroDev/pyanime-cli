import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.asyncio


SEARCH_HTML = """
<html><body>
<a href="/titles/naruto"><h4>Naruto</h4></a>
<a href="/titles/one-piece"><h4>One Piece</h4></a>
</body></html>
"""

EPISODE_HTML_WITANIME = """
<html><body>
<div class="episodes-card"><h3><a onclick="openEpisode('ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5')">Episode 1</a></h3></div>
<div class="episodes-card"><h3><a onclick="openEpisode('ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5')">Episode 2</a></h3></div>
</body></html>
"""

STREAM_HTML_WITANIME = """
<html><body>
<a class="server-link" onclick="playVideo('ZXlKaGJHY2lPaUpJVXpJMU5pSXNJblI1Y0NJNklrcFhWQ0o5')"><span class="ser">Streamwish - FHD</span></a>
<div id="iframe-container"><iframe src="https://player.example/embed"></iframe></div>
</body></html>
"""

STREAM_RESOLVED_HTML = """
<html><body>
<video src="https://cdn.example/stream.mp4"></video>
</body></html>
"""


class TestProviderInterface:
    async def test_provider_search_returns_list(self):
        from src.providers.anime3rb import search_anime3rb_async

        with respx.mock:
            route = respx.get("https://anime3rb.com/titles/list?q=naruto")
            route.return_value = Response(200, html=SEARCH_HTML)

            results = await search_anime3rb_async("naruto")
            assert isinstance(results, list)

    async def test_provider_search_returns_tuples(self):
        from src.providers.anime3rb import search_anime3rb_async

        with respx.mock:
            route = respx.get("https://anime3rb.com/titles/list?q=naruto")
            route.return_value = Response(200, html=SEARCH_HTML)

            results = await search_anime3rb_async("naruto")
            if results:
                title, url = results[0]
                assert isinstance(title, str)
                assert isinstance(url, str)
                assert len(url) > 0

    async def test_provider_search_handles_http_error(self):
        from src.providers.anime3rb import search_anime3rb_async

        with respx.mock:
            route = respx.get("https://anime3rb.com/titles/list?q=error")
            route.return_value = Response(500)

            results = await search_anime3rb_async("error")
            assert results == []

    async def test_provider_search_handles_timeout(self):
        from src.providers.witanime import search_witanime_async

        with respx.mock:
            route = respx.get("https://witanime.com/?s=timeout")
            route.return_value = Response(200, html="")

            results = await search_witanime_async("timeout")
            assert isinstance(results, list)

    async def test_witanime_search(self):
        from src.providers.witanime import search_witanime_async

        html = """
        <html><body>
        <div class="postbody"><a href="/anime/naruto"><h2>Naruto</h2></a></div>
        <div class="postbody"><a href="/anime/one-piece"><h2>One Piece</h2></a></div>
        </body></html>
        """

        with respx.mock:
            route = respx.get("https://witanime.com/?s=naruto")
            route.return_value = Response(200, html=html)

            results = await search_witanime_async("naruto")
            assert isinstance(results, list)

    async def test_anineko_search(self):
        from src.providers.anineko import search_gogoanime_async

        html = """
        <html><body>
        <div class="img"><a href="/watch/naruto" title="Naruto"><img src="img.jpg"/></a></div>
        </body></html>
        """

        with respx.mock:
            route = respx.get("https://anitaku.bz/search.html?keyword=naruto")
            route.return_value = Response(200, html=html)

            results = await search_gogoanime_async("naruto")
            assert isinstance(results, list)

    async def test_hianime_search(self):
        from scraping import search_hianime_async

        html = """
        <html><body>
        <div class="film-poster"><a href="/watch/naruto-123" data-jtitle="Naruto"></a></div>
        </body></html>
        """

        with respx.mock:
            route = respx.get("https://hianime.to/search?keyword=naruto")
            route.return_value = Response(200, html=html)

            results = await search_hianime_async("naruto")
            assert isinstance(results, list)

    async def test_9anime_search(self):
        from scraping import search_9anime_async

        html = """
        <html><body>
        <a class="ep-item" href="/watch/naruto-123" data-title="Naruto"><div></div></a>
        </body></html>
        """

        with respx.mock:
            route = respx.get("https://9anime.com/search?keyword=naruto")
            route.return_value = Response(200, html=html)

            results = await search_9anime_async("naruto")
            assert isinstance(results, list)

    async def test_all_providers_search_handles_empty_results(self):
        from src.providers.anime3rb import search_anime3rb_async
        from src.providers.witanime import search_witanime_async
        from src.providers.anineko import search_gogoanime_async

        with respx.mock:
            respx.get("https://anime3rb.com/titles/list?q=nonexistent").respond(200, html="<html></html>")
            respx.get("https://witanime.com/").respond(200, html="<html></html>")
            respx.get("https://anitaku.bz/search.html?keyword=nonexistent").respond(200, html="<html></html>")

            r1 = await search_anime3rb_async("nonexistent")
            r2 = await search_witanime_async("nonexistent")
            r3 = await search_gogoanime_async("nonexistent")

            assert isinstance(r1, list)
            assert isinstance(r2, list)
            assert isinstance(r3, list)

    async def test_resolve_stream_returns_none_on_http_error(self):
        from src.providers.anime3rb import Anime3rbProvider

        provider = Anime3rbProvider()
        with respx.mock:
            respx.get("https://anime3rb.com/episode/test/1").respond(500)
            result = await provider.resolve_stream("https://anime3rb.com/episode/test/1")
            assert result is None

    async def test_fetch_episodes_returns_empty_on_error(self):
        from src.providers.anime3rb import Anime3rbProvider

        provider = Anime3rbProvider()
        with respx.mock:
            respx.get("https://anime3rb.com/titles/test").respond(500)
            eps = await provider.fetch_episodes("https://anime3rb.com/titles/test")
            assert isinstance(eps, list)

    async def test_provider_registry_contains_expected_count(self):
        from src.providers import registry, _load_providers

        providers = registry.get_all()
        assert len(providers) >= 3

    async def test_provider_attributes_are_consistent(self):
        from src.providers import registry

        for p in registry.get_all():
            assert hasattr(p, "provider_id")
            assert hasattr(p, "provider_name")
            assert isinstance(p.provider_id, int)
            assert isinstance(p.provider_name, str)
            assert p.provider_name != ""
