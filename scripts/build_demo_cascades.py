"""
scripts/build_demo_cascades.py — synthesize a JSONL log file that contains real
causal cascades from the tier1+tier2 graph.

The shipped sample_data_logs.csv is Slingshot-only and has no node/timestamp,
so clicking events in the monitor mostly produces "independent." This script
builds a richer demo file where:

  - Several known cascades fire on distinct nodes (their upstream causes
    appear within the lookback window before the effect).
  - MULTIHOP_CASCADES additionally authors explicit depth-2+ chains (tier-1
    causes -> a tier-2 intermediate -> the final effect), each hop a real,
    verified edge — an actual multi-hop path through the graph, not a
    random walk — so clicking the final effect exercises the causal
    walker's recursive depth traversal, not just a single hop.
  - Background noise is sprinkled in so the classifier's sampling path is
    exercised.

Each line is JSON: {"ts": ISO8601, "node": "...", "log_message": "..."}

Output defaults to .data/syslog_demo.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog.classifier import DEFAULT_NOISE_SAMPLE_RATE  # noqa: E402
from src.syslog.patterns import classify_log_line  # noqa: E402


# Canonical log lines per event type — chosen to match the deployed regex DB.
# We assert below that each one classifies back to the expected label.
SAMPLE_MESSAGES: dict[str, str] = {
    "FS_CLUSTER_EVICT":  "LustreError: 11-0: orion-OST0042-osc-ffff8: This client was evicted by orion-OST0042; in progress operations using this service will fail.",
    "FS_LUSTRE_SLOW":    "LustreError: 11-0: orion-OST0042-osc-ffff8: operation ldlm_enqueue to NID 10.0.0.42@o2ib timed out: req@ffff882234 x1234/t0(0) o101->orion-OST0042 mdc lock timed out",
    "FS_LUSTRE_OST_ERR": "LustreError: 11-0: orion-OST0042-osc-ffff8: operation OST_WRITE to NID returned EIO; object 12345 extent [0,1048575] dirty page discard",
    # Avoid OST/MDS/SLOW keywords — those higher-priority regexes would steal this match.
    "FS_LUSTRE_ERR":     "Lustre: orion-client: recovery failed; VFS: Lookup of /orion/scratch caused loop",
    "NET_CXI_TIMEOUT":   "cxi_core: SCT timeout sct=4096 tct=0 because it only saw 12 of 64 expected packets",
    "NET_CXI_LINK":      "cxi_core: device hsn0 Carrier lost link down alert; auto lane degrade",
    "NET_CXI_HW_ECC":    "cxi_core: device hsn0 C_EC_UNCOR Fatal error reported by hardware",
    "NET_CXI_PHY_ERR":   "cxi_core: device hsn0 PCIe error: TX Nak detected; max llr replay exceeded",
    "NET_CXI_WARN":      "cxi_core: device hsn0 retried due to timeouts; nack_backoff exceeded threshold",
    "NET_CXI_RAW_DATA":  "cancel completed for sct=2952 (nid=7032, mac=00:1B:78)",
    "APP_INFRA_FAIL":    "slurmstepd: error: epilog failed for job 123456 on node frontier-0042",
    # APP_INFRA_FAIL also matches "slurmstepd startup took" and "Zero Bytes were transmitted",
    # so pick the only APP_JOB_LATENCY phrase NOT shared with INFRA_FAIL.
    "APP_JOB_LATENCY":   "slurmstepd: warning: steps did not complete quickly on frontier-0042",
    # "DUE TO NODE FAILURE", not "DUE TO TIME LIMIT" — this message is used
    # as the effect of SYS_OOM_KILL -> APP_JOB_CANCEL (a task vanishing to
    # the OOM-killer is exactly the kind of unexpected failure Slurm logs
    # this way), and "TIME LIMIT" would misleadingly suggest an unrelated
    # cause when read literally.
    "APP_JOB_CANCEL":    "slurmstepd: error: *** JOB 123456 ON frontier-0042 CANCELLED AT 2026-05-17T12:30:00 DUE TO NODE FAILURE ***",
    "SYS_OOM_KILL":      "kernel: Out of memory: Killed process 12345 (python) total-vm:65536kB anon-rss:32768kB",
    "FS_DVS_WARN":       "DVS: server reply path /lustre/orion failed; marking it down",
    "GPU_HARD_FAULT":    "amdgpu: 0000:c1:00.0: ih_fifo overflow; entering unrecoverable state",
    "GPU_MEM_FAULT":     "amdgpu: 0000:c1:00.0: retry page fault on VMID 8 in page starting at 0x7fff0000 RW: 0x0 for process gpu_app pid 4242",
    "HW_EDAC_ERR":       "EDAC MC0: 1 UE on csrow:0 channel:0 (page:0x12345 offset:0x0 grain:32 syndrome:0xa5)",
    "HW_PCIE_ERR":       "pcieport 0000:00:01.0: AER: Error of this Agent BadTLP RxErr",
    "INFO_NOISE":        "kernel: Hardware name: HPE Cray EX235a; BIOS 2.10.4 09/15/2024",
    "SVC_RSYSLOG_ERR":   "rsyslogd: action 'action 9' suspended (module 'omfwd'), retry 0",
    # 4-hop GPU driver-stack chain (see MULTIHOP_CASCADES gpu-driver-stack-failure).
    "GPU_FIRMWARE":      "amdgpu 0000:c1:00.0: firmware version too old; refusing to load ucode",
    "HW_IOMMU_ERR":      "AMD-Vi: Event logged [IO_PAGE_FAULT device=0000:c1:00.0]",
    "GPU_DRIVER_ERR":    "amdgpu 0000:c1:00.0: Failed to allocate process doorbells",
    "GPU_SOFT_LOCK":     "amdgpu 0000:c1:00.0: Queues reset on process gpu_app",
    "GPU_TIMEOUT":       "amdgpu 0000:c1:00.0: ring gfx timeout, signaled seq=1234, emitted seq=1236",
    "APP_JOB_ERR":       "systemd: Main process exited, code=exited, status=1/FAILURE",
}


# Cascades — (effect, [causes that should fire within window], demo_label).
# All edges below are verified present in the tier1+tier2 CSV.
CASCADES: list[tuple[str, list[str], str]] = [
    (
        "APP_INFRA_FAIL",
        ["FS_CLUSTER_EVICT", "NET_CXI_TIMEOUT", "FS_LUSTRE_SLOW"],
        "lustre-eviction-killed-job",
    ),
    (
        "SYS_OOM_KILL",
        ["APP_JOB_LATENCY", "FS_DVS_WARN"],
        "slow-step-then-oom",
    ),
    (
        "FS_LUSTRE_ERR",
        ["FS_LUSTRE_OST_ERR", "NET_CXI_LINK"],
        "ost-failure-fabric-storm",
    ),
    (
        "NET_CXI_PHY_ERR",
        ["NET_CXI_LINK", "NET_CXI_HW_ECC", "NET_CXI_TIMEOUT"],
        "fabric-phy-degrade",
    ),
    (
        "APP_JOB_CANCEL",
        ["SYS_OOM_KILL"],
        "oom-then-cancel",
    ),
]

# Multi-hop cascades — an explicitly authored path through the tier1+tier2
# graph (NOT a random walk): each entry is (levels, demo_label), where
# `levels` is the path in cause -> effect order, one hop per list entry.
# A level with more than one event_type means multiple independent causes
# converging on the same next-level effect (all fire before it, none before
# each other). Every cause -> effect step between adjacent levels is a real,
# verified edge in the tier1+tier2 CSV — see the citation on each entry.
MULTIHOP_CASCADES: list[tuple[list[list[str]], str]] = [
    (
        # GPU_MEM_FAULT -> GPU_HARD_FAULT (edge), HW_PCIE_ERR -> GPU_HARD_FAULT
        # (edge), GPU_HARD_FAULT -> APP_INFRA_FAIL (edge): two unrelated
        # tier-1 failure domains (memory, PCIe) converging on one tier-2
        # intermediate, which then cascades to the final effect — depth 2
        # from the clicked APP_INFRA_FAIL event.
        [["GPU_MEM_FAULT", "HW_PCIE_ERR"], ["GPU_HARD_FAULT"], ["APP_INFRA_FAIL"]],
        "gpu-fault-cascade",
    ),
    (
        # A genuine linear 4-hop chain (depth 4 from the clicked event, the
        # UI's max depth slider ceiling) straight down the GPU driver stack:
        # {GPU_FIRMWARE, HW_IOMMU_ERR} -> GPU_DRIVER_ERR -> GPU_SOFT_LOCK ->
        # GPU_TIMEOUT -> APP_JOB_ERR. Every edge verified in the tier1+tier2
        # CSV (lines for GPU_FIRMWARE/HW_IOMMU_ERR->GPU_DRIVER_ERR,
        # GPU_DRIVER_ERR->GPU_SOFT_LOCK, GPU_SOFT_LOCK->GPU_TIMEOUT,
        # GPU_TIMEOUT->APP_JOB_ERR).
        [
            ["GPU_FIRMWARE", "HW_IOMMU_ERR"],
            ["GPU_DRIVER_ERR"],
            ["GPU_SOFT_LOCK"],
            ["GPU_TIMEOUT"],
            ["APP_JOB_ERR"],
        ],
        "gpu-driver-stack-failure",
    ),
]

# Background noise for the timeline. NET_CXI_WARN/HW_EDAC_ERR/SVC_RSYSLOG_ERR
# have no edges in the graph — real, independent chatter, not a cascade.
NOISE_TYPES = ["NET_CXI_RAW_DATA", "INFO_NOISE", "NET_CXI_WARN", "HW_EDAC_ERR", "SVC_RSYSLOG_ERR"]
# Weighted inversely to each type's real classifier sample rate (1.0 for
# anything not in DEFAULT_NOISE_SAMPLE_RATE, i.e. never dropped) so the
# VISIBLE counts after classification come out roughly even across all 5
# types. Without this, NET_CXI_RAW_DATA/INFO_NOISE (deliberately dropped
# 90%/95% of the time — a real production behavior, not a demo artifact)
# would nearly vanish next to the other 3 types, which pass through
# unsampled — generating them at equal raw frequency produces a wildly
# uneven visible mix, not a realistic one.
NOISE_WEIGHTS = [1.0 / DEFAULT_NOISE_SAMPLE_RATE.get(nt, 1.0) for nt in NOISE_TYPES]


def _verify_samples() -> None:
    """Fail fast if a sample message doesn't classify to its intended label."""
    failures = []
    for label, msg in SAMPLE_MESSAGES.items():
        got = classify_log_line(msg)
        if got != label:
            failures.append(f"  {label}: classified as {got!r}\n      msg={msg!r}")
    if failures:
        raise SystemExit(
            "Sample messages don't round-trip through the regex DB:\n"
            + "\n".join(failures)
            + "\nFix the synthetic messages so they match the live LOG_PATTERNS."
        )


