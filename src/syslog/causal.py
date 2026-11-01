"""
src/syslog/causal.py — in-memory causal graph + walker.

Given a clicked event instance (event_type, node, ts),
which upstream causes fired within `lookback_seconds` on the same node?
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.syslog.classifier import ParsedEvent
from src.syslog.ringbuffer import PerNodeRingBuffer

DEFAULT_CAUSAL_CSV = ".data/causal_edges_placeholder.csv"


@dataclass(slots=True, frozen=True)
class CausalEdge:
    cause: str
    effect: str
    tier: str            # "Tier 1" | "Tier 2"
    num_methods: int     # 1..3
    detected_by: tuple[str, ...]  # subset of ("transformer", "pcmci_plus", "transfer_entropy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause": self.cause,
            "effect": self.effect,
            "tier": self.tier,
            "num_methods": self.num_methods,
            "detected_by": list(self.detected_by),
        }


@dataclass
class CausalGraph:
    edges: list[CausalEdge]
    incoming: dict[str, list[CausalEdge]] = field(default_factory=lambda: defaultdict(list))
    outgoing: dict[str, list[CausalEdge]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self):
        for e in self.edges:
            self.incoming[e.effect].append(e)
            self.outgoing[e.cause].append(e)

    def causes_of(self, effect: str) -> list[CausalEdge]:
        return list(self.incoming.get(effect, ()))

    def effects_of(self, cause: str) -> list[CausalEdge]:
        return list(self.outgoing.get(cause, ()))

    def to_dict(self) -> dict[str, Any]:
        nodes = sorted({e.cause for e in self.edges} | {e.effect for e in self.edges})
        return {
            "nodes": [{"id": n} for n in nodes],
            "edges": [e.to_dict() for e in self.edges],
            "edge_count": len(self.edges),
            "node_count": len(nodes),
        }

    def stats(self) -> dict[str, Any]:
        """Whole-graph analytics over the static cause→effect graph.

        Answers graph-wide ranking questions that the per-event lookup tools
        cannot ("which event has the longest dependency chain / deepest cascade /
        most direct causes / most direct effects"). Pure structure — no LLM, no
        DB, and polynomial (sub-millisecond on this ~200-edge graph).

        The graph contains cycles (feedback loops), so a plain "longest path" is
        both NP-hard and meaningless — a chain could wander inside a loop forever.
        Instead we condense each strongly-connected component (SCC) to a single
        stage and take the longest path over the resulting DAG. The longest_chain
        is therefore a sequence of stages; a stage with >1 event is a feedback
        loop whose members mutually cause each other (no internal ordering).
        `final_event` is the event at the end of that chain (the most
        downstream-dependent event) when the last stage is a single event.
        """
        nodes = sorted({e.cause for e in self.edges} | {e.effect for e in self.edges})
        adj: dict[str, list[str]] = {n: [] for n in nodes}
        for e in self.edges:
            adj[e.cause].append(e.effect)

        # ── Tarjan SCC (iterative; the graph is small but cycles are real) ──
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        comp_id: dict[str, int] = {}
        comps: list[list[str]] = []
        counter = 0
        for root in nodes:
            if root in index:
                continue
            work: list[tuple[str, int]] = [(root, 0)]
            while work:
                v, pi = work[-1]
                if pi == 0:
                    index[v] = low[v] = counter
                    counter += 1
                    stack.append(v)
                    on_stack.add(v)
                recursed = False
                children = adj[v]
                i = pi
                while i < len(children):
                    w = children[i]
                    if w not in index:
                        work[-1] = (v, i + 1)
                        work.append((w, 0))
                        recursed = True
                        break
                    if w in on_stack:
                        low[v] = min(low[v], index[w])
                    i += 1
                if recursed:
                    continue
                if low[v] == index[v]:
                    comp: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp_id[w] = len(comps)
                        comp.append(w)
                        if w == v:
                            break
                    comps.append(comp)
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])

        # ── Condensation DAG + longest path (in stages) ──
        cond: dict[int, set[int]] = {c: set() for c in range(len(comps))}
        for e in self.edges:
            cu, cv = comp_id[e.cause], comp_id[e.effect]
            if cu != cv:
                cond[cu].add(cv)

        best_len: dict[int, int] = {}
        nxt: dict[int, int | None] = {}
        def longest_from(c: int) -> int:
            if c in best_len:
                return best_len[c]
            bl, bn = 1, None
            for d in cond[c]:
                cand = 1 + longest_from(d)
                if cand > bl:
                    bl, bn = cand, d
            best_len[c], nxt[c] = bl, bn
            return bl

        def _label(c: int) -> dict[str, Any]:
            members = sorted(comps[c])
            return {"events": members, "cycle": len(members) > 1}

        stages: list[dict[str, Any]] = []
        if comps:
            start = max(range(len(comps)), key=longest_from)
            c: int | None = start
            while c is not None:
                stages.append(_label(c))
                c = nxt[c]

        last = stages[-1]["events"] if stages else []
        first = stages[0]["events"] if stages else []

        # Largest feedback loop (biggest SCC with >1 member), if any.
        cyc = [comps[i] for i in range(len(comps)) if len(comps[i]) > 1]
        largest_cycle = max(cyc, key=len) if cyc else None

        def _top(counts: dict[str, int]) -> dict[str, Any] | None:
            if not counts:
                return None
            event = max(counts, key=lambda k: (counts[k], k))
            return {"event": event, "count": counts[event]}

        fan_out = {n: len(self.outgoing.get(n, ())) for n in nodes}
        fan_in = {n: len(self.incoming.get(n, ())) for n in nodes}

        return {
            "node_count": len(nodes),
            "edge_count": len(self.edges),
            "longest_chain": {
                "stages": stages,
                "depth": max(len(stages) - 1, 0),  # hops over the condensed DAG
                "root_cause": first[0] if len(first) == 1 else first,
                "final_event": last[0] if len(last) == 1 else None,
                "note": "Each stage is one causal step; a stage with multiple "
                        "events is a feedback loop (mutual causation, no order).",
            },
            "largest_feedback_cluster": (
                {"size": len(largest_cycle), "events": sorted(largest_cycle)}
                if largest_cycle else None
            ),
            "highest_fan_out": _top(fan_out),  # most direct downstream effects
            "highest_fan_in": _top(fan_in),    # most direct upstream causes
        }


def _str_to_bool(s: str | None) -> bool:
    return s is not None and s.strip().lower() in ("true", "1", "t", "yes")


def load_causal_graph(path: str | Path | None = None) -> CausalGraph:
    """
    Load tier1+tier2 causal edges from CSV, then merge operator-declared
    manual edges from the extension JSONL (tier="Manual").

    Path resolution: explicit arg → HERALD_CAUSAL_CSV env var → DEFAULT_CAUSAL_CSV.
    """
    csv_path = Path(path or os.environ.get("HERALD_CAUSAL_CSV", DEFAULT_CAUSAL_CSV))
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Causal edges CSV not found: {csv_path}. "
            "Set HERALD_CAUSAL_CSV to override the default path."
        )

    edges: list[CausalEdge] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            detected = tuple(m for m, col in (
                ("transformer", "detected_by_transformer"),
                ("pcmci_plus", "detected_by_pcmci_plus"),
                ("transfer_entropy", "detected_by_transfer_entropy"),
            ) if _str_to_bool(row.get(col)))
            try:
                num_methods = int(row.get("num_methods", "0") or 0)
            except ValueError:
                num_methods = len(detected)
            edges.append(CausalEdge(
                cause=row["cause_event"].strip(),
                effect=row["effect_event"].strip(),
                tier=(row.get("tier") or "").strip() or "Tier 2",
                num_methods=num_methods,
                detected_by=detected,
            ))

    # P6+ manual edges. Imported lazily so a missing extensions module
    # (legacy deployments) doesn't break causal graph loading.
    try:
        from src.syslog.patterns_extension import EXTENSION_CAUSAL_EDGES
    except ImportError:
        EXTENSION_CAUSAL_EDGES = []

    existing_pairs = {(e.cause, e.effect) for e in edges}
    for me in EXTENSION_CAUSAL_EDGES:
        pair = (me["cause"], me["effect"])
        if pair in existing_pairs:
            # Triangulation already discovered this edge; the statistical
            # tier wins — don't downgrade by adding a Manual duplicate.
            continue
        # Cycle check: skip the manual edge if its reverse already exists.
        # Real cascades are usually acyclic; an LLM/operator can easily
        # propose a wrong direction. Better to drop than to corrupt.
        if (me["effect"], me["cause"]) in existing_pairs:
            continue
        edges.append(CausalEdge(
            cause=me["cause"], effect=me["effect"],
            tier="Manual", num_methods=0, detected_by=("operator",),
        ))
        existing_pairs.add(pair)

    return CausalGraph(edges=edges)


@dataclass
class ExplainResponse:
    independent: bool
    clicked: dict[str, Any]
    edges_with_instances: list[dict[str, Any]]
    candidates_without_instances: list[dict[str, Any]]
    lookback_seconds: int
    subgraph: dict[str, Any]
    # P6+ multi-hop: full upstream tree rooted at the clicked event.
    # Each tree node = {event_type, depth, tier?, instance_count?, instances?, upstream:[...]}
    cascade_tree: dict[str, Any] | None = None
    max_depth: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "independent": self.independent,
            "clicked": self.clicked,
            "edges_with_instances": self.edges_with_instances,
            "candidates_without_instances": self.candidates_without_instances,
            "lookback_seconds": self.lookback_seconds,
            "subgraph": self.subgraph,
            "cascade_tree": self.cascade_tree,
            "max_depth": self.max_depth,
        }


# Cap on raw instance previews per cause type — keeps response size bounded.
MAX_INSTANCES_PER_CAUSE = 5

# Multi-hop safety cap on total cause nodes in the cascade tree (across all
# depths). Prevents tree explosion when a deeply connected event has many
# upstream causes that each have many upstream causes.
MAX_CASCADE_NODES_TOTAL = 30


def _walk_upstream(
    *,
    graph: CausalGraph,
    buffer: PerNodeRingBuffer,
    event_type: str,
    node: str,
    anchor_ts: datetime,
    lookback_seconds: int,
    depth: int,
    max_depth: int,
    visited: set[str],
    budget: list[int],     # mutable single-int counter [remaining_nodes]
    depth1_edges: list[dict[str, Any]] | None = None,
    depth1_candidates_unfired: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Recursive BFS-ish walker. Sliding window per hop: a cause must have
    fired on `node` within [anchor_ts - lookback_seconds, anchor_ts].

    Returns a list of upstream-cause subtree dicts, each shaped as:
      {event_type, depth, tier, num_methods, detected_by,
       instance_count, instances:[...], upstream:[...]}

    Mutates `budget[0]` (decrements as nodes are added) and `visited`
    (per-path cycle protection — passed-by-reference to detect repeats).

    `depth1_edges` and `depth1_candidates_unfired`, when supplied, are
    populated as a side effect to preserve the back-compat depth-1 layer
    for the existing ExplainResponse fields.
    """
    if depth >= max_depth or budget[0] <= 0:
        return []
    incoming = graph.causes_of(event_type)
    if not incoming:
        return []

    cause_types = [e.cause for e in incoming]
    since = anchor_ts - timedelta(seconds=lookback_seconds)
    instances: list[ParsedEvent] = buffer.events_for_node(
        node, since=since, until=anchor_ts, of_types=cause_types,
    )
    by_cause: dict[str, list[ParsedEvent]] = defaultdict(list)
    for ev in instances:
        if ev.event_type is not None:
            by_cause[ev.event_type].append(ev)

    out: list[dict[str, Any]] = []
    fired_labels: set[str] = set()
    for edge in incoming:
        evs = by_cause.get(edge.cause, [])
        if not evs:
            continue
        fired_labels.add(edge.cause)
        if edge.cause in visited:
            # Cycle: this cause is already in the active path from root.
            # Record the edge at the current depth but DON'T recurse.
            if budget[0] <= 0:
                continue
            budget[0] -= 1
            out.append({
                "event_type": edge.cause,
                "depth": depth + 1,
                "tier": edge.tier,
                "num_methods": edge.num_methods,
                "detected_by": list(edge.detected_by),
                "instance_count": len(evs),
                "instances": _instance_dicts(evs),
                "upstream": [],
                "cycle_truncated": True,
            })
            if depth == 0 and depth1_edges is not None:
                depth1_edges.append(_depth1_edge_dict(edge, evs))
            continue
        if budget[0] <= 0:
            break
        budget[0] -= 1
        # Anchor recursion at the LATEST fired instance of this cause.
        # When a cause has multiple fires in the window (common when the
        # buffer holds older sessions or repeated cascades), the latest is
        # the one closest to the click time — and so the one whose own
        # upstream causes the operator actually cares about. Anchoring at
        # the earliest would walk depth-2 from a stale timestamp and miss
        # the recent cascade entirely.
        anchor = max(evs, key=lambda e: e.ts)
        next_visited = visited | {edge.cause}
        sub_upstream = _walk_upstream(
            graph=graph, buffer=buffer,
            event_type=edge.cause, node=node, anchor_ts=anchor.ts,
            lookback_seconds=lookback_seconds,
            depth=depth + 1, max_depth=max_depth,
            visited=next_visited, budget=budget,
        )
        out.append({
            "event_type": edge.cause,
            "depth": depth + 1,
            "tier": edge.tier,
            "num_methods": edge.num_methods,
            "detected_by": list(edge.detected_by),
            "instance_count": len(evs),
            "instances": _instance_dicts(evs),
            "upstream": sub_upstream,
        })
        if depth == 0 and depth1_edges is not None:
            depth1_edges.append(_depth1_edge_dict(edge, evs))

    # Back-compat: surface depth-1 causes that did NOT fire.
    if depth == 0 and depth1_candidates_unfired is not None:
        for edge in incoming:
            if edge.cause not in fired_labels:
                depth1_candidates_unfired.append(edge.to_dict())

    return out


def _instance_dicts(evs: list[ParsedEvent]) -> list[dict[str, Any]]:
    return [
        {
            "ts": ev.ts.isoformat(),
            "node": ev.node,
            "raw": ev.raw,
            "severity": ev.severity,
        }
        for ev in evs[-MAX_INSTANCES_PER_CAUSE:]
    ]


def _depth1_edge_dict(edge: CausalEdge, evs: list[ParsedEvent]) -> dict[str, Any]:
    return {
        **edge.to_dict(),
        "instance_count": len(evs),
        "instances": _instance_dicts(evs),
    }


def explain_click(
    graph: CausalGraph,
    buffer: PerNodeRingBuffer,
    *,
    event_type: str,
    node: str,
    ts: datetime,
    lookback_seconds: int = 60,
    max_depth: int = 1,
) -> ExplainResponse:
    """
    Walk upstream from a clicked event, up to `max_depth` hops.

    `max_depth = 1` reproduces the original P2 behavior: only DIRECT causes
    of the clicked event. `max_depth = 5` (the UI default) walks the full
    cascade up to 5 levels.

    Each hop stays on the same compute `node` (consistent with the SC
    paper's per-node temporal-locality methodology). Sliding window:
    a cause at depth N+1 must have fired within
    `[latest_instance_at_depth_N - lookback, latest_instance_at_depth_N]`.
    Picking the latest (not earliest) instance per cause anchors the walk
    on the most recent fire — which is what operators want when tracing
    a *recent* cascade, even if the buffer holds older sessions.

    Returns:
      - independent=True iff the clicked event has no upstream causes that
        fired anywhere in the trace (depth 1 came back empty).
      - cascade_tree: full recursive tree (None when the clicked event has
        no incoming edges at all).
      - edges_with_instances: depth-1 slice only — preserved for back-compat
        with the existing single-hop UI.
      - candidates_without_instances: depth-1 causes that didn't fire in window.
    """
    clicked = {"event_type": event_type, "node": node, "ts": ts.isoformat()}
    max_depth = max(1, min(int(max_depth), 10))

    incoming = graph.causes_of(event_type)
    if not incoming:
        return ExplainResponse(
            independent=True,
            clicked=clicked,
            edges_with_instances=[],
            candidates_without_instances=[],
            lookback_seconds=lookback_seconds,
            subgraph={"nodes": [{"id": event_type, "kind": "effect"}], "edges": []},
            cascade_tree=None,
            max_depth=max_depth,
        )

    depth1_edges: list[dict[str, Any]] = []
    depth1_unfired: list[dict[str, Any]] = []
    budget = [MAX_CASCADE_NODES_TOTAL]

    upstream = _walk_upstream(
        graph=graph, buffer=buffer,
        event_type=event_type, node=node, anchor_ts=ts,
        lookback_seconds=lookback_seconds,
        depth=0, max_depth=max_depth,
        visited={event_type}, budget=budget,
        depth1_edges=depth1_edges,
        depth1_candidates_unfired=depth1_unfired,
    )

    cascade_tree: dict[str, Any] = {
        "event_type": event_type,
        "depth": 0,
        "upstream": upstream,
    }

    # Back-compat single-hop subgraph (the legacy DAG renderer reads this).
    subgraph_nodes: list[dict[str, Any]] = [{"id": event_type, "kind": "effect"}]
    for e in depth1_edges:
        subgraph_nodes.append({
            "id": e["cause"],
            "kind": "cause",
            "tier": e["tier"],
            "instance_count": e["instance_count"],
        })
    subgraph_edges = [
        {"cause": e["cause"], "effect": e["effect"], "tier": e["tier"],
         "num_methods": e["num_methods"], "detected_by": e["detected_by"]}
        for e in depth1_edges
    ]

    return ExplainResponse(
        independent=not depth1_edges,
        clicked=clicked,
        edges_with_instances=depth1_edges,
        candidates_without_instances=depth1_unfired,
        lookback_seconds=lookback_seconds,
        subgraph={"nodes": subgraph_nodes, "edges": subgraph_edges},
        cascade_tree=cascade_tree,
        max_depth=max_depth,
    )
