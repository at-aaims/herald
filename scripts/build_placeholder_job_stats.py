#!/usr/bin/env python3
"""
scripts/build_placeholder_job_stats.py — stopgap stats.json for the synthetic
job-data generator (scripts/generate_frontier_job_data.py).

The real stats.json (replaced by this script's output) held mean/std and
linear-regression coefficients against node_count/runtime for ~300 power/
energy/temperature telemetry fields, fit from real Frontier measurements —
only aggregate statistics, no raw records, but still real-derived numbers,
not something to ship on a public branch. This writes a structurally
identical file (same field names, so nothing downstream — the SQL schema,
job-prediction's output columns — breaks) with entirely fabricated mean/std
values: self-consistent (min < mean < max, GPU draws more than CPU, temps
in a plausible range) but made up, not fit to any real measurement.

The field-name list below was extracted from the real file's keys (just the
names — generic telemetry labels like "stats_gpu0_power_node_mean", not
Frontier-specific or sensitive on their own) so this script has no
dependency on the real file at all; it can regenerate the placeholder from
scratch.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "site" / "ornl" / "frontier" / "stats.json"

STAT_FIELD_NAMES = [
    "stats_cpu0_energy_delta_measurement_max", "stats_cpu0_energy_delta_measurement_mean",
    "stats_cpu0_energy_delta_measurement_min", "stats_cpu0_energy_delta_measurement_stddev",
    "stats_cpu0_energy_delta_node_max", "stats_cpu0_energy_delta_node_mean",
    "stats_cpu0_energy_delta_node_min", "stats_cpu0_energy_delta_node_stddev",
    "stats_cpu0_energy_delta_timestamp_max", "stats_cpu0_energy_delta_timestamp_mean",
    "stats_cpu0_energy_delta_timestamp_min", "stats_cpu0_energy_delta_timestamp_stddev",
    "stats_cpu0_power_measurement_max", "stats_cpu0_power_measurement_mean",
    "stats_cpu0_power_measurement_min", "stats_cpu0_power_measurement_stddev",
    "stats_cpu0_power_node_max", "stats_cpu0_power_node_mean",
    "stats_cpu0_power_node_min", "stats_cpu0_power_node_stddev",
    "stats_cpu0_power_timestamp_max", "stats_cpu0_power_timestamp_mean",
    "stats_cpu0_power_timestamp_min", "stats_cpu0_power_timestamp_stddev",
    "stats_cpu0_temp_measurement_max", "stats_cpu0_temp_measurement_mean",
    "stats_cpu0_temp_measurement_min", "stats_cpu0_temp_measurement_stddev",
    "stats_cpu0_temp_node_max", "stats_cpu0_temp_node_mean",
    "stats_cpu0_temp_node_min", "stats_cpu0_temp_node_stddev",
    "stats_cpu0_temp_timestamp_max", "stats_cpu0_temp_timestamp_mean",
    "stats_cpu0_temp_timestamp_min", "stats_cpu0_temp_timestamp_stddev",
    "stats_cpu_memory_energy_delta_measurement_max", "stats_cpu_memory_energy_delta_measurement_mean",
    "stats_cpu_memory_energy_delta_measurement_min", "stats_cpu_memory_energy_delta_measurement_stddev",
    "stats_cpu_memory_energy_delta_node_max", "stats_cpu_memory_energy_delta_node_mean",
    "stats_cpu_memory_energy_delta_node_min", "stats_cpu_memory_energy_delta_node_stddev",
    "stats_cpu_memory_energy_delta_timestamp_max", "stats_cpu_memory_energy_delta_timestamp_mean",
    "stats_cpu_memory_energy_delta_timestamp_min", "stats_cpu_memory_energy_delta_timestamp_stddev",
    "stats_cpu_memory_power_measurement_max", "stats_cpu_memory_power_measurement_mean",
    "stats_cpu_memory_power_measurement_min", "stats_cpu_memory_power_measurement_stddev",
    "stats_cpu_memory_power_node_max", "stats_cpu_memory_power_node_mean",
    "stats_cpu_memory_power_node_min", "stats_cpu_memory_power_node_stddev",
    "stats_cpu_memory_power_timestamp_max", "stats_cpu_memory_power_timestamp_mean",
    "stats_cpu_memory_power_timestamp_min", "stats_cpu_memory_power_timestamp_stddev",
    "stats_gpu0_energy_delta_measurement_max", "stats_gpu0_energy_delta_measurement_mean",
    "stats_gpu0_energy_delta_measurement_min", "stats_gpu0_energy_delta_measurement_stddev",
    "stats_gpu0_energy_delta_node_max", "stats_gpu0_energy_delta_node_mean",
    "stats_gpu0_energy_delta_node_min", "stats_gpu0_energy_delta_node_stddev",
    "stats_gpu0_energy_delta_timestamp_max", "stats_gpu0_energy_delta_timestamp_mean",
    "stats_gpu0_energy_delta_timestamp_min", "stats_gpu0_energy_delta_timestamp_stddev",
    "stats_gpu0_power_measurement_max", "stats_gpu0_power_measurement_mean",
    "stats_gpu0_power_measurement_min", "stats_gpu0_power_measurement_stddev",
    "stats_gpu0_power_node_max", "stats_gpu0_power_node_mean",
    "stats_gpu0_power_node_min", "stats_gpu0_power_node_stddev",
    "stats_gpu0_power_timestamp_max", "stats_gpu0_power_timestamp_mean",
    "stats_gpu0_power_timestamp_min", "stats_gpu0_power_timestamp_stddev",
    "stats_gpu0_temp_measurement_max", "stats_gpu0_temp_measurement_mean",
    "stats_gpu0_temp_measurement_min", "stats_gpu0_temp_measurement_stddev",
    "stats_gpu0_temp_node_max", "stats_gpu0_temp_node_mean",
    "stats_gpu0_temp_node_min", "stats_gpu0_temp_node_stddev",
    "stats_gpu0_temp_timestamp_max", "stats_gpu0_temp_timestamp_mean",
    "stats_gpu0_temp_timestamp_min", "stats_gpu0_temp_timestamp_stddev",
    "stats_gpu1_energy_delta_measurement_max", "stats_gpu1_energy_delta_measurement_mean",
    "stats_gpu1_energy_delta_measurement_min", "stats_gpu1_energy_delta_measurement_stddev",
    "stats_gpu1_energy_delta_node_max", "stats_gpu1_energy_delta_node_mean",
    "stats_gpu1_energy_delta_node_min", "stats_gpu1_energy_delta_node_stddev",
    "stats_gpu1_energy_delta_timestamp_max", "stats_gpu1_energy_delta_timestamp_mean",
    "stats_gpu1_energy_delta_timestamp_min", "stats_gpu1_energy_delta_timestamp_stddev",
    "stats_gpu1_power_measurement_max", "stats_gpu1_power_measurement_mean",
    "stats_gpu1_power_measurement_min", "stats_gpu1_power_measurement_stddev",
    "stats_gpu1_power_node_max", "stats_gpu1_power_node_mean",
    "stats_gpu1_power_node_min", "stats_gpu1_power_node_stddev",
    "stats_gpu1_power_timestamp_max", "stats_gpu1_power_timestamp_mean",
    "stats_gpu1_power_timestamp_min", "stats_gpu1_power_timestamp_stddev",
    "stats_gpu1_temp_measurement_max", "stats_gpu1_temp_measurement_mean",
    "stats_gpu1_temp_measurement_min", "stats_gpu1_temp_measurement_stddev",
    "stats_gpu1_temp_node_max", "stats_gpu1_temp_node_mean",
    "stats_gpu1_temp_node_min", "stats_gpu1_temp_node_stddev",
    "stats_gpu1_temp_timestamp_max", "stats_gpu1_temp_timestamp_mean",
    "stats_gpu1_temp_timestamp_min", "stats_gpu1_temp_timestamp_stddev",
    "stats_gpu2_energy_delta_measurement_max", "stats_gpu2_energy_delta_measurement_mean",
    "stats_gpu2_energy_delta_measurement_min", "stats_gpu2_energy_delta_measurement_stddev",
    "stats_gpu2_energy_delta_node_max", "stats_gpu2_energy_delta_node_mean",
    "stats_gpu2_energy_delta_node_min", "stats_gpu2_energy_delta_node_stddev",
    "stats_gpu2_energy_delta_timestamp_max", "stats_gpu2_energy_delta_timestamp_mean",
    "stats_gpu2_energy_delta_timestamp_min", "stats_gpu2_energy_delta_timestamp_stddev",
    "stats_gpu2_power_measurement_max", "stats_gpu2_power_measurement_mean",
    "stats_gpu2_power_measurement_min", "stats_gpu2_power_measurement_stddev",
    "stats_gpu2_power_node_max", "stats_gpu2_power_node_mean",
    "stats_gpu2_power_node_min", "stats_gpu2_power_node_stddev",
    "stats_gpu2_power_timestamp_max", "stats_gpu2_power_timestamp_mean",
    "stats_gpu2_power_timestamp_min", "stats_gpu2_power_timestamp_stddev",
    "stats_gpu2_temp_measurement_max", "stats_gpu2_temp_measurement_mean",
    "stats_gpu2_temp_measurement_min", "stats_gpu2_temp_measurement_stddev",
    "stats_gpu2_temp_node_max", "stats_gpu2_temp_node_mean",
    "stats_gpu2_temp_node_min", "stats_gpu2_temp_node_stddev",
    "stats_gpu2_temp_timestamp_max", "stats_gpu2_temp_timestamp_mean",
    "stats_gpu2_temp_timestamp_min", "stats_gpu2_temp_timestamp_stddev",
    "stats_gpu3_energy_delta_measurement_max", "stats_gpu3_energy_delta_measurement_mean",
    "stats_gpu3_energy_delta_measurement_min", "stats_gpu3_energy_delta_measurement_stddev",
    "stats_gpu3_energy_delta_node_max", "stats_gpu3_energy_delta_node_mean",
    "stats_gpu3_energy_delta_node_min", "stats_gpu3_energy_delta_node_stddev",
    "stats_gpu3_energy_delta_timestamp_max", "stats_gpu3_energy_delta_timestamp_mean",
    "stats_gpu3_energy_delta_timestamp_min", "stats_gpu3_energy_delta_timestamp_stddev",
    "stats_gpu3_power_measurement_max", "stats_gpu3_power_measurement_mean",
    "stats_gpu3_power_measurement_min", "stats_gpu3_power_measurement_stddev",
    "stats_gpu3_power_node_max", "stats_gpu3_power_node_mean",
    "stats_gpu3_power_node_min", "stats_gpu3_power_node_stddev",
    "stats_gpu3_power_timestamp_max", "stats_gpu3_power_timestamp_mean",
    "stats_gpu3_power_timestamp_min", "stats_gpu3_power_timestamp_stddev",
    "stats_gpu3_temp_measurement_max", "stats_gpu3_temp_measurement_mean",
    "stats_gpu3_temp_measurement_min", "stats_gpu3_temp_measurement_stddev",
    "stats_gpu3_temp_node_max", "stats_gpu3_temp_node_mean",
    "stats_gpu3_temp_node_min", "stats_gpu3_temp_node_stddev",
    "stats_gpu3_temp_timestamp_max", "stats_gpu3_temp_timestamp_mean",
    "stats_gpu3_temp_timestamp_min", "stats_gpu3_temp_timestamp_stddev",
    "stats_gpu_energy_delta_measurement_max", "stats_gpu_energy_delta_measurement_mean",
    "stats_gpu_energy_delta_measurement_min", "stats_gpu_energy_delta_measurement_stddev",
    "stats_gpu_energy_delta_node_max", "stats_gpu_energy_delta_node_mean",
    "stats_gpu_energy_delta_node_min", "stats_gpu_energy_delta_node_stddev",
    "stats_gpu_energy_delta_timestamp_max", "stats_gpu_energy_delta_timestamp_mean",
    "stats_gpu_energy_delta_timestamp_min", "stats_gpu_energy_delta_timestamp_stddev",
    "stats_gpu_power_measurement_max", "stats_gpu_power_measurement_mean",
    "stats_gpu_power_measurement_min", "stats_gpu_power_measurement_stddev",
    "stats_gpu_power_node_max", "stats_gpu_power_node_mean",
    "stats_gpu_power_node_min", "stats_gpu_power_node_stddev",
    "stats_gpu_power_timestamp_max", "stats_gpu_power_timestamp_mean",
    "stats_gpu_power_timestamp_min", "stats_gpu_power_timestamp_stddev",
    "stats_gpu_temp_measurement_max", "stats_gpu_temp_measurement_mean",
    "stats_gpu_temp_measurement_min", "stats_gpu_temp_measurement_stddev",
    "stats_gpu_temp_node_max", "stats_gpu_temp_node_mean",
    "stats_gpu_temp_node_min", "stats_gpu_temp_node_stddev",
    "stats_gpu_temp_timestamp_max", "stats_gpu_temp_timestamp_mean",
    "stats_gpu_temp_timestamp_min", "stats_gpu_temp_timestamp_stddev",
    "stats_node_energy_delta_measurement_max", "stats_node_energy_delta_measurement_mean",
    "stats_node_energy_delta_measurement_min", "stats_node_energy_delta_measurement_stddev",
    "stats_node_energy_delta_node_max", "stats_node_energy_delta_node_mean",
    "stats_node_energy_delta_node_min", "stats_node_energy_delta_node_stddev",
    "stats_node_energy_delta_timestamp_max", "stats_node_energy_delta_timestamp_mean",
    "stats_node_energy_delta_timestamp_min", "stats_node_energy_delta_timestamp_stddev",
    "stats_node_power_measurement_max", "stats_node_power_measurement_mean",
    "stats_node_power_measurement_min", "stats_node_power_measurement_stddev",
    "stats_node_power_node_max", "stats_node_power_node_mean",
    "stats_node_power_node_min", "stats_node_power_node_stddev",
    "stats_node_power_timestamp_max", "stats_node_power_timestamp_mean",
    "stats_node_power_timestamp_min", "stats_node_power_timestamp_stddev",
    "stats_node_temp_measurement_max", "stats_node_temp_measurement_mean",
    "stats_node_temp_measurement_min", "stats_node_temp_measurement_stddev",
    "stats_node_temp_node_max", "stats_node_temp_node_mean",
    "stats_node_temp_node_min", "stats_node_temp_node_stddev",
    "stats_node_temp_timestamp_max", "stats_node_temp_timestamp_mean",
    "stats_node_temp_timestamp_min", "stats_node_temp_timestamp_stddev",
    "stats_total_cpu0_energy",
    "stats_total_cpu0_energy_node_max", "stats_total_cpu0_energy_node_mean",
    "stats_total_cpu0_energy_node_min", "stats_total_cpu0_energy_node_stddev",
    "stats_total_cpu_memory_energy",
    "stats_total_cpu_memory_energy_node_max", "stats_total_cpu_memory_energy_node_mean",
    "stats_total_cpu_memory_energy_node_min", "stats_total_cpu_memory_energy_node_stddev",
    "stats_total_gpu0_energy",
    "stats_total_gpu0_energy_node_max", "stats_total_gpu0_energy_node_mean",
    "stats_total_gpu0_energy_node_min", "stats_total_gpu0_energy_node_stddev",
    "stats_total_gpu1_energy",
    "stats_total_gpu1_energy_node_max", "stats_total_gpu1_energy_node_mean",
    "stats_total_gpu1_energy_node_min", "stats_total_gpu1_energy_node_stddev",
    "stats_total_gpu2_energy",
    "stats_total_gpu2_energy_node_max", "stats_total_gpu2_energy_node_mean",
    "stats_total_gpu2_energy_node_min", "stats_total_gpu2_energy_node_stddev",
    "stats_total_gpu3_energy",
    "stats_total_gpu3_energy_node_max", "stats_total_gpu3_energy_node_mean",
    "stats_total_gpu3_energy_node_min", "stats_total_gpu3_energy_node_stddev",
    "stats_total_gpu_energy",
    "stats_total_gpu_energy_node_max", "stats_total_gpu_energy_node_mean",
    "stats_total_gpu_energy_node_min", "stats_total_gpu_energy_node_stddev",
    "stats_total_node_energy",
    "stats_total_node_energy_node_max", "stats_total_node_energy_node_mean",
    "stats_total_node_energy_node_min", "stats_total_node_energy_node_stddev",
]

# Base (mean) + spread (std) per component, Watts for power / Celsius for
# temp — plausible orders of magnitude for a GPU-heavy HPC node, not fit to
# any real measurement.
_POWER_BASE = {"node": 650, "cpu0": 220, "cpu_memory": 70, "gpu": 380,
               "gpu0": 380, "gpu1": 380, "gpu2": 380, "gpu3": 380}
_TEMP_BASE = {"node": 55, "cpu0": 60, "gpu": 65, "gpu0": 65, "gpu1": 65, "gpu2": 65, "gpu3": 65}
_ENERGY_DELTA_BASE = {"node": 3000, "cpu0": 1000, "cpu_memory": 350, "gpu": 1800,
                       "gpu0": 1800, "gpu1": 1800, "gpu2": 1800, "gpu3": 1800}
_TOTAL_ENERGY_BASE = {"node": 800_000, "cpu0": 250_000, "cpu_memory": 90_000, "gpu": 500_000,
                       "gpu0": 500_000, "gpu1": 500_000, "gpu2": 500_000, "gpu3": 500_000}

_COMPONENT_RE = re.compile(r"stats_(cpu0|cpu_memory|gpu0|gpu1|gpu2|gpu3|gpu|node)_")
_TOTAL_COMPONENT_RE = re.compile(r"stats_total_(cpu0|cpu_memory|gpu0|gpu1|gpu2|gpu3|gpu|node)_energy")


def _field_stats(name: str, rng: random.Random) -> dict:
    if name.startswith("stats_total_"):
        component = _TOTAL_COMPONENT_RE.match(name).group(1)
        base, spread_frac = _TOTAL_ENERGY_BASE[component], 0.35
    else:
        component = _COMPONENT_RE.match(name).group(1)
        if "timestamp" in name:
            base, spread_frac = 2500, 0.6  # seconds-offset within a job, loose
        elif "temp" in name:
            base, spread_frac = _TEMP_BASE[component], 0.2
        elif "energy_delta" in name:
            base, spread_frac = _ENERGY_DELTA_BASE[component], 0.3
        else:  # power
            base, spread_frac = _POWER_BASE[component], 0.25

    jitter = rng.uniform(0.9, 1.1)
    base *= jitter
    spread = base * spread_frac

    if name.endswith("_min"):
        mean = max(base - spread * 0.8, 0)
    elif name.endswith("_max"):
        mean = base + spread * 1.4
    elif name.endswith("_stddev"):
        mean = spread * 0.3  # within-job variability, smaller than between-job spread
    else:  # _mean
        mean = base

    std = max(mean * 0.15, 1.0)
    return {
        "linear_regression": {},  # unused by the generator; real coefficients not reproduced
        "dist": [],
        "min": None, "max": None,  # unused by the generator (only mean/std are read)
        "mean": round(mean, 5),
        "std": round(std, 5),
        "median": round(mean, 5),
        "mad": round(std * 0.7, 5),
    }


def main() -> int:
    rng = random.Random(1234)  # fixed seed: reproducible, not meant to hide/vary anything

    stats = {name: _field_stats(name, rng) for name in STAT_FIELD_NAMES}

    out = {
        # Same scipy distribution family as the original (halfgennorm — a
        # right-skewed shape: many short/small jobs, a long tail of big
        # ones, which is qualitatively how HPC job mixes actually look),
        # with hand-picked, round, not-fit-to-data parameters.
        "node_count": {
            "dist": {"dist": "halfgennorm", "params": [0.3, -100.0, 50.0]},
            "min": 0.0, "max": 9000.0, "mean": 80.0, "std": 500.0, "median": 1.0, "mad": 0.0,
        },
        "runtime": {
            "dist": {"dist": "halfgennorm", "params": [0.3, -200.0, 100.0]},
            "min": 0.0, "max": 86400.0, "mean": 1100.0, "std": 3000.0, "median": 60.0, "mad": 50.0,
        },
        "stats": stats,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote placeholder stats for {len(stats)} fields to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
