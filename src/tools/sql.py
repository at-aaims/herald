"""
src/tools/sql.py — Lightweight SQL helper.

minimum API surface the Q&A chain needs:
  - run(sql) -> str   (JSON-encoded rows on success, error message on failure)
  - dialect           (e.g. 'duckdb')
"""
from __future__ import annotations
import itertools
import json
from typing import Any
from sqlalchemy import text
from sqlalchemy.engine import Engine
from pydantic import TypeAdapter


class JSONSQLDatabase:
    """SQL execution helper that returns JSON

    """

    def __init__(
        self,
        engine: Engine,
        *,
        max_result_length: int = 100,
        max_string_length: int = 300,
        **_ignored,  # swallow legacy kwargs like view_support
    ):
        self._engine = engine
        self.max_result_length = max_result_length
        self.max_string_length = max_string_length

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    def run(self, command: str) -> str:
        """Execute a SQL command and return JSON-encoded rows (or an error string)."""
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(command))
                if not result.returns_rows:
                    return "[]"
                rows = []
                for row in itertools.islice(result, 0, self.max_result_length):
                    rows.append({
                        col: self._truncate(value)
                        for col, value in row._mapping.items()
                    })
            serialized = TypeAdapter(Any).serializer.to_python(rows, mode="json")
            return "[\n" + ",\n".join(f"    {json.dumps(o)}" for o in serialized) + "\n]"
        except Exception as e:
            return f"Error: {e}"

    def _truncate(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > self.max_string_length:
            return value[: self.max_string_length] + "..."
        return value
