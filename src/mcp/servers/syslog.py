"""
src/mcp/servers/syslog.py — MCP server for the syslog causal-lookup tools.

Mirrors the rag/sql/jobpred servers so external MCP clients (Claude Desktop,
mcp CLI, etc.) can introspect the tier1+tier2 causal graph and recent
syslog activity without going through the HERALD HTTP API.

Run standalone:
    python -m src.mcp.servers.syslog

Or via MCP CLI:
    mcp run src/mcp/servers/syslog.py
"""
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "herald-syslog",
    instructions=(
        "Look up HPC syslog events in the tier1+tier2 causal graph (upstream "
        "causes, downstream effects, event taxonomy) and inspect recent activity "
        "on the live syslog monitor."
    ),
)


@mcp.tool()
async def lookup_syslog_event(event_type: str) -> str:
    """
    Look up an event type in the causal graph + event taxonomy.

    Args:
        event_type: One of the 87 taxonomy labels (e.g. "APP_INFRA_FAIL",
                    "NET_CXI_TIMEOUT", "FS_LUSTRE_OST_ERR"). Case-sensitive.

    Returns:
        JSON with upstream_causes, downstream_effects, description,
        recent_instances and convenience flags. Unknown inputs return
        {"error": ..., "suggestions": [...]}.
    """
    from src.syslog.qa import describe_event
    return json.dumps(describe_event(event_type), default=str)


@mcp.tool()
async def syslog_recent_activity(window_seconds: int = 300) -> str:
    """
    Return classifier counters and a per-node breakdown of recent events.

    Args:
        window_seconds: Lookback window for the per-node summary.

    Returns:
        JSON with classifier_stats, top_event_types_in_window, and per_node.
    """
    from src.syslog.qa import recent_activity
    return json.dumps(recent_activity(window_seconds=window_seconds), default=str)


@mcp.tool()
async def explain_syslog_event(
    event_type: str,
    node: str | None = None,
    ts: str | None = None,
    lookback_seconds: int = 60,
    max_depth: int = 5,
    include_advisory: bool = False,
) -> str:
    """
    Explain a specific occurrence of a syslog event — walk the tier1+tier2
    causal graph upstream from it within a time window, report which causes
    actually fired (with raw instances + a cascade tree), and (optionally)
    generate operator remediation advisory.

    Prefer this over lookup_syslog_event for concrete incidents ("why did this
    just happen, and what do I do?") rather than the event type in the abstract.

    Args:
        event_type: Taxonomy label (e.g. "APP_INFRA_FAIL"). Case-sensitive.
        node:       Compute node id. Inferred from the latest instance if omitted.
        ts:         ISO8601 timestamp of the occurrence. Defaults to the most
                    recent instance in the live ringbuffer (~1h).
        lookback_seconds: Per-hop window to scan for upstream causes.
        max_depth:  Cascade hops to walk upstream (1 = direct causes only; 5 = full).
        include_advisory: Generate operator-action remediation guidance. Defaults
                    to False (cascade trace alone is fast and LLM-free). Set True
                    when the user asks what to do / how to fix the incident.

    Returns:
        JSON with independent flag, edges_with_instances, cascade_tree,
        candidates_without_instances, resolved_anchor, and operator_advisory.
    """
    from src.syslog.qa import explain_event_occurrence
    result = await explain_event_occurrence(
        event_type,
        node=node,
        ts=ts,
        lookback_seconds=lookback_seconds,
        max_depth=max_depth,
        include_advisory=include_advisory,
    )
    return json.dumps(result, default=str)


@mcp.tool()
async def query_syslog_history(question: str) -> str:
    """
    Translate a natural-language question into SQL against the persistent
    DuckDB events store (with the tier1+tier2 causal_edges table joinable).
    Returns JSON with the generated SQL and the result rows.

    Use for historical / aggregate / cross-node questions that exceed the
    live ringbuffer's ~1h window.

    Args:
        question: Natural language question about historical syslog data.
    """
    from src.models.configured import get_sql_model_client, get_sql_model_name
    from src.syslog import state
    from src.syslog.sql_chain import run_syslog_sql_qna

    result = await run_syslog_sql_qna(
        client=get_sql_model_client(),
        model_name=get_sql_model_name(),
        store=state.syslog_store(),
        question=question,
    )
    return json.dumps(result, default=str)


if __name__ == "__main__":
    mcp.run()
