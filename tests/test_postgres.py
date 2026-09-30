"""Postgres integration tests. Run with PG_TEST_URL pointing at a *writable* seeded DB
(e.g. postgresql+psycopg://postgres@localhost/sales) so we prove read-only holds
even when the DB user itself could write."""
import os

import pytest
from sqlalchemy.exc import DBAPIError

from sales_insights_mcp.db import Database, QueryRejected
from sales_insights_mcp.seed import seed

URL = os.environ.get("PG_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="PG_TEST_URL not set")


@pytest.fixture(scope="module")
def db():
    seed(URL)
    return Database(URL)


def test_dialect_and_schema(db):
    assert db.dialect == "postgresql"
    assert {t["name"] for t in db.list_tables()} >= {"orders", "customers", "products", "order_items"}
    assert db.describe_table("order_items")["foreign_keys"]


def test_analytics_query_with_postgres_features(db):
    r = db.query(
        """WITH m AS (
             SELECT date_trunc('month', o.order_date) AS month,
                    SUM(oi.quantity * p.unit_price * (1 - oi.discount)) AS revenue
             FROM orders o JOIN order_items oi ON oi.order_id = o.id
             JOIN products p ON p.id = oi.product_id
             WHERE o.status = 'completed' GROUP BY 1)
           SELECT month, revenue, revenue / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) - 1 AS growth
           FROM m ORDER BY month"""
    )
    assert r.columns == ["month", "revenue", "growth"] and r.rows
    assert isinstance(r.rows[0][0], str)  # timestamps serialised


def test_replace_function_allowed(db):
    assert db.query("SELECT replace(name, 'Customer', 'C') FROM customers LIMIT 1").rows[0][0].startswith("C ")


def test_decimals_are_json_safe(db):
    import json
    json.dumps(db.query("SELECT unit_price FROM products LIMIT 3").to_dict())


@pytest.mark.parametrize("sql", [
    "SELECT set_config('transaction_read_only','off',true)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * INTO newt FROM orders",
])
def test_dangerous_selects_rejected(db, sql):
    with pytest.raises(QueryRejected):
        db.query(sql)


def test_session_is_read_only_even_for_writable_user(db):
    with db.engine.connect() as conn:
        db._enter_read_only(conn)
        with pytest.raises(DBAPIError, match="read-only"):
            conn.exec_driver_sql("DELETE FROM orders")
        conn.rollback()
    assert db.query("SELECT COUNT(*) FROM orders").rows[0][0] == 1500


def test_statement_timeout(db, monkeypatch):
    import sales_insights_mcp.db as m
    monkeypatch.setattr(m, "STATEMENT_TIMEOUT_MS", 200)
    with pytest.raises(DBAPIError, match="timeout"):
        # bypass keyword guard intentionally: pg_sleep is blocked at the SQL layer, so use a heavy cross join
        db.query("SELECT COUNT(*) FROM generate_series(1,20000000) a, generate_series(1,20) b")
