import json
import pytest
from app.repositories import offers
from scripts import import_offers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def test_build_offer_uses_authored_then_fallback():
    row = {"offer_id": 7, "name": "Cool Offer", "advertiser": "Acme",
           "category": "eComm", "countries": "US", "payout_type": "CPA",
           "payout_amount": "10.0", "tracking_url": "https://t/7", "preview_url": ""}
    authored = {"7": {"headline": "Win Big", "blurb": "Do it", "cta": "Claim"}}
    o = import_offers.build_offer(row, authored)
    assert o["headline"] == "Win Big" and o["cta"] == "Claim"
    o2 = import_offers.build_offer(row, {})
    assert o2["headline"] == "Cool Offer" and o2["cta"] == "Learn more"
    assert o2["image_url"] is None


async def test_run_imports_and_pauses(tmp_path, clean_db):
    manifest = [
        {"offer_id": 1, "name": "A", "advertiser": "x", "category": "c",
         "countries": "US", "payout_type": "CPA", "payout_amount": "1.0",
         "tracking_url": "https://t/1", "preview_url": ""},
        {"offer_id": 2, "name": "B", "advertiser": "y", "category": "c",
         "countries": "US", "payout_type": "CPA", "payout_amount": "2.0",
         "tracking_url": "https://t/2", "preview_url": ""},
    ]
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    cpath = tmp_path / "c.json"
    cpath.write_text(json.dumps({}))
    res = await import_offers.run(clean_db, str(mpath), str(cpath))
    assert res["imported"] == 2
    assert await offers.get_active(clean_db, 1) is not None
    # re-run with only offer 1 -> offer 2 paused
    mpath.write_text(json.dumps([manifest[0]]))
    res2 = await import_offers.run(clean_db, str(mpath), str(cpath))
    assert res2["paused"] >= 1
    assert await offers.get_active(clean_db, 2) is None
