"""
src/agent/herald_agent.py — PydanticAI agent for HERALD HPC operations assistant.

Architecture (post LangChain rip-out):
  - One Agent instance (created at import time, cheap)
  - HeraldDeps carries the per-session enabled_tools set
  - Each tool uses a `prepare` callback so disabled tools are invisible to the LLM
  - Tool functions call the LangChain-free chain code directly using AsyncOpenAI
    clients (built from settings.small_model / settings.sql_model)

Adding a new tool:
  1. Write a prepare_<name> function that gates on enabled_tools
  2. Decorate the tool function with @herald_agent.tool(prepare=prepare_<name>)
  3. Register the tool in src/mcp/registry.py
  4. Add the name to settings.enabled_tools default
"""
import json
from dataclasses import dataclass, field
from pydantic_ai import Agent, RunContext
from pydantic_ai.tools import ToolDefinition
from loguru import logger
from src.config import get_settings


# ── Dependencies ────────────────────────────────────────────────────────────

@dataclass
class HeraldDeps:
    enabled_tools: frozenset[str] = field(
        default_factory=lambda: frozenset(get_settings().enabled_tools)
    )
    # Per-request dedup cache: maps (tool, normalized-input) -> the tool's JSON
    # result. A fresh HeraldDeps is built per /api/chat request, so this is
    # scoped to a single turn — if the orchestrator re-calls a tool with the
    # same input (reasoning models occasionally do), the repeat returns the
    # cached result instantly instead of re-running the query.
    memo: dict = field(default_factory=dict)


# ── Agent ───────────────────────────────────────────────────────────────────

# No model= here deliberately: resolving it eagerly (get_large_pydantic_model())
# used to run at import time, which meant constructing the client — and on an
# unconfigured install (empty .env, the state /api/setup/configure expects to
# start from) that raises immediately and crashes the whole backend before it
# can even serve /api/setup. api.py's /api/chat already passes model= explicitly
# per request (re-fetched fresh so setup-wizard reconfigures take effect with no
# restart), so the agent never actually needs one bound here — model resolution
# is deferred to first real use instead of import time.
herald_agent = Agent(
    deps_type=HeraldDeps,
)


