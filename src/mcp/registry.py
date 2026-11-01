"""
src/mcp/registry.py — Central registry of all available MCP tool servers.

To add a new tool:
  1. Create src/mcp/servers/<name>.py with a FastMCP instance named `mcp`
  2. Add an MCPToolDef entry to TOOL_REGISTRY below
  3. Add the name to settings.enabled_tools default in config.py

Nothing else needs to change — the agent and chain builder discover tools from here.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MCPToolDef:
    name: str
    display_name: str
    description: str
    server_module: str
    requires: list[str] = field(default_factory=list)
    enabled_by_default: bool = True


TOOL_REGISTRY: dict[str, MCPToolDef] = {
    "sql": MCPToolDef(
        name="sql",
        display_name="HPC Telemetry Analytics",
        description="Query the HPC telemetry database with natural language — jobs, energy, power, utilization.",
        server_module="src.mcp.servers.sql",
        requires=["sql_model", "db_module"],
    ),
    "rag": MCPToolDef(
        name="rag",
        display_name="HPC Documentation Search",
        description="Search HPC system documentation, policies, user guides, and operational runbooks.",
        server_module="src.mcp.servers.rag",
        requires=["small_model"],
    ),
    "jobpred": MCPToolDef(
        name="jobpred",
        display_name="Job Power/Energy Prediction",
        description="Predict power, temperature, and energy statistics for HPC jobs given domain, node count, and runtime.",
        server_module="src.mcp.servers.jobpred",
        requires=["small_model"],
    ),
    "syslog": MCPToolDef(
        name="syslog",
        display_name="Syslog Causal Lookup",
        description="Look up HPC syslog events in the tier1+tier2 causal graph (upstream causes, downstream effects, taxonomy), rank the graph as a whole (longest dependency chain, deepest cascade, highest fan-in/out), explain why a specific event fired, and inspect recent activity on the live monitor.",
        server_module="src.mcp.servers.syslog",
    ),
}


def get_enabled_tools(enabled_names: list[str]) -> dict[str, MCPToolDef]:
    """Return only the tools whose names appear in enabled_names."""
    unknown = set(enabled_names) - TOOL_REGISTRY.keys()
    if unknown:
        from loguru import logger
        logger.warning(f"Unknown tool names in enabled_tools config: {unknown}")
    return {name: TOOL_REGISTRY[name] for name in enabled_names if name in TOOL_REGISTRY}
