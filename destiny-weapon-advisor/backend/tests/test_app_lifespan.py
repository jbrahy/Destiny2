import pytest
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_lifespan_sets_pool_and_health_ok():
    from app.main import app
    async with LifespanManager(app):
        assert hasattr(app.state, "pool") and app.state.pool is not None
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/api/health")
            assert r.status_code == 200 and r.json() == {"status": "ok"}
