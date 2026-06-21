from app.perk_ratings import PerkRatings, load_ratings, save_rating
from app.storage import get_conn


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


def test_save_and_load_round_trip():
    conn = get_conn(":memory:")
    save_rating(conn, "Outlaw", "Hand Cannon", "A", "fast reload", ["pve", "pvp"], "my note")
    ratings = load_ratings(conn)
    info = ratings.get("Outlaw", "Hand Cannon")
    assert info["rating"] == "A"
    assert info["tags"] == ["pve", "pvp"]
    assert ratings.notes("Outlaw", "Hand Cannon") == "my note"
    assert ratings.is_override("Outlaw", "Hand Cannon") is True
    assert ratings.is_override("Outlaw", "Sniper Rifle") is False
