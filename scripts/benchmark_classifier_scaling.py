#!/usr/bin/env python3
"""
scripts/benchmark_classifier_scaling.py — local proof-of-concept for
horizontally scaling StreamingClassifier.classify() (P8).

Compares (a) today's single-process sequential classify() loop against
(b) a ProcessPoolExecutor with N worker processes, each owning its own
StreamingClassifier instance, on a synthetic corpus with a deliberately
uneven per-node distribution (a few chatty nodes dominate — the realistic
shape of Kafka traffic partitioned by hostname, not uniform round-robin).

IMPORTANT — this process pool is a *local N-process throughput simulator*,
not the production dispatch mechanism. In the real deployment (once a real
Kafka topic exists), each worker process owns its Kafka partition(s)
directly and classifies its own consumed batches locally — there is no
cross-process dispatch of individual lines in production; that would
reintroduce the exact IPC overhead this benchmark works around by dispatching
chunks instead of lines.

classify() mutates a Counter/deque/random.Random with no lock — it is
CPU-bound and NOT thread-safe, so this deliberately uses processes, not
threads (threads would also buy nothing here under the GIL for CPU-bound
regex matching).

Usage:
    .venv/bin/python scripts/benchmark_classifier_scaling.py [--lines 1000000] [--workers 1 2 4 8]
"""
from __future__ import annotations

import argparse
import random
import sys
import time
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_demo_cascades import SAMPLE_MESSAGES  # noqa: E402
from src.syslog.classifier import StreamingClassifier  # noqa: E402

CHUNK_SIZE = 1000  # lines per dispatched task — see module docstring


def make_corpus(n_lines: int, n_nodes: int = 64, seed: int = 17) -> list[tuple[str, str]]:
    """[(node, log_message)], with a Zipf-like node distribution (a handful
    of chatty nodes dominate) — the realistic shape of hostname-partitioned
    traffic, not uniform round-robin."""
    rng = random.Random(seed)
    nodes = [f"frontier-{i:04d}" for i in range(n_nodes)]
    # Zipf-ish weights: node 0 is ~10x noisier than the median node.
    weights = [1.0 / (i + 1) for i in range(n_nodes)]
    messages = list(SAMPLE_MESSAGES.values())
    corpus = []
    for _ in range(n_lines):
        node = rng.choices(nodes, weights=weights, k=1)[0]
        msg = rng.choice(messages)
        corpus.append((node, msg))
    return corpus


def _classify_chunk(chunk: list[tuple[int, str, str]], seed: int) -> list[tuple[int, str | None]]:
    """Runs in a worker process: classify a chunk with a fresh, seeded
    StreamingClassifier. Returns (original_index, event_type) pairs —
    event_type is what we compare for correctness (deterministic; unlike
    the sampling-drop decision, which depends on RNG state and is expected
    to differ between the sequential and parallel runs)."""
    clf = StreamingClassifier(rng_seed=seed)
    out = []
    for idx, node, msg in chunk:
        ev = clf.classify(msg, node=node)
        out.append((idx, ev.event_type if ev else None))
    return out


def run_sequential(corpus: list[tuple[str, str]]) -> tuple[float, dict[int, str | None]]:
    clf = StreamingClassifier(rng_seed=17)
    t0 = time.perf_counter()
    results = {}
    for i, (node, msg) in enumerate(corpus):
        ev = clf.classify(msg, node=node)
        results[i] = ev.event_type if ev else None
    dt = time.perf_counter() - t0
    return dt, results


def run_parallel(corpus: list[tuple[str, str]], n_workers: int) -> tuple[float, dict[int, str | None]]:
    # Shard by node-hash (not round-robin) — matches how a real Kafka topic
    # partitioned by hostname would distribute traffic across consumers.
    # zlib.crc32, not the builtin hash(): str hashing is salted per-process
    # (PYTHONHASHSEED) for DoS-hardening, so builtin hash(node) would assign
    # nodes to different shards on every run, making a specific run's
    # shard-N failure impossible to reproduce.
    shards: list[list[tuple[int, str, str]]] = [[] for _ in range(n_workers)]
    for i, (node, msg) in enumerate(corpus):
        shards[zlib.crc32(node.encode()) % n_workers].append((i, node, msg))

    chunks = []
    for shard_id, shard in enumerate(shards):
        for start in range(0, len(shard), CHUNK_SIZE):
            chunks.append((shard[start:start + CHUNK_SIZE], 1000 + shard_id))

    t0 = time.perf_counter()
    results: dict[int, str | None] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for chunk_result in pool.map(_classify_chunk, [c for c, _ in chunks], [s for _, s in chunks]):
            for idx, event_type in chunk_result:
                results[idx] = event_type
    dt = time.perf_counter() - t0
    return dt, results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lines", type=int, default=1_000_000)
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8])
    args = ap.parse_args()

    print(f"Generating {args.lines:,} synthetic log lines (uneven node distribution)...")
    corpus = make_corpus(args.lines)

    print("\n--- sequential baseline ---")
    seq_time, seq_results = run_sequential(corpus)
    seq_rate = args.lines / seq_time
    print(f"  {seq_time:.2f}s, {seq_rate:,.0f} events/sec")

    for n_workers in args.workers:
        if n_workers == 1:
            continue
        print(f"\n--- {n_workers} worker processes ---")
        par_time, par_results = run_parallel(corpus, n_workers)
        par_rate = args.lines / par_time
        speedup = seq_time / par_time
        print(f"  {par_time:.2f}s, {par_rate:,.0f} events/sec ({speedup:.2f}x vs sequential)")

        # A line missing from one run and present in the other is expected
        # sampling-drop variance (each run's classifier has independent RNG
        # state) — NOT a bug. A real bug is the same line classified as two
        # DIFFERENT event_types when both runs kept it, since regex
        # classification itself has no randomness.
        sampling_variance = 0
        real_mismatches = 0
        for i in seq_results:
            seq_type, par_type = seq_results[i], par_results.get(i)
            if seq_type == par_type:
                continue
            if seq_type is None or par_type is None:
                sampling_variance += 1
            else:
                real_mismatches += 1
        status = "OK" if real_mismatches == 0 else f"BUG: {real_mismatches} real mismatches"
        print(f"  correctness: {status} ({sampling_variance} sampling-drop variance, expected)")

    print(
        "\nNote: this process pool is a local N-process throughput simulator, not the "
        "production dispatch mechanism — see module docstring. A real Kafka consumer "
        "group's usable parallelism is capped by the topic's partition count."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
