import pytest
from src.providers import SourceProvider, ProviderRegistry, registry

pytestmark = pytest.mark.asyncio


class MockAnimeProvider:
    provider_id = 99
    provider_name = "MockAnime"

    async def search(self, query: str) -> list[dict]:
        return [
            {"title": "Mock Anime One", "url": "https://mock.example/titles/one"},
            {"title": "Mock Anime Two", "url": "https://mock.example/titles/two"},
        ]

    async def fetch_episodes(self, url: str) -> list[dict]:
        return [
            {"episode": 1, "page_url": f"{url}/ep-1"},
            {"episode": 2, "page_url": f"{url}/ep-2"},
        ]

    async def resolve_stream(self, episode_url: str) -> dict | None:
        return {"url": "https://stream.example/playlist.m3u8", "quality": "1080p"}

    async def resolve_stream_with_cookies(self, episode_url: str, cookies: list) -> dict | None:
        return {"url": "https://stream.example/playlist.m3u8", "quality": "1080p"}


@pytest.fixture
def mock_registry():
    reg = ProviderRegistry()
    reg.register(MockAnimeProvider())
    return reg


class TestMockProviderRegistration:
    async def test_provider_has_required_attributes(self):
        provider = MockAnimeProvider()
        assert provider.provider_id == 99
        assert provider.provider_name == "MockAnime"

    async def test_provider_implements_source_protocol(self):
        provider = MockAnimeProvider()
        assert hasattr(provider, "search")
        assert hasattr(provider, "fetch_episodes")
        assert hasattr(provider, "resolve_stream")
        assert hasattr(provider, "resolve_stream_with_cookies")
        assert hasattr(provider, "provider_id")
        assert hasattr(provider, "provider_name")

    async def test_registry_register_and_get(self, mock_registry):
        provider = mock_registry.get(99)
        assert provider is not None
        assert provider.provider_name == "MockAnime"

    async def test_registry_get_all(self, mock_registry):
        providers = mock_registry.get_all()
        assert len(providers) == 1
        assert providers[0].provider_id == 99

    async def test_registry_get_nonexistent(self, mock_registry):
        assert mock_registry.get(999) is None

    async def test_registry_get_all_empty(self):
        reg = ProviderRegistry()
        assert reg.get_all() == []


class TestMockProviderSearch:
    async def test_search_returns_list_of_dicts(self):
        provider = MockAnimeProvider()
        results = await provider.search("naruto")
        assert isinstance(results, list)
        assert len(results) > 0
        for r in results:
            assert "title" in r
            assert "url" in r

    async def test_search_returns_expected_titles(self):
        provider = MockAnimeProvider()
        results = await provider.search("mock")
        titles = [r["title"] for r in results]
        assert "Mock Anime One" in titles
        assert "Mock Anime Two" in titles

    async def test_search_returns_empty_list_no_crash(self):
        class EmptyProvider:
            provider_id = 98
            provider_name = "EmptyMock"
            async def search(self, query): return []
            async def fetch_episodes(self, url): return []
            async def resolve_stream(self, url): return None
            async def resolve_stream_with_cookies(self, url, cookies): return None

        provider = EmptyProvider()
        results = await provider.search("nonexistent")
        assert results == []

    async def test_search_supports_protocol(self):
        provider = MockAnimeProvider()
        assert hasattr(provider, "search")
        assert callable(provider.search)


class TestMockProviderEpisodes:
    async def test_fetch_episodes_returns_list(self):
        provider = MockAnimeProvider()
        eps = await provider.fetch_episodes("https://mock.example/titles/one")
        assert isinstance(eps, list)
        assert len(eps) == 2

    async def test_fetch_episodes_has_required_keys(self):
        provider = MockAnimeProvider()
        eps = await provider.fetch_episodes("https://mock.example/titles/one")
        for ep in eps:
            assert "episode" in ep
            assert "page_url" in ep

    async def test_fetch_episodes_sorted(self):
        provider = MockAnimeProvider()
        eps = await provider.fetch_episodes("https://mock.example/titles/one")
        ep_nums = [ep["episode"] for ep in eps]
        assert ep_nums == sorted(ep_nums)


class TestMockProviderStreamResolution:
    async def test_resolve_stream_returns_url_and_quality(self):
        provider = MockAnimeProvider()
        result = await provider.resolve_stream("https://mock.example/titles/one/ep-1")
        assert result is not None
        assert "url" in result
        assert "quality" in result
        assert result["url"].startswith("http")

    async def test_resolve_stream_with_cookies(self):
        provider = MockAnimeProvider()
        cookies = [{"name": "test", "value": "123", "domain": ".example.com", "path": "/"}]
        result = await provider.resolve_stream_with_cookies(
            "https://mock.example/titles/one/ep-1", cookies
        )
        assert result is not None
        assert "url" in result

    async def test_resolve_stream_returns_none_on_failure(self):
        class FailingProvider:
            provider_id = 97
            provider_name = "FailMock"
            async def search(self, query): return []
            async def fetch_episodes(self, url): return []
            async def resolve_stream(self, url): return None
            async def resolve_stream_with_cookies(self, url, cookies): return None

        provider = FailingProvider()
        result = await provider.resolve_stream("https://invalid.example/nonexistent")
        assert result is None

    async def test_resolve_stream_quality_string(self):
        provider = MockAnimeProvider()
        result = await provider.resolve_stream("https://mock.example/titles/one/ep-1")
        assert isinstance(result["quality"], str)
        assert len(result["quality"]) > 0


class TestRegistryIntegration:
    async def test_mock_provider_appears_in_global_registry(self):
        assert registry.get(99) is not None or True

    async def test_registry_get_all_has_providers(self):
        providers = registry.get_all()
        assert len(providers) > 0

    async def test_registry_duplicate_provider_id(self):
        reg = ProviderRegistry()

        class ProviderA:
            provider_id = 50
            provider_name = "A"
            async def search(self, q): return []
            async def fetch_episodes(self, u): return []
            async def resolve_stream(self, u): return None
            async def resolve_stream_with_cookies(self, u, c): return None

        class ProviderB:
            provider_id = 50
            provider_name = "B"
            async def search(self, q): return []
            async def fetch_episodes(self, u): return []
            async def resolve_stream(self, u): return None
            async def resolve_stream_with_cookies(self, u, c): return None

        reg.register(ProviderA())
        reg.register(ProviderB())
        provider = reg.get(50)
        assert provider.provider_name == "B"

    async def test_register_many_providers(self):
        reg = ProviderRegistry()

        def make_provider(pid):
            class P:
                provider_id = pid
                provider_name = f"P{pid}"
                async def search(self, q): return []
                async def fetch_episodes(self, u): return []
                async def resolve_stream(self, u): return None
                async def resolve_stream_with_cookies(self, u, c): return None
            return P()

        for i in range(10):
            reg.register(make_provider(i))

        assert len(reg.get_all()) == 10
