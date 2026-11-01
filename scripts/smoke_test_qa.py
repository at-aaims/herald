"""
scripts/smoke_test_qa.py — verify the syslog chat-tool layer.

Loads the cascade demo JSONL into the shared singletons, then calls
describe_event() and recent_activity() the same way the PydanticAI tools
do, and prints the JSON the orchestrator would see.

Usage:
    .venv/bin/python scripts/smoke_test_qa.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog import state  # noqa: E402
from src.syslog.ingest import replay_source  # noqa: E402
from src.syslog.qa import describe_event, recent_activity  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / ".data" / "syslog_demo.jsonl"


async def main() -> int:
    if not DEMO.exists():
        print(f"ERROR: demo JSONL not found at {DEMO}. Run scripts/build_demo_cascades.py first.")
        return 2

    # Drain the cascade demo into the shared ringbuffer.
    n = 0
    async for raw in replay_source(DEMO, speed_eps=10_000, default_node="node-0"):
        ev = state.classifier.classify(
            raw.log_message, node=raw.node, ts=raw.ts,
            pid=raw.pid, identifier=raw.identifier,
        )
        if ev is not None:
            state.ringbuffer.add(ev)
            n += 1
    print(f"Loaded {n} classified events into the ringbuffer\n")

    # ── lookup_syslog_event ────────────────────────────────────────────────
    for et in ("APP_INFRA_FAIL", "NET_CXI_RAW_DATA", "MYSTERY_EVENT"):
        print(f"=== lookup_syslog_event({et!r}) ===")
        result = describe_event(et)
        print(json.dumps(result, indent=2, default=str)[:1200])
        print()

    # ── syslog_recent_activity ─────────────────────────────────────────────
    print("=== syslog_recent_activity(window_seconds=3600) ===")
    activity = recent_activity(window_seconds=3600)
    print(json.dumps(activity, indent=2, default=str)[:1500])

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
