#!/usr/bin/env python3
"""
scripts/build_placeholder_causal_edges.py — stopgap causal-edges CSV.

The real causal_edges_combined_tier1_tier2.csv is triangulation output
from the sister `frontier-agent` project (Transformer-ATE / PCMCI+ /
Transfer Entropy over real Frontier syslogs) and isn't available on this
machine. This script writes a hand-authored, domain-knowledge placeholder
covering plausible HPC failure cascades so the syslog causal-graph UI has
something to render. Every row is tagged tier="Placeholder" (not "Tier 1"
/ "Tier 2") and num_methods=0 so it's never confused with real triangulated
edges. Replace src/syslog/causal.py's HERALD_CAUSAL_CSV once the real file
is recovered.
"""
import csv
from pathlib import Path

# (cause, effect) pairs. Includes the exact edges exercised by
# scripts/build_demo_cascades.py's four verified cascades so the demo
# data actually shows connected DAGs when clicked.
EDGES = [
    # --- demo-cascade edges (must match build_demo_cascades.py) ---
    ("FS_CLUSTER_EVICT", "APP_INFRA_FAIL"),
    ("NET_CXI_TIMEOUT", "APP_INFRA_FAIL"),
    ("FS_LUSTRE_SLOW", "APP_INFRA_FAIL"),
    ("APP_JOB_LATENCY", "SYS_OOM_KILL"),
    ("FS_DVS_WARN", "SYS_OOM_KILL"),
    ("FS_LUSTRE_OST_ERR", "FS_LUSTRE_ERR"),
    ("NET_CXI_LINK", "FS_LUSTRE_ERR"),
    ("NET_CXI_LINK", "NET_CXI_PHY_ERR"),
    ("NET_CXI_HW_ECC", "NET_CXI_PHY_ERR"),
    ("NET_CXI_TIMEOUT", "NET_CXI_PHY_ERR"),

    # --- network fabric precursors ---
    ("HW_FABRIC_INT", "NET_CXI_LINK"),
    ("HW_FABRIC_RTR", "NET_CXI_TIMEOUT"),
    ("NET_CXI_FIRMWARE", "NET_CXI_LINK"),
    ("NET_CXI_LINK", "NET_CXI_TIMEOUT"),
    ("NET_CXI_TIMEOUT", "FS_LUSTRE_SLOW"),
    ("NET_CXI_TIMEOUT", "FS_DVS_WARN"),
    ("NET_LNET_WARN", "NET_LNET_ERR"),
    ("NET_LNET_ERR", "FS_LUSTRE_ERR"),

    # --- filesystem ---
    ("FS_LUSTRE_MDS_ERR", "FS_LUSTRE_ERR"),
    ("FS_LUSTRE_ERR", "FS_CLUSTER_EVICT"),
    ("FS_LUSTRE_SLOW", "APP_JOB_LATENCY"),
    ("FS_DVS_WARN", "APP_JOB_LATENCY"),
    ("FS_GPFS_ERR", "APP_INFRA_FAIL"),
    ("FS_IO_ERR", "APP_JOB_ERR"),
    ("FS_XFS_ERR", "FS_IO_ERR"),
    ("FS_DISK_FULL", "APP_JOB_ERR"),
    ("STO_NVME_STALL", "FS_IO_ERR"),

    # --- GPU ---
    ("HW_THERMAL_CRIT", "GPU_TIMEOUT"),
    ("GPU_FIRMWARE", "GPU_DRIVER_ERR"),
    ("GPU_DRIVER_ERR", "GPU_SOFT_LOCK"),
    ("GPU_SOFT_LOCK", "GPU_TIMEOUT"),
    ("GPU_TIMEOUT", "APP_JOB_ERR"),
    ("GPU_MEM_FAULT", "GPU_HARD_FAULT"),
    ("GPU_RAS_FAIL", "GPU_HARD_FAULT"),
    ("GPU_HARD_FAULT", "APP_INFRA_FAIL"),
    ("HW_IF_GPU_LINK", "GPU_TIMEOUT"),
    ("HW_IOMMU_ERR", "GPU_DRIVER_ERR"),

    # --- hardware / MCE ---
    ("HW_ACPI_WARN", "HW_THERMAL_CRIT"),
    ("HW_BMC_WARN", "HW_THERMAL_CRIT"),
    ("HW_CPU_CORE", "HW_MCE_CPU"),
    ("HW_EDAC_ERR", "HW_MCE_CPU"),
    ("HW_MCE_CORRECTED", "HW_MCE_FATAL"),
    ("HW_MCE_UNK", "HW_MCE_GENERIC"),
    ("HW_MCE_GENERIC", "HW_MCE_CPU"),
    ("HW_MCE_DUMP", "HW_MCE_FATAL"),
    ("HW_MEM_DIMM", "HW_MEM_CORRUPT"),
    ("HW_MEM_CORRUPT", "SYS_KERNEL_PANIC"),
    ("HW_PCIE_HUB", "HW_PCIE_ERR"),
    ("HW_PCIE_ERR", "GPU_HARD_FAULT"),
    ("HW_USB_FAIL", "SVC_SYSTEMD_EXIT"),

    # --- memory / OOM / kernel ---
    ("APP_JOB_CGROUP", "SYS_OOM_KILL"),
    ("SYS_OOM_KILL", "APP_JOB_CANCEL"),
    ("SYS_RCU_STALL", "SYS_WATCHDOG"),
    ("SYS_WATCHDOG", "SYS_KERNEL_PANIC"),
    ("SYS_KERNEL_PANIC", "APP_INFRA_FAIL"),
    ("SYS_SEGFAULT", "SYS_COREDUMP"),
    ("SYS_COREDUMP", "APP_JOB_ERR"),
    ("SYS_PROCESS_LIM", "APP_JOB_ERR"),

    # --- services / config / scheduler ---
    ("SVC_CONFIG_ERR", "SVC_SYSTEMD_EXIT"),
    ("SVC_SYSTEMD_KILL", "APP_JOB_CANCEL"),
    ("SVC_SYSTEMD_EXIT", "APP_JOB_ERR"),
    ("SVC_SYSTEMD_TIME", "APP_JOB_LATENCY"),
    ("SEC_AUTH_FAIL", "SVC_SYSTEMD_PAM"),
    ("SYS_CONFIG_ERR", "APP_CFG_ERR"),
    ("APP_CFG_ERR", "APP_JOB_ERR"),
    ("APP_FILE_MISSING", "APP_JOB_ERR"),
    ("APP_GITLAB_FAIL", "APP_JOB_ERR"),

    # --- clock / RPC ---
    ("SYS_CLOCK_SKEW", "NET_TCP_FAIL"),
    ("NET_CONFIG_ERR", "NET_TCP_FAIL"),
    ("NET_TCP_FAIL", "NET_RPC_ERR"),
    ("NET_RPC_ERR", "APP_INFRA_FAIL"),
]


def main() -> int:
    out_path = Path(__file__).parent.parent / ".data" / "causal_edges_placeholder.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "cause_event", "effect_event", "tier", "num_methods",
            "detected_by_transformer", "detected_by_pcmci_plus", "detected_by_transfer_entropy",
        ])
        for cause, effect in EDGES:
            writer.writerow([cause, effect, "Placeholder", 0, "False", "False", "False"])
    print(f"Wrote {len(EDGES)} placeholder edges to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
