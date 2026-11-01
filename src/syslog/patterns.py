"""
src/syslog/patterns.py — HPC syslog regex pattern database.

Ported verbatim from:
  syslog_model/codes/data_processing/preprocess_dataset_event_generation/
  log_parsing_regex_patterns_based_2_for_2_slurm.py

The taxonomy of 87 event types is the output of the SC paper's Stage 1
LLM-based semantic parsing; this module is Stage 2 — deterministic regex
classification, runs on the hot path with no LLM dependency.

Iteration order matters: critical events are listed first, noise classes
last (INFO_NOISE / SYS_X11_NOISE). classify_log_line returns the first
matching label, so reordering changes behavior.
"""
import re
from typing import Pattern

from src.syslog.patterns_extension import EXTENSION_PATTERNS, EXTENSION_TAXONOMY


def get_mc_bank_token(line: str | None) -> str | None:
    """Architecture-aware MCE bank decoder. Returns a HW_* token or None."""
    if not line:
        return None
    match = re.search(r'(?:Bank\s*|MC)(\d+)(?:_STATUS)?', line)
    if not match:
        return None
    bank = int(match.group(1))

    if 0 <= bank <= 6:   return "HW_CPU_CORE"
    if 7 <= bank <= 15:  return "HW_FABRIC_INT"
    if 16 <= bank <= 23: return "HW_MEM_DIMM"
    if 24 <= bank <= 31: return "HW_PCIE_HUB"
    if 32 <= bank <= 47: return "HW_FABRIC_RTR"
    if 48 <= bank <= 63: return "HW_IF_GPU_LINK"
    return "HW_MCE_UNK"


