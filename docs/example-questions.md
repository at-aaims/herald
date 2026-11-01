# HERALD — Example Questions by Tool

A catalog of example questions for the HERALD chat assistant, grouped by the
sub-agent / tool each one is meant to exercise. Use these to demo the system,
to sanity-check tool routing after changes, or as a starting point for your own
prompts.

> **Tip — enabling tools:** each group below maps to a tool you can toggle in
> the chat's tool selector. A question only routes to a tool if that tool is
> **enabled** for the session. Defaults: `sql` (HPC Telemetry Analytics) is on;
> `rag`, `jobpred`, and `syslog` are off — turn them on to use the questions in
> those sections.

> **Tip — routing:** HERALD has two distinct data domains. **Jobs / telemetry**
> (scheduler state, energy, power, nodes, accounts, users) → the HPC Database
> tools. **Syslog events** — `UPPER_SNAKE_CASE` taxonomy labels like
> `APP_INFRA_FAIL`, `NET_CXI_TIMEOUT`, `FS_CLUSTER_EVICT` — → the Syslog tools.
> If a syslog question routes to the jobs database, the syslog tool is either
> disabled or the phrasing was ambiguous; name the event label explicitly.

---

## 1. HPC Telemetry Analytics — `sql` (`query_hpc_database`)

**What it does:** Natural-language → SQL against the HPC **job/telemetry**
database (jobs, energy, power, node utilization, scheduler state, accounts,
science domains, time-series metrics). The UI renders the full result as a
chart + table.

**Route here for:** job counts, runtimes, energy/power stats, utilization,
per-user / per-account / per-domain breakdowns, anything time-series over jobs.

**Example questions:**
- How many jobs ran in the last 24 hours?
- Which 10 jobs consumed the most energy last week?
- Show the hourly count of FAILED jobs over the past 7 days.
- What is the average runtime of jobs science domain wise?
- Which user submitted the most jobs this month?
- Total power draw per node group yesterday.
- List jobs that ran on more than 50 nodes and failed.
- Average node utilization by account over the last 30 days.
- What's the median elapsed time for completed jobs on partition `batch`?
- Energy used per science domain last quarter, as a breakdown.

---

## 2. HPC Documentation Search — `rag` (`search_hpc_docs`)

**What it does:** Semantic search over the ingested HPC **documentation** —
retrieves the most relevant passages (and a related table/diagram when present)
and the orchestrator synthesizes a grounded answer from them.

**Route here for:** "how do I…", policy questions, system/hardware specs,
scheduling and storage procedures — anything answered by the user guides rather
than live job data.

**What you'll see:** the answer, a **Sources:** line citing the document(s)
(e.g. `frontier_user_guide.rst`), and **inline diagram thumbnails** when a figure
is relevant. (Enable **HPC Documentation Search** in the tool selector first.)

**Currently ingested corpus:** OLCF user guides — **Frontier**, **Andes**,
**Crusher**, **Spock**, **Citadel**, **DTN**, **HPSS**, **Odo**, home, the 2024
OLCF system changes, and the Frontier Wikipedia page. The questions below target
that content, plus you can upload your own docs via the **Knowledge Base** panel.

**Jobs / scheduling (Slurm):**
- How do I submit a batch job on Frontier?
- Show an example Slurm batch script for Frontier with `#SBATCH` directives.
- How do I run a job interactively with `salloc` on Frontier?
- What's the difference between `srun` and just running a command in the batch script?
- How do I submit to Frontier from the DTNs?

**Hardware / architecture (often returns a diagram):**
- What does a Frontier compute node look like? *(expect the node diagram)*
- How many GCDs/GPUs are on a Frontier node, and how are they connected?
- Show the Andes node description / core layout.
- What are the SMT thread-layout options on Andes?
- What is the NVMe / node-local storage configuration on Frontier?

**Storage / data movement:**
- What filesystems are available on Frontier (Orion/Lustre, NFS, etc.)?
- How do I archive data to HPSS with `hsi` and `htar`?
- How do I transfer data using the Data Transfer Nodes (Globus / DTNs)?
- Where is scratch, and what is the purge policy?

**Environment / getting started:**
- How do I load and manage software modules on Frontier?
- What's the quick-start procedure for Crusher / Spock?
- What changed in the 2024 OLCF system updates?

**Tables (returns a related table when relevant):**
- What are the partition / queue limits on Frontier?
- List the available compute partitions and their node counts.

---

## 3. Job Power/Energy Prediction — `jobpred` (`predict_job_stats`)

**What it does:** Predicts **power, temperature, and energy** statistics for a
hypothetical job given its science domain, node count, and runtime — i.e.
forward-looking estimates, not historical queries.

**Route here for:** "what would X cost / draw / consume" style predictions
about a job that hasn't run yet.

**Example questions:**
- Predict the energy use of a 128-node CFD job running for 6 hours.
- What power draw should I expect from a 64-node molecular-dynamics run?
- Estimate the peak node temperature for a 256-node climate simulation over 12h.
- How much energy will a 32-node ML training job use in 4 hours?
- Compare predicted energy for a job at 64 vs 128 nodes for the same runtime.
- What's the expected average power for a genomics workload on 16 nodes?
- Forecast total energy for a 512-node, 2-hour CFD job.
- Predicted temperature envelope for an 8-node, 24-hour run.

