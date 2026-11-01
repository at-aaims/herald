"""
scripts/inject_residuals.py — pump synthetic unmatched lines into the syslog
store so scripts/propose_patterns.py has something to work with.

Use when your DuckDB doesn't yet have real residuals (e.g. you just spun up
the demo and every line matches a built-in regex). The injected lines are
deliberately gibberish-with-structure so the built-in regex DB returns None
and they show up as residuals.

Run AFTER stopping `make api` to avoid DuckDB single-writer contention.

Usage:
    .venv/bin/python scripts/inject_residuals.py
    .venv/bin/python scripts/inject_residuals.py --templates 5 --per-template 6
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog import state  # noqa: E402
from src.syslog.classifier import ParsedEvent  # noqa: E402
from src.syslog.patterns import classify_log_line  # noqa: E402


DEFAULT_TEMPLATES = [
    "qwerty_gizmo glorp factor exceeds plateau by {} percent",
    "flarble service plinth wobble at sensor {} measured high",
    "zorblax controller emitted spurious frob token {}",
    "wibble cache eviction rate {} per second observed",
    "foobar daemon thermal headroom dropped to {} kelvin",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--templates", type=int, default=len(DEFAULT_TEMPLATES),
                    help="How many templates from the built-in list to use.")
    ap.add_argument("--per-template", type=int, default=6,
                    help="How many variations to emit per template.")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    templates = DEFAULT_TEMPLATES[: args.templates]

    # Confirm the templates are actually unmatched (catches regressions where
    # someone tightens a built-in regex to swallow our test lines).
    for tmpl in templates:
        label = classify_log_line(tmpl.format(1234))
        if label is not None:
            print(f"ERROR: template would classify as {label!r}, not a residual:")
            print(f"  {tmpl}")
            return 2

    t0 = datetime.now(timezone.utc) - timedelta(minutes=10)
    events = []
    for i, tmpl in enumerate(templates):
        for j in range(args.per_template):
            events.append(ParsedEvent(
                ts=t0 + timedelta(seconds=i * 5 + j),
                node=f"frontier-{rng.randint(1, 100):04d}",
                event_type=None,
                raw=tmpl.format(rng.randint(1, 9999)),
                severity="residual",
                subsystem="UNKNOWN",
            ))

    try:
        store = state.syslog_store()
    except Exception as exc:
        print(f"ERROR: could not open store: {exc}")
        print("If the API is running, stop it first (Ctrl-C `make api`).")
        return 1

    before = store.event_count()
    store.write_events(events)
    after = store.event_count()
    print(f"Injected {len(events)} synthetic residuals "
          f"across {len(templates)} templates.")
    print(f"Store row count: {before} → {after}")
    print()
    print("Next steps:")
    print("  .venv/bin/python scripts/propose_patterns.py "
          "--limit 1000 --min-cluster 3 --min-residuals 0")
    print("  .venv/bin/python scripts/review_proposals.py .data/syslog_proposals_*.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
