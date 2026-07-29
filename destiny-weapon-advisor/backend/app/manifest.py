import json
from dataclasses import dataclass, field

from app.repositories import cache

_BASE = "https://www.bungie.net"
_AMMO_TYPES = {1: "Primary", 2: "Special", 3: "Heavy"}


@dataclass
class Manifest:
    items: dict[int, dict] = field(default_factory=dict)
    stats: dict[int, dict] = field(default_factory=dict)
    plug_sets: dict[int, dict] = field(default_factory=dict)

    def _def(self, item_hash: int) -> dict:
        return self.items.get(item_hash, {})

    def name(self, item_hash: int) -> str:
        dp = self._def(item_hash).get("displayProperties", {})
        return dp.get("name") or f"Unknown ({item_hash})"

    def item_type(self, item_hash: int) -> str:
        return self._def(item_hash).get("itemTypeDisplayName", "")

    def description(self, item_hash: int) -> str:
        return self._def(item_hash).get("displayProperties", {}).get("description", "")

    def icon(self, item_hash: int) -> str:
        return self._def(item_hash).get("displayProperties", {}).get("icon", "")

    def tier_type(self, item_hash: int) -> int:
        return self._def(item_hash).get("inventory", {}).get("tierType", 0)

    def bucket_hash(self, item_hash: int) -> int:
        """The item's home inventory bucket. Read from the definition, not the
        profile: a vault-held item reports the vault bucket in the profile."""
        return self._def(item_hash).get("inventory", {}).get("bucketTypeHash", 0)

    def is_weapon(self, item_hash: int) -> bool:
        return self._def(item_hash).get("itemType") == 3

    def is_armor(self, item_hash: int) -> bool:
        return self._def(item_hash).get("itemType") == 2

    def item_class_type(self, item_hash: int) -> int:
        return self._def(item_hash).get("classType", 3)

    def ammo_type(self, item_hash: int) -> str:
        ammo = self._def(item_hash).get("equippingBlock", {}).get("ammoType", 0)
        return _AMMO_TYPES.get(ammo, "")

    def socket_entries(self, item_hash: int) -> list[dict]:
        """The item's socket definitions, in socket-index order."""
        return self._def(item_hash).get("sockets", {}).get("socketEntries", [])

    def plug_set_hashes(self, plug_set_hash: int, only_current: bool = False) -> list[int]:
        """Plug hashes in a DestinyPlugSetDefinition.

        `only_current` keeps just plugs that can still drop — a chase list must
        not send someone farming a perk that has left the loot pool.
        Returns [] for an unknown set, and for manifests cached before plug sets
        were downloaded at all.
        """
        entries = self.plug_sets.get(plug_set_hash, {}).get("reusablePlugItems", [])
        return [
            e["plugItemHash"] for e in entries
            if e.get("plugItemHash") is not None
            and (not only_current or e.get("currentlyCanRoll"))
        ]

    def is_trait(self, plug_hash: int) -> bool:
        """True for the perks that actually determine a weapon's quality.

        Positive filter on "Trait" — Barrel, Magazine, Guard, Blade, Origin Trait
        and Weapon Mod are all distinct itemTypeDisplayName values, and the
        existing _NON_PERK_TYPES negative filter excludes none of them.
        """
        return self.item_type(plug_hash) == "Trait"

    def stat_name(self, stat_hash: int) -> str:
        dp = self.stats.get(stat_hash, {}).get("displayProperties", {})
        return dp.get("name", "")


async def load_cached_manifest(pool) -> "Manifest | None":
    """Load the manifest from the MySQL cache only (no network). Returns None
    if it has not been downloaded yet."""
    raw = await cache.manifest_get(pool, "manifest_items")
    raw_stats = await cache.manifest_get(pool, "manifest_stats")
    if not raw or not raw_stats:
        return None
    # Plug sets are optional: caches written before they were downloaded still
    # load, they just yield no roll pools until the next manifest refresh.
    raw_plugs = await cache.manifest_get(pool, "manifest_plugsets")
    return Manifest(
        items={int(k): v for k, v in json.loads(raw).items()},
        stats={int(k): v for k, v in json.loads(raw_stats).items()},
        plug_sets={int(k): v for k, v in json.loads(raw_plugs).items()} if raw_plugs else {},
    )


async def load_manifest(client, pool, throttle) -> "Manifest":
    """Load the manifest. The passed httpx client MUST be constructed with an
    'X-API-Key' default header — the Bungie /Platform manifest endpoint requires it."""
    meta = await throttle.run(lambda: client.get(f"{_BASE}/Platform/Destiny2/Manifest/"))
    meta.raise_for_status()
    data = meta.json()["Response"]
    version = data["version"]
    cached_version = await cache.manifest_version(pool)

    if cached_version == version:
        raw = await cache.manifest_get(pool, "manifest_items")
        raw_stats = await cache.manifest_get(pool, "manifest_stats")
        raw_plugs = await cache.manifest_get(pool, "manifest_plugsets")
        # Re-download when plug sets are absent even at a matching version, so
        # an existing cache picks them up without waiting for a Bungie release.
        if raw and raw_stats and raw_plugs:
            return Manifest(
                items={int(k): v for k, v in json.loads(raw).items()},
                stats={int(k): v for k, v in json.loads(raw_stats).items()},
                plug_sets={int(k): v for k, v in json.loads(raw_plugs).items()},
            )

    paths = data["jsonWorldComponentContentPaths"]["en"]
    defs = await throttle.run(
        lambda: client.get(f"{_BASE}{paths['DestinyInventoryItemDefinition']}", timeout=120.0)
    )
    defs.raise_for_status()
    items = defs.json()
    stat_defs = await throttle.run(
        lambda: client.get(f"{_BASE}{paths['DestinyStatDefinition']}", timeout=120.0)
    )
    stat_defs.raise_for_status()
    stats = stat_defs.json()
    # ~10 MB against the item table's ~204 MB. Holds each socket's roll pool,
    # which is the only place a weapon's possible traits are enumerated.
    plug_defs = await throttle.run(
        lambda: client.get(f"{_BASE}{paths['DestinyPlugSetDefinition']}", timeout=120.0)
    )
    plug_defs.raise_for_status()
    plug_sets = plug_defs.json()
    await cache.manifest_set(pool, "manifest_items", json.dumps(items), version)
    await cache.manifest_set(pool, "manifest_stats", json.dumps(stats), version)
    await cache.manifest_set(pool, "manifest_plugsets", json.dumps(plug_sets), version)
    return Manifest(
        items={int(k): v for k, v in items.items()},
        stats={int(k): v for k, v in stats.items()},
        plug_sets={int(k): v for k, v in plug_sets.items()},
    )
