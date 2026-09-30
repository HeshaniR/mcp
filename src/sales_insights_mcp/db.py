"""Database access layer: connection handling and read-only query guard."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

MAX_ROWS = int(os.environ.get("MAX_ROWS", "500"))
DB_SCHEMA = os.environ.get("DB_SCHEMA") or None  # e.g. "sales" (Postgres schema)
STATEMENT_TIMEOUT_MS = int(os.environ.get("STATEMENT_TIMEOUT_MS", "15000"))

# Backstop only: the session is also read-only. Kept narrow so common analytics
# functions (e.g. REPLACE(), string ops) are not rejected.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"attach|detach|pragma|vacuum|copy|call|execute|into|"
    r"set_config|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_terminate_backend|"
    r"pg_cancel_backend|lo_import|lo_export|dblink\w*|pg_sleep\w*)\b",
    re.IGNORECASE,
)


class QueryRejected(ValueError):
    """Raised when a query is not a safe, single, read-only statement."""


def _strip_comments_and_strings(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def validate_read_only(sql: str) -> str:
    """Defence in depth (the DB session is also read-only). Returns cleaned SQL."""
    cleaned = _strip_comments_and_strings(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise QueryRejected("Empty query.")
    if ";" in cleaned:
        raise QueryRejected("Only a single statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise QueryRejected("Only SELECT / WITH queries are allowed.")
    if (m := _FORBIDDEN.search(cleaned)):
        raise QueryRejected(f"Keyword '{m.group(0)}' is not allowed in read-only mode.")
    return sql.strip().rstrip(";")


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": len(self.rows),
            "truncated": self.truncated,
        }


class Database:
    def __init__(self, url: str | None = None) -> None:
        url = url or os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set (e.g. postgresql+psycopg://user:pw@host/db).")
        self.engine: Engine = create_engine(url, pool_pre_ping=True)
        self.dialect = self.engine.dialect.name

    def _enter_read_only(self, conn) -> None:
        if self.dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only = ON")
        elif self.dialect == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            if DB_SCHEMA:
                conn.exec_driver_sql(f"SET LOCAL search_path = {self.quote(DB_SCHEMA)}, public")
        elif self.dialect in ("mysql", "mariadb"):
            conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
            if self.dialect == "mysql":
                conn.exec_driver_sql(f"SET SESSION MAX_EXECUTION_TIME = {STATEMENT_TIMEOUT_MS}")

    def query(self, sql: str, params: dict[str, Any] | None = None, limit: int = MAX_ROWS) -> QueryResult:
        safe_sql = validate_read_only(sql)
        limit = max(1, min(limit, MAX_ROWS))
        with self.engine.connect() as conn:
            try:
                self._enter_read_only(conn)
                result = conn.execute(text(safe_sql), params or {})
                fetched = result.fetchmany(limit + 1)
                columns = list(result.keys())
            finally:
                conn.rollback()
        truncated = len(fetched) > limit
        rows = [[_jsonable(v) for v in row] for row in fetched[:limit]]
        return QueryResult(columns, rows, truncated)

    def list_tables(self) -> list[dict[str, Any]]:
        insp = inspect(self.engine)
        tables = sorted(insp.get_table_names(schema=DB_SCHEMA))
        views = sorted(insp.get_view_names(schema=DB_SCHEMA))
        return [{"name": n, "kind": "table"} for n in tables] + [{"name": n, "kind": "view"} for n in views]

    def describe_table(self, table: str) -> dict[str, Any]:
        insp = inspect(self.engine)
        known = insp.get_table_names(schema=DB_SCHEMA) + insp.get_view_names(schema=DB_SCHEMA)
        if table not in known:
            raise ValueError(f"Unknown table '{table}'. Call list_tables first.")
        cols = [
            {"name": c["name"], "type": str(c["type"]), "nullable": c["nullable"]}
            for c in insp.get_columns(table, schema=DB_SCHEMA)
        ]
        pk = insp.get_pk_constraint(table, schema=DB_SCHEMA).get("constrained_columns", [])
        fks = [
            {"columns": fk["constrained_columns"], "references": f'{fk["referred_table"]}({", ".join(fk["referred_columns"])})'}
            for fk in insp.get_foreign_keys(table, schema=DB_SCHEMA)
        ]
        return {"table": table, "columns": cols, "primary_key": pk, "foreign_keys": fks}

    def quote(self, ident: str) -> str:
        return self.engine.dialect.identifier_preparer.quote(ident)


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)
