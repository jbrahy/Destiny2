import pytest
from app import db

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_execute_and_fetch(db_pool):
    await db.execute(db_pool, "DROP TABLE IF EXISTS t_demo", ())
    await db.execute(db_pool, "CREATE TABLE t_demo (id INT PRIMARY KEY, v VARCHAR(10))", ())
    await db.execute(db_pool, "INSERT INTO t_demo (id, v) VALUES (%s, %s)", (1, "a"))
    assert await db.fetchone(db_pool, "SELECT v FROM t_demo WHERE id=%s", (1,)) == ("a",)
    assert await db.fetchall(db_pool, "SELECT id FROM t_demo", ()) == [(1,)]
