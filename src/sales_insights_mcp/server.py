"""MCP server exposing a business database to an analytical agent (read-only)."""
from __future__ import annotations

import functools
import os
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .db import Database, QueryRejected

INSTRUCTIONS = """\
You are connected to a company's business database (read-only).
Workflow: list_tables -> describe_table for relevant tables -> sample_rows / column_profile
to learn the data -> run_query for the actual analysis. Prefer aggregating in SQL
(GROUP BY, window functions) over pulling raw rows. Always state assumptions
(date ranges, how revenue is defined, excluded statuses) alongside your findings.
"""

mcp = MCPServer("sales-insights", instructions=INSTRUCTIONS)
_db: Database | None = None


def _guard(fn):
    """Turn expected failures into clean tool errors (no server traceback)."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (QueryRejected, ValueError) as e:
            raise ToolError(str(e)) from e
        except SQLAlchemyError as e:
            raise ToolError(f"Database error: {getattr(e, 'orig', e)}") from e
    return wrapper


def db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


@mcp.tool()
@_guard
def list_tables() -> list[dict[str, Any]]:
    """List all tables and views in the connected database."""
    return db().list_tables()


@mcp.tool()
@_guard
def describe_table(table: str) -> dict[str, Any]:
    """Show columns, types, primary key and foreign keys of a table."""
    return db().describe_table(table)


@mcp.tool()
@_guard
def sample_rows(table: str, limit: int = 5) -> dict[str, Any]:
    """Return a few example rows from a table to understand its contents."""
    d = db()
    d.describe_table(table)  # validates the table name against the schema
    return d.query(f"SELECT * FROM {d.quote(table)}", limit=min(limit, 50)).to_dict()


@mcp.tool()
@_guard
def column_profile(table: str, column: str) -> dict[str, Any]:
    """Profile a column: row count, nulls, distinct values, min/max, and top values."""
    d = db()
    info = d.describe_table(table)
    if column not in {c["name"] for c in info["columns"]}:
        raise ValueError(f"Unknown column '{column}' in '{table}'.")
    t, c = d.quote(table), d.quote(column)
    stats = d.query(
        f"SELECT COUNT(*) AS total, COUNT({c}) AS non_null, COUNT(DISTINCT {c}) AS distinct_values, "
        f"MIN({c}) AS min_value, MAX({c}) AS max_value FROM {t}"
    ).to_dict()
    top = d.query(
        f"SELECT {c} AS value, COUNT(*) AS n FROM {t} GROUP BY {c} ORDER BY n DESC", limit=10
    ).to_dict()
    return {"stats": dict(zip(stats["columns"], stats["rows"][0])), "top_values": top["rows"]}


@mcp.tool()
@_guard
def run_query(sql: str, limit: int = 200) -> dict[str, Any]:
    """Run a single read-only SELECT/WITH query and return rows.

    Results are capped (see `truncated`). Write statements are rejected.
    Use the database's own SQL dialect.
    """
    return db().query(sql, limit=limit).to_dict()


@mcp.prompt()
def analyze_sales(question: str = "How is the business performing?") -> str:
    """Kick off a structured sales analysis."""
    return (
        f"Business question: {question}\n\n"
        "Explore the schema first, then answer with numbers. Cover where relevant: revenue trend over time, "
        "growth vs previous period, top/bottom products and customers, concentration risk, and anomalies. "
        "Finish with 3 concrete, prioritised recommendations and list the assumptions you made."
    )


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
