"""
src/syslog/proposals_queue.py — shared logic for the proposals queue.

Used by both scripts/review_proposals.py (interactive CLI) and the
/api/syslog/proposals/* REST endpoints, so both paths produce identical
extension-JSONL entries and identical rejected-JSONL entries.

Data model:

  .data/syslog_proposals_<ts>.json        proposals written by propose_patterns
                                          (immutable; one file per proposer run)
  .data/syslog_patterns_extension.jsonl   approved (with optional disabled_at)
  .data/syslog_proposals_rejected.jsonl   rejected (don't show me again)

A proposal is "pending" if:
  - It appears in some proposals_*.json
  - Its (event_type, regex) is not yet in extension JSONL
  - Its (event_type, regex) is not yet in rejected JSONL
  - The regex compiles and matches at least one representative sample
    (i.e. valid=True from the proposer's own validation)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Paths ─────────────────────────────────────────────────────────────────


def _data_dir() -> Path:
    """The `.data/` dir under the repo root (where proposals + JSONLs live)."""
    return Path(__file__).resolve().parent.parent.parent / ".data"


def _extension_path() -> Path:
    from src.config import get_settings
    path = os.environ.get("HERALD_SYSLOG_EXTENSIONS_PATH")
    if path:
        return Path(path)
    try:
        return Path(get_settings().syslog_extensions_path)
    except Exception:
        return _data_dir() / "syslog_patterns_extension.jsonl"


def _rejected_path() -> Path:
    from src.config import get_settings
    try:
        return Path(get_settings().syslog_proposals_rejected_path)
    except Exception:
        return _data_dir() / "syslog_proposals_rejected.jsonl"


# ── Identity ──────────────────────────────────────────────────────────────


def proposal_key(event_type: str, regex: str) -> str:
    """Stable short hash identifying a unique (label, regex) proposal.
    Used to dedupe across multiple proposer runs and JSONL appends.
    """
    return hashlib.sha256(f"{event_type}|{regex}".encode("utf-8")).hexdigest()[:16]


# ── File I/O ──────────────────────────────────────────────────────────────


def list_proposal_files() -> list[Path]:
    """All proposals_*.json under .data/, newest first."""
    files = sorted(
        _data_dir().glob("syslog_proposals_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # Exclude .debug.json sidecars
    return [p for p in files if not p.name.endswith(".debug.json")]


def load_proposals_file(path: Path | str) -> dict[str, Any]:
    """Returns the parsed JSON. Caller can read meta + proposals."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Status queries ────────────────────────────────────────────────────────


def _approved_keys() -> set[str]:
    """All (event_type, regex) hashes currently approved (non-disabled).
    Honors disabled_at by tracking last-write-wins per event_type."""
    state: dict[str, str | None] = {}  # event_type -> regex (or None if disabled)
    for entry in _read_jsonl(_extension_path()):
        et = entry.get("event_type")
        if not et:
            continue
        if entry.get("disabled_at"):
            state[et] = None
        elif entry.get("regex"):
            state[et] = entry["regex"]
    return {proposal_key(et, regex) for et, regex in state.items() if regex}


def _rejected_keys() -> set[str]:
    return {
        proposal_key(e["event_type"], e["regex"])
        for e in _read_jsonl(_rejected_path())
        if e.get("event_type") and e.get("regex")
    }


# ── Pending list ──────────────────────────────────────────────────────────


def list_pending() -> list[dict[str, Any]]:
    """All pending proposals across all proposals files, newest file first.

    Each returned dict is the proposal augmented with:
      - `file`: name of the proposals file it came from
      - `file_path`: absolute path
      - `index`: position within that file's proposals list
      - `key`: proposal_key for stable identity
      - `proposer_generated_at`: from the proposals file header
      - `proposer_model`: from the proposals file header
    """
    approved = _approved_keys()
    rejected = _rejected_keys()
    out: list[dict[str, Any]] = []
    for path in list_proposal_files():
        try:
            doc = load_proposals_file(path)
        except (json.JSONDecodeError, OSError):
            continue
        meta_gen_at = doc.get("generated_at")
        meta_model = doc.get("model")
        for i, p in enumerate(doc.get("proposals", [])):
            if not p.get("valid", True):
                continue
            et = p.get("proposed_event_type")
            rx = p.get("proposed_regex")
            if not et or not rx:
                continue
            key = proposal_key(et, rx)
            if key in approved or key in rejected:
                continue
            enriched = dict(p)
            enriched["file"] = path.name
            enriched["file_path"] = str(path)
            enriched["index"] = i
            enriched["key"] = key
            enriched["proposer_generated_at"] = meta_gen_at
            enriched["proposer_model"] = meta_model
            out.append(enriched)
    return out