---

## 4. Syslog Causal Lookup — `syslog`

The syslog tool group covers **HPC syslog events** and their **causal graph**
(tier1 + tier2 statistically-validated edges, plus operator-curated Manual
edges). It has **four sub-tools**, each for a different shape of question.

Event types are `UPPER_SNAKE_CASE` taxonomy labels, e.g. `APP_INFRA_FAIL`,
`NET_CXI_TIMEOUT`, `FS_CLUSTER_EVICT`, `GPU_HARD_FAULT`, `SYS_KERNEL_PANIC`,
`FS_LUSTRE_OST_ERR`.

### 4a. Static causal graph — `lookup_syslog_event`

**What it does:** Looks up an event *type in the abstract* — its description,
**every possible** upstream cause and downstream effect from the causal graph,
whether it's an independent source or a terminal effect, plus any recent
instances on the live monitor.

**Route here for:** "what causes / what is / what does X lead to" — the event
in general, not a specific occurrence.

**Example questions:**
- What causes `APP_INFRA_FAIL`?
- What is `GPU_HARD_FAULT`?
- What does `FS_CLUSTER_EVICT` lead to downstream?
- Is `SYS_KERNEL_PANIC` an independent event or part of a cascade?
- Which events can trigger `NET_CXI_TIMEOUT`?
- What are the downstream effects of `FS_LUSTRE_OST_ERR`?
- Show the upstream causes and downstream effects of `APP_JOB_LATENCY`.

### 4b. Occurrence cascade trace + advisory — `explain_syslog_event`

**What it does:** Explains a **specific occurrence** — the chat equivalent of
clicking an event in the Syslog Monitor. Anchors on the most recent instance
(or an explicit node + timestamp), walks the causal graph upstream within a
time window, and reports which causes **actually fired** (with raw instances
and a cascade tree). When asked *what to do*, it also generates **operator
remediation advisory**.

**Route here for:** "why did *this* happen", "trace the cascade behind the
last X", and "what should the operator do about X".

**Example questions (trace only — fast, no advisory):**
- Why did the last `APP_INFRA_FAIL` happen?
- Trace the cascade behind the most recent `SYS_KERNEL_PANIC`.
- What actually caused the latest `FS_CLUSTER_EVICT` on `frontier-0042`?
- Walk 3 hops upstream from the last `NET_CXI_TIMEOUT`.
- Which upstream causes fired before the recent `GPU_HARD_FAULT`?

**Example questions (trace + operator advisory):**
- What should the operator do about the recent `FS_CLUSTER_EVICT`?
- The last `APP_INFRA_FAIL` on `frontier-0042` — what happened and how do I fix it?
- Give me remediation steps for the latest `GPU_HARD_FAULT` cascade.
- Walk me through the last `SYS_KERNEL_PANIC` and recommend actions.

### 4c. Live activity snapshot — `syslog_recent_activity`

**What it does:** Snapshot of what's flowing through the monitor *right now* —
classifier counters, top event types in a window, and a per-node breakdown.

**Route here for:** "what's happening on the system", "which nodes are noisy".

**Example questions:**
- What's happening on the system right now?
- Show me recent syslog activity.
- Which nodes are the noisiest in the last 5 minutes?
- What are the top event types in the last 10 minutes?
- How many residual (unclassified) log lines have we seen?

### 4d. Historical event queries — `query_syslog_history`

**What it does:** Natural-language → SQL against the **persistent** syslog
events store (every classified message, JOINable against the causal-edges
table). Use for history/aggregates beyond the live ring buffer's ~1-hour window.

**Route here for:** counts/trends of events over time, cross-node comparisons,
per-subsystem breakdowns, JOINs against the causal graph.

**Example questions:**
- How many `GPU_HARD_FAULT`s did each node have in the last 24 hours?
- Hourly histogram of `FS_CLUSTER_EVICT` over the past week.
- Which causes preceded each `APP_INFRA_FAIL` on `frontier-0042` yesterday?
- Top 10 most frequent event types in the last 7 days.
- Compare `NET_CXI_TIMEOUT` counts across nodes this month.
- Per-subsystem event breakdown (NET / GPU / FS / SYS …) for the last day.
- List all Manual-tier causal edges in the graph.

---

## 5. Cross-tool / follow-up flows

Questions that naturally chain tools, or that show the difference between the
abstract graph and a concrete occurrence:

- "Why did the last `APP_INFRA_FAIL` happen?" → *(then)* "and what should the
  operator do about it?" — first turn traces the cascade; the follow-up adds
  the advisory.
- "What *can* cause `FS_CLUSTER_EVICT`?" (static graph, `lookup_syslog_event`)
  vs. "What caused the *last* `FS_CLUSTER_EVICT`?" (occurrence,
  `explain_syslog_event`).
- "How many `GPU_HARD_FAULT`s today?" (`query_syslog_history`) → "Why did the
  most recent one happen?" (`explain_syslog_event`).
- "Predict energy for a 128-node CFD job" (`jobpred`) → "What's the policy on
  energy budgets for CFD allocations?" (`rag`).
