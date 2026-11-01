"""
src/syslog/sql_chain.py — natural-language to SQL for the syslog events store.

Mirrors src/sql/sql.py's retry-on-error pattern but inlines the prompt and
schema instead of going through a site db_module: the syslog schema is
universal across deployments.

Prompt contents:
  - DuckDB CREATE TABLE block from store.schema_for_prompt()
  - The vocabulary of 80 event_type labels so the model picks correct ones
  - A few example questions with their canonical SQL
  - Current date (the model needs an anchor for "last week" / "yesterday")
  - The user's question
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

from openai import AsyncOpenAI

from src.syslog.patterns import LOG_PATTERNS
from src.syslog.store import SyslogStore


def _vocab_block() -> str:
    return "Valid event_type values:\n" + ", ".join(sorted(LOG_PATTERNS)) + "\n"


_EXAMPLES = """\
Example 1 — counts by event type in the last hour:
  SELECT event_type, COUNT(*) AS n
  FROM events
  WHERE ts >= now() - INTERVAL 1 HOUR
  GROUP BY event_type
  ORDER BY n DESC;

Example 2 — which nodes had the most GPU faults yesterday:
  SELECT node, COUNT(*) AS faults
  FROM events
  WHERE event_type IN ('GPU_HARD_FAULT', 'GPU_MEM_FAULT', 'GPU_RAS_FAIL')
    AND ts >= CURRENT_DATE - INTERVAL 1 DAY
    AND ts <  CURRENT_DATE
  GROUP BY node
  ORDER BY faults DESC
  LIMIT 20;

Example 3 — JOIN events with the causal graph to list known causes of FS_CLUSTER_EVICT
that fired on the same node within 60s before each eviction:
  WITH evictions AS (
    SELECT ts, node FROM events WHERE event_type = 'FS_CLUSTER_EVICT'
  )
  SELECT e.node, e.ts AS evict_ts, c.cause, ce.tier
  FROM evictions e
  JOIN causal_edges ce ON ce.effect = 'FS_CLUSTER_EVICT'
  JOIN events c
    ON c.node = e.node
   AND c.event_type = ce.cause
   AND c.ts BETWEEN e.ts - INTERVAL 60 SECOND AND e.ts
  ORDER BY e.node, e.ts;

Example 4 — hourly histogram of a specific event type:
  SELECT date_trunc('hour', ts) AS hour, COUNT(*) AS n
  FROM events
  WHERE event_type = 'NET_CXI_TIMEOUT'
    AND ts >= now() - INTERVAL 24 HOUR
  GROUP BY hour
  ORDER BY hour;

Example 5 — list all operator-curated (Manual-tier) causal edges:
  SELECT cause, effect FROM causal_edges WHERE tier = 'Manual';

Example 6 — events whose effect labels have at least one Manual upstream cause
in the static graph:
  SELECT e.ts, e.node, e.event_type, ce.cause AS manual_upstream_cause
  FROM events e
  JOIN causal_edges ce ON ce.effect = e.event_type
  WHERE ce.tier = 'Manual'
    AND e.ts >= now() - INTERVAL 1 HOUR
  ORDER BY e.ts;
"""


def render_syslog_sql_prompt(
    *,
    question: str,
    schema: str,
    dialect: str,
    conversation: list[dict],
    now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    system = (
        f"You are a {dialect} SQL expert. Translate the user's question into "
        f"a single SQL query against the schema below. Return ONLY the SQL — "
        f"no commentary, no markdown fences. The schema is fixed; do not "
        f"invent columns. event_type is one of the listed taxonomy labels; "
        f"if the user uses a synonym, map it to the closest label. Use "
        f"INTERVAL syntax for time math. Anchor relative dates to the current "
        f"UTC datetime: {now.isoformat()}.\n\n"
        f"{schema}\n\n{_vocab_block()}\n\n{_EXAMPLES}"
    )
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(conversation)
    messages.append({"role": "user", "content": question})
    return messages


_FENCE = re.compile(r"```(?:sql)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)


def _strip_fences(text: str) -> str:
    """The model occasionally wraps SQL in ```sql ... ``` despite the prompt."""
    m = _FENCE.search(text)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


async def run_syslog_sql_qna(
    *,
    client: AsyncOpenAI,
    model_name: str,
    store: SyslogStore,
    question: str,
    max_depth: int = 3,
) -> dict:
    """Generate SQL, execute it; on error feed the error back and retry."""
    schema = store.schema_for_prompt()
    dialect = store.dialect
    conversation: list[dict] = []
    generated_sql: str | None = None
    query_result = None
    error: str | None = None

    for _ in range(max_depth):
        messages = render_syslog_sql_prompt(
            question=question, schema=schema, dialect=dialect, conversation=conversation,
        )
        response = await client.chat.completions.create(
            model=model_name, messages=messages,
        )
        generated_sql = _strip_fences(response.choices[0].message.content or "")
        execute_result = await asyncio.get_event_loop().run_in_executor(
            None, store.run_sql, generated_sql,
        )
        try:
            query_result = json.loads(execute_result)
            error = None
            break
        except ValueError:
            error = str(execute_result)
            query_result = None
            conversation.append({"role": "assistant", "content": generated_sql})
            conversation.append({
                "role": "user",
                "content": f"That query failed: {error}\nFix the SQL — return the corrected query only.",
            })

    return {
        "question": question,
        "query": generated_sql,
        "query_result": query_result,
        "error": error,
    }
