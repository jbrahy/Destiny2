"""Tests for per-user data repositories: perk_ratings, builds, user_tables."""
import pytest
import pytest_asyncio

from app.repositories import users as users_repo
from app.repositories import perk_ratings as perk_ratings_repo
from app.repositories import builds as builds_repo
from app.repositories import user_tables as user_tables_repo

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def two_users(clean_db):
    """Create two users and return (pool, user_a_id, user_b_id)."""
    pool = clean_db
    uid_a = await users_repo.upsert(pool, "bungieA", "UserA", 3, "mbrA")
    uid_b = await users_repo.upsert(pool, "bungieB", "UserB", 3, "mbrB")
    return pool, uid_a, uid_b


# ---------------------------------------------------------------------------
# Perk ratings
# ---------------------------------------------------------------------------

async def test_perk_ratings_isolation(two_users):
    """User A override does not affect user B."""
    pool, uid_a, uid_b = two_users

    # Save an override for user A
    await perk_ratings_repo.save(
        pool, uid_a,
        perk_name="Wellspring", weapon_type="Auto Rifle",
        rating="S", reason="top tier", tags=["pve", "healing"], notes="great synergy"
    )

    ratings_a = await perk_ratings_repo.load(pool, uid_a)
    ratings_b = await perk_ratings_repo.load(pool, uid_b)

    entry_a = ratings_a.get("Wellspring", "Auto Rifle")
    assert entry_a is not None
    assert entry_a["rating"] == "S"
    assert entry_a["reason"] == "top tier"
    assert "pve" in entry_a["tags"]
    assert entry_a["notes"] == "great synergy"
    # is_override returns True for A
    assert ratings_a.is_override("Wellspring", "Auto Rifle")

    # B should NOT see the override (sees seed or None)
    assert not ratings_b.is_override("Wellspring", "Auto Rifle")


async def test_perk_ratings_empty_tags(two_users):
    """Tags=[] round-trips as empty list."""
    pool, uid_a, _ = two_users

    await perk_ratings_repo.save(
        pool, uid_a,
        perk_name="Demolitionist", weapon_type="",
        rating="A", reason="", tags=[], notes=""
    )
    ratings_a = await perk_ratings_repo.load(pool, uid_a)
    entry = ratings_a.get("Demolitionist", "")
    assert entry["tags"] == []


# ---------------------------------------------------------------------------
# Builds
# ---------------------------------------------------------------------------

async def test_builds_isolation(two_users):
    """save_build for A overrides the seed key for A only; B still sees seed."""
    pool, uid_a, uid_b = two_users

    # Get the first seed build key
    from app.builds import _seed_builds
    seed = _seed_builds()
    first_key = next(iter(seed))
    original_data = seed[first_key]

    custom_data = {"description": "custom for A", "notes": "A only"}
    await builds_repo.save_build(pool, uid_a, first_key, custom_data)

    builds_a = await builds_repo.load_builds(pool, uid_a)
    builds_b = await builds_repo.load_builds(pool, uid_b)

    assert builds_a[first_key] == {**original_data, **custom_data}
    assert builds_b[first_key] == original_data


async def test_a_saved_build_keeps_seed_fields_it_never_knew_about(two_users):
    """Overrides saved before a field was added to the seed must not drop it.

    statPriority landed after users had already saved builds; a wholesale
    replace silently degraded their outfits to subclass-blind armour picks
    forever, with nothing to signal it.
    """
    pool, uid_a, _ = two_users

    from app.builds import _seed_builds
    key = next(iter(_seed_builds()))

    legacy_row = {"description": "saved before statPriority existed"}
    await builds_repo.save_build(pool, uid_a, key, legacy_row)

    build = (await builds_repo.load_builds(pool, uid_a))[key]
    assert build["description"] == legacy_row["description"]
    assert build["statPriority"], "seed statPriority was dropped by the override"


async def test_builds_new_key_for_a(two_users):
    """New build key added for A does not appear in B."""
    pool, uid_a, uid_b = two_users

    new_key = "TestClass|TestSubclass"
    new_data = {"description": "brand new"}
    await builds_repo.save_build(pool, uid_a, new_key, new_data)

    builds_a = await builds_repo.load_builds(pool, uid_a)
    builds_b = await builds_repo.load_builds(pool, uid_b)

    assert builds_a[new_key] == new_data
    assert new_key not in builds_b


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

