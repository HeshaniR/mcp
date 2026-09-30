"""Create a demo sales database (SQLite) so the server can be tried without real data."""
from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, timedelta


def seed(path: str = "demo_sales.db") -> None:
    rnd = random.Random(42)
    con = sqlite3.connect(path)
    con.executescript(
        """
        DROP TABLE IF EXISTS order_items; DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS customers;
        CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT, segment TEXT, signup_date TEXT);
        CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL, unit_cost REAL);
        CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                            order_date TEXT, status TEXT);
        CREATE TABLE order_items(id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id),
                                 product_id INTEGER REFERENCES products(id), quantity INTEGER, discount REAL);
        """
    )
    regions = ["North", "South", "East", "West"]
    segments = ["SMB", "Mid-market", "Enterprise"]
    cats = {"Hardware": (200, 900), "Software": (50, 400), "Services": (100, 1500)}
    start = date(2025, 1, 1)
    con.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?)",
        [(i, f"Customer {i}", rnd.choice(regions), rnd.choice(segments),
          (start + timedelta(days=rnd.randint(0, 200))).isoformat()) for i in range(1, 101)],
    )
    prods = []
    for i in range(1, 31):
        cat = rnd.choice(list(cats))
        price = round(rnd.uniform(*cats[cat]), 2)
        prods.append((i, f"{cat} Product {i}", cat, price, round(price * rnd.uniform(0.4, 0.75), 2)))
    con.executemany("INSERT INTO products VALUES (?,?,?,?,?)", prods)
    item_id = 1
    for oid in range(1, 1501):
        d = start + timedelta(days=int(rnd.triangular(0, 620, 500)))
        con.execute("INSERT INTO orders VALUES (?,?,?,?)",
                    (oid, rnd.randint(1, 100), d.isoformat(),
                     rnd.choices(["completed", "refunded", "cancelled"], [90, 5, 5])[0]))
        for _ in range(rnd.randint(1, 4)):
            con.execute("INSERT INTO order_items VALUES (?,?,?,?,?)",
                        (item_id, oid, rnd.randint(1, 30), rnd.randint(1, 10), rnd.choice([0, 0, 0.05, 0.1])))
            item_id += 1
    con.commit()
    con.close()


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "demo_sales.db"
    seed(path)
    print(f"Created {path}. Use DATABASE_URL=sqlite:///{path}")


if __name__ == "__main__":
    main()
