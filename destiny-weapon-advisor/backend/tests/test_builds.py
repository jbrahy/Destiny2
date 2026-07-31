"""Tests for build/activity seed data helpers in app/builds.py.

The SQLite-based load_builds/save_build/load_activities/save_activity functions
were removed when the app migrated to MySQL.  Per-user round-trips are covered
by tests/test_user_data_repos.py.  This file keeps the seed-loading assertions.
"""
from app.builds import _seed_builds, _seed_activities


def test_seed_builds_load():
    builds = _seed_builds()
    assert len(builds) == 18  # 3 classes x 6 subclasses
    assert "Titan|Solar" in builds
    assert "super" in builds["Titan|Solar"]


def test_seed_activities_load():
    activities = _seed_activities()
    assert len(activities) >= 10
    assert all("name" in a and "type" in a for a in activities)


_ARMOR_STATS = {"Health", "Melee", "Grenade", "Super", "Class", "Weapons"}


def test_every_build_declares_a_stat_priority():
    """Outfits pick armour by these; a missing one silently degrades to raw focus."""
    import json
    from pathlib import Path
    seed = json.loads(
        (Path(__file__).parent.parent / "app" / "data" / "builds_seed.json").read_text()
    )
    builds = {k: v for k, v in seed.items() if not k.startswith("_")}
    assert len(builds) == 18
    for key, build in builds.items():
        prio = build.get("statPriority")
        assert prio, f"{key} has no statPriority"
        assert 2 <= len(prio) <= 3, f"{key} statPriority should be 2-3 stats, got {prio}"
        assert set(prio) <= _ARMOR_STATS, f"{key} has unknown stats: {set(prio) - _ARMOR_STATS}"
        assert len(set(prio)) == len(prio), f"{key} has duplicate stats: {prio}"
