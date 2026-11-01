"""
src/sql/sql.py — Natural-language → SQL Q&A.

LangChain-free. Each site module (e.g. src/site/ornl/frontier/db.py) provides:
  - create_sql_database() -> JSONSQLDatabase
  - render_sql_prompt(question, conversation, dialect) -> list[ChatCompletionMessageParam]
"""
from __future__ import annotations
import json
import re
import asyncio
from pathlib import Path
from openai import AsyncOpenAI
from pydantic import TypeAdapter, ImportString
from src.config import get_settings
from src.tools.sql import JSONSQLDatabase
import pandas as pd

settings = get_settings()


def make_table_description(
    table_name: str,
    metadata_file: str | Path,
    relationships: list[str | None] = [],
) -> str:
    """Build a CREATE TABLE description from a metadata CSV (column,type,description,...)."""
    df = pd.read_csv(metadata_file)
    out = f"CREATE TABLE {table_name} ( \n"
    for _, row in df.iterrows():
        out += f"{row['Column']}"
        if row['isPrimary'] in ('true', True):
            out += " PRIMARY"
        type_map = {
            'string': " VARCHAR(50) ",
            'int': " INT ",
            'number': " INT ",
            'float': " DOUBLE PRECISION ",
            'timestamp': " TIMESTAMP ",
            'date': " DATE ",
        }
        out += type_map.get(row['Type'], "")
        if row['isForeign'] not in ('false', False):
            out += f", {row['isForeign']} "
        out += f"COMMENT '{row['Description']}'\n"
    out += ")"
    return out


def get_db(db_module: str) -> JSONSQLDatabase:
    """Import the site module and return its JSONSQLDatabase."""
    db_module_obj = TypeAdapter(ImportString).validate_strings(db_module)
    return db_module_obj.create_sql_database()


def de_markdown(text: str) -> str:
    """Strip ```sql ... ``` fences the model often emits around SQL."""
    match = re.fullmatch(r"(.*```.*?\n)?(.+)```.*", text, flags=re.DOTALL)
    if match:
        text = match[2]
    return text.strip()


async def run_sql_qna(
    *,
    client: AsyncOpenAI,
    model_name: str,
    db_module: str,
    question: str,
    max_depth: int = 3,
) -> dict:
    """Generate SQL from a natural-language question; retry up to max_depth on errors.

    Returns:
        {
            "question", "query", "query_result", "error",
            "usage": {"input_tokens": int, "output_tokens": int},  # summed across retries
        }
    """
    db_module_obj = TypeAdapter(ImportString).validate_strings(db_module)
    db: JSONSQLDatabase = db_module_obj.create_sql_database()
    render_sql_prompt = db_module_obj.render_sql_prompt

    generated_sql: str | None = None
    query_result = None
    error: str | None = None
    conversation: list[dict] = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for _ in range(max_depth):
        messages = render_sql_prompt(
            question=question,
            conversation=conversation,
            dialect=db.dialect,
        )
        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
        )
        if response.usage:
            usage["input_tokens"] += response.usage.prompt_tokens or 0
            usage["output_tokens"] += response.usage.completion_tokens or 0
        generated_sql = de_markdown(response.choices[0].message.content or "")

        # SQLAlchemy is sync — run in a thread so we don't block the event loop
        execute_result = await asyncio.get_event_loop().run_in_executor(
            None, db.run, generated_sql,
        )
        try:
            query_result = json.loads(execute_result)
            error = None
            break
        except ValueError:
            query_result = None
            error = str(execute_result)
            conversation.append({"role": "assistant", "content": generated_sql})
            conversation.append({
                "role": "user",
                "content": f"The previous query failed:\n{error}\nCorrect the SQL query.",
            })

    return {
        "question": question,
        "query": generated_sql,
        "query_result": query_result,
        "error": error,
        "usage": usage,
    }
