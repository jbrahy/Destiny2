"""Sweep persistence: prior lock state must survive so undo can restore it.

Follows the two_users fixture pattern from test_user_data_repos.py — users are
created with users_repo.upsert against the clean_db pool.
"""
import pytest
import pytest_asyncio

from app.repositories import user_tables
from app.repositories import users as users_repo

pytestmark = pytest.mark.asyncio(loop_scope="session")

_MID = "mem-1"


@pytest_asyncio.fixture(loop_scope="session")
async def two_users(clean_db):
    """Create two users and return (pool, user_a_id, user_b_id)."""
    pool = clean_db
    uid_a = await users_repo.upsert(pool, "sweepA", "SweepA", 3, "mbrSweepA")
    uid_b = await users_repo.upsert(pool, "sweepB", "SweepB", 3, "mbrSweepB")
    return pool, uid_a, uid_b


async def test_staged_rows_round_trip_with_lock_state(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, _MID, [("a", True), ("b", False)])
    assert await user_tables.get_staged_sweep(pool, uid, _MID) == {"a": True, "b": False}


async def test_staging_the_same_instance_twice_keeps_the_first_lock_state(two_users):
    """Re-staging an instance must not duplicate it, and must not change what
    was recorded. Staging unlocks the item, so any second pass reads it as
    unlocked; letting that False win would overwrite the true original — the
    only record of it — and undo could never restore the lock. The upsert is
    insert-only precisely so no read-then-write race can lose this."""
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, _MID, [("a", True)])
    await user_tables.stage_sweep_items(pool, uid, _MID, [("a", False)])
    assert await user_tables.get_staged_sweep(pool, uid, _MID) == {"a": True}


async def test_clear_removes_only_the_named_instances(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, _MID, [("a", True), ("b", True)])
    await user_tables.clear_sweep_items(pool, uid, _MID, ["a"])
    assert await user_tables.get_staged_sweep(pool, uid, _MID) == {"b": True}


async def test_clear_with_an_empty_list_is_a_no_op(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, _MID, [("a", True)])
    await user_tables.clear_sweep_items(pool, uid, _MID, [])
    assert await user_tables.get_staged_sweep(pool, uid, _MID) == {"a": True}


async def test_sweeps_are_isolated_per_user(two_users):
    pool, uid_a, uid_b = two_users
    await user_tables.stage_sweep_items(pool, uid_a, _MID, [("a", True)])
    assert await user_tables.get_staged_sweep(pool, uid_b, _MID) == {}


async def test_sweeps_are_isolated_per_membership(two_users):
    """FINDING 1: an account switch must not let undo see (and then wipe) a
    different Destiny membership's staged rows on the same user_id. Staging
    under membership A must be invisible to a get_staged_sweep call scoped
    to membership B, even for the identical user."""
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, "membership-A", [("a", True)])
    assert await user_tables.get_staged_sweep(pool, uid, "membership-B") == {}
    # And membership A's rows are untouched by that lookup.
    assert await user_tables.get_staged_sweep(pool, uid, "membership-A") == {"a": True}
