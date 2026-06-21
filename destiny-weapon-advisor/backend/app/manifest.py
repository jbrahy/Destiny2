import json
import sqlite3
from dataclasses import dataclass, field

import httpx

from app.storage import kv_get, kv_set

_BASE = "https://www.bungie.net"
_AMMO_TYPES = {1: "Primary", 2: "Special", 3: "Heavy"}


@dataclass
class Manifest:
    items: dict[int, dict] = field(default_factory=dict)
    stats: dict[int, dict] = field(default_factory=dict)

    def _def(self, item_hash: int) -> dict:
        return self.items.get(item_hash, {})

    def name(self, item_hash: int) -> str:
        dp = self._def(item_hash).get("displayProperties", {})
        return dp.get("name") or f"Unknown ({item_hash})"

    def item_type(self, item_hash: int) -> str:
        return self._def(item_hash).get("itemTypeDisplayName", "")

    def tier_type(self, item_hash: int) -> int:
        return self._def(item_hash).get("inventory", {}).get("tierType", 0)

    def is_weapon(self, item_hash: int) -> bool:
        return self._def(item_hash).get("itemType") == 3

    def ammo_type(self, item_hash: int) -> str:
        ammo = self._def(item_hash).get("equippingBlock", {}).get("ammoType", 0)
        return _AMMO_TYPES.get(ammo, "")

    def stat_name(self, stat_hash: int) -> str:
        dp = self.stats.get(stat_hash, {}).get("displayProperties", {})
        return dp.get("name", "")


def load_cached_manifest(conn: sqlite3.Connection) -> Manifest | None:
    """Load the manifest from the local cache only (no network). Returns None
    if it has not been downloaded yet."""
    raw = kv_get(conn, "manifest_items")
    raw_stats = kv_get(conn, "manifest_stats")
    if not raw or not raw_stats:
        return None
    return Manifest(
        items={int(k): v for k, v in json.loads(raw).items()},
        stats={int(k): v for k, v in json.loads(raw_stats).items()},
    )


async def load_manifest(client: httpx.AsyncClient, conn: sqlite3.Connection) -> Manifest:
    """Load the manifest. The passed httpx client MUST be constructed with an
    'X-API-Key' default header — the Bungie /Platform manifest endpoint requires it."""
    meta = await client.get(f"{_BASE}/Platform/Destiny2/Manifest/")
    meta.raise_for_status()
    data = meta.json()["Response"]
    version = data["version"]
    cached_version = kv_get(conn, "manifest_version")

    if cached_version == version:
        raw = kv_get(conn, "manifest_items")
        raw_stats = kv_get(conn, "manifest_stats")
        if raw and raw_stats:
            return Manifest(
                items={int(k): v for k, v in json.loads(raw).items()},
                stats={int(k): v for k, v in json.loads(raw_stats).items()},
            )

    paths = data["jsonWorldComponentContentPaths"]["en"]
    defs = await client.get(f"{_BASE}{paths['DestinyInventoryItemDefinition']}", timeout=120.0)
    defs.raise_for_status()
    items = defs.json()
    stat_defs = await client.get(f"{_BASE}{paths['DestinyStatDefinition']}", timeout=120.0)
    stat_defs.raise_for_status()
    stats = stat_defs.json()
    kv_set(conn, "manifest_items", json.dumps(items))
    kv_set(conn, "manifest_stats", json.dumps(stats))
    kv_set(conn, "manifest_version", version)
    return Manifest(
        items={int(k): v for k, v in items.items()},
        stats={int(k): v for k, v in stats.items()},
    )