def _chain_records(
    levels: list[list[str]], chain_start: datetime, node: str, label: str, rng: random.Random,
) -> list[dict[str, object]]:
    """Emit one multi-hop chain: level 0 (tier-1 causes) fires first, each
    subsequent level fires 5-15s after the LATEST event of the level
    before it — so the causal walker's time-ordering constraint (a cause
    must appear before its effect within the lookback window) holds at
    every hop, not just the first one. Events within the same level
    (multiple independent causes converging on one next-level effect) get
    a small 1-4s stagger between them so they don't share one timestamp,
    but none of them depends on order relative to each other."""
    out: list[dict[str, object]] = []
    prev_max_ts: datetime | None = None
    for level_idx, level_types in enumerate(levels):
        if level_idx == 0:
            offsets = sorted(rng.sample(range(5, 50), k=len(level_types)))
            level_ts = [chain_start + timedelta(seconds=o) for o in offsets]
        else:
            base = prev_max_ts + timedelta(seconds=rng.randint(5, 15))  # type: ignore[operator]
            level_ts = [base + timedelta(seconds=j * rng.randint(1, 4)) for j in range(len(level_types))]
        for event_type, ts in zip(level_types, level_ts):
            out.append({
                "ts": ts.isoformat(),
                "node": node,
                "log_message": SAMPLE_MESSAGES[event_type],
                "demo_tag": label,
            })
        prev_max_ts = max(level_ts)
    return out


