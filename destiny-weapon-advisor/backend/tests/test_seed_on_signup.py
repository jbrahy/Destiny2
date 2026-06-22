"""Tests for Task 16: seed default perk ratings for new users on first login."""
import pytest
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_new_user_gets_default_ratings(app_client, monkeypatch, clean_db):
    """A brand-new user gets the default perk ratings seeded after first login."""
    from app.repositories import perk_ratings as perk_ratings_repo

    uid = await login_user(app_client, monkeypatch, bungie_id="seed_test_1")
    pool = app_client._transport.app.state.pool

    pr = await perk_ratings_repo.load(pool, uid)

    # Frenzy should be an override with rating "S"
    assert pr.is_override("Frenzy", ""), "Frenzy should be an override for new user"
    frenzy = pr.get("Frenzy", "")
    assert frenzy["rating"] == "S", f"Expected S, got {frenzy['rating']}"


async def test_returning_user_not_reseeded(app_client, monkeypatch, clean_db):
    """Logging in a second time does not overwrite a user's custom ratings."""
    from app.repositories import perk_ratings as perk_ratings_repo

    # First login — creates user and seeds defaults
    uid = await login_user(app_client, monkeypatch, bungie_id="seed_test_2")
    pool = app_client._transport.app.state.pool

    # Verify defaults are present
    pr = await perk_ratings_repo.load(pool, uid)
    assert pr.is_override("Frenzy", "")
    assert pr.get("Frenzy", "")["rating"] == "S"

    # User customizes Frenzy rating to "C"
    await perk_ratings_repo.save(pool, uid, "Frenzy", "", "C", "Changed my mind", [], "")

    # Verify the change was saved
    pr2 = await perk_ratings_repo.load(pool, uid)
    assert pr2.get("Frenzy", "")["rating"] == "C"

    # Second login with the same bungie_id — should NOT re-seed
    uid2 = await login_user(app_client, monkeypatch, bungie_id="seed_test_2")
    assert uid == uid2, "Should be the same user"

    # Frenzy should still be "C", not reset to "S"
    pr3 = await perk_ratings_repo.load(pool, uid)
    frenzy = pr3.get("Frenzy", "")
    assert frenzy["rating"] == "C", (
        f"Expected rating 'C' after second login, got '{frenzy['rating']}' — "
        "returning user was incorrectly re-seeded"
    )
