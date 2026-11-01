"""
scripts/verify_extensions.py — confirm approved extensions are live.

Loads the syslog patterns + extension layer in this fresh Python process
and prints what got merged, then classifies a sample line per extension
to prove the regex actually takes effect.

Usage:
    .venv/bin/python scripts/verify_extensions.py
    .venv/bin/python scripts/verify_extensions.py "your test line here"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.patterns import LOG_PATTERNS, classify_log_line  # noqa: E402
from src.syslog.patterns_extension import EXTENSION_PATTERNS, EXTENSION_TAXONOMY  # noqa: E402


DEFAULT_SAMPLES = [
    "qwerty_gizmo glorp factor exceeds plateau by 50 percent",
    "flarble service plinth wobble at sensor 42 measured high",
    "zorblax controller emitted spurious frob token 7",
    "wibble cache eviction rate 9999 per second observed",
    "foobar daemon thermal headroom dropped to 280 kelvin",
]


def main() -> int:
    print(f"extensions loaded:  {len(EXTENSION_PATTERNS)}")
    print(f"total LOG_PATTERNS: {len(LOG_PATTERNS)}")
    print()

    if not EXTENSION_PATTERNS:
        print("No extensions in the JSONL. Run propose_patterns.py + review_proposals.py first.")
        return 1

    print("Extension labels:")
    for label, meta in EXTENSION_TAXONOMY.items():
        print(f"  {label:<32}  {meta.get('subsystem','?')}/{meta.get('severity','?')}"
              f"  — {meta.get('description','')}")
    print()

    samples = sys.argv[1:] or DEFAULT_SAMPLES
    print("Classification results:")
    all_classified = True
    for s in samples:
        label = classify_log_line(s)
        marker = " " if label else "!"
        if not label:
            all_classified = False
        print(f"  {marker} {s[:80]:<80}  ->  {label}")
    return 0 if all_classified else 1


if __name__ == "__main__":
    raise SystemExit(main())