async def test_activities_isolation(two_users):
    """save_activity overrides for A only; B still sees seed."""
    pool, uid_a, uid_b = two_users

    from app.builds import _seed_activities
    seed = _seed_activities()
    first_activity = seed[0]
    activity_name = first_activity["name"]

    custom = {**first_activity, "notes": "A custom notes"}
    await builds_repo.save_activity(pool, uid_a, activity_name, custom)

    acts_a = await builds_repo.load_activities(pool, uid_a)
    acts_b = await builds_repo.load_activities(pool, uid_b)

    act_a = next(a for a in acts_a if a["name"] == activity_name)
    act_b = next(a for a in acts_b if a["name"] == activity_name)

    assert act_a["notes"] == "A custom notes"
    assert act_b["notes"] == first_activity["notes"]


async def test_activities_user_only(two_users):
    """User-only activity (not in seed) appears for A but not B."""
    pool, uid_a, uid_b = two_users

    user_only_name = "Custom Raid for A"
    custom = {"name": user_only_name, "description": "only A's raid"}
    await builds_repo.save_activity(pool, uid_a, user_only_name, custom)

    acts_a = await builds_repo.load_activities(pool, uid_a)
    acts_b = await builds_repo.load_activities(pool, uid_b)

    names_a = {a["name"] for a in acts_a}
    names_b = {a["name"] for a in acts_b}

    assert user_only_name in names_a
    assert user_only_name not in names_b


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

async def test_tags_set_and_get(two_users):
    """set_tag then get_tags returns the tag for correct user."""
    pool, uid_a, uid_b = two_users

    instance_id = "item123"
    await user_tables_repo.set_tag(pool, uid_a, instance_id, "keep")

    tags_a = await user_tables_repo.get_tags(pool, uid_a)
    tags_b = await user_tables_repo.get_tags(pool, uid_b)

    assert tags_a.get(instance_id) == "keep"
    assert instance_id not in tags_b


async def test_tags_clear(two_users):
    """set_tag with empty string removes the tag."""
    pool, uid_a, _ = two_users

    instance_id = "item456"
    await user_tables_repo.set_tag(pool, uid_a, instance_id, "infuse")
    tags = await user_tables_repo.get_tags(pool, uid_a)
    assert tags.get(instance_id) == "infuse"

    await user_tables_repo.set_tag(pool, uid_a, instance_id, "")
    tags = await user_tables_repo.get_tags(pool, uid_a)
    assert instance_id not in tags


# ---------------------------------------------------------------------------
# Loadouts
# ---------------------------------------------------------------------------

async def test_loadouts_round_trip(two_users):
    """save_loadout → get_loadouts round-trip including name."""
    pool, uid_a, _ = two_users

    name = "My PvE Loadout"
    data = {"weapons": ["Gjallarhorn"], "class": "Warlock"}
    await user_tables_repo.save_loadout(pool, uid_a, name, data)

    loadouts = await user_tables_repo.get_loadouts(pool, uid_a)
    found = next((l for l in loadouts if l["name"] == name), None)
    assert found is not None
    assert found["weapons"] == ["Gjallarhorn"]
    assert found["class"] == "Warlock"


async def test_loadouts_delete(two_users):
    """delete_loadout removes the loadout."""
    pool, uid_a, _ = two_users

    name = "Temp Loadout"
    await user_tables_repo.save_loadout(pool, uid_a, name, {"note": "temp"})
    loadouts = await user_tables_repo.get_loadouts(pool, uid_a)
    assert any(l["name"] == name for l in loadouts)

    await user_tables_repo.delete_loadout(pool, uid_a, name)
    loadouts = await user_tables_repo.get_loadouts(pool, uid_a)
    assert not any(l["name"] == name for l in loadouts)


# ---------------------------------------------------------------------------
# Armor sets
# ---------------------------------------------------------------------------

async def test_armor_sets_round_trip(two_users):
    """save_armor_set → get_armor_sets round-trip including name."""
    pool, uid_a, _ = two_users

    name = "Endgame Armor"
    data = {"helmet": "Crown of Tempests", "stats": {"recovery": 100}}
    await user_tables_repo.save_armor_set(pool, uid_a, name, data)

    sets = await user_tables_repo.get_armor_sets(pool, uid_a)
    found = next((s for s in sets if s["name"] == name), None)
    assert found is not None
    assert found["helmet"] == "Crown of Tempests"
    assert found["stats"]["recovery"] == 100


async def test_armor_sets_delete(two_users):
    """delete_armor_set removes the armor set."""
    pool, uid_a, _ = two_users

    name = "Temp Armor"
    await user_tables_repo.save_armor_set(pool, uid_a, name, {"note": "temp"})
    sets = await user_tables_repo.get_armor_sets(pool, uid_a)
    assert any(s["name"] == name for s in sets)

    await user_tables_repo.delete_armor_set(pool, uid_a, name)
    sets = await user_tables_repo.get_armor_sets(pool, uid_a)
    assert not any(s["name"] == name for s in sets)
