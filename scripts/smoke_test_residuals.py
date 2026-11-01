"""
scripts/smoke_test_residuals.py — verify the P6 control plane end-to-end
WITHOUT calling an LLM. Exercises:

  - normalize() and cluster_residuals() collapse near-duplicate lines
  - load_extension_patterns() reads the JSONL roundtrip
  - severity_for / subsystem_for consult EXTENSION_TAXONOMY
  - Extension regex is iterated FIRST (priority over built-ins) and wins
    on key collision

The LLM proposer itself is exercised by scripts/propose_patterns.py
against a live model — that requires settings configured.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.patterns_extension import load_extension_patterns  # noqa: E402
from src.syslog.residuals import cluster_residuals, normalize  # noqa: E402


def test_normalize_clusters_variants():
    print("=== test 1: cluster_residuals collapses variants ===")
    lines = [
        "foobar daemon error: socket bind failed on port 1234 for /tmp/foo.sock",
        "foobar daemon error: socket bind failed on port 5678 for /tmp/bar.sock",
        "foobar daemon error: socket bind failed on port 999 for /tmp/baz.sock",
        "foobar daemon error: socket bind failed on port 42 for /tmp/qux.sock",
        "foobar daemon error: socket bind failed on port 8080 for /tmp/abc.sock",
        "wibble service warning: queue depth 234 above threshold",
        "wibble service warning: queue depth 567 above threshold",
        "wibble service warning: queue depth 891 above threshold",
        "wibble service warning: queue depth 12 above threshold",
        "wibble service warning: queue depth 99 above threshold",
        "single one-off line that should not cluster",
    ]
    clusters = cluster_residuals(lines, min_size=3)
    assert len(clusters) == 2, f"expected 2 clusters, got {len(clusters)}"
    assert clusters[0].frequency == 5
    assert clusters[1].frequency == 5
    assert "<N>" in clusters[0].template
    assert "<PATH>" in clusters[0].template
    print(f"  ok — 2 clusters of 5; templates use placeholders")
    print(f"  template[0]: {clusters[0].template}")
    print(f"  template[1]: {clusters[1].template}")


def test_extension_jsonl_roundtrip():
    print("\n=== test 2: extension JSONL roundtrip ===")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ext.jsonl"
        entries = [
            {
                "event_type": "APP_FOOBAR_FAIL",
                "regex": r"foobar daemon error: socket bind failed",
                "subsystem": "APP",
                "severity": "error",
                "description": "Foobar daemon socket bind failure",
                "ignorecase": False,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": "SVC_WIBBLE_QUEUE_WARN",
                "regex": r"wibble service warning: queue depth \d+ above threshold",
                "subsystem": "SVC",
                "severity": "warning",
                "description": "Wibble service queue depth threshold breach",
                "ignorecase": False,
            },
            # Malformed line — loader should skip and continue.
            '{"event_type": "BAD_MISSING_REGEX"}',
            # Bad regex — loader should warn and skip.
            json.dumps({"event_type": "BAD_REGEX", "regex": "[unterminated"}),
        ]
        with path.open("w") as f:
            for e in entries[:2]:
                f.write(json.dumps(e) + "\n")
            f.write(entries[2] + "\n")
            f.write(entries[3] + "\n")

        patterns, taxonomy = load_extension_patterns(path)
        assert "APP_FOOBAR_FAIL" in patterns, "expected APP_FOOBAR_FAIL"
        assert "SVC_WIBBLE_QUEUE_WARN" in patterns
        assert "BAD_MISSING_REGEX" not in patterns
        assert "BAD_REGEX" not in patterns
        # Verify regex actually matches a sample line
        assert patterns["APP_FOOBAR_FAIL"].search(
            "foobar daemon error: socket bind failed on port 1234 for /tmp/x.sock"
        )
        assert patterns["SVC_WIBBLE_QUEUE_WARN"].search(
            "wibble service warning: queue depth 234 above threshold"
        )
        assert taxonomy["APP_FOOBAR_FAIL"]["severity"] == "error"
        assert taxonomy["SVC_WIBBLE_QUEUE_WARN"]["subsystem"] == "SVC"
        print("  ok — 2 valid loaded, 2 invalid skipped, regexes compile and match")


def test_extension_overrides_builtin():
    print("\n=== test 3: extension priority (overrides built-in on key collision) ===")
    # Approve an entry that REUSES a built-in label name — extension's regex
    # should be the one in LOG_PATTERNS after re-loading.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ext.jsonl"
        with path.open("w") as f:
            f.write(json.dumps({
                "event_type": "INFO_NOISE",   # collides with built-in
                "regex": r"^FAKE_OVERRIDE_NOISE_TOKEN$",
                "subsystem": "SYS",
                "severity": "info",
            }) + "\n")
        patterns, _ = load_extension_patterns(path)
        # The loaded extension regex must NOT match "Hardware name: X" (a
        # built-in INFO_NOISE hit). It must match its own override token.
        assert patterns["INFO_NOISE"].match("FAKE_OVERRIDE_NOISE_TOKEN")
        assert not patterns["INFO_NOISE"].match("Hardware name: HPE Cray EX235a")
        print("  ok — extension entry wins on key collision when merged")


def test_disabled_at_soft_rollback():
    print("\n=== test 4: disabled_at retracts earlier approval; re-approval wins ===")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ext.jsonl"
        with path.open("w") as f:
            # Line 1: approve LABEL_A
            f.write(json.dumps({
                "event_type": "APP_TEST_LABEL_A",
                "regex": "first regex version for A",
                "subsystem": "APP", "severity": "info",
                "approved_at": "2026-05-18T20:00:00Z",
            }) + "\n")
            # Line 2: approve LABEL_B (will survive)
            f.write(json.dumps({
                "event_type": "APP_TEST_LABEL_B",
                "regex": "regex for B",
                "subsystem": "APP", "severity": "info",
                "approved_at": "2026-05-18T20:01:00Z",
            }) + "\n")
            # Line 3: DISABLE LABEL_A (retracts line 1)
            f.write(json.dumps({
                "event_type": "APP_TEST_LABEL_A",
                "disabled_at": "2026-05-18T21:00:00Z",
            }) + "\n")
            # Line 4: re-approve LABEL_A with a new regex (supersedes the disable)
            f.write(json.dumps({
                "event_type": "APP_TEST_LABEL_A",
                "regex": "second regex version for A",
                "subsystem": "APP", "severity": "warning",
                "approved_at": "2026-05-18T22:00:00Z",
            }) + "\n")

        patterns, taxonomy = load_extension_patterns(path)
        assert "APP_TEST_LABEL_A" in patterns, "re-approval after disable should restore the label"
        assert "APP_TEST_LABEL_B" in patterns
        # The active regex must be the SECOND version (line 4), not the first.
        assert patterns["APP_TEST_LABEL_A"].search("second regex version for A")
        assert not patterns["APP_TEST_LABEL_A"].search("first regex version for A")
        assert taxonomy["APP_TEST_LABEL_A"]["severity"] == "warning"  # from line 4
        print("  ok — disable retracts earlier approval, re-approval supersedes the disable")

    # Sub-case: disable with NO re-approval -> label fully removed.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ext.jsonl"
        with path.open("w") as f:
            f.write(json.dumps({
                "event_type": "APP_RETIRED",
                "regex": "old regex",
                "subsystem": "APP", "severity": "info",
            }) + "\n")
            f.write(json.dumps({
                "event_type": "APP_RETIRED",
                "disabled_at": "2026-05-18T23:00:00Z",
            }) + "\n")
        patterns, _ = load_extension_patterns(path)
        assert "APP_RETIRED" not in patterns, "disabled label without re-approval should be absent"
        print("  ok — disabled-only label is absent from the loaded set")


def test_score_proposal_criteria():
    print("\n=== test 5: score_proposal — tiered auto-apply criteria ===")
    from src.syslog.residuals import PatternProposal, score_proposal

    def make(**over):
        defaults = dict(
            template="t",
            representative_samples=["specific token 42 pattern"],
            frequency=100,
            proposed_event_type="HW_TEST_NEW",
            proposed_regex=r"specific token \d+ pattern",
            subsystem="HW",
            severity="warning",
            description="",
            is_new_label=True,
            rationale="",
            ignorecase=False,
            valid=True,
            validation_error=None,
        )
        defaults.update(over)
        return PatternProposal(**defaults)

    known = {"INFO_NOISE", "NET_CXI_TIMEOUT"}

    # happy path
    v = score_proposal(make(), known_labels=known, min_frequency=50)
    assert v.auto_approve, f"happy path should auto-approve; got: {v.reason}"

    # invalid input
    v = score_proposal(make(valid=False, validation_error="x"),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "invalid" in v.reason

    # collision
    v = score_proposal(make(proposed_event_type="INFO_NOISE"),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "collision" in v.reason

    # non-canonical subsystem
    v = score_proposal(make(subsystem="WTF"),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "non-canonical" in v.reason

    # unknown severity
    v = score_proposal(make(severity="emergency"),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "severity" in v.reason

    # too-low frequency
    v = score_proposal(make(frequency=10),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "frequency" in v.reason

    # over-broad regex
    v = score_proposal(make(proposed_regex=r".* token \d+"),
                       known_labels=known, min_frequency=50)
    assert not v.auto_approve and "over-broad" in v.reason

    print("  ok — 7 criteria evaluated, only the happy path auto-approves")


def test_manual_causal_edges_roundtrip():
    print("\n=== test 6: manual causal edges roundtrip via extension JSONL ===")
    import contextlib
    import io as _io
    from src.syslog.patterns_extension import load_extension_edges, load_extension_patterns

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ext.jsonl"
        with path.open("w") as f:
            # Form (a): edges declared alongside the approval
            f.write(json.dumps({
                "event_type": "HW_FOOBAR_TEST",
                "regex": "foobar pattern",
                "subsystem": "HW", "severity": "warning",
                "approved_at": "2026-05-18T20:00:00Z",
                "causal_edges": {
                    "upstream": ["HW_THERMAL_CRIT", "GPU_RAS_FAIL"],
                    "downstream": ["APP_INFRA_FAIL"],
                },
            }) + "\n")
            # Form (b): edges-only patch for an already-known label
            f.write(json.dumps({
                "event_type": "SYS_TEST_OTHER",
                "graph_edges_only": True,
                "causal_edges": {"upstream": ["HW_THERMAL_CRIT"]},
                "edges_added_at": "2026-05-18T21:00:00Z",
            }) + "\n")

        edges = load_extension_edges(path)
        pairs = {(e["cause"], e["effect"]) for e in edges}
        assert ("HW_THERMAL_CRIT", "HW_FOOBAR_TEST") in pairs
        assert ("GPU_RAS_FAIL", "HW_FOOBAR_TEST") in pairs
        assert ("HW_FOOBAR_TEST", "APP_INFRA_FAIL") in pairs
        assert ("HW_THERMAL_CRIT", "SYS_TEST_OTHER") in pairs
        assert len(pairs) == 4
        print(f"  ok — 4 manual edges loaded across forms (a) + (b)")

        # graph_edges_only entries must NOT trigger spurious "missing regex"
        # warnings from the patterns loader (they intentionally carry no regex).
        captured = _io.StringIO()
        with contextlib.redirect_stderr(captured):
            patterns, _tax = load_extension_patterns(path)
        stderr_out = captured.getvalue()
        assert "missing regex" not in stderr_out, (
            f"graph_edges_only entry produced spurious warning:\n{stderr_out}"
        )
        # Form (a) still loads its pattern; Form (b) doesn't define a pattern.
        assert "HW_FOOBAR_TEST" in patterns
        assert "SYS_TEST_OTHER" not in patterns
        print("  ok — graph_edges_only entries skipped silently by patterns loader")

        # Disable the form-a entry → its edges should be retracted.
        with path.open("a") as f:
            f.write(json.dumps({
                "event_type": "HW_FOOBAR_TEST",
                "disabled_at": "2026-05-18T22:00:00Z",
            }) + "\n")
        edges_after = load_extension_edges(path)
        pairs_after = {(e["cause"], e["effect"]) for e in edges_after}
        assert ("HW_THERMAL_CRIT", "HW_FOOBAR_TEST") not in pairs_after
        assert ("HW_THERMAL_CRIT", "SYS_TEST_OTHER") in pairs_after  # form (b) still alive
        assert len(pairs_after) == 1
        print(f"  ok — disable retracts the form-a entry's edges; form-b survives")


def main() -> int:
    test_normalize_clusters_variants()
    test_extension_jsonl_roundtrip()
    test_extension_overrides_builtin()
    test_disabled_at_soft_rollback()
    test_score_proposal_criteria()
    test_manual_causal_edges_roundtrip()
    print("\nAll P6 unit checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
