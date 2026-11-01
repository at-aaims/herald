"""
src/syslog/patterns_extension.py — load human-approved regex extensions.

Approved patterns are stored as JSONL at settings.syslog_extensions_path
(default `.data/syslog_patterns_extension.jsonl`). One entry per line:

  {
    "event_type": "FS_LUSTRE_NEW_PATTERN",
    "regex": "LustreError: .* something specific",
    "subsystem": "FS",
    "severity": "error",
    "description": "Short one-line operational meaning.",
    "ignorecase": false,
    "approved_at": "2026-05-18T00:00:00Z",
    "approved_from_template": "LustreError: <PATH> ..."
  }

This module loads them at import time. `patterns.py` merges
EXTENSION_PATTERNS ahead of the built-in LOG_PATTERNS so user-approved
extensions take priority on the regex match order, and so users can
override a built-in by approving a same-named entry.

The file is plain JSONL on purpose:
  - human-editable
  - line-grained append (no rewrite hazards on parallel approvals)
  - greppable and trivially diff-able in git
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Pattern


# Default lives alongside the syslog DuckDB and demo data.
_DEFAULT_REL_PATH = ".data/syslog_patterns_extension.jsonl"


def _resolve_path(explicit: str | Path | None = None) -> Path:
    """Path resolution: explicit arg > env var > settings > repo-relative default."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get("HERALD_SYSLOG_EXTENSIONS_PATH")
    if env:
        return Path(env)
    # Lazy import — settings access here would cause a circular import if
    # config.py ever imports patterns.py. Today it doesn't, but defensive.
    try:
        from src.config import get_settings
        return Path(get_settings().syslog_extensions_path)
    except Exception:
        return Path(__file__).resolve().parent.parent.parent / _DEFAULT_REL_PATH


def load_extension_edges(
    path: str | Path | None = None,
) -> list[dict]:
    """Parse `causal_edges` blocks from every (non-disabled) entry in the
    extension JSONL and return a flat list of `(cause, effect, source_label)`
    dicts. These become tier="Manual" edges in the in-memory CausalGraph and
    in the SQL `causal_edges` table.

    JSONL schema this function understands:

      Form (a) — declared at approval time, attached to the entry that also
      defines a new regex:
        {"event_type": "HW_NEW", "regex": "...", "approved_at": "...",
         "causal_edges": {"upstream": ["HW_THERMAL_CRIT"],
                          "downstream": ["APP_INFRA_FAIL"]},
         "causal_edges_proposed_by_llm": true}

      Form (b) — graph-edges-only entry, added later for an already-known
      label (built-in or earlier extension):
        {"event_type": "HW_FOOBAR", "graph_edges_only": true,
         "causal_edges": {"upstream": ["HW_THERMAL_CRIT"]},
         "edges_added_at": "..."}

      An entry with disabled_at retracts ALL of its previously declared edges
      (same disabled-at semantic as for the regex itself).
    """
    p = _resolve_path(path)
    if not p.exists():
        return []
    # event_type -> dict of (other_event_type, direction) edges, last-write-wins.
    # We mirror the disabled_at semantic: an entry with disabled_at clears
    # the label's contributions and a later (re-)approval restores them.
    state: dict[str, list[tuple[str, str, str]]] = {}  # label -> [(other, direction, source)]
    for entry in _iter_entries(p):
        label = entry.get("event_type")
        if not label:
            continue
        if entry.get("disabled_at"):
            state[label] = []
            continue
        edges_block = entry.get("causal_edges") or {}
        if not isinstance(edges_block, dict):
            continue
        contributions: list[tuple[str, str, str]] = []
        for other in _label_list(edges_block.get("upstream")):
            contributions.append((other, "upstream", label))
        for other in _label_list(edges_block.get("downstream")):
            contributions.append((other, "downstream", label))
        # Last write wins for this label — a re-approval REPLACES the prior
        # edges, matching how regex replacement works.
        if contributions or "causal_edges" in entry or entry.get("graph_edges_only"):
            state[label] = contributions

    # Flatten contributions into directed edges. Direction "upstream" means
    # the OTHER event causes the LABEL; "downstream" means LABEL causes OTHER.
    out: list[dict] = []
    for label, contributions in state.items():
        for other, direction, source in contributions:
            if direction == "upstream":
                cause, effect = other, label
            else:
                cause, effect = label, other
            out.append({
                "cause": cause, "effect": effect,
                "source_event_type": source,
            })
    return out