@herald_agent.system_prompt
async def build_system_prompt(ctx: RunContext[HeraldDeps]) -> str:
    # Tell the model which sub-agents EXIST but are currently switched off, so it
    # can point the user at the right one instead of forcing a misleading answer
    # out of an unrelated tool (e.g. answering a syslog "log event" question with
    # job-scheduling telemetry because the SQL tool was the only one enabled).
    from src.mcp.registry import TOOL_REGISTRY
    disabled = [
        TOOL_REGISTRY[name].display_name
        for name in TOOL_REGISTRY
        if name not in ctx.deps.enabled_tools
    ]
    disabled_note = (
        ""
        if not disabled
        else (
            "DISABLED SUB-AGENTS: the following capabilities exist but the user "
            "has switched them OFF for this chat: " + ", ".join(disabled) + ". "
            "You CANNOT call them. If a question would be best answered by a "
            "disabled sub-agent, do NOT force an answer out of an unrelated tool "
            "(e.g. do not answer a syslog/log-event question using job telemetry). "
            "Instead, tell the user that capability is turned off and to enable it "
            "from the sidebar, then ask again.\n\n"
        )
    )
    return (
        "You are HERALD (HPC Ensemble Reasoning, Analytics, and LLM-Driven "
        "Diagnostics), an HPC operations assistant. "
        "Use the tools provided to answer questions about HPC jobs and policies. "
        "If no tool can answer the question, say so plainly. "
        + disabled_note +
        "ROUTING — match the question's SUBJECT to what each sub-agent COVERS:\n"
        "  • HPC Telemetry Analytics (query_hpc_database): the job-accounting "
        "database — job records, counts, runtimes, queue and job-dependency wait "
        "times, energy, power, node utilization, science domains, and time-series "
        "metrics about JOBS.\n"
        "  • Syslog tools: SYSLOG (system-log) events — the kernel/hardware/"
        "service messages emitted by compute nodes, classified into event TYPES "
        "(written UPPER_SNAKE_CASE, e.g. SYS_OOM_KILL, HW_MCE_FATAL), and the "
        "causal graph between those types. Use syslog_graph_stats for whole-graph "
        "questions (longest dependency chain, deepest cascade, most "
        "causes/effects); lookup_syslog_event for one event's causes/effects; "
        "explain_syslog_event for why a specific occurrence fired; "
        "query_syslog_history for historical counts of syslog events.\n"
        "  • HPC Documentation Search (search_hpc_docs): policies, user guides, "
        "runbooks, and system documentation.\n"
        "  • Job Power/Energy Prediction (predict_job_stats): predicted power, "
        "temperature, and energy for a hypothetical job.\n"
        "Route by the SUBJECT first. The bare word 'log' is ambiguous (job "
        "telemetry is sometimes loosely called a 'log' too), so disambiguate: a "
        "question about SYSLOG / system-log events, node messages, or an event "
        "TYPE belongs to the syslog tools — even when it also contains a word like "
        "'dependency'. A syslog-event dependency lives in the causal graph "
        "(syslog tools); a job dependency lives in telemetry. Pick the tool whose "
        "subject matches, then act.\n"
        "KNOW WHEN TO STOP: if a tool errors or returns nothing useful, do NOT "
        "retry the same call with near-identical arguments. First consider whether "
        "a DIFFERENT enabled tool covers the subject better and try that. Only "
        "after the subject-appropriate tool(s) have failed — or if no enabled tool "
        "covers it — stop and reply in plain language that you cannot answer "
        "(briefly say why and suggest how to rephrase or which sub-agent to "
        "enable). A clear 'I can't answer this' beats looping, but do NOT give up "
        "before trying the tool that actually covers the topic. For whole-graph "
        "syslog questions (longest dependency chain, deepest cascade, most "
        "causes/effects) use syslog_graph_stats — do not assemble the answer from "
        "repeated single-event lookups. "
        "Do not write SQL queries, code, or tool results in your reply unless "
        "they came from an actual tool call you made in this turn. "
        "After a tool returns, summarize the result in one sentence. Do not "
        "invent scope the user didn't ask for (a time range, filter, etc.) — "
        "answer literally what was asked. If it's genuinely ambiguous, state "
        "the assumption you made in your answer rather than silently trying "
        "a second, narrower version of the same query.\n"
        "\n"
        "DOCUMENTATION SEARCH: search_hpc_docs returns retrieved passages in "
        "`context` (not a written answer) — synthesize a concise answer from "
        "them and cite the documents in `sources`. One good retrieval is "
        "normally enough; do NOT call it repeatedly with near-identical queries "
        "for the same question. If the passages are insufficient, answer with "
        "what's there and state what's missing rather than re-searching. "
        "(Calling it again for a genuinely different question — or alongside "
        "other tools — is fine.)\n"
        "\n"
        "IMPORTANT about SQL tool output: the JSON you receive contains only "
        "up to the first 200 rows of the result for your context efficiency "
        "— the user's UI is separately rendering ALL rows in a chart and a table, "
        "so from the user's perspective nothing is truncated. Do NOT tell "
        "the user the result is 'truncated', 'limited', or 'a sample'. Do "
        "NOT mention 'full_result_token', tokens, or internal fields — "
        "those are implementation details the user does not see. Summarize "
        "the data using the row_count, the column names, and the small "
        "sample you can see; the user has the rest in the chart. If the "
        "question asks for a per-row or day-by-day breakdown, do NOT try to "
        "retype the full table into your reply, and do NOT call the tool "
        "again with a narrower date range or a tweaked WHERE/GROUP BY to "
        "see more rows — that runs a DIFFERENT query over a different "
        "slice of data, not a continuation of the first one, and hand-"
        "assembling an answer from several such slices produces numbers "
        "that disagree with the complete, correct result already in the "
        "table/chart. One query is enough — describe the trend/total from "
        "row_count and the sample and point the user at the table/chart "
        "for the full breakdown."
    )


