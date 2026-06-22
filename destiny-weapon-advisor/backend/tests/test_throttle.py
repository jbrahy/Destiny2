import asyncio
import httpx
import pytest

from app.bungie_throttle import Throttle

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _resp(status):
    return httpx.Response(status, request=httpx.Request("GET", "http://x"))


@pytest.mark.asyncio
async def test_retries_429_then_succeeds():
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.HTTPStatusError(
                "429", request=_resp(429).request, response=_resp(429)
            )
        return "ok"

    t = Throttle(concurrency=2)
    assert await t.run(factory) == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_concurrency_capped():
    cur = {"n": 0, "max": 0}

    async def factory():
        cur["n"] += 1
        cur["max"] = max(cur["max"], cur["n"])
        await asyncio.sleep(0.01)
        cur["n"] -= 1
        return 1

    t = Throttle(concurrency=3)
    await asyncio.gather(*[t.run(factory) for _ in range(20)])
    assert cur["max"] <= 3
