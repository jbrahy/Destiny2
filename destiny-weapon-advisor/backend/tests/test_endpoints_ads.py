import pytest
from app.repositories import offers

pytestmark = pytest.mark.asyncio(loop_scope="session")

from tests.conftest import login_user


async def _seed(pool, oid):
    await offers.upsert(pool, {"offer_id": oid, "name": f"O{oid}", "category": "Gaming",
        "advertiser": "A", "countries": "US", "payout_type": "CPA", "payout_amount": "8.0",
        "tracking_url": f"https://track.example/{oid}", "headline": f"H{oid}", "blurb": "b",
        "cta": "Go", "image_url": None, "status": "active"})


async def test_ads_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/ads")
    assert r.status_code == 401


async def test_ads_returns_capped_list_with_click_url(app_client, monkeypatch, clean_db):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-ads")
    for i in range(1, 7):
        await _seed(clean_db, i)
    r = await app_client.get("/api/ads?n=4")
    assert r.status_code == 200
    ads = r.json()["ads"]
    assert len(ads) == 4
    a = ads[0]
    assert set(a) >= {"offer_id", "headline", "blurb", "cta", "image_url", "click_url"}
    assert a["click_url"] == f"/api/ads/{a['offer_id']}/click"


async def test_click_logs_and_redirects(app_client, monkeypatch, clean_db):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-ads2")
    await _seed(clean_db, 42)
    r = await app_client.get("/api/ads/42/click", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://track.example/42"
    from app import db
    cnt = await db.fetchone(clean_db, "SELECT COUNT(*) FROM ad_clicks WHERE offer_id=42 AND user_id=%s", (uid,))
    assert cnt[0] == 1


async def test_click_unknown_offer_404(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ads3")
    r = await app_client.get("/api/ads/123456/click", follow_redirects=False)
    assert r.status_code == 404
