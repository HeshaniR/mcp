# Sales Insights MCP Server

An [MCP](https://modelcontextprotocol.io) server that connects an AI agent to your business database
so it can explore the schema and answer sales / analytics questions with real numbers.

## Tools
| Tool | Purpose |
|---|---|
| `list_tables` | Discover tables and views |
| `describe_table` | Columns, types, primary/foreign keys |
| `sample_rows` | A few example rows |
| `column_profile` | Nulls, distinct count, min/max, top values |
| `run_query` | Run a single read-only `SELECT`/`WITH` query (row-capped) |

Plus an `analyze_sales` prompt that starts a structured analysis (trend, growth, top products/customers, anomalies, recommendations).

## Safety
Read-only is enforced twice: SQL is validated (single `SELECT`/`WITH`, no write keywords) **and** the DB session is opened read-only
(SQLite `query_only`, Postgres/MySQL `READ ONLY` transactions, with statement timeouts). Results are capped at `MAX_ROWS` (default 500).
**Still connect with a dedicated read-only DB user** — that's the real security boundary. Consider pointing it at a replica or reporting views.

## Setup
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[postgres]"      # or ".[mysql]"; SQLite works out of the box

# try it with demo data
sales-insights-seed demo_sales.db
DATABASE_URL=sqlite:///demo_sales.db sales-insights-mcp
```

Config (env vars): `DATABASE_URL` (SQLAlchemy URL, e.g. `postgresql+psycopg://user:pw@host/db`), `MAX_ROWS`, `STATEMENT_TIMEOUT_MS`,
`MCP_TRANSPORT` (`stdio` default, or `streamable-http`).

### Claude Desktop / Claude Code
```json
{
  "mcpServers": {
    "sales-insights": {
      "command": "/path/to/.venv/bin/sales-insights-mcp",
      "env": { "DATABASE_URL": "postgresql+psycopg://readonly:pw@host/db" }
    }
  }
}
```
Then ask: *"Use the analyze_sales prompt: why did revenue drop last month?"*

## Tests
`pytest`