# ── Tool gating (per-session enabled set) ───────────────────────────────────

async def _gate(tool_name: str, ctx: RunContext[HeraldDeps], tool_def: ToolDefinition):
    return tool_def if tool_name in ctx.deps.enabled_tools else None

async def prepare_sql(ctx, tool_def):     return await _gate("sql", ctx, tool_def)
async def prepare_rag(ctx, tool_def):     return await _gate("rag", ctx, tool_def)
async def prepare_jobpred(ctx, tool_def): return await _gate("jobpred", ctx, tool_def)
async def prepare_syslog(ctx, tool_def):  return await _gate("syslog", ctx, tool_def)


# ── Tools ───────────────────────────────────────────────────────────────────

# Near-duplicate threshold for the SQL dedup cache below. difflib's ratio() is
# a character-level similarity (roughly 2*matches/(len(a)+len(b))), not
# semantic — 0.92 catches punctuation/whitespace/politeness-filler variants
# of the *same* question ("job count by day?" vs "What is the job count by
# day") without being loose enough to conflate two genuinely different
# questions (which would silently return the wrong answer — worse than the
# redundant query it would save).
_SQL_DEDUP_SIMILARITY_THRESHOLD = 0.92


def _normalize_question(question: str) -> str:
    import re
    return re.sub(r"\s+", " ", question.strip().lower()).rstrip("?.! ")


def _find_similar_cached_sql(memo: dict, normalized_question: str) -> str | None:
    import difflib
    best_ratio, best_payload = 0.0, None
    for key, payload in memo.items():
        # memo is a shared per-turn cache; other tools store keys of different
        # shapes (e.g. 1-tuples), so only look at 2-tuple ("sql", question) keys.
        if len(key) != 2 or key[0] != "sql":
            continue
        _, cached_question = key
        ratio = difflib.SequenceMatcher(None, normalized_question, cached_question).ratio()
        if ratio > best_ratio:
            best_ratio, best_payload = ratio, payload
    if best_ratio >= _SQL_DEDUP_SIMILARITY_THRESHOLD:
        return best_payload
    return None


