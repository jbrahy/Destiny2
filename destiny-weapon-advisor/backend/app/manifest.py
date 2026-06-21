import json
import sqlite3
from dataclasses import dataclass, field

import httpx

from app.storage import kv_get, kv_set

_BASE = "https://www.bungie.net"
_API_KEY_HEADER = "X-API-Key"


@dataclass
class Manifest:
    items: dict[int, dict] = field(default_factory=dict)

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


async def load_manifest(client: httpx.AsyncClient, conn: sqlite3.Connection) -> Manifest:
    meta = await client.get(f"{_BASE}/Platform/Destiny2/Manifest/")
    meta.raise_for_status()
    data = meta.json()["Response"]
    version = data["version"]
    cached_version = kv_get(conn, "manifest_version")

    if cached_version == version:
        raw = kv_get(conn, "manifest_items")
        if raw:
            return Manifest(items={int(k): v for k, v in json.loads(raw).items()})

    path = data["jsonWorldComponentContentPaths"]["en"]["DestinyInventoryItemDefinition"]
    defs = await client.get(f"{_BASE}{path}", timeout=120.0)
    defs.raise_for_status()
    items = defs.json()
    kv_set(conn, "manifest_items", json.dumps(items))
    kv_set(conn, "manifest_version", version)
    return Manifest(items={int(k): v for k, v in items.items()})
