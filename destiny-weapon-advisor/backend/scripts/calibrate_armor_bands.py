"""Read-only focus distribution over a real armour collection.

Verdict bands must carve an actual collection sensibly. Guessing them produces
a scorer that calls half a vault "top roll". Run this, read the percentiles,
then set app/data/armor_scoring_seed.json.

    python -m scripts.calibrate_armor_bands --user 1
"""
import argparse
import asyncio
import json

import aiomysql

from app.armor_scoring import focus
from app.bungie_client import assemble_armor
from app.config import get_settings
from app.manifest import load_cached_manifest


def _pct(values: list[int], p: float) -> int:
    return values[min(int(len(values) * p), len(values) - 1)] if values else 0


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=int, default=1)
    args = parser.parse_args()

    s = get_settings()
    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=s.db_name, autocommit=True,
    )
    try:
        manifest = await load_cached_manifest(pool)
        if manifest is None:
            print("No cached manifest. Open the Weapons tab, then re-run.")
            return
        async with pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT value FROM user_cache WHERE cache_key='profile_cache' AND user_id=%s",
                (args.user,),
            )
            row = await cur.fetchone()
        if not row:
            print("No cached profile. Open the Weapons tab and Refresh, then re-run.")
            return

        armor = assemble_armor(json.loads(row[0]), manifest)
        legendary = [a for a in armor if not a.is_exotic and a.stats]
        values = sorted(focus(a.stats) for a in legendary)
        print(f"legendary pieces with stats: {len(values)}  (exotics are auto-keeps)")
        print()
        for p in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
            print(f"   p{int(p * 100):<3} focus = {_pct(values, p)}")
        print(f"   max      focus = {values[-1] if values else 0}")
        print()
        print("Suggested starting bands (tune to taste):")
        print(f'   "top_roll": {_pct(values, 0.90)},   # top ~10%')
        print(f'   "good":     {_pct(values, 0.60)},   # top ~40%')
        print(f'   "ok":       {_pct(values, 0.25)}    # bottom ~25% become dismantle')
    finally:
        pool.close()
        await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(_main())
