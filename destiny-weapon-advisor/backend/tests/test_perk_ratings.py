"""Tests for the PerkRatings class in app/perk_ratings.py.

The SQLite-based load_ratings/save_rating functions were removed when the app
migrated to MySQL.  Per-user round-trips are covered by test_user_data_repos.py.
This file keeps the pure-Python PerkRatings logic tests.
"""
from app.perk_ratings import PerkRatings


def test_override_precedence():
    seed = {"Frenzy": {"rating": "A", "reason": "seed", "tags": ["pve"]}}
    overrides = {
        ("Frenzy", ""): {"rating": "B", "reason": "base override", "tags": [], "notes": ""},
        ("Frenzy", "Sniper Rifle"): {"rating": "D", "reason": "bad", "tags": [], "notes": "n"},
    }
    ratings = PerkRatings(seed, overrides)
    assert ratings.get("Frenzy", "Sniper Rifle")["rating"] == "D"  # weapon-type override
    assert ratings.get("Frenzy", "Hand Cannon")["rating"] == "B"  # base override
    assert ratings.get("Frenzy", "")["rating"] == "B"
    assert ratings.get("Unknown", "Hand Cannon") is None


def test_notes_resolution():
    overrides = {("Frenzy", "Sniper Rifle"): {"rating": "D", "reason": "", "tags": [], "notes": "watch"}}
    ratings = PerkRatings({}, overrides)
    assert ratings.notes("Frenzy", "Sniper Rifle") == "watch"
    assert ratings.notes("Frenzy", "Hand Cannon") == ""
