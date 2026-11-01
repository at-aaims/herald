"""
scripts/smoke_test_proposals_queue.py — verify the proposals queue helper.

In-process unit checks for src/syslog/proposals_queue.py. The HTTP layer
is thin glue around these functions; if these pass, the endpoints work.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Use a temp .data/ dir so we don't pollute the user's real proposals.
TMP = tempfile.mkdtemp(prefix="herald_pq_")
DATA_DIR = Path(TMP) / ".data"
DATA_DIR.mkdir(parents=True)

# Point the queue (and the patterns_extension loader) at the temp dir
# BEFORE importing the queue module so its path resolution picks it up.
os.environ["HERALD_SYSLOG_EXTENSIONS_PATH"] = str(DATA_DIR / "syslog_patterns_extension.jsonl")

# Monkey-patch the queue's data-dir resolver and the rejected-path
# accessor before any cached lookups occur. Easier than touching settings.
from src.syslog import proposals_queue  # noqa: E402

proposals_queue._data_dir = lambda: DATA_DIR  # type: ignore[assignment]
proposals_queue._rejected_path = lambda: DATA_DIR / "syslog_proposals_rejected.jsonl"  # type: ignore[assignment]


def _write_proposal_file(name: str, proposals: list[dict]) -> Path:
    p = DATA_DIR / name
    p.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "MANUAL_TEST",
        "residuals_seen": 100,
        "clusters": len(proposals),
        "proposals": proposals,
    }, indent=2))
    return p


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def test_list_pending_excludes_invalid_and_already_decided():
    print("=== test 1: list_pending excludes invalid / approved / rejected ===")
    _write_proposal_file("syslog_proposals_001.json", [
        {
            "template": "valid template <N>",
            "representative_samples": ["valid template 42"],
            "frequency": 10,
            "proposed_event_type": "TEST_VALID_A",
            "proposed_regex": "valid template \\d+",
            "subsystem": "TEST", "severity": "info",
            "description": "valid", "is_new_label": True, "rationale": "...",
            "ignorecase": False, "valid": True, "validation_error": None,
        },
        {
            "template": "invalid template <N>",
            "representative_samples": ["invalid template 1"],
            "frequency": 5,
            "proposed_event_type": "TEST_INVALID",
            "proposed_regex": "[bad", "subsystem": "TEST", "severity": "info",
            "description": "", "is_new_label": True, "rationale": "...",
            "ignorecase": False,
            "valid": False, "validation_error": "did not compile",
        },
        {
            "template": "another valid <N>",
            "representative_samples": ["another valid 7"],
            "frequency": 8,
            "proposed_event_type": "TEST_VALID_B",
            "proposed_regex": "another valid \\d+",
            "subsystem": "TEST", "severity": "warning",
            "description": "", "is_new_label": True, "rationale": "...",
            "ignorecase": False, "valid": True, "validation_error": None,
        },
    ])
    pending = proposals_queue.list_pending()
    labels = [p["proposed_event_type"] for p in pending]
    assert labels == ["TEST_VALID_A", "TEST_VALID_B"], f"got {labels}"
    print(f"  ok — 2 of 3 pending (invalid filtered), labels: {labels}")


def test_approve_writes_extension_jsonl():
    print("\n=== test 2: approve appends to extension JSONL and removes from pending ===")
    entry = proposals_queue.approve("syslog_proposals_001.json", 0)
    assert entry["event_type"] == "TEST_VALID_A"
    assert entry["regex"] == "valid template \\d+"
    assert "approved_at" in entry
    ext = _read_jsonl(DATA_DIR / "syslog_patterns_extension.jsonl")
    assert any(e["event_type"] == "TEST_VALID_A" for e in ext)
    # Now should be filtered from pending
    pending = proposals_queue.list_pending()
    labels = [p["proposed_event_type"] for p in pending]
    assert labels == ["TEST_VALID_B"], f"after approve, expected only TEST_VALID_B; got {labels}"
    print(f"  ok — TEST_VALID_A approved; pending now: {labels}")


def test_reject_writes_rejected_jsonl():
    print("\n=== test 3: reject appends to rejected JSONL and removes from pending ===")
    entry = proposals_queue.reject("syslog_proposals_001.json", 2, reason="test reject")
    assert entry["event_type"] == "TEST_VALID_B"
    assert entry["reason"] == "test reject"
    rej = _read_jsonl(DATA_DIR / "syslog_proposals_rejected.jsonl")
    assert any(e["event_type"] == "TEST_VALID_B" for e in rej)
    assert len(proposals_queue.list_pending()) == 0
    print("  ok — TEST_VALID_B rejected; queue is empty")


def test_dedupe_by_event_type_and_regex():
    print("\n=== test 4: dedupe — same (label, regex) emitted again is still hidden ===")
    # Write a NEW proposals file with the same (label, regex) as TEST_VALID_A
    # (already approved). It should NOT appear in pending.
    _write_proposal_file("syslog_proposals_002.json", [
        {
            "template": "valid template <N>",
            "representative_samples": ["valid template 99"],
            "frequency": 7,
            "proposed_event_type": "TEST_VALID_A",
            "proposed_regex": "valid template \\d+",
            "subsystem": "TEST", "severity": "info",
            "description": "duplicate", "is_new_label": True, "rationale": "...",
            "ignorecase": False, "valid": True, "validation_error": None,
        },
    ])
    pending = proposals_queue.list_pending()
    assert len(pending) == 0, f"expected 0 pending, got {len(pending)}"
    print("  ok — re-proposed duplicate is hidden because the (label, regex) is already approved")


def test_disabled_extension_unhides_proposal():
    print("\n=== test 5: disabling an approved extension lets the same proposal show up again ===")
    # Append a disable line for TEST_VALID_A
    with (DATA_DIR / "syslog_patterns_extension.jsonl").open("a") as f:
        f.write(json.dumps({
            "event_type": "TEST_VALID_A",
            "disabled_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
    pending = proposals_queue.list_pending()
    labels = [p["proposed_event_type"] for p in pending]
    # Both proposals files have a TEST_VALID_A; both should be pending again
    assert labels.count("TEST_VALID_A") == 2, f"expected 2 TEST_VALID_A entries, got {labels}"
    print(f"  ok — after disable, both TEST_VALID_A proposals are pending again ({len(labels)} total)")


def main() -> int:
    test_list_pending_excludes_invalid_and_already_decided()
    test_approve_writes_extension_jsonl()
    test_reject_writes_rejected_jsonl()
    test_dedupe_by_event_type_and_regex()
    test_disabled_extension_unhides_proposal()
    print("\nAll proposals_queue checks passed.")
    print(f"(Temp data dir was {TMP}; remove with `rm -rf {TMP}`.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
