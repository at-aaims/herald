"""
scripts/smoke_test_multihop.py — verify the multi-hop click-walker.

Two scenarios:
  1. 4-hop linear cascade (NET_CXI_LINK -> FS_LUSTRE_OST_ERR -> FS_LUSTRE_ERR
     -> FS_CLUSTER_EVICT -> APP_INFRA_FAIL). max_depth=1..5 should return
     exactly that many cause levels.
  2. 3-cycle (A -> B -> C -> A): walker must not infinite-loop and the
     cycle-back must surface as cycle_truncated.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.causal import CausalEdge, CausalGraph, explain_click  # noqa: E402
from src.syslog.classifier import ParsedEvent  # noqa: E402
from src.syslog.ringbuffer import PerNodeRingBuffer  # noqa: E402


def _flatten(node, depth=0, out=None):
    out = out or []
    out.append((depth, node["event_type"], node.get("cycle_truncated", False)))
    for child in node.get("upstream", []) or []:
        _flatten(child, depth + 1, out)
    return out


def test_linear_cascade_depth_truncation():
    print("=== test 1: 4-hop linear cascade, depth control ===")
    edges = [
        CausalEdge("NET_CXI_LINK",      "FS_LUSTRE_OST_ERR", "Tier 1", 3, ("transformer","pcmci_plus","transfer_entropy")),
        CausalEdge("FS_LUSTRE_OST_ERR", "FS_LUSTRE_ERR",     "Tier 1", 3, ("transformer","pcmci_plus","transfer_entropy")),
        CausalEdge("FS_LUSTRE_ERR",     "FS_CLUSTER_EVICT",  "Tier 1", 3, ("transformer","pcmci_plus","transfer_entropy")),
        CausalEdge("FS_CLUSTER_EVICT",  "APP_INFRA_FAIL",    "Tier 1", 3, ("transformer","pcmci_plus","transfer_entropy")),
    ]
    g = CausalGraph(edges=edges)
    buf = PerNodeRingBuffer(retention_seconds=3600)
    node = "frontier-X"
    t0 = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    chain = [
        ("NET_CXI_LINK",      t0 + timedelta(seconds=0)),
        ("FS_LUSTRE_OST_ERR", t0 + timedelta(seconds=20)),
        ("FS_LUSTRE_ERR",     t0 + timedelta(seconds=40)),
        ("FS_CLUSTER_EVICT",  t0 + timedelta(seconds=60)),
        ("APP_INFRA_FAIL",    t0 + timedelta(seconds=80)),
    ]
    for et, ts in chain:
        buf.add(ParsedEvent(ts=ts, node=node, event_type=et,
                            raw=f"synth {et}", severity="info", subsystem=et.split("_")[0]))

    click_ts = chain[-1][1]
    expected = {
        1: ["APP_INFRA_FAIL", "FS_CLUSTER_EVICT"],
        2: ["APP_INFRA_FAIL", "FS_CLUSTER_EVICT", "FS_LUSTRE_ERR"],
        3: ["APP_INFRA_FAIL", "FS_CLUSTER_EVICT", "FS_LUSTRE_ERR", "FS_LUSTRE_OST_ERR"],
        4: ["APP_INFRA_FAIL", "FS_CLUSTER_EVICT", "FS_LUSTRE_ERR", "FS_LUSTRE_OST_ERR", "NET_CXI_LINK"],
        5: ["APP_INFRA_FAIL", "FS_CLUSTER_EVICT", "FS_LUSTRE_ERR", "FS_LUSTRE_OST_ERR", "NET_CXI_LINK"],
    }
    for d in (1, 2, 3, 4, 5):
        r = explain_click(g, buf, event_type="APP_INFRA_FAIL", node=node, ts=click_ts,
                          lookback_seconds=30, max_depth=d)
        flat = _flatten(r.cascade_tree) if r.cascade_tree else []
        got = [et for _depth, et, _trunc in flat]
        assert got == expected[d], f"depth={d}: expected {expected[d]}, got {got}"
        # back-compat: depth-1 edges always populated for the legacy UI
        assert len(r.edges_with_instances) == 1
        assert r.edges_with_instances[0]["cause"] == "FS_CLUSTER_EVICT"
    print("  ok — depth=1..5 truncates correctly; depth-1 back-compat preserved")


def test_cycle_truncation():
    print("\n=== test 2: 3-cycle A -> B -> C -> A is cycle-truncated ===")
    edges = [
        CausalEdge("A", "B", "Tier 2", 2, ("transformer","pcmci_plus")),
        CausalEdge("B", "C", "Tier 2", 2, ("transformer","pcmci_plus")),
        CausalEdge("C", "A", "Manual", 0, ("operator",)),
    ]
    g = CausalGraph(edges=edges)
    buf = PerNodeRingBuffer()
    t0 = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    # Chronological insertion so the ringbuffer's bin order is monotonic.
    for offset, et, label in [(5,"C","C-early"),(10,"A","A"),(15,"B","B"),(20,"C","C-late")]:
        buf.add(ParsedEvent(ts=t0 + timedelta(seconds=offset), node="n1", event_type=et,
                            raw=label, severity="info", subsystem="?"))
    r = explain_click(g, buf, event_type="C", node="n1",
                      ts=t0 + timedelta(seconds=20), lookback_seconds=60, max_depth=5)
    flat = _flatten(r.cascade_tree)
    labels = [et for _depth, et, _trunc in flat]
    assert labels == ["C", "B", "A", "C"], f"expected C->B->A->C(truncated), got {labels}"
    truncated_flags = [trunc for _depth, _et, trunc in flat]
    assert truncated_flags == [False, False, False, True], \
        f"only the cycle-back C should be truncated, got {truncated_flags}"
    print("  ok — cycle terminates at the repeat with cycle_truncated=True")


def main() -> int:
    test_linear_cascade_depth_truncation()
    test_cycle_truncation()
    print("\nAll multi-hop checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
