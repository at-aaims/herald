"""
scripts/review_proposals.py — P6 interactive review of LLM-proposed patterns.

Walks a proposals JSON file (output of scripts/propose_patterns.py) and
prompts approve/reject/edit/skip per proposal. Approved entries are
appended to the extension JSONL (syslog_extensions_path setting).

Usage:
    .venv/bin/python scripts/review_proposals.py .data/syslog_proposals_<ts>.json
    .venv/bin/python scripts/review_proposals.py FILE --extensions /custom/path.jsonl
    .venv/bin/python scripts/review_proposals.py FILE --auto-approve-valid    # skip prompts

After approving, restart the API to load the new patterns.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402


def _prompt(msg: str, choices: str) -> str:
    while True:
        try:
            ans = input(f"{msg} [{choices}]: ").strip().lower()
        except EOFError:
            return "q"
        if ans in choices.replace("/", ""):
            return ans


def _validate_regex(regex: str, ignorecase: bool, samples: list[str]) -> tuple[bool, str]:
    try:
        flags = re.IGNORECASE if ignorecase else 0
        compiled = re.compile(regex, flags)
    except re.error as e:
        return False, f"compile error: {e}"
    if samples and not any(compiled.search(s) for s in samples):
        return False, "regex matches none of the representative samples"
    return True, ""


def _edit_proposal(prop: dict) -> dict:
    print("\nEdit fields (blank = keep current). Ctrl-D to finish.")
    fields = ("proposed_event_type", "proposed_regex", "subsystem", "severity",
              "description", "ignorecase")
    for f in fields:
        cur = prop.get(f)
        try:
            new = input(f"  {f} [{cur}]: ").strip()
        except EOFError:
            print()
            break
        if not new:
            continue
        prop[f] = (new.lower() in ("true", "1", "yes")) if f == "ignorecase" else new
    return prop


def _prompt_edges(prop: dict, auto: bool) -> tuple[list[str] | None, list[str] | None]:
    """Show the LLM-proposed causal edges and ask which to keep.
    Returns (keep_upstream, keep_downstream); None = keep all on that side."""
    up = prop.get("proposed_upstream") or []
    dn = prop.get("proposed_downstream") or []
    if not up and not dn:
        return None, None

    def _show(side, items):
        print(f"  {side}:")
        for i, e in enumerate(items, 1):
            label = e.get("label") if isinstance(e, dict) else str(e)
            rationale = e.get("rationale", "") if isinstance(e, dict) else ""
            print(f"    [{i}] {label}" + (f" — {rationale}" if rationale else ""))

    print("\n  LLM-proposed causal edges (operator-approve to land in graph as tier='Manual'):")
    if up: _show("upstream causes", up)
    if dn: _show("downstream effects", dn)
    if auto:
        return None, None  # keep all in --auto-approve-valid

    def _parse(side_name, items):
        if not items:
            return None
        try:
            ans = input(f"  Keep which {side_name}? [all/none/comma-list, default=all]: ").strip().lower()
        except EOFError:
            return None
        if not ans or ans == "all":
            return None
        if ans == "none":
            return []
        kept = []
        for tok in ans.split(","):
            tok = tok.strip()
            try:
                idx = int(tok) - 1
                if 0 <= idx < len(items):
                    label = items[idx].get("label") if isinstance(items[idx], dict) else str(items[idx])
                    if label: kept.append(label)
            except ValueError:
                continue
        return kept

    keep_up = _parse("upstream", up)
    keep_dn = _parse("downstream", dn)
    return keep_up, keep_dn


def _append_extension(
    path: Path, prop: dict,
    *,
    keep_upstream: list[str] | None = None,
    keep_downstream: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict = {
        "event_type": prop["proposed_event_type"],
        "regex": prop["proposed_regex"],
        "subsystem": prop.get("subsystem", "UNKNOWN"),
        "severity": prop.get("severity", "info"),
        "description": prop.get("description", ""),
        "ignorecase": bool(prop.get("ignorecase", False)),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_from_template": prop.get("template", ""),
    }
    # Apply the same edge-filter as proposals_queue.approve so CLI and
    # REST/UI paths produce identical JSONL entries.
    up = prop.get("proposed_upstream") or []
    dn = prop.get("proposed_downstream") or []
    def _keep(proposed, keep):
        if keep is None:
            return [e.get("label") if isinstance(e, dict) else str(e) for e in proposed if (e.get("label") if isinstance(e, dict) else e)]
        ks = set(keep)
        return [e.get("label") if isinstance(e, dict) else str(e) for e in proposed
                if (e.get("label") if isinstance(e, dict) else e) in ks]
    kept_up = _keep(up, keep_upstream)
    kept_dn = _keep(dn, keep_downstream)
    if kept_up or kept_dn:
        entry["causal_edges"] = {"upstream": kept_up, "downstream": kept_dn}
        if up or dn:
            entry["causal_edges_proposed_by_llm"] = True
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("proposals_file", help="JSON output of propose_patterns.py")
    ap.add_argument("--extensions", default=None,
                    help="Override syslog_extensions_path.")
    ap.add_argument("--auto-approve-valid", action="store_true",
                    help="Approve every valid proposal without prompting.")
    args = ap.parse_args()

    proposals_path = Path(args.proposals_file)
    if not proposals_path.exists():
        print(f"ERROR: {proposals_path} not found")
        return 2
    payload = json.loads(proposals_path.read_text(encoding="utf-8"))
    proposals = payload.get("proposals", [])
    print(f"Loaded {len(proposals)} proposals from {proposals_path}\n")

    settings = get_settings()
    ext_path = Path(args.extensions or settings.syslog_extensions_path)
    print(f"Approved entries → {ext_path}\n")

    approved = rejected = skipped = 0
    for i, prop in enumerate(proposals, 1):
        print("─" * 60)
        print(f"[{i}/{len(proposals)}]  freq={prop.get('frequency'):>5}  "
              f"label={prop.get('proposed_event_type')!r}  "
              f"({'new' if prop.get('is_new_label') else 'existing'}, "
              f"{prop.get('subsystem')}/{prop.get('severity')})")
        print(f"  template: {prop.get('template','')[:120]}")
        for s in prop.get("representative_samples", [])[:3]:
            print(f"    sample: {s[:120]}")
        print(f"  regex:   {prop.get('proposed_regex')}")
        print(f"  why:     {prop.get('rationale','')[:200]}")
        if not prop.get("valid", True):
            print(f"  !! INVALID: {prop.get('validation_error')}")

        ok, err = _validate_regex(
            prop.get("proposed_regex", ""),
            bool(prop.get("ignorecase", False)),
            prop.get("representative_samples", []),
        )
        if not ok:
            print(f"  !! re-validation: {err}")

        if args.auto_approve_valid:
            ans = "a" if ok else "r"
            print(f"  [auto: {'approve' if ans == 'a' else 'reject'}]")
        else:
            ans = _prompt("approve / reject / edit / skip / quit", "a/r/e/s/q")

        if ans == "q":
            print("Stopping.")
            break
        if ans == "e":
            prop = _edit_proposal(prop)
            ok, err = _validate_regex(
                prop.get("proposed_regex", ""),
                bool(prop.get("ignorecase", False)),
                prop.get("representative_samples", []),
            )
            if not ok:
                print(f"  !! still invalid after edit: {err}")
                ans = _prompt("approve anyway / reject / skip", "a/r/s")
            else:
                ans = _prompt("approve / reject / skip", "a/r/s")

        if ans == "a":
            keep_up, keep_dn = _prompt_edges(prop, auto=args.auto_approve_valid)
            _append_extension(
                ext_path, prop,
                keep_upstream=keep_up, keep_downstream=keep_dn,
            )
            approved += 1
            print(f"  → approved → {ext_path}")
        elif ans == "r":
            rejected += 1
        else:
            skipped += 1

    print()
    print(f"Summary: approved={approved} rejected={rejected} skipped={skipped}")
    if approved:
        print(f"\nRestart the API to pick up the new patterns:")
        print(f"  (Ctrl-C the running `make api`, then re-run `make api`.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