_BUILTIN_LOG_PATTERNS: dict[str, Pattern[str]] = {

    # --- SLINGSHOT (Network) ---
    "NET_CXI_HW_ECC":    re.compile(r"(?:cxi_ss1|cxi_core|device hsn\d+|pnp 00:\d+).* (?:C_EC_UNCOR|C_EC_CRIT|C_EC_UNCOR_NS|C_EC_BADCON_S)|Fatal error"),
    "NET_CXI_MGMT_ERR":  re.compile(r"(?:cxi_ss1|cxi_core|device hsn\d+|hsn\d+|ens\d+|sbl|cxi_sbl).* (?:Unexpected PLDM completion|failed to bring up device|Decoupling failed|unable to apply configuration|Failed to read setting!)"),
    "NET_CXI_PHY_ERR":   re.compile(r"(?:cxi_ss1|cxi_core|sbl|cxi_sbl).* (?:PCIe error:.*(?:TX Nak|RX Nak|LCRC Error|BAD TLP|RX Recovery|Replay Timer|Retry LLP|Replay Timeout|BAD DLLP)|max llr replay|pml hdlr|ucw fail|bad ucw|Failed CRC check)", re.IGNORECASE),
    "NET_CXI_LINK":      re.compile(r"(?:(?:warning:|error:)\s*)?(?:cxi_ss1|cxi_core|\[ID \d+\]|sbl|cxi_sbl|hsn\d+).* (?:Carrier lost|link down alert|unexpected disconnect|auto lane degrade|PCS lock|pcs lock|alignment lost|alignment failed|Unable to set state up|some eyes have gone bad|serdes_.* failed|SerDes .* failed|LLR .* failed|LLR .* timeout|pcs_wait .* timeout|errors already present|pml_start failed|sbl_serdes_op failed|link fault detect start failed|link failed during startup|exchange timeout)|high BER port|determined to be down|CXI_EVENT_LINK_UP|CXI_EVENT_LINK_DOWN|lmon: up request failed|rx degrade failure alert|Inbound wait is stuck|Inbound wait timeout|Operstate or carrier state down|sbl_link_down failed"),
    "NET_CXI_INT_ERR":   re.compile(r"(?:cxi_ss1|cxi_core|kfi_cxi|kcxi_\w+|kcxi_md_alloc|kcxi_md_cache_remove_md|kcxi_msg_tx_req_cb|kcxi_sendmsg|kfi_cxi - .* Failed to match).* (?:uC failed to return|OXE_AT_EPOCH_CNTR|cxi_user_pte_status|ucxi_write|couldn't read page|No VMA covering|Failed to map|Failed to update IOV|freeing cached md|Failed to allocate|Failed to match with local)", re.IGNORECASE),
    "NET_CXI_WARN":      re.compile(r"(?:cxi_ss1|cxi_core|sbl|cxi_sbl|kfi_cxi).* (?:C_EC_COR|C_EC_BADCON|port_dfa_mismatch|lmon: warning|warning, ccw|out of bounds|tuning params bad|Unable to get AMA|not AMA format)|retried due to timeouts|nack_backoff|sct_.*_epoch|reset_inflight_ordered|Unable to get AMA"),
    "NET_CXI_SVC":       re.compile(r"(?:(?:error:)\s*)?(?:mlx5_core|cxi_core).* (?:CXI allocation failed|Slingshot service allocation failed|No TLE pools|Failed to destroy CXI Service|give fail|failed to allocate page)|No TLE pools available|CXI allocation failed for|Failed to destroy CXI Service"),
    "NET_CXI_FIRMWARE":  re.compile(r"(?:cxi_sbl|sbl|cxi_core|firmware|cxi_ss1).* (?:multiple software versions|kfi_cxi|kdreg2|Image was not found|DRV_MSG_CODE|serdes fw loaded|failed to read the cable eeprom)"),
    "NET_CXI_RAW_DATA":  re.compile(r"^(?:Tracking|PCT|sct=|retrying|retry completed|force closing|will close|cancel completed|now cancelling|CXI retry).* (?:sct=|tct=|nid=|cxi_retry|PCT |SPT chain|because it only saw|scheduled retry)", re.IGNORECASE),
    "NET_CXI_TIMEOUT":   re.compile(r"(?:cxi_core|cxi_ss1|kfi_cxi|kcxi_\w+|PCT).* (?:SCT|TCT|FC Timeout|Message timeout|sct|tct|taking longer than)|(?:now cancelling|will close|force closing|force close|cancel completed).* (?:SCT|TCT|sct|tct|because it only saw)", re.IGNORECASE),

    # --- GPU (AMD) ---
    "GPU_RAS_FAIL":      re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:RAS records|Fatal error during GPU init|RAS init harvest failure|Saved bad pages|EEPROM failed|EEPROM table records error|amdgpu_ras_eeprom|Failed to save .* data|Writing .* records error|due to bad_page_threshold)"),
    "GPU_MEM_FAULT":     re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:retry page fault|no-retry page fault|VM_L2_PROTECTION_FAULT|Failed to map bo to gpuvm|init_user_pages: Failed|WALKER_ERROR|PERMISSION_FAULTS|MAPPING_ERROR|MORE_FAULTS|Faulty UTCL2|in page starting at|RW:|for process .* pid|already allocated by SVM|userq sem|still active bo|Didn't find vmid)"),
    "GPU_SOFT_LOCK":     re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:Runlist is getting oversubscribed|No more .* queue|DQM create queue.*failed|Queues reset on process|queue id .* is reset)"),
    "GPU_HARD_FAULT":    re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:unrecoverable state|Fence fallback timer|ih_fifo overflow|ih ring buffer overflow|IH soft ring buffer overflow|IH ring buffer overflow|GCEA err detected|MMHUB EA err detected|sq_intr: error|failed to write reg)"),
    "GPU_FIRMWARE":      re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:firmware version too old|Failed to import|Failed to quiesce|Unable to find adev|failed to load ucode|Board power calibration failed|amdgpu_device_ip_init failed|probe of .* failed|hw_init of IP block .* failed)"),
    "GPU_TIMEOUT":       re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:timeout waiting for .* fence|stall on|VM flush ACK|SMU: I'm not done|ring .* timeout|fence wait loop timeout)"),
    "GPU_DRIVER_ERR":    re.compile(r"(?:amdgpu|\[?drm|kfd).* (?:amdgpu_irq_put|Failed to|PCI INT A: not connected|No irq handler|failed to validate PT BOs|Freeing queue vital buffer|Failed to allocate process doorbells|failed to allocate kernel bo|psp gfx command INVOKE_CMD.*failed|\[TTM\]|Illegal opcode|amdgpu_vm_bo_update|update_gpuvm_pte|failed to resume KFD|Queue preemption failed|psp gfx command .* failed|GPU Recovery Failed|reset failed!|Bug: No PASID|failed to load driver|resume of IP block .* failed|Resetting wave fronts)|\[drm:.*\] \*ERROR\*|failed to load driver: \w+|Bug: No .* in .*|MESA: error|ZINK:|VK_ERROR_"),

    # --- HARDWARE (MCE/PCIe) ---
    "HW_MCE_FATAL":      re.compile(r"mce: Uncorrected hardware memory error|Fatal Machine Check|Machine Check:|\[Hardware Error\]: (IPID|PPIN|System Hub|Unified Memory|TSC)|Uncorrected, software restartable|Hardware error from APEI Generic"),
    "HW_MCE_CPU":        re.compile(r"mce: \[Hardware Error\]: PROCESSOR|mce: Unexpected threshold interrupt"),
    "HW_MCE_DUMP":       re.compile(r"IPID |PPIN |SYND |MISC |\|SyndV\||\|CECC\||\|UECC\||\|UECC|\|Deferred\||\|Scrub\||\|Scrub\]|ADDR [0-9a-f]+|\]: 0x[0-9a-f]+|\|-\|-\|-\]:|Syndrome:|\|SyndV"),
    "HW_MCE_GENERIC":    re.compile(r"\[Hardware Error\]: (?:Error|L3 Cache|Coherent Slave|Ext Global Memory|Load Store Unit|Power, Interrupts)(?:.*) (?:Addr|Misc|Ext\. Error Code)|internal: RESV|cache level:|MCE records pool full|APEI Generic|LSI_IDLE_CHECK|too many record IDs|ERST|failed \(load will be required"),
    "HW_MCE_CORRECTED":  re.compile(r"\[Hardware Error\]: Corrected error|\[Hardware Error\]: Deferred error"),
    "HW_EDAC_ERR":       re.compile(r"EDAC MC\d+|EDAC .* (UE|CE) on|UE Cannot decode|CE Cannot decode|Cannot decode normalized address|edac_mc_handle_error|edac_raw_mc_handle_error"),
    "HW_IOMMU_ERR":      re.compile(r"AMD-Vi: Event logged|INVALID_DEVICE_REQUEST|IOMMU_FAULT|Inconsistent EFR|Found inconsistent EFR|EFR mismatch|AMD-Vi: Completion-Wait loop timed out"),
    "HW_MEM_CORRUPT":    re.compile(r"Memory failure:.*Sending SIGBUS|unhandlable page|hardware memory corruption|page_counter underflow|shrink_folio_list|generic_error_remove_page|hmm_range_fault|Send SIGBUS to process|recovery action for dirty LRU page"),
    "HW_PCIE_ERR":       re.compile(r"PCIe (?:Bus|AER) (?:Error|not enabled)|PCIe link lost|DPC: (ERR_FATAL|unmasked uncorrectable)|L0 to Recovery|not connected|Unknown NUMA node|can't derive routing|PCI INT A: no GSI|pcieport.*RxErr|device.*error status/mask|BadTLP|AER: Error of this Agent|NonFatalErr|RxErr|BadDLLP|Rollover|Timeout|RX Recovery Request|failed to enable I/O ports|AER:\s+Error|pci .* can't derive routing|SDES"),
    "HW_USB_FAIL":       re.compile(r"usb .*: (?:Cannot enable|unable to enumerate)|i8042: (?:probe of .* failed|Can't aux|.* failed|Can't read .* while initializing)"),
    "HW_ACPI_WARN":      re.compile(r"ACPI (Warning|AML tables)|Invalid PCCT"),
    "HW_BMC_WARN":       re.compile(r"ipmi_si.*BMC does not support|Failed to execute ipmitool|hpilo.*Open could not dequeue|Couldn't read the IPMI|command failed: BMC initialization"),
    "HW_THERMAL_CRIT":   re.compile(r"temperature.*exceeds warning threshold|thermal throttling|THERMAL_FAULT|sensor .* in (fatal|critical|warning) state"),

    # --- STORAGE ---
    "FS_CLUSTER_EVICT":  re.compile(r"LustreError:.*(evicted|Evicted|Lost membership|unmounting file system)|\[E\] Lost membership|\[E\] Remount failed|Unable to contact any quorum nodes|Failed unmounting|Lustre: Evicted|Lustre: Unmounted|Connection to .* was lost|DVS: No valid nodes|Close connection to .* Node failed"),
    "FS_LUSTRE_SLOW":    re.compile(r"(?:LustreError:|Lustre:).* (?:timed out|slow reply|sluggish|lock timed out|Network is sluggish|Request sent has timed out)|connected to the broker .* but haven't received|rpc_clnt_ping_timer_expired"),
    "FS_LUSTRE_MDS_ERR": re.compile(r"LustreError:.*(MDC|mdc|MDS|mds|refresh file layout|lookup|namespace|can't stat MDS)|no group lock held"),
    "FS_LUSTRE_OST_ERR": re.compile(r"LustreError:.*(OSC|osc|OST|ost|object|extent|page discard|recovery action)|dirty page discard|resending request on EINPROGRESS|import=connection"),
    "FS_LUSTRE_ERR":     re.compile(r"LustreError:|Lustre: .* (?:mount|recovery|connect|setup|initialize|Request sent has) failed|VFS: Lookup of .* caused loop|File System .* unmounted by the system|page is under heavy contention"),
    "FS_GPFS_ERR":       re.compile(r"Error=MMFS_PHOENIX|\[X\] Recovery Log I/O failed|\[W\] GPFS detected .* vCPUs|\[W\] The TCP connection .* unexpected|\[E\] Failed to join|\[E\] Failed to open|Command: err .* mount|Error=MMFS_SYSTEM_UNMOUNT|Unrecoverable file system operation|expelled from the cluster|Error=MMFS_DISKFAIL|\[E\] Disk failure|Could not open the key store file|The RKM is in quarantine|TCP connection with the RKM|Freeing shared GPFS trace buffer|key server .* quarantined|Key .* could not be fetched|A severe error was encountered during cluster probe|Disk free space collection .* aborting"),
    "FS_XFS_ERR":        re.compile(r"XFS .* metadata I/O error|xfs filesystem being mounted"),
    "FS_DISK_FULL":      re.compile(r"No space left on device|write error .* No space left|Region database full|SEL buffer used at \d+|no space left on logging partition|Disk quota exceeded"),
    "FS_IO_ERR":         re.compile(r"Input/output error|SQUASHFS error|Failed to read block|kernel resource error|Read-only file system|iSCSI Login negotiation failed|Device: /dev/sd.* \[SAT\]|Offline uncorrectable sectors|journal corrupted|I/O Cmd.*I/O Error|Admin Cmd.*I/O Error|I/O error, dev .*|overlayfs: failed to|overlayfs: .* in-use|Stale file handle|VG .* incomplete|PV .* has no VG metadata|PV .* is duplicate for PVID"),
    "STO_NVME_STALL":    re.compile(r"nvme.*taking a long time|nvme.*frozen state|nvme.*reset controller|Worker.*processing SEQNUM|Worker .* terminated by signal|Device: .*, Critical Warning"),
    "FS_DVS_WARN":       re.compile(r"DVS: .* failed|DVS: .* error|DVS: .* timeout|WARNING: dvs.* is down|WARNING: dvs.* is up|killing request RQ_FILE|DVS debugfs|read_clustered_super|cray-dvs-mqtt|DVS: common_retry|loadbalance_index|marking it down|from downed node|All replies .* stuck|No sign of dvs.* after reconnect"),

    # --- OS & KERNEL (Including Context Splits) ---
    "SYS_OOM_KILL":      re.compile(r"Out of memory: (Killed|Setting TIF_MEMDIE)|invoked oom-killer|page allocation failure: order:|SLUB: Unable to allocate|VM_FAULT_OOM|Cannot allocate memory|slab_out_of_memory|pagefault_out_of_memory|rtnetlink .* Out of memory"),
    "SYS_SEGFAULT":      re.compile(r"segfault at .* ip |kernel trap in|General Protection Fault at|RIP: [0-9a-f]+:[0-9a-f]+|traps: .* general protection|traps: .* trap invalid opcode"),
    "SYS_KERNEL_PANIC":  re.compile(r"Kernel panic|BUG: (?:soft|hard|spinlock) lockup|unable to handle kernel|No irq handler for vector|DVS: .* is NULL!"),

    # [SPLIT] Specific Kernel Contexts (Check these BEFORE generic context)
    "CTX_AMDGPU":        re.compile(r"(?:Call Trace:|RIP:).*?(?:amdgpu_|kfd_|drm_|ttm_|atom_)", re.IGNORECASE),
    "CTX_LUSTRE":        re.compile(r"(?:Call Trace:|RIP:).*?(?:ptlrpc|lustre|ldlm|obd_|lnet_)", re.IGNORECASE),
    "CTX_SLINGSHOT":     re.compile(r"(?:Call Trace:|RIP:).*?(?:cxi_|kfi_|ss_core)", re.IGNORECASE),
    "CTX_MEMORY":        re.compile(r"(?:Call Trace:|RIP:).*?(?:mm_|slab_|alloc_pages|kmem_cache|vmalloc|page_fault)", re.IGNORECASE),
    "CTX_SCHEDULER":     re.compile(r"(?:Call Trace:|RIP:).*?(?:schedule|pick_next_task|rcu_|spin_lock|mutex_lock)", re.IGNORECASE),

    # [FALLBACK] Generic Kernel Context
    "SYS_KERNEL_CTX":    re.compile(r"(?:R(?:1[0-5]|0?[0-9]): |RBP: |RSP: |FS: |GS: |EFLAGS: |ORIG_RAX: |Modules linked in: [\w_]+|CPU: \d+ PID:|CS: .* DS: .*|RAX: |CR2: |<TASK>|</TASK>|<IRQ>|</IRQ>|RDX: |RSI: |-{4,}\[ (?:cut here|end trace) \]-{4,}|[\w_]+\+0x[0-9a-f]+/[0-9a-f]+|RIP: [0-9a-f]+:[0-9a-f]+|Call Trace:|(?:[\w_]+\([A-Z]+\)\s+)+[\w_]+\([A-Z]+\)|Code: (?:[0-9a-f]{2}\s+){2,}[0-9a-f]{2}|rcu: Stack dump where .*|rcu: CPU \d+: RCU dump cpu stacks)"),

    "SYS_RCU_STALL":     re.compile(r"rcu_.*self-detected stall|rcu_sched kthread starved|blocking rcu_node structures|tasks blocking .* RCU grace period|detected expedited stalls on CPUs|rcu: \s*\d+[-.!:]+ \(\d+ (?:GPs behind|ticks this GP)\)"),
    "SYS_WATCHDOG":      re.compile(r"NETDEV WATCHDOG|NMI watchdog: BUG|watchdog: BUG: soft lockup|watchdog: BUG: hard lockup|terminated by own WATCHDOG|watchdog did not stop|watchdog on CPU|Child .* terminated by own WATCHDOG|Failed to send WATCHDOG=.* notification message|NMI backtrace for cpu"),
    "SYS_CLOCK_SKEW":    re.compile(r"clocksource: (?:Long readout|Switched to|timekeeping watchdog|Marking clocksource)|Checking clocksource tsc synchronization|chronyd.*(?:Forward time jump|System clock wrong)|ntpd.*(?:System clock wrong|time reset)|Forward time .* jump detected|System clock wrong by|Ring buffer clock went backwards"),
    "SYS_CONFIG_ERR":    re.compile(r"sysctl: .* cannot be set|amd_hsmp: Family.*not supported|request_module: kmod_concurrent_max|pstore: ignoring unexpected backend|modprobe: FATAL:|modules\.dep.*No such file|Speculative Return Stack Overflow:.*microcode not applied"),
    "SYS_PROCESS_LIM":   re.compile(r"over core_pipe_limit"),
    "SYS_COREDUMP":      re.compile(r"systemd-coredump|Skipping core dump|Failed to send coredump|systemd-coredump\.socket: Too many incoming connections"),

    # --- SYSTEMD SPLIT (Crucial for RCA) ---
    "SVC_SYSTEMD_START": re.compile(r"(?:systemd\[\d+\]|[\w.-]+\.(?:service|mount|scope)): (?:Failed to start|Unit .* entered failed state|.* Dependency failed|Failed with result|Start request repeated(?: too quickly)?)"),
    "SVC_SYSTEMD_TIME":  re.compile(r"(?:systemd\[\d+\]|[\w.-]+\.(?:service|mount|scope)): .* timed out|call to .* failed: DBus method call timed out|Failed to activate service '.*': timed out"),
    "SVC_SYSTEMD_EXIT":  re.compile(r"[\w.-]+\.(?:service|mount|scope): (?:Main process exited|Mount process exited|Control process exited|Failed with result)"),
    "SVC_SYSTEMD_KILL":  re.compile(r"(?:Mount|Main|Control) process still around after SIGKILL|Processes still around after SIGKILL"),
    "SVC_SYSTEMD_PAM":   re.compile(r"pam_systemd\(\S+\): Failed to (?:stat.*runtime directory|create session|release session)"),
    "SVC_SYSTEMD_SPEC":  re.compile(r"Failed to start (?:Ipmievd Daemon|Rotate log files|User Manager for UID|Rule-based Manager|CM Configuration|k3s|Cluster Manager|Kafka Message Processor|Session \d+ of User|Cray Parallel Application Launch Service Daemon)"),

    # --- APPS ---
    "APP_GITLAB_FAIL":   re.compile(r"(?:ERROR: Job failed|Checking for jobs\.\.\. failed|failed to authorize user|invalid authorization target|Job was canceled|ERROR: after_script failed|Error encountered during job|Error executing run_exec|RunAs message|Failed to process runner|get_sources could not run|script canceled externally \(UI, API\)|Error executing [\w_-]+: exit status \d+|WARNING: Job failed: exit status|Job failed: execution took longer than)"),
    "APP_FILE_MISSING":  re.compile(r"(?:grep:|execve\(\):|open:|stat:|python:|cat:|rm:|ls:|mv:|cp:|head:|tail:|sort:|bash:|sh:|sudo:).*No such file|cannot open shared object file|Could not initialize handlers|Opening file .* failed|Could not open stdout file|unable to open (?:/[a-zA-Z0-9]+|.*No such file)|Failed to open (?:/[a-zA-Z0-9]+|.*No such file|.*directory)|Error opening directory"),
    "APP_CFG_ERR":       re.compile(r"(?:grep:|execve\(\):|bind:|bash:|sh:|sudo:|chmod:|chown:|python:).*(?:Permission denied|Access denied|Not a directory|Text file busy)|command not allowed|incorrect password|execve\(\): .* failed|launched .* with NULL argv|started with executable stack|Failed to get current user|Bind request .* does not specify|Exec format error|execve\(\): .* Exec format error|FATAL: .* change permissions failed|CPU binding outside|ERROR chdir failed|Running with local config file despite|Skipping.*because of failed dependencies|Failed to generate additional resources|error: couldn't chdir to"),
    "APP_INFRA_FAIL":    re.compile(r"job_manager: exiting abnormally|slurmstepd.*startup took|slurm_send_node_msg.*failed|Slurmd could not connect IO|epilog failed|no task list created|Zero Bytes were transmitted|Job .* already killed|called without a previous step|Slurmd could not connect IO|_rpc_launch_tasks|connect_to .* failed|switch_g_job_postfini|prolog failed|STEPD TERMINATED|Submitting job to coordinator|job failed|INTERACTIVE STEP|Job trace termination|Job failed \(system failure\)|Unable to receive \"ok ack\"|bad node index|stepd_completion|Preparation failed|failed sending step completion|WIFSTOPPED|stat_jobacct|Header lengths are longer than|called without a previous init|Couldn't sent slurm_io_init_msg|failed to get link speed|STEP .* FAILED|no cmds found|No executable program specified|Failed mpi_|no command for task id|Failed to kill program|Prolog failure|XALT_EXCEPTION|epilog: timeout|fatal: _handle_connection|RH: fatal error|Not enough .* to bind|ssh_msg_send failed|slurmstepd:.*Process .* failed with exit code|Failed to send RESPONSE_LAUNCH_TASKS|_forward_thread: failed to|says my messages were dropped|Failed to start Apache Kafka|Failed to start .* for Apache Kafka|rdkafka.* request\(s\) timed out|Failed to send MESSAGE_TASK_EXIT|slurm_receive_resp_msgs.*Socket timed out|stepd_connect to StepId.*failed"),
    "APP_JOB_CANCEL":    re.compile(r"CANCELLED AT|EXTERN STEP.*TERMINATED|DUE TO TIME LIMIT|RaisedSignal|killed by signal 15"),
    "APP_JOB_ERR":       re.compile(r"kill.*No such process|Process '.*' failed with exit code|Main process exited, code=|Error while executing .* script error="),
    "APP_JOB_CGROUP":    re.compile(r"cgroup plugin has.*processes|can't add pid.*to jobacct_gather|unable to read .* cgroup|Failed to add PIDs to .* control group|_cgroup_procs_check: failed|common_file_write_uints: write value .* failed|slurmstepd:.*Unable to move pid|(?:error:|slurmstepd:.*) Unable to move pid"),
    "APP_JOB_LATENCY":   re.compile(r"slurmstepd startup took|steps did not complete quickly|Zero Bytes were transmitted"),
    "NET_TCP_FAIL":      re.compile(r"(?:cannot connect|connect to|send_launch|connect io|dial tcp|Connection to).*Connection refused|FAIL: .* disconnect|Connection reset by peer|Broken pipe|No route to host|Network is unreachable|Transport endpoint is not connected|Net::OpenTimeout|bond0: Could not generate persistent MAC|unable to connect to broker|Name or service not known|Bad TCP state detected|Temporary failure in name resolution|Unexpected failure.*Connection refused|\[E\] Connection from .* timed out"),
    "SVC_RSYSLOG_ERR":   re.compile(r"rsyslogd: .* action '.*' suspended|action '.*' suspended \(module '.*'\)|(?:rsyslogd: .*|action '.*' .*) message lost|Stopping 'rsyslog.service'|rsyslogd: .* Framing Error|rsyslogd: .* no working or state file directory|imjournal: .*|rsyslogd: .* cannot resolve hostname|rsyslogd: .* Error in publish_message|rsyslogd: .* \$WorkDirectory: .* can not be accessed|cannot resolve hostname '[\w.-]+': Resource temporarily unavailable|Framing Error in received TCP message"),
    "SEC_AUTH_FAIL":     re.compile(r"Authentication failure|Invalid credential|PAM: .* failure|Could not start TLS|LDAP connection error|Munge decode failed|Expired credential|unpermitted request|Invalid authentication credential|Protocol major versions differ|userauth_|PAM: User not known|pam_.*:.*failed|pam_unix|Invalid job credential|If munged is up|Disconnecting authenticating user|Protocol authentication error|Proposer's value list|maximum authentication attempts|Munge encode failed|MESSAGE_TASK_EXIT has authentication error|User account has expired|failed decode|kex_protocol_error|PAM adding faulty module|sbcast credential expired|banner line contains invalid|kex_exchange_identification|Failed to set up PAM|Failed at step PAM|Cannot determine the user's name|refused, authentication failed|NOT in sudoers|corruption detected in|error: type \d+ seq|fatal: Access denied .* PAM"),
    "SVC_CONFIG_ERR":    re.compile(r"unable to open config|Failed to apply catalog|Failed to fork off|Compatibility logic is deprecated|lacks a native systemd unit|Please update package|\(Facter\) error|Referenced but unset environment variable|marked world-inaccessible|Execution of .* returned|change from .* to .* failed|exceeds the number of facts limit|Duplicate entry in|configuration issue|unrecognized key\(s\) detected|marked executable|Could not evaluate|Skipping .* because of failed dependencies|Couldn't write .* ignoring|attribute has been deprecated|assigned as slingshot"),
    "NET_LNET_ERR":      re.compile(r"(?:LNetError:|LNet:).* (?:failed|transport init failed|Discovery failed|unexpected network error|Failed to allocate|Error .* reading HELLO|starting up LNI|total bytes allocated|out of memory|Unexpected error|Failed to get)|Failed to start lnet", re.IGNORECASE),
    "NET_LNET_WARN":     re.compile(r"LNet: Ignoring interface|LNet: Host .* reset|lnet: Ignoring interface|\w+\(OE\)|Warning: No 802\.3ad response"),
    "NET_RPC_ERR":       re.compile(r"Failed to create listener|Unexpected disconnect|Malformed RPC|Protocol major versions differ|channel .* protocol error"),
    "NET_CONFIG_ERR":    re.compile(r"Address family not supported|Binding to IPv6|Invalid priority|DHCPDISCOVER|Multiple interfaces match|bond0.*speed changed"),

    # --- NOISE (Check Last) ---
    "SYS_X11_NOISE":     re.compile(r"(?:^|[\"'])\((?:II|==|--|\+\+|WW|\*\*)\) |Module class: X\.Org|X\.Org Video Driver|X\.Org XInput driver|X Protocol Version|using VT number|modeset\(\d+\):|systemd-logind:|config/udev:|GLX: Initialized|Unloading .*module|Using input driver|Loading .*module|Matrox|AIGLX:|Markers: \(--\) probed|Running in \w+-mode|Entry deleted from|The XKEYBOARD keymap compiler|font path|pci id for fd|ABI class:|Errors from .* not fatal|glx: failed|Failed to grab accelerator|If no devices become available|Unsupported high keycode|Could not resolve keysym|font directory|Default Screen Section|to colour .* device|Extension :|X\.Org ANSI C|cannot support keycodes|Failed to abandon session scope|X\.Org X Server|Failed to load module .* \(module does not exist"),
    "INFO_NOISE":        re.compile(r"Skipped \d+|message repeated|Hardware name:|BIOS|kernel module|Initializing the GPFS|automatic interface scanning|closing TCT|Setting log level|CAUTION|Dynamic interrupt throttling|Deprecated parameter|Using mlock ulimits|audit daemon|switch has rebooted|HTTP error 500 on POST|Allocated shared GPFS|Content changed during rsync|Last unloaded:|mlx5_core.*Missing SyncE|igb.*Reset adapter|snd_hda_intel|pnp 00:|bpmcd|can't read from|cannot create socket|indirect call not allowed|device .* set up|run_command_poll_child|chan_read_failed|Already killed|Received disconnect|_open_as_other|MaxStartups|cannot listen to port|connect_to localhost|no more sessions|hrtimer|initial_batch_size|kernel read not supported|unexpected unlock status|max_batch_size|max_fabric_packet_age|max_no_matching|max_resource_busy|max_spt_retries|max_trs_pend_rsp|message too long|min_free_kbytes|error forwarding|remote server|failed to set xattr|pause_wait_time|pct_cfg_timing|peer_tct_free_wait_time|rsync returned|RT throttling|spt_timeout_epoch_sel|statsFS|mems_allowed|tct_timeout_epoch_sel|client does not accept|warn_alloc|warn_unsupported|warning during parsing|nvidia-caps-imex|PEFILE|PKRU|REQTMOUT|Received unknown opcode|Return Package|See systemctl|See \"\"systemctl|total number of facts|Unloaded tainted|VFS: Lookup|Watching pool|Workqueue:|Wrapped exception|Abandoning IO|Killing connection|Unable to contact|Duplicated hardware|Unable to set up|No AMA found|commMsgCheckMessages|Local host not found|Adding nid|Removing nid|Attempted connection|Can't get traces|Can't load configuration|Can't write to|Cannot find unit|Could not open command|Could not send report|conserver.service|pe.service|compatibility logic is deprecated|Device: /dev/sd|Flags: TI-RPC|NO devices found|retry backoff|Lustre: Mounted|See \"systemctl status|Successfully deleted service|DVS: Revision|Disabling lock debugging|Connection lasted|Interface wait time|restricted to a subset of cpus|TOPOLOGY: no switch|smartd\.service|Predictable network names|LNet.*deprecated|</TASK>|#\d+|build_script|Maximum GFX clk|\{\"@timestamp\":|filebeat|beat|TRACE|ROCm System Management Interface|xGMI error counters not enabled|Potentially caused by missing/incomplete job|No registered file transfer|telegraf\.service|stuck for \d+s|cray_power_management|dvsipc|craytrace|ksocklnd|lnet\(OEn\)|dvsproc|llc\(E\)|fmpm|Overwriting existing symlink|legacy kernel without|slabs: \d+|Traceback|nsprepkg|callbacks suppressed|scheduler tick|Activating service|Successfully activated|module .* already in this config|system status/update|exiting\.|Worker \[\d+\] failed|metric.* \(\d+\.\d+s\)|cpuset=|active=|refcnt=|flags=|node=|cpus=|libEGL warning|failed to enable I/O ports|Applying InputClass|is tagged by udev as|CPU features:|wait_time|C_ATU_STS_|syslog.socket|Current version of|Unknown error|mem-tx:|IA GA PC|CXI retry handler version|Not setting|Unable to get user's local|jackdbus|xfs filesystem .* supports timestamps|report bugs on|latest version|received this message due to a bug|timeout_backoff_multiplier|empty or malformed|X2APIC|NX|^\d+, \d+$|PC GA|GT IA|Failed to connect to avahi|Runtime directory .* not owned|checkname failed|PV .* online|VG .* complete|Module .* not loaded|\[\d+\]|Deferred|Supervising process|root directory access|step_|automatic interface scanning|reporting|tx:|compiled for|VG unknown|PPR|GT|Before reporting problems|process and the information|Using a default|Enabled .* GPEs|backoff_multiplier|This warning only shows|empty or null message|unit configures an IP firewall|is deprecated|WARNING: Use sudo|unknown input|bugs on either our web page|informational message about|system status/update|GA PC|Lustre: .* failed, not fatal|rcu: All QSes seen|cache: [\w_-]+, object size:|VG .* finished|amdgpu_irq_handle|failed to reload|supported: no, unsupported modules|ida_free called for|WARNING: \$ sudo|TaskKilled \(another attempt succeeded\)|TaskSetManager: Lost task"),
}


