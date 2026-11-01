"""
src/mcp/servers/sql.py — MCP server for natural-language HPC database queries.

Run standalone:
    python -m src.mcp.servers.sql

Or via MCP CLI:
    mcp run src/mcp/servers/sql.py
"""
import json
from mcp.server.fastmcp import FastMCP
from src.config import get_settings

mcp = FastMCP(
    "herald-sql",
    instructions=(
        "Query the HPC telemetry database using natural language. "
        "Translates questions to SQL, executes them, and returns structured results."
    ),
)


@mcp.tool()
async def query_hpc_database(question: str) -> str:
    """
    Query the HPC telemetry database using a natural language question.

    Generates and executes SQL against the HPC job database, returning
    rows as structured JSON. Handles SQL errors by retrying with corrections.

    Args:
        question: Natural language question about HPC jobs, energy, power,
                  node utilization, science domains, or time-series metrics.

    Returns:
        JSON string with keys:
          - query: the SQL that was executed
          - query_result: list of row dicts (up to the configured limit)
          - row_count: total rows returned
          - error: present only on failure
    """
    from src.models.configured import get_sql_model_client, get_sql_model_name
    from src.sql.sql import run_sql_qna

    settings = get_settings()
    client = get_sql_model_client()
    model_name = get_sql_model_name()

    result = await run_sql_qna(
        client=client,
        model_name=model_name,
        db_module=settings.db_module,
        question=question,
    )
    if result.get("error"):
        return json.dumps({"error": result["error"], "query": result.get("query")})
    rows = result.get("query_result") or []
    return json.dumps({
        "query": result["query"],
        "query_result": rows[:settings.query_output_limit],
        "row_count": len(rows),
        "truncated": len(rows) > settings.query_output_limit,
    })


if __name__ == "__main__":
    mcp.run()
