import pytest

from sales_insights_mcp.db import Database, QueryRejected, validate_read_only
from sales_insights_mcp.seed import seed


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "t.db"
    seed(str(p))
    return Database(f"sqlite:///{p}")


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders", "SELECT 1; DELETE FROM orders", "UPDATE orders SET status='x'",
    "WITH x AS (SELECT 1) DELETE FROM orders", "PRAGMA writable_schema=1", "",
])
def test_rejects_unsafe(sql):
    with pytest.raises(QueryRejected):
        validate_read_only(sql)


def test_allows_keywords_in_strings_and_comments():
    validate_read_only("SELECT 'drop table' AS x -- delete\n")


def test_query_and_truncation(db):
    r = db.query("SELECT * FROM orders", limit=10)
    assert r.truncated and len(r.rows) == 10


def test_join_aggregation(db):
    r = db.query(
        "SELECT p.category, SUM(oi.quantity*p.unit_price) AS rev FROM order_items oi "
        "JOIN products p ON p.id=oi.product_id GROUP BY 1 ORDER BY 2 DESC"
    )
    assert r.columns == ["category", "rev"] and len(r.rows) == 3


def test_schema_tools(db):
    assert {t["name"] for t in db.list_tables()} >= {"orders", "customers"}
    assert db.describe_table("orders")["foreign_keys"]
    with pytest.raises(ValueError):
        db.describe_table("nope")


def test_db_level_read_only(db):
    with db.engine.connect() as conn:
        db._enter_read_only(conn)
        with pytest.raises(Exception):
            conn.exec_driver_sql("DELETE FROM orders")
