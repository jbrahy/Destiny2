"""Tests for the async manifest cache functions (Task 11).

These tests verify that load_cached_manifest and load_manifest correctly
interact with the MySQL manifest_cache repository instead of SQLite kv_get/kv_set.
"""
import json
import pytest

from app.repositories import cache
from app.manifest import load_cached_manifest, load_manifest
from app.bungie_throttle import Throttle

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeResponse:
    """Minimal httpx-like response object."""

    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass  # always 200

    def json(self) -> dict:
        return self._payload


class FakeClient:
    """Fake async httpx client that records which URLs were fetched."""

    def __init__(self, responses: dict[str, dict]):
        """responses maps URL (substring or exact) to the dict payload to return."""
        self._responses = responses
        self.fetched_urls: list[str] = []

    async def get(self, url: str, **kwargs) -> FakeResponse:
        self.fetched_urls.append(url)
        for key, payload in self._responses.items():
            if key in url:
                return FakeResponse(payload)
        raise ValueError(f"FakeClient: unexpected URL {url!r}")


# ---------------------------------------------------------------------------
# Test 1: load_cached_manifest reconstructs Manifest with int keys
# ---------------------------------------------------------------------------

async def test_load_cached_manifest_reconstructs(clean_db):
    items_data = {"123": {"displayProperties": {"name": "Gun", "description": "", "icon": ""}}}
    stats_data = {"4": {"displayProperties": {"name": "Range"}}}

    await cache.manifest_set(clean_db, "manifest_items", json.dumps(items_data), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps(stats_data), "v1")

    m = await load_cached_manifest(clean_db)

    assert m is not None
    assert m.name(123) == "Gun"
    assert m.stat_name(4) == "Range"


# ---------------------------------------------------------------------------
# Test 2: load_cached_manifest returns None when DB is empty
# ---------------------------------------------------------------------------

async def test_load_cached_manifest_none_when_empty(clean_db):
    # clean_db truncates manifest_cache before each test
    result = await load_cached_manifest(clean_db)
    assert result is None


# ---------------------------------------------------------------------------
# Test 3: load_manifest returns cached Manifest when version matches
# ---------------------------------------------------------------------------

_META_PAYLOAD = {
    "Response": {
        "version": "v1",
        "jsonWorldComponentContentPaths": {
            "en": {
                "DestinyInventoryItemDefinition": "/common/destiny2_content/json/en/items.json",
                "DestinyStatDefinition": "/common/destiny2_content/json/en/stats.json",
                "DestinyPlugSetDefinition": "/common/destiny2_content/json/en/plugsets.json",
                "DestinyEquipableItemSetDefinition": "/common/destiny2_content/json/en/itemsets.json",
                "DestinySandboxPerkDefinition": "/common/destiny2_content/json/en/sandboxperks.json",
            }
        },
    }
}


async def test_load_manifest_uses_cache_when_version_matches(clean_db):
    items_data = {"555": {"displayProperties": {"name": "CachedGun", "description": "", "icon": ""}}}
    stats_data = {"7": {"displayProperties": {"name": "Stability"}}}
    plug_data = {"5002": {"reusablePlugItems": [{"plugItemHash": 11, "currentlyCanRoll": True}]}}
    set_data = {"900": {"displayProperties": {"name": "Techsec"}, "setItems": [10], "setPerks": []}}
    perk_data = {"7001": {"displayProperties": {"name": "Wrecker", "description": "x"}}}

    await cache.manifest_set(clean_db, "manifest_items", json.dumps(items_data), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps(stats_data), "v1")
    await cache.manifest_set(clean_db, "manifest_plugsets", json.dumps(plug_data), "v1")
    await cache.manifest_set(clean_db, "manifest_item_sets", json.dumps(set_data), "v1")
    await cache.manifest_set(clean_db, "manifest_sandbox_perks", json.dumps(perk_data), "v1")

    fake_client = FakeClient({"/Platform/Destiny2/Manifest/": _META_PAYLOAD})

    throttle = Throttle(2)
    m = await load_manifest(fake_client, clean_db, throttle)

    assert m is not None
    assert m.name(555) == "CachedGun"
    assert m.stat_name(7) == "Stability"
    assert m.plug_set_hashes(5002) == [11]

    # Only the meta URL should have been fetched — no definition downloads
    assert len(fake_client.fetched_urls) == 1
    assert "/Platform/Destiny2/Manifest/" in fake_client.fetched_urls[0]


async def test_load_manifest_redownloads_when_plug_sets_are_missing(clean_db):
    """A cache written before plug sets existed must pick them up on the next
    load, not sit without a roll pool until Bungie ships a new manifest version.
    """
    await cache.manifest_set(clean_db, "manifest_items", json.dumps({"555": {}}), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps({"7": {}}), "v1")
    # No manifest_plugsets row — the pre-plug-set state.

    fake_client = FakeClient({
        "/Platform/Destiny2/Manifest/": _META_PAYLOAD,
        "items.json": {"555": {"displayProperties": {"name": "FreshGun"}}},
        "stats.json": {"7": {"displayProperties": {"name": "Stability"}}},
        "plugsets.json": {"5002": {"reusablePlugItems": [
            {"plugItemHash": 11, "currentlyCanRoll": True}]}},
        "itemsets.json": {"900": {"displayProperties": {"name": "Techsec"},
                                  "setItems": [10], "setPerks": []}},
        "sandboxperks.json": {"7001": {"displayProperties": {"name": "Wrecker", "description": "x"}}},
    })

    m = await load_manifest(fake_client, clean_db, Throttle(2))

    assert m.name(555) == "FreshGun"
    assert m.plug_set_hashes(5002) == [11]
    assert any("plugsets.json" in u for u in fake_client.fetched_urls)
    # And it is persisted, so the next load hits cache.
    assert await cache.manifest_get(clean_db, "manifest_plugsets") is not None


async def test_load_manifest_redownloads_when_set_tables_are_missing(clean_db):
    """A cache predating the set tables picks them up on next load."""
    await cache.manifest_set(clean_db, "manifest_items", json.dumps({"1": {}}), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps({"2": {}}), "v1")
    await cache.manifest_set(clean_db, "manifest_plugsets", json.dumps({"3": {}}), "v1")
    # no manifest_item_sets / manifest_sandbox_perks

    fake_client = FakeClient({
        "/Platform/Destiny2/Manifest/": _META_PAYLOAD,
        "items.json": {"1": {"displayProperties": {"name": "Fresh"}}},
        "stats.json": {"2": {}},
        "plugsets.json": {"3": {}},
        "itemsets.json": {"900": {"displayProperties": {"name": "Techsec"},
                                  "setItems": [10], "setPerks": []}},
        "sandboxperks.json": {"7001": {"displayProperties": {"name": "Wrecker", "description": "x"}}},
    })

    m = await load_manifest(fake_client, clean_db, Throttle(2))

    assert m.set_items(900) == [10]
    assert m.perk_text(7001)[0] == "Wrecker"
    assert await cache.manifest_get(clean_db, "manifest_item_sets") is not None


async def test_load_cached_manifest_without_plug_sets_still_loads(clean_db):
    """Degrade, don't crash: old caches load with an empty roll pool."""
    await cache.manifest_set(clean_db, "manifest_items",
                             json.dumps({"1": {"displayProperties": {"name": "Old"}}}), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps({"2": {}}), "v1")

    m = await load_cached_manifest(clean_db)

    assert m is not None
    assert m.name(1) == "Old"
    assert m.plug_set_hashes(5002) == []
