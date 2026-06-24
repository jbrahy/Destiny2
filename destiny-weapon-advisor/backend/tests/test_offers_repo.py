import pytest
from app.repositories import offers, users

pytestmark = pytest.mark.asyncio(loop_scope="session")

def _offer(oid, status="active"):
    return {"offer_id": oid, "name": f"Offer {oid}", "category": "Gaming",
            "advertiser": "Adv", "countries": "US", "payout_type": "CPA",
            "payout_amount": "8.0", "tracking_url": f"https://t/{oid}",
            "headline": f"H{oid}", "blurb": "b", "cta": "Go", "image_url": None,
            "status": status}

async def test_upsert_and_get_active(clean_db):
    await offers.upsert(clean_db, _offer(1))
    got = await offers.get_active(clean_db, 1)
    assert got["offer_id"] == 1 and got["tracking_url"] == "https://t/1"
    assert await offers.get_active(clean_db, 999) is None

async def test_upsert_idempotent_updates(clean_db):
    await offers.upsert(clean_db, _offer(1))
    o = _offer(1); o["headline"] = "NEW"
    await offers.upsert(clean_db, o)
    assert (await offers.get_active(clean_db, 1))["headline"] == "NEW"

async def test_list_random_active_only_active_and_capped(clean_db):
    for i in range(1, 6):
        await offers.upsert(clean_db, _offer(i))
    await offers.upsert(clean_db, _offer(99, status="paused"))
    rows = await offers.list_random_active(clean_db, 4)
    assert len(rows) == 4
    assert all(r["status"] == "active" for r in rows)
    assert 99 not in [r["offer_id"] for r in rows]

async def test_pause_missing(clean_db):
    for i in range(1, 4):
        await offers.upsert(clean_db, _offer(i))
    paused = await offers.pause_missing(clean_db, [1, 2])
    assert paused == 1
    assert await offers.get_active(clean_db, 3) is None  # now paused
    assert await offers.get_active(clean_db, 1) is not None

async def test_log_click(clean_db):
    uid = await users.upsert(clean_db, "bm-click", "G", 3, "mid")
    await offers.upsert(clean_db, _offer(1))
    await offers.log_click(clean_db, 1, uid)
    from app import db
    cnt = await db.fetchone(clean_db, "SELECT COUNT(*) FROM ad_clicks WHERE offer_id=%s AND user_id=%s", (1, uid))
    assert cnt[0] == 1
