"""
src/mcp/servers/rag.py — MCP server for HPC documentation search (RAG).

Run standalone:
    python -m src.mcp.servers.rag

Or via MCP CLI:
    mcp run src/mcp/servers/rag.py
"""
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "herald-rag",
    instructions=(
        "Search HPC system documentation, policies, user guides, and operational runbooks. "
        "Use for questions about system capabilities, job policies, hardware specs, and usage procedures."
    ),
)


@mcp.tool()
async def search_hpc_docs(query: str) -> str:
    """
    Search HPC system documentation using semantic retrieval.

    Retrieval-only: searches text/table collections in the ChromaDB vector store,
    reranks, and returns the relevant passages for the CALLING model to answer
    from (it does not pre-write an answer). Synthesize a concise answer from
    `context` and cite the documents in `sources`.

    Args:
        query: Natural language question about HPC system policies, hardware,
               job scheduling, software modules, or operational procedures.

    Returns:
        JSON string with keys:
          - context: [{text, source}]  — passages to ground the answer in
          - table_context: str|absent  — a related table (markdown) if relevant
          - sources: [{title, source}] — documents to cite
    """
    from src.rag.chain import run_rag_retrieval

    result = await run_rag_retrieval(query)
    output: dict = {}

    chunks = result.get("chunks") or []
    if chunks:
        output["context"] = [{"text": c["chunk"], "source": c.get("title", "")} for c in chunks]
        seen: set[str] = set()
        srcs = []
        for c in chunks:
            t = (c.get("title") or "").strip()
            if t and t not in seen:
                seen.add(t)
                srcs.append({"title": t, "source": c.get("source", "")})
        if srcs:
            output["sources"] = srcs

    table = result.get("table")
    if isinstance(table, dict) and table.get("table"):
        output["table_context"] = table["table"]

    if not output:
        output["context"] = []
        output["note"] = "No relevant documentation found for this query."
    return json.dumps(output)


if __name__ == "__main__":
    mcp.run()
