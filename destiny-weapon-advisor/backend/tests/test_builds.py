from app.builds import load_activities, load_builds, save_activity, save_build
from app.storage import get_conn


def test_seed_builds_load():
    builds = load_builds(get_conn(":memory:"))
    assert len(builds) == 18  # 3 classes x 6 subclasses
    assert "Titan|Solar" in builds
    assert "super" in builds["Titan|Solar"]


def test_build_override_round_trip():
    conn = get_conn(":memory:")
    save_build(conn, "Titan|Solar", {"super": "Custom Super", "weapons": "mine"})
    builds = load_builds(conn)
    assert builds["Titan|Solar"]["super"] == "Custom Super"
    assert builds["Titan|Solar"]["weapons"] == "mine"


def test_seed_activities_load():
    activities = load_activities(get_conn(":memory:"))
    assert len(activities) >= 10
    assert all("name" in a and "type" in a for a in activities)


def test_activity_add_and_override():
    conn = get_conn(":memory:")
    save_activity(conn, "My Custom GM", {
        "name": "My Custom GM", "type": "Custom", "recommendedClass": "Hunter",
        "recommendedSubclass": "Void", "weapons": "anti-champion", "notes": "n",
    })
    names = [a["name"] for a in load_activities(conn)]
    assert "My Custom GM" in names
