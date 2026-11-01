"""
scripts/smoke_test_causal.py — sanity check the causal walker.

Loads the tier1+tier2 graph, synthesizes a small event timeline on one node,
clicks one effect event, and prints the explain response.

Usage:
    .venv/bin/python scripts/smoke_test_causal.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.causal import explain_click, load_causal_graph  # noqa: E402
from src.syslog.classifier import StreamingClassifier  # noqa: E402
from src.syslog.ringbuffer import PerNodeRingBuffer  # noqa: E402


def main() -> int:
    graph = load_causal_graph()
    print(f"Loaded causal graph: {len(graph.edges)} edges, "
          f"{len(graph.incoming)} effects, {len(graph.outgoing)} causes")

    # Pick a high-degree effect to demo against. From the CSV head:
    # APP_INFRA_FAIL has many incoming edges (FS_CLUSTER_EVICT, APP_JOB_CANCEL, etc).
    effect = "APP_INFRA_FAIL"
    causes_of_effect = graph.causes_of(effect)
    print(f"\n{effect} has {len(causes_of_effect)} upstream causes in the static graph:")
    for e in causes_of_effect[:10]:
        print(f"  {e.cause:<22}  tier={e.tier}  num_methods={e.num_methods}")
    if not causes_of_effect:
        print("ERROR: chosen effect has no upstream edges in the loaded graph.")
        return 1

    # Synthesize a timeline on one node. Two of the upstream causes fire
    # within the lookback; one doesn't. Then the effect fires.
    clf = StreamingClassifier(emit_residuals=False)
    buf = PerNodeRingBuffer(retention_seconds=600)
    node = "frontier-0042"
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)

    # Pick two real causes from the graph for this effect.
    cause_a = causes_of_effect[0].cause
    cause_b = causes_of_effect[1].cause if len(causes_of_effect) > 1 else cause_a

    timeline: list[tuple[datetime, str, str]] = [
        # (ts, event_type — synthesized directly, bypass regex)
        (t0 + timedelta(seconds=0),  cause_a, f"synthetic raw line for {cause_a}"),
        (t0 + timedelta(seconds=15), cause_b, f"synthetic raw line for {cause_b}"),
        (t0 + timedelta(seconds=45), effect,  f"synthetic raw line for {effect}"),
    ]

    # We bypass the regex by constructing ParsedEvents directly via the
    # classifier's record path. Easier: synthesize ParsedEvents inline.
    from src.syslog.classifier import ParsedEvent
    from src.syslog.patterns import severity_for, subsystem_for

    for ts, et, raw in timeline:
        ev = ParsedEvent(
            ts=ts,
            node=node,
            event_type=et,
            raw=raw,
            severity=severity_for(et),
            subsystem=subsystem_for(et),
        )
        buf.add(ev)

    click_ts = timeline[-1][0]
    print(f"\n>>> Clicking {effect} on {node} at {click_ts.isoformat()} "
          f"with lookback=60s\n")

    resp = explain_click(
        graph, buf,
        event_type=effect, node=node, ts=click_ts, lookback_seconds=60,
    )
    print(json.dumps(resp.to_dict(), indent=2, default=str))

    # Sanity assertions
    assert not resp.independent, "expected to find upstream causes"
    fired = {e["cause"] for e in resp.edges_with_instances}
    assert cause_a in fired, f"expected {cause_a} in fired causes"

    # Click an event that has no incoming edges → should be independent.
    no_causes = next(
        (n for n in (set(graph.outgoing) - set(graph.incoming))), None,
    )
    if no_causes:
        print(f"\n>>> Click an event with NO incoming edges: {no_causes}")
        resp2 = explain_click(
            graph, buf,
            event_type=no_causes, node=node,
            ts=click_ts, lookback_seconds=60,
        )
        print(json.dumps(resp2.to_dict(), indent=2, default=str))
        assert resp2.independent, "expected independent=True for source-only event"

    print("\nOK — walker behaviour verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