# ── Mutations: approve and reject ─────────────────────────────────────────


def _proposal_at(file: str, index: int) -> dict[str, Any]:
    """Look up a proposal by (file_name, index). Raises KeyError on miss."""
    path = _data_dir() / file
    if not path.exists():
        raise KeyError(f"proposals file not found: {file}")
    doc = load_proposals_file(path)
    proposals = doc.get("proposals", [])
    if not (0 <= index < len(proposals)):
        raise KeyError(f"index {index} out of range for {file} (have {len(proposals)})")
    return proposals[index]


def approve(
    file: str,
    index: int,
    *,
    overrides: dict | None = None,
    keep_upstream: list[str] | None = None,
    keep_downstream: list[str] | None = None,
) -> dict[str, Any]:
    """
    Append the proposal at (file, index) to the extension JSONL.

    `overrides` lets the caller adjust regex/severity/description/etc.
    before append (same as the CLI's 'edit then approve' flow).

    `keep_upstream` / `keep_downstream` filter the LLM-proposed causal
    edges. None = keep every proposed edge. Empty list = drop all of
    that side. A list of labels = keep only those (subset of the
    proposed labels).

    Returns the appended entry. Raises KeyError on bad (file, index).
    """
    prop = _proposal_at(file, index)
    merged = {**prop, **(overrides or {})}

    # Build the causal_edges block from LLM proposals + caller filters.
    proposed_up = merged.get("proposed_upstream") or []
    proposed_dn = merged.get("proposed_downstream") or []

    def _filter_edges(proposed, keep):
        if keep is None:
            return proposed
        kept = []
        keep_set = {k for k in keep}
        for e in proposed:
            if isinstance(e, dict) and e.get("label") in keep_set:
                kept.append(e)
        return kept

    kept_up = _filter_edges(proposed_up, keep_upstream)
    kept_dn = _filter_edges(proposed_dn, keep_downstream)

    entry: dict[str, Any] = {
        "event_type": merged["proposed_event_type"],
        "regex": merged["proposed_regex"],
        "subsystem": merged.get("subsystem", "UNKNOWN"),
        "severity": merged.get("severity", "info"),
        "description": merged.get("description", ""),
        "ignorecase": bool(merged.get("ignorecase", False)),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_from_template": merged.get("template", ""),
        "approved_from_file": file,
        "approved_from_index": index,
    }
    if kept_up or kept_dn:
        entry["causal_edges"] = {
            "upstream": [e["label"] for e in kept_up],
            "downstream": [e["label"] for e in kept_dn],
        }
        if proposed_up or proposed_dn:
            entry["causal_edges_proposed_by_llm"] = True
    _append_jsonl(_extension_path(), entry)
    return entry


def reject(file: str, index: int, *, reason: str | None = None) -> dict[str, Any]:
    """Append a rejection entry to the rejected JSONL so this proposal
    stops appearing in list_pending(). Identity is (event_type, regex)
    so re-proposed duplicates also get suppressed."""
    prop = _proposal_at(file, index)
    entry = {
        "event_type": prop["proposed_event_type"],
        "regex": prop["proposed_regex"],
        "template": prop.get("template", ""),
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        "rejected_from_file": file,
        "rejected_from_index": index,
        "reason": reason,
    }
    _append_jsonl(_rejected_path(), entry)
    return entry


def summary() -> dict[str, Any]:
    """One-shot stats for dashboards / alerts."""
    return {
        "pending": len(list_pending()),
        "approved_total": len(_approved_keys()),
        "rejected_total": len(_rejected_keys()),
        "proposal_files": [str(p.name) for p in list_proposal_files()],
    }
