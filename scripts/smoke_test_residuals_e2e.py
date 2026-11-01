"""
scripts/smoke_test_residuals_e2e.py — P6 end-to-end (no LLM).

Demonstrates the full residual control plane WITHOUT calling the LLM:

  1. Generate synthetic residuals (lines no built-in pattern matches).
  2. Cluster them with cluster_residuals().
  3. Build a *manual* proposals JSON (the shape the LLM would produce).
  4. Pipe it through review_proposals.py --auto-approve-valid.
  5. Spawn a fresh Python process and re-import the syslog modules so
     patterns_extension.py picks up the new JSONL.
  6. Verify classify_log_line() now returns the new label.

This proves the full (clusterer + JSONL append + extension load
+ patterns.py merge) is wired end-to-end. The LLM proposer itself is the
only piece this script does NOT exercise — that's smoke_test_residuals
(unit checks) plus propose_patterns.py against a live model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.patterns import classify_log_line  # noqa: E402
from src.syslog.residuals import cluster_residuals  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    # --- 1: synthesize residuals that the built-in regex DB won't match ---
    # Avoid common log keywords (kernel/module, error/warn/fail, []/{}/
    # cpus=/flags=, slurmstepd, amdgpu, Lustre, CXI, EDAC, etc.) since
    # INFO_NOISE is a very wide catch-all by design.
    synthetic_residuals = [
        "qwerty_gizmo glorp factor exceeds plateau by 42 percent",
        "qwerty_gizmo glorp factor exceeds plateau by 100 percent",
        "qwerty_gizmo glorp factor exceeds plateau by 7 percent",
        "qwerty_gizmo glorp factor exceeds plateau by 999 percent",
        "qwerty_gizmo glorp factor exceeds plateau by 555 percent",
        "qwerty_gizmo glorp factor exceeds plateau by 12 percent",
        "flarble status 7 ok",
    ]
    # Sanity: confirm built-in regex DB does NOT classify these.
    for line in synthetic_residuals:
        label = classify_log_line(line)
        assert label is None, f"expected residual, got {label!r} for: {line}"
    print(f"[1] synthesized {len(synthetic_residuals)} residuals "
          f"(all unclassified by built-in regex DB) — ok")

    # --- 2: cluster ---
    clusters = cluster_residuals(synthetic_residuals, min_size=3)
    assert len(clusters) == 1, f"expected 1 cluster, got {len(clusters)}"
    cluster = clusters[0]
    print(f"[2] cluster_residuals -> 1 cluster freq={cluster.frequency}, "
          f"template={cluster.template[:80]!r} — ok")

    # --- 3: build a manual proposal (shape the LLM would emit) ---
    proposal_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "MANUAL_TEST",
        "residuals_seen": len(synthetic_residuals),
        "clusters": 1,
        "proposals": [
            {
                "template": cluster.template,
                "representative_samples": cluster.samples,
                "frequency": cluster.frequency,
                "proposed_event_type": "APP_QWERTY_GLORP_WARN",
                "proposed_regex": r"qwerty_gizmo glorp factor exceeds plateau by \d+ percent",
                "subsystem": "APP",
                "severity": "warning",
                "description": "Qwerty_gizmo glorp factor exceeded nominal plateau.",
                "is_new_label": True,
                "rationale": "All samples share this verbatim form; distinct subsystem warrants a new label.",
                "ignorecase": False,
                "valid": True,
                "validation_error": None,
            }
        ],
    }

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        proposals_path = td_path / "proposals.json"
        ext_path = td_path / "ext.jsonl"
        proposals_path.write_text(json.dumps(proposal_doc, indent=2))
        print(f"[3] wrote synthetic proposals to {proposals_path}")

        # --- 4: review_proposals --auto-approve-valid ---
        result = subprocess.run(
            [
                str(REPO / ".venv" / "bin" / "python"),
                str(REPO / "scripts" / "review_proposals.py"),
                str(proposals_path),
                "--extensions", str(ext_path),
                "--auto-approve-valid",
            ],
            capture_output=True, text=True, cwd=str(REPO),
        )
        if result.returncode != 0:
            print("review_proposals.py STDOUT:\n" + result.stdout)
            print("review_proposals.py STDERR:\n" + result.stderr)
            return 1
        print(f"[4] review_proposals.py --auto-approve-valid: exit 0")
        ext_entries = [
            json.loads(ln) for ln in ext_path.read_text().splitlines() if ln.strip()
        ]
        assert len(ext_entries) == 1, f"expected 1 extension entry, got {len(ext_entries)}"
        assert ext_entries[0]["event_type"] == "APP_QWERTY_GLORP_WARN"
        assert "approved_at" in ext_entries[0]
        print(f"    extension JSONL has 1 entry: {ext_entries[0]['event_type']} — ok")

        # --- 5+6: fresh-process reload + classification check ---
        # patterns_extension.py loads at MODULE import time, so we must
        # spawn a new Python process to see the extension take effect.
        probe = (
            f"import os, sys, json;"
            f"os.environ['HERALD_SYSLOG_EXTENSIONS_PATH'] = {str(ext_path)!r};"
            f"sys.path.insert(0, {str(REPO)!r});"
            f"from src.syslog.patterns import classify_log_line, LOG_PATTERNS;"
            f"from src.syslog.patterns_extension import EXTENSION_PATTERNS, EXTENSION_TAXONOMY;"
            f"out = {{"
            f"  'ext_count': len(EXTENSION_PATTERNS),"
            f"  'in_merged': 'APP_QWERTY_GLORP_WARN' in LOG_PATTERNS,"
            f"  'classify_first': classify_log_line({synthetic_residuals[0]!r}),"
            f"  'classify_third': classify_log_line({synthetic_residuals[2]!r}),"
            f"  'taxonomy_subsystem': EXTENSION_TAXONOMY.get('APP_QWERTY_GLORP_WARN', {{}}).get('subsystem'),"
            f"  'taxonomy_severity': EXTENSION_TAXONOMY.get('APP_QWERTY_GLORP_WARN', {{}}).get('severity'),"
            f"}};"
            f"print(json.dumps(out))"
        )
        proc = subprocess.run(
            [str(REPO / ".venv" / "bin" / "python"), "-c", probe],
            capture_output=True, text=True, cwd=str(REPO),
        )
        if proc.returncode != 0:
            print("subprocess STDOUT:\n" + proc.stdout)
            print("subprocess STDERR:\n" + proc.stderr)
            return 1
        # The subprocess prints stderr from patterns_extension load — skip blank lines
        # to find the JSON.
        out_line = next((ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")), None)
        assert out_line, f"no JSON in subprocess stdout: {proc.stdout!r}"
        result = json.loads(out_line)
        print(f"[5] fresh-process reload check:")
        print(f"    EXTENSION_PATTERNS count:   {result['ext_count']}")
        print(f"    label in merged LOG_PATTERNS: {result['in_merged']}")
        print(f"    classify(sample 1): {result['classify_first']!r}")
        print(f"    classify(sample 3): {result['classify_third']!r}")
        print(f"    taxonomy:           {result['taxonomy_subsystem']} / "
              f"{result['taxonomy_severity']}")
        assert result["ext_count"] == 1
        assert result["in_merged"] is True
        assert result["classify_first"] == "APP_QWERTY_GLORP_WARN"
        assert result["classify_third"] == "APP_QWERTY_GLORP_WARN"
        assert result["taxonomy_subsystem"] == "APP"
        assert result["taxonomy_severity"] == "warning"
        print("[6] new label classifies the previously-unmatched residuals — ok")

    print("\nAll P6 end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
