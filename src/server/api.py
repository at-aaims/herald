"""
src/server/api.py — FastAPI server for HERALD using PydanticAI + Vercel AI SDK.

Endpoints:
  POST /api/chat          → streaming chat via VercelAIAdapter (SSE)
  GET  /api/tools         → list available tools and their enabled-by-default state
  GET  /api/health        → liveness check

Run:
  uvicorn src.server.api:app --reload --port 8000
"""
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse, FileResponse, PlainTextResponse

from loguru import logger
from pydantic_ai.usage import UsageLimits
from src.config import get_settings
from src.mcp.registry import TOOL_REGISTRY
from src.agent.herald_agent import herald_agent, HeraldDeps
from src.models.pydantic_ai import get_large_pydantic_model
from src.syslog.service import router as syslog_router
from src.server.setup_wizard import router as setup_router

app = FastAPI(title="HERALD API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(syslog_router)
app.include_router(setup_router)


@app.post("/api/chat")
async def chat(request: Request) -> Response:
    """
    Streaming chat endpoint compatible with the Vercel AI SDK useChat hook.

    The request body follows the Vercel AI Data Stream Protocol:
      { messages: [...], body: { enabledTools: ['sql', 'rag', 'jobpred'] } }

    enabledTools overrides settings.enabled_tools for this session.
    """
    from pydantic_ai.ui.vercel_ai import VercelAIAdapter

    # We need to read enabledTools from the body, but VercelAIAdapter will
    # also need to read the body. Reading request.json() consumes the stream,
    # so we cache it on the request scope for the adapter to reuse.
    body = await request.json()
    # The Vercel AI SDK's `body` option on useChat merges custom fields at the
    # top level of the request body (alongside `messages`). Some integrations
    # nest under "body" — accept either to be safe.
    # Use explicit None check, not `or`: an empty list means "disable all tools"
    # and `or` would short-circuit that to the nested lookup / default.
    requested_tools = body.get("enabledTools")
    if requested_tools is None:
        requested_tools = body.get("body", {}).get("enabledTools")

    # Restore the request body for the adapter (since request.json() is one-shot)
    async def _replay_receive():
        import json as _json
        return {"type": "http.request", "body": _json.dumps(body).encode(), "more_body": False}
    request._receive = _replay_receive  # type: ignore[assignment]

    if requested_tools is not None:
        # Intersect with what's in the registry — ignore unknown names
        enabled = frozenset(t for t in requested_tools if t in TOOL_REGISTRY)
    else:
        enabled = frozenset(get_settings().enabled_tools)

    # Observability: confirm the per-session toggle actually reaches the gate.
    # `requested` is what the UI sent (None = no override); `enabled` is what the
    # agent will expose after intersecting with the registry.
    logger.info(
        f"chat: requested_tools={sorted(requested_tools) if requested_tools is not None else None} "
        f"→ enabled_tools={sorted(enabled)}"
    )

    deps = HeraldDeps(enabled_tools=enabled)
    # Loop backstop: cap how many tool calls / model requests one turn may make
    # so a reasoning model can never spin forever on an unanswerable question.
    # When exceeded, pydantic_ai raises UsageLimitExceeded and the run ends (the
    # stream surfaces an error part) instead of looping. Generous enough for
    # legitimate multi-tool turns.
    limits = UsageLimits(request_limit=12, tool_calls_limit=12)
    # Explicit model= override, re-fetched every request rather than relying on
    # herald_agent's model (bound once at import time): lets the setup wizard's
    # config changes take effect immediately, no restart — get_large_pydantic_model
    # is cache_clear()'d by /api/setup/configure, so the next request after a
    # reconfigure picks up the new backend here.
    #
    # Resolving it can itself raise (e.g. no key set yet — herald_agent.py no
    # longer binds a model at import time specifically so the server can boot
    # unconfigured; this is where that deferred failure actually surfaces).
    # Catch it here rather than let the SDK's raw error ("OpenAIError: Missing
    # credentials...") reach the client as an unhandled 500/traceback.
    try:
        model = get_large_pydantic_model()
    except Exception as exc:
        logger.warning(f"chat: no usable orchestrator model configured: {exc}")
        # Plain text, not JSON: the AI SDK's fetch transport does
        # `throw new Error(await response.text())` on a non-ok response — it
        # uses the raw body as the error message verbatim, not parsed JSON.
        # A JSONResponse here would show the literal '{"error": "..."}'
        # string in the chat bubble instead of a clean sentence.
        return PlainTextResponse(
            "No model backend is configured yet. Visit /setup to pick one.",
            status_code=503,
        )
    return await VercelAIAdapter.dispatch_request(
        request, agent=herald_agent, deps=deps, usage_limits=limits,
        model=model,
    )


@app.get("/api/tools")
async def list_tools() -> JSONResponse:
    """
    Return all registered tools with their metadata and whether they are
    enabled by default. The frontend uses this to populate the tool selector.
    """
    enabled_tools = get_settings().enabled_tools
    tools = [
        {
            "name": t.name,
            "displayName": t.display_name,
            "description": t.description,
            "enabledByDefault": t.name in enabled_tools,
        }
        for t in TOOL_REGISTRY.values()
    ]
    return JSONResponse({"tools": tools})


@app.get("/api/sql-result/{token}")
async def sql_result(token: str) -> JSONResponse:
    """
    Side-channel for SQL tool results. The tool returns only a small slice
    to the LLM to keep the context window bounded, while stashing the full
    rows in an in-process cache. The UI calls this endpoint with the
    `full_result_token` from the tool output to retrieve the full data for
    charting.
    """
    from src.server.sql_cache import fetch as cache_fetch
    rows = cache_fetch(token)
    if rows is None:
        return JSONResponse(
            {"error": "result not found or evicted from cache"},
            status_code=404,
        )
    return JSONResponse({"query_result": rows, "row_count": len(rows)})


@app.post("/api/rag/ingest")
async def rag_ingest(
    files: list[UploadFile] = File(...),
    replace_doc_id: str | None = Form(None),
) -> JSONResponse:
    """Ingest one or more uploaded files into the RAG store so they become
    searchable by the `rag` tool. Each file is saved, parsed (text/markdown/
    HTML/PDF/DOCX/image), embedded, and recorded in the manifest. Returns a
    per-file summary.

    When `replace_doc_id` is given, the prior document is deleted *after* the
    new file ingests successfully — an atomic-ish swap that won't lose the old
    version if the new ingest fails.
    """
    import os
    import tempfile
    from src.rag.ingest_user import ingest_file, delete_document

    settings = get_settings()
    allowed = set(settings.rag_upload_allowed_extensions)
    results = []
    any_success = False
    for f in files:
        name = f.filename or "upload"
        ext = os.path.splitext(name)[1].lower()
        if ext not in allowed:
            results.append({"filename": name, "error": f"Unsupported file type: {ext}"})
            continue
        # Spool to a temp file, then hand off to the ingester (which copies it
        # into the document's permanent folder).
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        try:
            data = await f.read()
            if len(data) > settings.rag_upload_max_bytes:
                results.append({"filename": name, "error": "File exceeds max size"})
                continue
            tmp.write(data)
            tmp.close()
            try:
                summary = await ingest_file(tmp.name, original_name=name)
                if not summary.get("error"):
                    any_success = True
            except Exception as exc:
                summary = {"filename": name, "error": f"{type(exc).__name__}: {exc}"}
            results.append(summary)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # Replace: drop the superseded document only once the new one is in.
    if replace_doc_id and any_success:
        delete_document(replace_doc_id)

    return JSONResponse({"results": results})


@app.get("/api/rag/documents")
async def rag_documents() -> JSONResponse:
    """List user-ingested RAG documents (newest first)."""
    from src.rag.ingest_user import list_documents
    return JSONResponse({"documents": list_documents()})


@app.delete("/api/rag/documents/{doc_id}")
async def rag_delete_document(doc_id: str) -> JSONResponse:
    """Delete an ingested document: drop its rows from every collection and
    remove its stored files."""
    from src.rag.ingest_user import delete_document
    ok = delete_document(doc_id)
    if not ok:
        return JSONResponse({"error": "document not found"}, status_code=404)
    return JSONResponse({"deleted": doc_id})


@app.get("/api/rag/documents/{doc_id}/file")
async def rag_document_file(doc_id: str):
    """Serve an ingested document's original file (used for image thumbnails
    and downloads). Path is resolved strictly inside the upload dir."""
    import os
    from pathlib import Path
    from src.rag.ingest_user import list_documents

    settings = get_settings()
    upload_root = Path(settings.rag_upload_dir).resolve()
    docs = {d["doc_id"]: d for d in list_documents()}
    doc = docs.get(doc_id)
    if doc is None:
        return JSONResponse({"error": "document not found"}, status_code=404)
    target = (upload_root / doc_id / f"source{doc['ext']}").resolve()
    # Guard against path traversal — target must stay under the upload root.
    if upload_root not in target.parents or not target.is_file():
        return JSONResponse({"error": "file not available"}, status_code=404)
    return FileResponse(str(target), filename=doc.get("filename") or target.name)


@app.on_event("startup")
async def _start_rag_watcher() -> None:
    """Launch the RAG folder watcher if rag_watch_dir is configured. Runs in a
    daemon thread, so it neither blocks startup nor the request event loop."""
    try:
        from src.rag.ingest_user import start_watcher
        start_watcher()
    except Exception as exc:  # never let watcher startup break the API
        logger.warning(f"RAG folder watcher not started: {exc}")


@app.get("/api/rag-image/{token}")
async def rag_image(token: str):
    """Serve a RAG image by its side-channel token. Only paths the docs tool
    vetted and cached are reachable, so this can't be used for path traversal."""
    from pathlib import Path
    from src.rag.image_cache import fetch
    p = fetch(token)
    if not p or not Path(p).is_file():
        return JSONResponse({"error": "image not found or expired"}, status_code=404)
    return FileResponse(p)


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": "2.0.0"})
