# HERALD
## HERALD: HPC Ensemble Reasoning, Analytics, and LLM-Driven Diagnostics

**HPC operations assistant** — natural-language interface to system-logs, job telemetry, energy data, scheduling policies, documents, and resource-prediction models for HPC systems.

## What's in the box

- **Agent**: PydanticAI orchestrator that routes to specialised sub-agents.
- **Sub-agents** (tools):
  - **SQL** (`src/sql/`) — text-to-SQL against DuckDB tables of job records.
  - **RAG** (`src/rag/`) — semantic search over HPC documentation.
  - **Job prediction** (`src/job_pred/`) — regression model for resource
    forecasting (energy / runtime / nodes). Ships with a **sample model
    trained on fabricated synthetic data** (see `src/job_pred/model_data/README.md`)
    — illustrative only, clearly labeled as such in every response, not
    real Frontier measurements. Swap in a model trained on real data for
    anything operational (same 5 files: `encoder.joblib`,
    `input_scalers.joblib`, `output_scalers.joblib`, `decision_tree.joblib`,
    `model_latest.pth`); if those files are ever missing, the tool reports
    that clearly instead of failing.
  - **Syslog** (`src/syslog/`) — real-time HPC log classifier (80 regex
    event types), causal-graph walker over a configurable edge set
    (ships with a hand-authored placeholder; schema matches the SC
    paper's tier1+tier2 triangulation output for drop-in replacement)
    with operator-curated manual edges, persistent events store
    (DuckDB or ClickHouse) with a text-to-SQL chain, LLM-driven operator
    advisory, and a residual control plane that proposes new regex
    patterns from unmatched lines for human review.
- **Server** (`src/server/api.py`) — FastAPI with Vercel AI SDK v5 streaming
  protocol + a side-channel for full SQL results so the LLM context stays
  bounded while the UI gets every row.
- **MCP servers** (`src/mcp/servers/`) — `herald-sql`, `herald-rag`,
  `herald-jobpred`, `herald-syslog` for use from external clients
  (Claude Desktop, etc.).
- **Frontend** (`frontend/`) — Next.js 15 + AI SDK v5 chat UI with a Plotly
  chart panel (Simple toolbar + an Advanced panel with multi-trace,
  group-by, filter, cumulative, stacked / relative bars, log axes, and a
  draggable card width). Two additional routes: `/syslog` (live monitor
  with click-to-cause DAG) and `/syslog/proposals` (operator queue for
  LLM-proposed regex extensions).
- **Deployments** (`agent_orchestration_deployments/`) — vLLM launch
  scripts for self-hosted models (Hermes-14B FP8 here; Hermes-4-70B-AWQ
  and Nemotron-120B-NVFP4 covered in `ONBOARDING.md`).

## Getting started

**No terminal at all (macOS)**: double-click `Start HERALD.command` in
Finder. Requires [Docker Desktop](https://www.docker.com/products/docker-desktop)
already installed (the script launches it if it's installed but not
running, and tells you clearly if it isn't installed at all). Builds/starts
the stack and opens your browser straight to Setup (first run) or chat
(already configured) once it's ready. First launch: right-click → Open once
to get past Gatekeeper's unsigned-script warning — normal macOS behavior
for any downloaded script, not specific to this one.

Prefer a terminal — one interactive script, no manual `.env` editing:

```bash
./setup.sh
```

Walks through picking a model backend, writes `.env` for you, then offers
to start everything with `make docker-up` (auto-generates demo data and
builds the RAG index on first boot).

Already running (e.g. via `make docker-up` with defaults, or you just want
to reconfigure without touching a terminal again)? Open **Setup** in the
app's left sidebar (`/setup`) — same model-backend picker as `setup.sh`,
as a web form. Changes apply immediately, no restart.

See **[ONBOARDING.md](./ONBOARDING.md)** for the manual, step-by-step path —
covers prerequisites, env config, four model-backend options (Anthropic /
Azure / Ollama / self-hosted vLLM), and an end-to-end smoke test.

Short version once everything is wired:

```bash
make init               # creates .venv and installs requirements
make generate-data      # synth jobstat dataset under .data/ (last 3 months through today)
make api                # FastAPI on :8000
make frontend           # Next.js on :3000 (separate terminal)
```

Then open <http://localhost:3000>.

## Repository layout

```
.
├── src/
│   ├── agent/herald_agent.py    # PydanticAI agent + tool definitions
│   ├── server/api.py            # FastAPI + Vercel AI SDK adapter
│   ├── server/sql_cache.py      # Full-result side-channel
│   ├── sql/   rag/   job_pred/  # Sub-agent implementations
│   ├── syslog/                  # Streaming classifier, causal walker,
│   │                            #   text-to-SQL chain, residual proposer,
│   │                            #   proposals queue
│   ├── mcp/servers/             # Standalone MCP servers
│   ├── models/                  # ModelConfig + provider factories
│   └── site/                    # Per-site DB / data adapters (ORNL Frontier, …)
├── frontend/
│   ├── app/                     # Next.js routes (/ chat, /syslog, /syslog/proposals)
│   ├── components/              # Chat UI, chart panels, tool cards, syslog UI
│   └── lib/
├── agent_orchestration_deployments/ # vLLM launch scripts
├── scripts/                     # Data generators, syslog smoke tests,
│                                #   proposer + reviewer CLIs, alert dispatcher
├── site/                        # Site-specific env scripts (make env)
└── Makefile                     # init / api / frontend / generate-data / env
```

## Model backends

Configured in `.env`. See `.env.example` and `ONBOARDING.md` for full
options. Tested combinations:

| Orchestrator | SQL sub-agent | Notes |
|---|---|---|
| Hermes-4-70B (AWQ 4-bit) | SQLcoder-8B | Production target; ~85 GiB VRAM total |
| Claude Opus 4.7 (Anthropic API) | (shares orchestrator) | Quick start, no GPU needed |
| Azure OpenAI GPT-5.5 | (shares orchestrator) | If VPN doesn't collide with on-prem LAN |
| Ollama llama3.1:8b (local) | (shares orchestrator) | Development convenience |

## License

[MIT](./LICENSE)