def _merge_with_extensions() -> dict[str, Pattern[str]]:
    """
    Extensions FIRST in iteration order so they're checked before built-ins
    (higher classification priority). On key collision, the EXTENSION value
    wins — that's how a user overrides a built-in by approving a same-named
    pattern through the P6 control plane.
    """
    merged = dict(EXTENSION_PATTERNS)
    for k, v in _BUILTIN_LOG_PATTERNS.items():
        if k not in merged:
            merged[k] = v
    return merged


LOG_PATTERNS: dict[str, Pattern[str]] = _merge_with_extensions()


# High-volume noise classes — by default sampled down before storage/UI.
NOISE_EVENT_TYPES: frozenset[str] = frozenset({
    "NET_CXI_RAW_DATA",
    "FS_DISK_FULL",
    "INFO_NOISE",
    "SYS_X11_NOISE",
})


# Event types operators should never miss — these bypass any sampling.
CRITICAL_EVENT_TYPES: frozenset[str] = frozenset({
    "HW_MCE_FATAL", "HW_MEM_CORRUPT", "HW_THERMAL_CRIT",
    "GPU_HARD_FAULT", "GPU_RAS_FAIL",
    "FS_CLUSTER_EVICT",
    "SYS_KERNEL_PANIC", "SYS_OOM_KILL",
})


