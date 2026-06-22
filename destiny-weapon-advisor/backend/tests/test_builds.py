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
