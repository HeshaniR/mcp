"""Create demo sales data so the server can be tried without real data.

Works on any SQLAlchemy URL (SQLite or Postgres), e.g.
    sales-insights-seed postgresql+psycopg://user:pw@localhost/sales
    sales-insights-seed demo_sales.db          # shorthand for sqlite
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta

from sqlalchemy import create_engine, text

SCHEMA = [
    "DROP TABLE IF EXISTS order_items", "DROP TABLE IF EXISTS orders",
    "DROP TABLE IF EXISTS products", "DROP TABLE IF EXISTS customers",
    """CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT, segment TEXT, signup_date DATE)""",
    """CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT,
                            unit_price NUMERIC(10,2), unit_cost NUMERIC(10,2))""",
    """CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                          order_date DATE, status TEXT)""",
    """CREATE TABLE order_items(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
                               product_id INTEGER REFERENCES products(id), quantity INTEGER, discount NUMERIC(4,2))""",
]


def seed(url: str = "demo_sales.db") -> None:
    if "://" not in url:
        url = f"sqlite:///{url}"
    rnd = random.Random(42)
    engine = create_engine(url)
    regions = ["North", "South", "East", "West"]
    segments = ["SMB", "Mid-market", "Enterprise"]
    cats = {"Hardware": (200, 900), "Software": (50, 400), "Services": (100, 1500)}
    start = date(2025, 1, 1)
    with engine.begin() as c:
        for stmt in SCHEMA:
            c.execute(text(stmt))
        c.execute(
            text("INSERT INTO customers VALUES (:id,:name,:region,:segment,:signup)"),
            [dict(id=i, name=f"Customer {i}", region=rnd.choice(regions), segment=rnd.choice(segments),
                  signup=start + timedelta(days=rnd.randint(0, 200))) for i in range(1, 101)],
        )
        prods = []
        for i in range(1, 31):
            cat = rnd.choice(list(cats))
            price = round(rnd.uniform(*cats[cat]), 2)
            prods.append(dict(id=i, name=f"{cat} Product {i}", cat=cat, price=price,
                              cost=round(price * rnd.uniform(0.4, 0.75), 2)))
        c.execute(text("INSERT INTO products VALUES (:id,:name,:cat,:price,:cost)"), prods)
        orders, items, item_id = [], [], 1
        for oid in range(1, 1501):
            d = start + timedelta(days=int(rnd.triangular(0, 620, 500)))
            orders.append(dict(id=oid, cust=rnd.randint(1, 100), d=d,
                               status=rnd.choices(["completed", "refunded", "cancelled"], [90, 5, 5])[0]))
            for _ in range(rnd.randint(1, 4)):
                items.append(dict(id=item_id, oid=oid, pid=rnd.randint(1, 30), q=rnd.randint(1, 10),
                                  disc=rnd.choice([0, 0, 0, 0.05, 0.1])))
                item_id += 1
        c.execute(text("INSERT INTO orders VALUES (:id,:cust,:d,:status)"), orders)
        c.execute(text("INSERT INTO order_items VALUES (:id,:oid,:pid,:q,:disc)"), items)


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "demo_sales.db"
    seed(target)
    print(f"Seeded {target}")


if __name__ == "__main__":
    main()
