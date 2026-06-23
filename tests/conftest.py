import pytest
import respx
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    return None


@pytest.fixture
async def async_client():
    async with AsyncClient(base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_httpx():
    with respx.mock as respx_mock:
        yield respx_mock