def build_records(
    out_path: Path,
    *,
    start_ts: datetime,
    seed: int = 17,
    repeats: int = 1,
    noise_count: int | None = None,
) -> int:
    """`repeats` replays the whole staggered-cascade block back-to-back
    `repeats` times, each round shifted later by one round's worth of
    timeline (round_seconds below) and rotated onto a different starting
    node — this is what makes `--repeats` actually add new datapoints
    rather than just producing more copies of the exact same 12 lines at
    the exact same relative offsets on the exact same nodes.

    noise_count defaults to 120 * repeats (matching the original fixed
    120-per-single-round density) unless overridden."""
    rng = random.Random(seed)
    nodes = ["frontier-0042", "frontier-1337", "frontier-2200", "frontier-7777"]
    records: list[dict[str, object]] = []

    n_slots = len(CASCADES) + len(MULTIHOP_CASCADES)
    round_seconds = max(60, n_slots * 90)
    for r in range(repeats):
        round_start = start_ts + timedelta(seconds=r * round_seconds)
        for i, (effect, causes, label) in enumerate(CASCADES):
            node = nodes[(i + r) % len(nodes)]
            cascade_start = round_start + timedelta(seconds=i * 90 + 10)
            offsets = sorted(rng.sample(range(5, 50), k=len(causes)))
            for cause, dt in zip(causes, offsets):
                records.append({
                    "ts": (cascade_start + timedelta(seconds=dt)).isoformat(),
                    "node": node,
                    "log_message": SAMPLE_MESSAGES[cause],
                    "demo_tag": label,
                })
            # The effect fires 5-15s after the last cause.
            effect_ts = cascade_start + timedelta(seconds=offsets[-1] + rng.randint(5, 15))
            records.append({
                "ts": effect_ts.isoformat(),
                "node": node,
                "log_message": SAMPLE_MESSAGES[effect],
                "demo_tag": label,
            })

        for j, (levels, label) in enumerate(MULTIHOP_CASCADES):
            slot = len(CASCADES) + j
            node = nodes[(slot + r) % len(nodes)]
            chain_start = round_start + timedelta(seconds=slot * 90 + 10)
            records.extend(_chain_records(levels, chain_start, node, label, rng))

    # Sprinkle background noise across the full (all-rounds) timeline.
    timeline_seconds = round_seconds * repeats
    n_noise = noise_count if noise_count is not None else 120 * repeats
    for _ in range(n_noise):
        t = start_ts + timedelta(seconds=rng.uniform(0, timeline_seconds))
        node = rng.choice(nodes)
        nt = rng.choices(NOISE_TYPES, weights=NOISE_WEIGHTS, k=1)[0]
        records.append({
            "ts": t.isoformat(),
            "node": node,
            "log_message": SAMPLE_MESSAGES[nt],
        })

    # Sort by ts so the replay feels natural.
    records.sort(key=lambda r: r["ts"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return len(records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "-o", "--out",
        default=str(Path(__file__).resolve().parent.parent / ".data" / "syslog_demo.jsonl"),
        help="Output JSONL path",
    )
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument(
        "--repeats", type=int, default=1,
        help="Replay the staggered-cascade block this many times back-to-back "
             "(rotated onto different starting nodes each round) for a longer, "
             "more diverse demo file — e.g. --repeats 20 for ~2700 records.",
    )
    ap.add_argument(
        "--noise-count", type=int, default=None,
        help="Background noise record count (default: 120 * --repeats).",
    )
    args = ap.parse_args()

    _verify_samples()
    start_ts = datetime.now(timezone.utc).replace(microsecond=0)
    out_path = Path(args.out)
    n = build_records(
        out_path, start_ts=start_ts, seed=args.seed,
        repeats=args.repeats, noise_count=args.noise_count,
    )
    print(f"Wrote {n} records to {out_path}")
    print("Cascades:")
    for effect, causes, label in CASCADES:
        print(f"  {label}: {' + '.join(causes)} -> {effect}")
    for levels, label in MULTIHOP_CASCADES:
        print(f"  {label}: {' -> '.join(' + '.join(level) for level in levels)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
