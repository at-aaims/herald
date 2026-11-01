"""
scripts/smoke_test_syslog.py — sanity-check the syslog classifier.

Runs the regex DB against a CSV log source and reports:
  - lines seen, matched, residual
  - match rate
  - top-N event types by count
  - a few sample residual lines (so we can see what's slipping through)

Usage:
    python -m scripts.smoke_test_syslog                          # uses default sample
    python -m scripts.smoke_test_syslog /path/to/logs.csv
    python -m scripts.smoke_test_syslog /path/to/logs.csv --no-sample-noise
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# Allow running as `python scripts/smoke_test_syslog.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.patterns import classify_log_line, severity_for, subsystem_for  # noqa: E402

DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".data" / "sample_data_logs.csv"


def iter_csv_messages(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return
        msg_col = "log_message" if "log_message" in reader.fieldnames else reader.fieldnames[-1]
        for row in reader:
            msg = row.get(msg_col)
            if msg:
                yield msg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(DEFAULT_PATH))
    ap.add_argument("--top", type=int, default=20, help="Top-N event types to show")
    ap.add_argument("--residual-samples", type=int, default=10)
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    counts: Counter[str] = Counter()
    by_subsystem: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    residual_samples: list[str] = []
    total = 0
    matched = 0

    for msg in iter_csv_messages(path):
        total += 1
        label = classify_log_line(msg)
        if label is None:
            if len(residual_samples) < args.residual_samples:
                residual_samples.append(msg)
            continue
        matched += 1
        counts[label] += 1
        by_subsystem[subsystem_for(label)] += 1
        by_severity[severity_for(label)] += 1

    print(f"Source:           {path}")
    print(f"Lines seen:       {total}")
    print(f"Matched:          {matched}  ({matched/total*100:.1f}%)" if total else "Matched: 0")
    print(f"Residual:         {total - matched}")
    print()
    print(f"Top {args.top} event types:")
    for label, n in counts.most_common(args.top):
        pct = n / total * 100 if total else 0
        print(f"  {label:<22} {n:>6}  ({pct:5.2f}%)  [{severity_for(label)}]")
    print()
    print("By subsystem:")
    for sub, n in by_subsystem.most_common():
        print(f"  {sub:<10} {n:>6}")
    print()
    print("By severity:")
    for sev, n in by_severity.most_common():
        print(f"  {sev:<10} {n:>6}")

    if residual_samples:
        print()
        print(f"Residual samples (first {len(residual_samples)}):")
        for s in residual_samples:
            preview = s if len(s) <= 140 else s[:137] + "..."
            print(f"  - {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