def classify_log_line(log_message: str | None) -> str | None:
    """
    Return the event-type label for a log line, or None if no pattern matched.
    Iteration order matters: see LOG_PATTERNS for priority.
    """
    if not log_message:
        return None

    # Priority 1: architecture-aware MCE bank decode
    if "Machine Check" in log_message or ("MC" in log_message and "_STATUS" in log_message):
        mce_token = get_mc_bank_token(log_message)
        if mce_token:
            return mce_token

    # Priority 2: regex database
    for label, pattern in LOG_PATTERNS.items():
        if pattern.search(log_message):
            return label
    return None


def severity_for(event_type: str | None) -> str:
    """
    Coarse severity bucket for UI coloring.
    Returns one of: critical, error, warning, info, residual.

    Extension-approved labels (P6) provide explicit severity in their
    JSONL entry and override the heuristic below.
    """
    if event_type is None:
        return "residual"
    if event_type in EXTENSION_TAXONOMY:
        return EXTENSION_TAXONOMY[event_type].get("severity") or "info"
    if event_type in CRITICAL_EVENT_TYPES:
        return "critical"
    if event_type in NOISE_EVENT_TYPES:
        return "info"
    if event_type.startswith("CTX_") or event_type.endswith("_CTX"):
        return "info"
    if event_type.endswith(("_WARN", "_SLOW")) or "WATCHDOG" in event_type:
        return "warning"
    if (
        event_type.endswith(("_ERR", "_FAIL", "_FAULT", "_KILL", "_PANIC", "_EVICT",
                             "_CANCEL", "_CORRUPT", "_CRIT", "_FATAL"))
        or "EDAC" in event_type
        or "MCE" in event_type
    ):
        return "error"
    return "info"


def subsystem_for(event_type: str | None) -> str:
    """Return the subsystem prefix (NET, GPU, HW, FS, SYS, SVC, APP, SEC, STO, CTX).
    Extension-approved labels (P6) declare subsystem explicitly.
    """
    if not event_type:
        return "UNKNOWN"
    if event_type in EXTENSION_TAXONOMY:
        return EXTENSION_TAXONOMY[event_type].get("subsystem") or event_type.split("_", 1)[0]
    return event_type.split("_", 1)[0]