def _iter_entries(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _label_list(raw) -> list[str]:
    """Accept ['LABEL', ...] or [{'label': 'LABEL', ...}, ...]; return strings."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for e in raw:
        if isinstance(e, str) and e.strip():
            out.append(e.strip())
        elif isinstance(e, dict):
            label = str(e.get("label") or e.get("cause") or e.get("effect") or "").strip()
            if label:
                out.append(label)
    return out


def load_extension_patterns(
    path: str | Path | None = None,
) -> tuple[dict[str, Pattern[str]], dict[str, dict]]:
    """
    Returns (compiled_patterns_by_label, taxonomy_metadata_by_label).

    Silently skips malformed lines or invalid regex (so a bad approval
    doesn't break the whole regex DB at import time). Bad entries are
    flagged via stderr so they're not invisible.

    Soft-rollback: an entry with a non-empty `disabled_at` field REMOVES
    its label from the loaded set, even if an earlier line approved it.
    Re-approval is simply appending another entry for the same label
    (without `disabled_at`) — last write wins. This keeps the JSONL
    strictly append-only so the file IS the audit log.
    """
    p = _resolve_path(path)
    patterns: dict[str, Pattern[str]] = {}
    taxonomy: dict[str, dict] = {}
    if not p.exists():
        return patterns, taxonomy

    with p.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[patterns_extension] {p}:{lineno} JSON error: {e}", file=__import__("sys").stderr)
                continue
            label = entry.get("event_type")
            if not label:
                print(f"[patterns_extension] {p}:{lineno} missing event_type; skipped",
                      file=__import__("sys").stderr)
                continue
            # Soft-rollback: a disabled entry retracts any earlier approval
            # for this label. The label may be re-approved by a later line.
            if entry.get("disabled_at"):
                patterns.pop(label, None)
                taxonomy.pop(label, None)
                continue
            # graph_edges_only entries are legitimate — they declare manual
            # causal edges for an existing label and intentionally carry no
            # regex. The edges loader (load_extension_edges) consumes them;
            # the patterns loader skips them silently.
            if entry.get("graph_edges_only"):
                continue
            regex = entry.get("regex")
            if not regex:
                print(f"[patterns_extension] {p}:{lineno} missing regex; skipped",
                      file=__import__("sys").stderr)
                continue
            try:
                flags = re.IGNORECASE if entry.get("ignorecase") else 0
                patterns[label] = re.compile(regex, flags)
            except re.error as e:
                print(f"[patterns_extension] {p}:{lineno} bad regex {label}: {e}",
                      file=__import__("sys").stderr)
                continue
            taxonomy[label] = {
                "subsystem": entry.get("subsystem", "UNKNOWN"),
                "severity": entry.get("severity", "info"),
                "description": entry.get("description", ""),
                "approved_at": entry.get("approved_at"),
                # P6+ auto-apply provenance (None for human-approved entries):
                "auto_approved_at": entry.get("auto_approved_at"),
                "auto_approved_reason": entry.get("auto_approved_reason"),
            }
    return patterns, taxonomy


# Module-level singletons. `patterns.py` reads these at its own import time.
EXTENSION_PATTERNS, EXTENSION_TAXONOMY = load_extension_patterns()
# Manual causal edges (P6+). Empty list when no extension entries declare any.
# Consumed by causal.py (in-memory CausalGraph) and store.py (SQL causal_edges).
EXTENSION_CAUSAL_EDGES: list[dict] = load_extension_edges()
