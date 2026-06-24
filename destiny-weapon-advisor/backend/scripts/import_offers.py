import asyncio
import json
from pathlib import Path

import aiomysql

from app.config import get_settings
from app.repositories import offers

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_MANIFEST_PATH = _REPO_ROOT / "docs" / "offers" / "270920-offers-manifest.json"
_CREATIVES_PATH = Path(__file__).parent.parent / "app" / "data" / "offer_creatives.json"


def build_offer(manifest_row: dict, creatives: dict) -> dict:
    """Pure function: merge manifest row with authored creative (with fallback)."""
    offer_id = manifest_row["offer_id"]
    key = str(offer_id)
    if key in creatives:
        headline = creatives[key]["headline"]
        blurb = creatives[key]["blurb"]
        cta = creatives[key]["cta"]
    else:
        headline = manifest_row["name"]
        blurb = f'{manifest_row["advertiser"]} — check out this offer.'
        cta = "Learn more"

    image_url = manifest_row.get("preview_url") or None

    return {
        "offer_id": offer_id,
        "name": manifest_row["name"],
        "category": manifest_row.get("category", ""),
        "advertiser": manifest_row.get("advertiser", ""),
        "countries": manifest_row.get("countries", ""),
        "payout_type": manifest_row.get("payout_type", ""),
        "payout_amount": manifest_row.get("payout_amount", 0),
        "tracking_url": manifest_row["tracking_url"],
        "headline": headline,
        "blurb": blurb,
        "cta": cta,
        "image_url": image_url,
    }


async def run(pool, manifest_path: str, creatives_path: str) -> dict:
    """Load manifest and creatives, upsert all offers, pause missing ones."""
    manifest = json.loads(Path(manifest_path).read_text())
    creatives = json.loads(Path(creatives_path).read_text())

    for row in manifest:
        await offers.upsert(pool, build_offer(row, creatives))

    keep_ids = [int(r["offer_id"]) for r in manifest]
    paused = await offers.pause_missing(pool, keep_ids)

    return {"imported": len(manifest), "paused": paused}


async def _main():
    s = get_settings()
    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=s.db_name, autocommit=False,
    )
    try:
        result = await run(pool, str(_MANIFEST_PATH), str(_CREATIVES_PATH))
        print(f"imported: {result['imported']}, paused: {result['paused']}")
    finally:
        pool.close()
        await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(_main())
