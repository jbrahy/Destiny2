"""Read-only audit of what Bungie's ItemReusablePlugs component actually contains.

Component 310 has been requested in PROFILE_COMPONENTS since the first commit but
never parsed, so nobody knows what it returns for a NON-CRAFTED random roll. That
matters: if Bungie returns the full randomized plug set for every legendary rather
than only for craftable ones, expanding perk options for all weapons would rate the
entire vault a god roll.

This script answers that question from real cached data instead of inference. It is
the gate for widening `score_uncrafted_perk_options` — do not flip that flag on a
guess, flip it on this output.

Reads only. Touches no Bungie API, writes nothing.

    python -m scripts.audit_perk_options            # every user with a cached profile
    python -m scripts.audit_perk_options --user 3   # one user
    python -m scripts.audit_perk_options --verbose  # per-weapon detail
"""
import argparse
import asyncio
import json
from collections import Counter

import aiomysql

from app.config import get_settings
from app.manifest import load_cached_manifest

_CRAFTED_STATE = 8


def summarize(profile: dict, manifest) -> dict:
    """Count per-socket plug options per weapon, split by crafted vs not.

    Deliberately does NOT reuse assemble_weapons: this must observe the raw
    component as Bungie sends it, before any filtering this codebase applies.
    """
    components = profile.get("itemComponents", {})
    sockets = components.get("sockets", {}).get("data", {})
    reusable = components.get("reusablePlugs", {}).get("data", {})

    rows = []
    for entry in _iter_items(profile):
        instance_id = entry.get("itemInstanceId")
        item_hash = entry.get("itemHash")
        if not instance_id or not manifest.is_weapon(item_hash):
            continue
        socket_list = sockets.get(instance_id, {}).get("sockets", [])
        plugs = reusable.get(instance_id, {}).get("plugs", {})

        per_socket = []
        for idx, sock in enumerate(socket_list):
            active = sock.get("plugHash")
            options = plugs.get(str(idx), [])
            hashes = {p.get("plugItemHash") for p in options if p.get("plugItemHash")}
            if active is not None:
                hashes.add(active)
            # Only count sockets this app would treat as perks.
            perk_hashes = [h for h in hashes if _looks_like_perk(manifest, h)]
            if perk_hashes:
                per_socket.append((idx, len(perk_hashes),
                                   [manifest.name(h) for h in sorted(perk_hashes)]))

        rows.append({
            "instanceId": instance_id,
            "name": manifest.name(item_hash),
            "crafted": bool(entry.get("state", 0) & _CRAFTED_STATE),
            "hasReusableComponent": instance_id in reusable,
            "columns": per_socket,
            "maxOptions": max((n for _, n, _ in per_socket), default=0),
        })
    return {"weapons": rows}


def _looks_like_perk(manifest, plug_hash: int) -> bool:
    from app.bungie_client import _NON_PERK_TYPES
    name = manifest.name(plug_hash)
    return manifest.item_type(plug_hash) not in _NON_PERK_TYPES and not name.startswith("Unknown (")


def _iter_items(profile: dict):
    buckets = [profile.get("profileInventory", {}).get("data", {})]
    buckets += list(profile.get("characterInventories", {}).get("data", {}).values())
    buckets += list(profile.get("characterEquipment", {}).get("data", {}).values())
    for entry in buckets:
        for item in entry.get("items", []):
            yield item


def report(rows: list[dict], verbose: bool) -> None:
    crafted = [r for r in rows if r["crafted"]]
    uncrafted = [r for r in rows if not r["crafted"]]
    multi_uncrafted = [r for r in uncrafted if r["maxOptions"] > 1]
    multi_crafted = [r for r in crafted if r["maxOptions"] > 1]

    print(f"weapons scanned:            {len(rows)}")
    print(f"  crafted:                  {len(crafted)}")
    print(f"  not crafted:              {len(uncrafted)}")
    print(f"with reusablePlugs present: {sum(1 for r in rows if r['hasReusableComponent'])}")
    print()
    print(f"CRAFTED with >1 option in some column:     {len(multi_crafted)}")
    print(f"NOT CRAFTED with >1 option in some column: {len(multi_uncrafted)}   <-- the answer")
    print()
    if multi_uncrafted:
        print("A non-crafted weapon reporting multiple options means reusablePlugs is NOT")
        print("crafted-only. Expanding options for all weapons would inflate verdicts.")
        print("KEEP the crafted gate. Sample:")
        for r in multi_uncrafted[:5]:
            widest = max(r["columns"], key=lambda c: c[1])
            print(f"  {r['name']}: socket {widest[0]} has {widest[1]} options -> {widest[2][:4]}")
    else:
        print("No non-crafted weapon reports alternates. reusablePlugs appears to be")
        print("crafted-only in this data, so widening the gate would likely be safe --")
        print("but this is one account's inventory, not a guarantee.")

    dist = Counter(r["maxOptions"] for r in rows)
    print()
    print("max options in any column -> weapon count:", dict(sorted(dist.items())))

    if verbose:
        print("\n--- per weapon ---")
        for r in sorted(rows, key=lambda r: -r["maxOptions"]):
            flag = "CRAFTED" if r["crafted"] else "       "
            print(f"{flag} max={r['maxOptions']:2d} {r['name']}")
            for idx, count, names in r["columns"]:
                if count > 1:
                    print(f"           socket {idx}: {count} -> {names}")


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=int, help="user_id (default: every cached profile)")
    parser.add_argument("--verbose", action="store_true", help="per-weapon detail")
    args = parser.parse_args()

    s = get_settings()
    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=s.db_name, autocommit=True,
    )
    try:
        manifest = await load_cached_manifest(pool)
        if manifest is None:
            print("No cached manifest. Open the Weapons tab once, then re-run.")
            return

        async with pool.acquire() as conn, conn.cursor() as cur:
            if args.user is not None:
                await cur.execute(
                    "SELECT user_id, value FROM user_cache WHERE cache_key='profile_cache' "
                    "AND user_id=%s", (args.user,),
                )
            else:
                await cur.execute(
                    "SELECT user_id, value FROM user_cache WHERE cache_key='profile_cache'"
                )
            found = await cur.fetchall()

        if not found:
            print("No cached profile found. Open the Weapons tab once, then re-run.")
            return

        for user_id, raw in found:
            print(f"\n=== user_id {user_id} ===")
            rows = summarize(json.loads(raw), manifest)["weapons"]
            report(rows, args.verbose)
    finally:
        pool.close()
        await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(_main())
