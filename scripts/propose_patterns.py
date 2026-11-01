"""
scripts/propose_patterns.py — P6 batch: residuals -> clusters -> LLM proposals.

Pulls unclassified events (event_type NULL/empty) from the persistent
syslog store, clusters them by template, asks the configured LLM to
propose a regex + event_type for each cluster, and writes the proposals
to .data/syslog_proposals_<timestamp>.json for human review by
scripts/review_proposals.py.

Usage:
    .venv/bin/python scripts/propose_patterns.py
    .venv/bin/python scripts/propose_patterns.py --limit 5000 --min-cluster 10
    .venv/bin/python scripts/propose_patterns.py --out /tmp/foo.json

Reads settings:
    syslog_proposal_min_cluster
    syslog_proposal_min_residuals
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402
from src.syslog import state  # noqa: E402
from src.syslog.patterns import LOG_PATTERNS  # noqa: E402
from src.syslog.residuals import (  # noqa: E402
    cluster_residuals,
    propose_patterns,
    score_proposal,
)


def fetch_residuals(limit: int) -> list[str]:
    """
    Pull raw lines for residuals. Uses COALESCE so the same query works
    on both backends (DuckDB → NULL, ClickHouse → '').
    """
    store = state.syslog_store()
    sql = (
        "SELECT raw FROM events "
        "WHERE coalesce(event_type, '') = '' "
        f"LIMIT {int(limit)}"
    )
    raw_json = store.run_sql(sql)
    try:
        rows = json.loads(raw_json)
    except ValueError as exc:
        raise RuntimeError(f"residual query failed: {raw_json}") from exc
    out: list[str] = []
    for row in rows:
        raw = row.get("raw")
        if raw:
            out.append(raw)
    return out


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    # Explicit None check — `or` would treat `--min-cluster 0` and
    # `--min-residuals 0` as "unspecified" and fall back to the settings default.
    min_cluster = (
        args.min_cluster if args.min_cluster is not None
        else settings.syslog_proposal_min_cluster
    )
    min_residuals = (
        args.min_residuals if args.min_residuals is not None
        else settings.syslog_proposal_min_residuals
    )

    residuals = fetch_residuals(args.limit)
    print(f"Pulled {len(residuals)} residual lines from the store.")
    if len(residuals) < min_residuals:
        print(f"Below min_residuals={min_residuals}; nothing to propose.")
        return 0

    clusters = cluster_residuals(
        residuals,
        min_size=min_cluster,
        max_samples_per_cluster=args.samples_per_cluster,
        max_clusters=args.max_clusters,
    )
    print(f"Built {len(clusters)} clusters (min_cluster={min_cluster}).")
    if not clusters:
        print("No clusters meet the size threshold.")
        return 0
    for c in clusters[:10]:
        print(f"  freq={c.frequency:>6}  template={c.template[:100]}")
    if len(clusters) > 10:
        print(f"  ... (+{len(clusters) - 10} more)")

    try:
        from src.models.configured import get_large_model_client, get_large_model_name
    except Exception:
        # Fall back to whatever PydanticAI uses for the orchestrator.
        from src.models.pydantic_ai import get_large_pydantic_model  # noqa: F401
        print("ERROR: no get_large_model_client/get_large_model_name helper exposed.")
        print("Cannot run the LLM proposer in this configuration.")
        return 2

    client = get_large_model_client()
    model_name = get_large_model_name()

    print(f"\nCalling LLM ({model_name}) to propose patterns…")
    debug_sink: list[dict] = []
    proposals = await propose_patterns(
        clusters,
        client=client, model_name=model_name,
        known_labels=sorted(LOG_PATTERNS.keys()),
        batch_size=args.batch_size,
        debug_sink=debug_sink,
    )
    print(f"LLM returned {len(proposals)} proposals "
          f"({sum(1 for p in proposals if p.valid)} valid, "
          f"{sum(1 for p in proposals if not p.valid)} invalid).")

    # P6+ tiered auto-apply. CLI flag overrides the setting; default is the
    # setting value (which itself defaults to False — disabled until opt-in).
    auto_apply = (
        args.auto_apply if args.auto_apply is not None
        else settings.syslog_proposer_auto_apply
    )
    auto_min_freq = settings.syslog_proposer_auto_apply_min_frequency

    auto_approved: list = []
    queued: list = proposals
    if auto_apply:
        known_labels = set(LOG_PATTERNS.keys())
        auto_approved = []
        queued = []
        for p in proposals:
            verdict = score_proposal(
                p, known_labels=known_labels, min_frequency=auto_min_freq,
            )
            if verdict.auto_approve:
                auto_approved.append((p, verdict))
            else:
                queued.append(p)

        if auto_approved:
            ext_path = Path(settings.syslog_extensions_path)
            ext_path.parent.mkdir(parents=True, exist_ok=True)
            now_iso = datetime.now(timezone.utc).isoformat()
            with ext_path.open("a", encoding="utf-8") as f:
                for p, verdict in auto_approved:
                    entry = {
                        "event_type": p.proposed_event_type,
                        "regex": p.proposed_regex,
                        "subsystem": p.subsystem,
                        "severity": p.severity,
                        "description": p.description,
                        "ignorecase": p.ignorecase,
                        "auto_approved_at": now_iso,
                        "auto_approved_reason": verdict.reason,
                        "approved_from_template": p.template,
                        # No file/index — this proposal never entered the queue.
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"\nAuto-approved {len(auto_approved)} high-confidence proposal(s) "
                  f"to {ext_path}:")
            for p, verdict in auto_approved:
                print(f"  {p.proposed_event_type}  ({verdict.reason})")
        print(f"Queued for human review: {len(queued)} "
              f"(use --no-auto-apply or set syslog_proposer_auto_apply=false to disable)")
    else:
        print("\nAuto-apply: OFF (every proposal goes to the queue). "
              "Set syslog_proposer_auto_apply=true or pass --auto-apply to opt in.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(args.out or f".data/syslog_proposals_{ts}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": model_name,
            "residuals_seen": len(residuals),
            "clusters": len(clusters),
            "auto_apply": auto_apply,
            "auto_approved": [p.proposed_event_type for p, _ in auto_approved],
            "proposals": [p.to_dict() for p in queued],
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote proposals → {out_path}")

    # If we got debug batches with parse errors OR zero proposals, dump the
    # raw LLM responses alongside the proposals file so the failure is
    # diagnosable without re-running.
    if debug_sink and (not proposals or any(b.get("parse_error") for b in debug_sink)):
        debug_path = out_path.with_suffix(".debug.json")
        debug_path.write_text(
            json.dumps(debug_sink, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Wrote raw LLM debug dump → {debug_path}")
        print("(Inspect to see exactly what the model returned and why parsing failed.)")

    print(f"Review with: scripts/review_proposals.py {out_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=10_000,
                    help="Max residuals to fetch from the store.")
    ap.add_argument("--min-cluster", type=int, default=None,
                    help="Override syslog_proposal_min_cluster setting (0 disables the threshold).")
    ap.add_argument("--min-residuals", type=int, default=None,
                    help="Override syslog_proposal_min_residuals setting (0 disables the threshold).")
    ap.add_argument("--samples-per-cluster", type=int, default=5)
    ap.add_argument("--max-clusters", type=int, default=80)
    ap.add_argument("--batch-size", type=int, default=20,
                    help="Clusters per LLM call.")
    ap.add_argument("--auto-apply", dest="auto_apply", action="store_true",
                    default=None,
                    help="Override settings: enable tiered auto-apply for this run.")
    ap.add_argument("--no-auto-apply", dest="auto_apply", action="store_false",
                    help="Override settings: force every proposal to the human queue.")
    ap.add_argument("--out", default=None, help="Output JSON path.")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