def _sql_skeleton(sql: str) -> str:
    """Structural fingerprint of a SQL query, ignoring its WHERE clause.

    Two queries with the same SELECT/GROUP BY/ORDER BY but a different WHERE
    (e.g. one plain, one with a guessed date-range filter bolted on) reduce to
    the same skeleton. This catches the reasoning model's tendency to re-run
    an already-answered question with an invented scope narrowing, no matter
    how differently it rephrases the natural-language question each time —
    unlike the text-similarity check above, this looks at what the SQL
    actually computes, not the English wording that produced it.
    """
    import re
    stripped = re.sub(
        r"\bWHERE\b.*?(?=\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|;|$)",
        " ", sql, flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s+", " ", stripped).strip().lower()


@herald_agent.tool(prepare=prepare_sql)
async def query_hpc_database(ctx: RunContext[HeraldDeps], question: str) -> str:
    """
    Query the HPC job-accounting telemetry database using natural language.

    Translates the question into SQL, executes it against the HPC job
    database, and returns the results. Covers JOB data: job counts, runtimes,
    queue and job-dependency wait times, energy usage, power statistics, node
    utilization, science domains, and time-series metrics about jobs.

    (For SYSLOG / system-log events — node kernel/hardware/service messages and
    the causal dependencies between event types — use the syslog tools instead;
    those live in the causal graph, not this job database.)

    Args:
        question: Natural language question about HPC job data.
    """
    # Dedup within this turn: a repeated or near-duplicate (rephrased) query
    # returns the prior result (incl. its full_result_token, which still
    # resolves) instead of re-running text-to-SQL + the DB query.
    normalized = _normalize_question(question)
    cache_key = ("sql", normalized)
    cached = _find_similar_cached_sql(ctx.deps.memo, normalized)
    if cached is not None:
        logger.info("SQL dedup cache hit — returning prior result for near-duplicate query")
        return cached

    # Hard cap on query attempts per turn, mirroring search_hpc_docs's
    # RAG_CALL_CAP. Observed in practice: asked for a per-row/day-wise
    # breakdown, the model can only see the first
    # query_output_limit_chat_model rows of a result, so it tries to see
    # "the rest" by firing off more queries scoped to narrower date
    # sub-ranges -- each written with just enough SQL variation (COUNT(*) vs
    # COUNT(col), a different alias, GROUP BY target vs alias) to dodge the
    # skeleton dedup above, then hand-assembles a table from those partial,
    # inconsistently-aggregated slices instead of using the one correct,
    # complete result already rendered to the user from the first query.
    SQL_CALL_CAP = 4
    count_key = ("sql_call_count",)
    first_key = ("sql_first_result",)
    count = ctx.deps.memo.get(count_key, 0)
    if count >= SQL_CALL_CAP and first_key in ctx.deps.memo:
        logger.info(f"SQL call cap ({SQL_CALL_CAP}) reached — reusing first query's result")
        capped = json.loads(ctx.deps.memo[first_key])
        capped["note"] = (
            "STOP QUERYING: you have already queried the HPC database the "
            "maximum number of times this turn. This is the result of your "
            "FIRST (broadest) query. Re-querying with a narrower date range "
            "or a tweaked WHERE/GROUP BY does not get you more rows of the "
            "same result -- it runs a DIFFERENT query over a different "
            "slice of data. The table and chart already shown to the user "
            "render the COMPLETE result set from that first query. Answer "
            "now using row_count and the sample above; do not call "
            "query_hpc_database again this turn."
        )
        return json.dumps(capped)
    ctx.deps.memo[count_key] = count + 1

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
    import uuid
    from src.server.sql_cache import store as cache_store

    rows = result.get("query_result") or []
    logger.info(f"SQL query returned {len(rows)} rows")

    # Structural dedup: if this query's SELECT/GROUP BY/ORDER BY skeleton
    # matches an earlier successful query this turn (only the WHERE clause
    # differs), the model is re-scoping an already-answered question rather
    # than asking something new — reuse the earlier (first) result instead
    # of surfacing the newly guessed scope. See _sql_skeleton for why this
    # works even when the question text itself doesn't match.
    skeleton_key = ("sql_skeleton", _sql_skeleton(result["query"] or ""))
    prior_payload = ctx.deps.memo.get(skeleton_key)
    if prior_payload is not None:
        logger.info(
            "SQL structural dedup hit — same query shape as an earlier call "
            "this turn (only WHERE differs); reusing the earlier result "
            "instead of the newly guessed scope"
        )
        ctx.deps.memo[cache_key] = prior_payload
        return prior_payload

    # Side-channel: the tool's JSON return goes into both the LLM context
    # *and* the UI stream. To keep the LLM context tight (Llama-8B has a 16k
    # limit and conversation history accumulates), we feed the LLM only
    # `query_output_limit_chat_model` rows. The full result is stashed in
    # an in-process cache keyed by `full_result_token`, which the UI fetches
    # via GET /api/sql-result/{token} to render charts on the complete data.
    token = uuid.uuid4().hex
    cache_store(token, rows)
    payload = json.dumps({
        "query": result["query"],
        "query_result": rows[:settings.query_output_limit_chat_model],
        "row_count": len(rows),
        "truncated": len(rows) > settings.query_output_limit_chat_model,
        "full_result_token": token,
    })
    ctx.deps.memo[cache_key] = payload  # dedup repeats within this turn
    ctx.deps.memo[skeleton_key] = payload  # dedup re-scoped repeats within this turn
    ctx.deps.memo.setdefault(first_key, payload)  # fallback once SQL_CALL_CAP is hit
    return payload


@herald_agent.tool(prepare=prepare_rag)
async def search_hpc_docs(ctx: RunContext[HeraldDeps], query: str) -> str:
    """
    Search HPC system documentation, policies, and user guides.

    Retrieval-only: returns the most relevant documentation passages (and a
    related table/images when present) for you to answer FROM. It does NOT
    pre-write the answer — you synthesize a concise answer from `context` and
    cite the documents in `sources`. Use for questions about system policies,
    hardware specs, software modules, job scheduling rules, or procedures.

    One good retrieval is normally enough. If `context` is thin, answer with
    what's there and note what's missing rather than re-searching the same
    question with slightly reworded queries.

    Returns JSON:
      - context: [{text, source}]  — passages to ground your answer in
      - table_context: str|absent  — a related table (markdown) if relevant
      - sources: [{title, source}] — documents to cite
      - images:  [{url, caption}]  — rendered to the user automatically

    Args:
        query: Natural language question about HPC system documentation.
    """
    from src.rag.chain import run_rag_retrieval
    from src.rag.ingest_user import build_image_refs

    logger.info(f"search_hpc_docs called with query={query!r}")

    # Hard cap on retrieval attempts per turn. Unlike the SQL tool, rephrased
    # RAG queries rarely share enough text to dedup by similarity — the model
    # sometimes tries many differently-worded queries hunting for one passage
    # that isn't well-covered by the corpus, which can otherwise run until
    # PydanticAI's own tool_calls_limit kills the whole turn with zero answer.
    # Capping here means it always gets *something* back to answer from.
    RAG_CALL_CAP = 3
    count_key = ("rag_call_count",)
    last_key = ("rag_last_result",)
    count = ctx.deps.memo.get(count_key, 0)
    if count >= RAG_CALL_CAP and last_key in ctx.deps.memo:
        logger.info(f"search_hpc_docs call cap ({RAG_CALL_CAP}) reached — reusing last retrieval")
        # Returning the same JSON unchanged isn't a strong enough signal to
        # stop — observed empirically: the model kept issuing new rephrased
        # calls anyway, burning the agent's overall request budget instead of
        # the tool-call budget. An explicit stop directive is.
        capped = json.loads(ctx.deps.memo[last_key])
        capped["note"] = (
            "STOP SEARCHING: you have already retrieved documentation for "
            "this topic the maximum number of times this turn. This is the "
            "same result as your prior call. Answer now using what's in "
            "`context`/`table_context` above, or tell the user this specific "
            "detail isn't in the available documentation — do not call "
            "search_hpc_docs again this turn."
        )
        return json.dumps(capped)
    ctx.deps.memo[count_key] = count + 1

    try:
        result = await run_rag_retrieval(query)
    except Exception as exc:
        # The embedding/reranker models are fetched from huggingface.co on
        # first use (model_cache.py); if that's unreachable (offline, a
        # TLS-inspecting proxy without its CA trusted — see deploy/README.md)
        # every call fails the identical way. Surfacing a clean, explicit
        # "unavailable" result -- and explicitly telling the model this is
        # systemic, not query-specific -- stops it from burning further calls
        # re-trying the same failure with rephrased queries.
        logger.warning(f"search_hpc_docs: retrieval failed ({type(exc).__name__}: {exc})")
        return json.dumps({
            "context": [],
            "note": (
                "Documentation search is unavailable right now (the retrieval "
                "backend failed to respond). This will fail the same way for "
                "any query this turn -- do NOT retry search_hpc_docs. Tell the "
                "user documentation search is currently unavailable."
            ),
        })
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

    # Surface relevant images for inline rendering. The model only sees how many
    # were attached; the frontend fetches each via /api/rag-image/<token>.
    image_results = result.get("image") or result.get("images")
    if isinstance(image_results, list) and image_results:
        refs = build_image_refs(image_results)
        if refs:
            output["images"] = refs
            output["image_count"] = len(refs)

    if not output.get("context") and not output.get("table_context"):
        output["context"] = []
        output["note"] = "No relevant documentation found for this query."
    payload = json.dumps(output)
    ctx.deps.memo[last_key] = payload
    return payload


@herald_agent.tool(prepare=prepare_jobpred)
async def predict_job_stats(ctx: RunContext[HeraldDeps], question: str) -> str:
    """
    Predict power, temperature, and energy statistics for HPC jobs.

    Extracts job parameters (domain, node count, runtime, utilization type)
    from natural language and runs the regression model over all combinations.
    Use when the user wants to estimate resource consumption before running a job.

    Args:
        question: Natural language description of the job(s) to predict.
                  Can include multiple domains, node counts, or runtimes.
    """
    from src.models.configured import get_small_model_client, get_small_model_name
    from src.job_pred.regression import run_job_prediction

    logger.info(f"predict_job_stats called with question={question!r}")
    result = await run_job_prediction(
        client=get_small_model_client(),
        model_name=get_small_model_name(),
        question=question,
    )
    return json.dumps(result)


@herald_agent.tool(prepare=prepare_syslog)
async def lookup_syslog_event(ctx: RunContext[HeraldDeps], event_type: str) -> str:
    """
    Look up an HPC syslog event type in the tier1+tier2 causal graph and the
    87-event taxonomy.

    Returns upstream causes, downstream effects, a short description, and any
    recent instances seen on the live monitor. Use when the user asks
    questions like:
      - "what causes APP_INFRA_FAIL?"
      - "what does FS_CLUSTER_EVICT lead to?"
      - "what is GPU_HARD_FAULT?"
      - "is SYS_KERNEL_PANIC an independent event or part of a cascade?"

    Args:
        event_type: One of the 87 taxonomy labels (e.g. "APP_INFRA_FAIL",
                    "NET_CXI_TIMEOUT", "FS_LUSTRE_OST_ERR"). Case-sensitive.
                    On unknown input the response includes nearest matches.
    """
    from src.syslog.qa import describe_event
    return json.dumps(describe_event(event_type), default=str)


@herald_agent.tool(prepare=prepare_syslog)
async def syslog_graph_stats(ctx: RunContext[HeraldDeps]) -> str:
    """
    Whole-graph analytics over the tier1+tier2 causal graph — answers ranking
    questions ACROSS ALL events that lookup_syslog_event (single event, one hop)
    cannot. Deterministic and fast (no DB, no further LLM calls).

    Use for questions like:
      - "which log event has the longest dependency (chain)?"
      - "what's the deepest cascade / longest causal chain in the graph?"
      - "which event has the most direct causes / effects?"
      - "what is the ultimate root cause at the top of the longest chain?"

    Returns:
        longest_chain: {path, hops, root_cause, final_event, truncated}
            — the longest cause→effect path. final_event is the event with the
              longest dependency chain; root_cause is the chain's origin.
        highest_fan_out / highest_fan_in: {event, count}
            — the event with the most direct downstream effects / upstream causes.
        node_count, edge_count.
    """
    from src.syslog import state
    cache_key = ("syslog_graph_stats",)
    cached = ctx.deps.memo.get(cache_key)
    if cached is not None:
        return cached
    payload = json.dumps(state.causal_graph().stats(), default=str)
    ctx.deps.memo[cache_key] = payload
    return payload


@herald_agent.tool(prepare=prepare_syslog)
async def syslog_recent_activity(
    ctx: RunContext[HeraldDeps],
    window_seconds: int = 300,
) -> str:
    """
    Snapshot of syslog events flowing through the monitor right now.

    Returns classifier counters (total events seen, residual count, top event
    types) plus a per-node breakdown of events in the requested window. Use
    when the user asks:
      - "what's happening on the system?"
      - "show me recent syslog activity"
      - "which nodes are noisy right now?"

    Args:
        window_seconds: Lookback window for the per-node summary (default 300).
    """
    from src.syslog.qa import recent_activity
    return json.dumps(recent_activity(window_seconds=window_seconds), default=str)


@herald_agent.tool(prepare=prepare_syslog)
async def explain_syslog_event(
    ctx: RunContext[HeraldDeps],
    event_type: str,
    node: str | None = None,
    ts: str | None = None,
    lookback_seconds: int = 60,
    max_depth: int = 5,
    include_advisory: bool = False,
) -> str:
    """
    Explain a *specific occurrence* of a syslog event — the chat equivalent of
    clicking an event in the Syslog Monitor. Walks the tier1+tier2 causal graph
    upstream from the occurrence within a time window, reports which causes
    ACTUALLY FIRED (with raw instances + a cascade tree), and (optionally)
    generates operator remediation advisory.

    Prefer this over lookup_syslog_event when the user asks about a concrete
    incident rather than the event type in the abstract:
      - "why did APP_INFRA_FAIL just happen on frontier-0042?"
      - "trace the cascade behind the last SYS_KERNEL_PANIC"
      - "what should the operator do about the recent FS_CLUSTER_EVICT?"

    (lookup_syslog_event gives the static graph — every possible cause/effect.
    This gives the cause chain that actually fired before one occurrence, plus
    what to do about it.)

    Args:
        event_type: Taxonomy label (e.g. "APP_INFRA_FAIL"). Case-sensitive.
        node:       Compute node id. Inferred from the latest instance if omitted.
        ts:         ISO8601 timestamp of the occurrence. Defaults to the most
                    recent instance in the live ringbuffer (~1h). For older
                    occurrences pass an explicit ts (and node), or use
                    query_syslog_history.
        lookback_seconds: Per-hop window to scan for upstream causes (default 60).
        max_depth:  Cascade hops to walk upstream (1 = direct causes only; 5 = full).
        include_advisory: Generate operator-action remediation guidance. Defaults
                    to False (the cascade trace alone is fast and LLM-free). Set
                    True when the user asks what to DO / how to fix / what action
                    to take — e.g. "what should the operator do about ...".
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


@herald_agent.tool(prepare=prepare_syslog)
async def query_syslog_history(ctx: RunContext[HeraldDeps], question: str) -> str:
    """
    Run a natural-language query against the persistent syslog events store.

    The store is a DuckDB table of every classified log message seen by the
    monitor, plus the tier1+tier2 causal_edges table for JOINs. Use for
    questions that need:
      - Historical data outside the live ringbuffer (which only holds ~1h)
      - Aggregations / counts / time-series across many events
      - Cross-node comparisons or per-subsystem breakdowns
      - JOINs against the causal graph (e.g., events grouped by upstream cause)

    Examples:
      - "How many GPU_HARD_FAULTs did each node have in the last 24 hours?"
      - "Hourly histogram of FS_CLUSTER_EVICT in the last week"
      - "Which causes preceded each APP_INFRA_FAIL on frontier-0042 yesterday?"

    Args:
        question: Natural language question about historical syslog data.
    """
    import uuid
    from src.models.configured import get_sql_model_client, get_sql_model_name
    from src.server.sql_cache import store as cache_store
    from src.syslog import state
    from src.syslog.sql_chain import run_syslog_sql_qna

    settings = get_settings()
    try:
        store = state.syslog_store()
    except Exception as exc:
        return json.dumps({"error": f"syslog store unavailable: {exc}"})

    result = await run_syslog_sql_qna(
        client=get_sql_model_client(),
        model_name=get_sql_model_name(),
        store=store,
        question=question,
    )
    if result.get("error"):
        return json.dumps({"error": result["error"], "query": result.get("query")})

    rows = result.get("query_result") or []
    logger.info(f"syslog SQL returned {len(rows)} rows")
    # Same side-channel pattern as query_hpc_database: keep the LLM context
    # bounded while the UI fetches the full result via /api/sql-result/{token}.
    token = uuid.uuid4().hex
    cache_store(token, rows)
    return json.dumps({
        "query": result["query"],
        "query_result": rows[:settings.query_output_limit_chat_model],
        "row_count": len(rows),
        "truncated": len(rows) > settings.query_output_limit_chat_model,
        "full_result_token": token,
    })
