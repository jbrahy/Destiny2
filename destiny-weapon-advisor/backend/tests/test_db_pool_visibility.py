import pytest

from app import db
from app.config import get_settings

_TEST_DB = "advisor_test"


@pytest.mark.usefixtures("db_pool")
async def test_committed_write_visible_to_connection_that_read_earlier():
    """A pooled read connection must not pin a stale REPEATABLE READ snapshot.

    Regression for the OAuth "Invalid or expired OAuth state" bug: ``/api/login``
    INSERTs + commits a state on one pooled connection, but ``/callback``'s SELECT
    can land on a *different* pooled connection whose snapshot predates the insert.
    With ``autocommit`` disabled and reads that never commit/rollback, that
    connection holds an open transaction for its entire lifetime and can never see
    the newly committed row -> the callback wrongly reports an invalid state.

    The pool must run with autocommit so each statement is its own transaction and
    committed writes are immediately visible to every connection.
    """
    settings = get_settings().model_copy(update={"db_name": _TEST_DB})
    pool = await db.create_pool(settings)
    probe = "regr-visibility-probe"
    try:
        async with pool.acquire() as reader, pool.acquire() as writer:
            assert reader is not writer  # two distinct pooled connections

            # Reader takes its snapshot first (what pins it under REPEATABLE READ).
            async with reader.cursor() as rc:
                await rc.execute("SELECT COUNT(*) FROM oauth_states")
                await rc.fetchone()

            # Writer inserts + commits a brand-new state on another connection.
            async with writer.cursor() as wc:
                await wc.execute(
                    "INSERT INTO oauth_states (state, expires_at) "
                    "VALUES (%s, NOW() + INTERVAL 10 MINUTE)",
                    (probe,),
                )
            await writer.commit()

            # The reader must now be able to see the committed row.
            async with reader.cursor() as rc2:
                await rc2.execute(
                    "SELECT state FROM oauth_states WHERE state=%s", (probe,)
                )
                row = await rc2.fetchone()

            assert row is not None, (
                "reader cannot see a committed write -> stale snapshot; "
                "the pool must use autocommit"
            )
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM oauth_states WHERE state=%s", (probe,))
            await conn.commit()
    finally:
        pool.close()
        await pool.wait_closed()
