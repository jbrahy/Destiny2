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

async def test_load_manifest_uses_cache_when_version_matches(clean_db):
    items_data = {"555": {"displayProperties": {"name": "CachedGun", "description": "", "icon": ""}}}
    stats_data = {"7": {"displayProperties": {"name": "Stability"}}}

    await cache.manifest_set(clean_db, "manifest_items", json.dumps(items_data), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps(stats_data), "v1")

    meta_payload = {
        "Response": {
            "version": "v1",
            "jsonWorldComponentContentPaths": {
                "en": {
                    "DestinyInventoryItemDefinition": "/common/destiny2_content/json/en/items.json",
                    "DestinyStatDefinition": "/common/destiny2_content/json/en/stats.json",
                }
            },
        }
    }

    fake_client = FakeClient({
        "/Platform/Destiny2/Manifest/": meta_payload,
    })

    throttle = Throttle(2)
    m = await load_manifest(fake_client, clean_db, throttle)

    assert m is not None
    assert m.name(555) == "CachedGun"
    assert m.stat_name(7) == "Stability"

    # Only the meta URL should have been fetched — no definition downloads
    assert len(fake_client.fetched_urls) == 1
    assert "/Platform/Destiny2/Manifest/" in fake_client.fetched_urls[0]
