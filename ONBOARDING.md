# Onboarding — running HERALD on a new system

HERALD stands for HPC Ensemble Reasoning, Analytics, and LLM-Driven Diagnostics. It is an HPC operations assistant. Architecture:

- **Backend**: FastAPI + PydanticAI agent that calls SQL / RAG / job-prediction
  sub-agents. Stream protocol = Vercel AI SDK v5. Job prediction ships with
  a sample model trained on fabricated synthetic data (not real Frontier
  measurements — see `src/job_pred/model_data/README.md`); if those model
  files are ever missing, the tool reports that clearly instead of failing.
- **Frontend**: Next.js 15 chat UI with a Plotly chart panel
  (Simple / Advanced tabs) that hits the backend via `/api/chat`.
- **Models**: OpenAI-compatible HTTP endpoints (vLLM, Ollama, Azure OpenAI,
  or Anthropic Claude). Configured in `.env`.

**No terminal at all (macOS)?** Double-click `Start HERALD.command` in
Finder instead of everything below — it launches Docker Desktop if needed,
builds/starts the stack, and opens your browser straight to Setup or chat.
First launch: right-click → Open once to get past Gatekeeper's unsigned-
script warning.

**In a hurry, but comfortable with a terminal?** Run `./setup.sh` instead
of steps 1-6 below — it prompts for a model backend, writes `.env`, and
offers to launch `make docker-up` for you. The rest of this doc is the
manual, step-by-step equivalent.

## Prerequisites

| | Version | Needed for | Notes |
|---|---|---|---|
| Docker Desktop | any recent | Recommended path (`Start HERALD.command`/`setup.sh`/`make docker-up`) | Or another BuildKit-capable Docker. `Start HERALD.command` offers to launch it if installed but not running, and tells you clearly if it's not installed at all. |
| Python | 3.12 | Bare-metal path only | Pinned in `Makefile` as `SYS_PY := python3.12`. Docker path doesn't need this on your machine — it's installed inside the container. |
| Node.js | 20 LTS | Bare-metal path only | `make frontend` uses `nvm use v20`; system Node ≥18 also works. Docker path doesn't need this on your machine either. |
| OS | macOS or Linux | Either path | tested on macOS 25 (Darwin) + Linux x86 / ARM |
| Disk | ~50 GB if hosting your own 70B model | Self-hosted vLLM only | weights + KV cache |

Optional but recommended for production: NVIDIA GPU(s) for vLLM, plus a
Hugging Face account for model downloads.

## 1. Clone and bootstrap the Python env

```bash
git clone https://github.com/at-aaims/herald.git
cd herald

make init       # creates .venv, installs requirements.txt
```

## 2. Generate demo data (DuckDB)

The SQL sub-agent queries a DuckDB file under `.data/`. Sample data is
synthesized from a generator script:

```bash
make generate-data
# → writes .data/private/ornl/frontier/jobsummary/*.parquet (last 3 months through today)
```

## 3. Build the RAG documentation index

`src/rag/chroma_db` is a regenerable build artifact, not committed to git —
build it once from the corpus already bundled in `src/rag/rag_assets/`:

```bash
.venv/bin/python scripts/ingest_rag_corpus.py
# → builds src/rag/chroma_db (text/table/image collections, 5 demo-ready
#   OLCF docs by default -- see DEFAULT_CORPUS in the script. The rest of
#   src/rag/rag_assets/ (7 more files) stays in the repo for you to add
#   later via the Knowledge Base upload panel in /setup, no restart needed)
```

Skip this if you don't need the HPC Documentation Search tool.

## 4. Hugging Face login (only if you're going to self-host weights)

```bash
. .venv/bin/activate
huggingface-cli login       # paste a token from huggingface.co/settings/tokens
```

Skip this if you're using Anthropic / Azure / Ollama only.

## 5. Configure `.env`

```bash
cp .env.example .env
```

(`make env` is a separate, site-profile-driven setup used for ORNL-internal
deployments — see `site/README.md`. For a plain checkout, copying
`.env.example` directly is simpler and all you need.)

Open `.env` and pick **one** large-model backend:

### Option A — Anthropic Claude (simplest, no local GPU)

```env
LARGE_MODEL__TYPE=anthropic
LARGE_MODEL__NAME=claude-opus-4-7
LARGE_MODEL__KEY=sk-ant-…
```

### Option B — Azure OpenAI

```env
LARGE_MODEL__TYPE=openai
LARGE_MODEL__NAME=gpt-5.5
LARGE_MODEL__URL=https://<your-resource>.openai.azure.com/openai/deployments/<deployment>?api-version=2025-01-01-preview
LARGE_MODEL__KEY=<your-azure-key>
```

### Option C — Local Ollama (free, modest hardware)

```bash
ollama pull llama3.1:8b
```

```env
LARGE_MODEL__TYPE=vllm
LARGE_MODEL__NAME=llama3.1:8b
LARGE_MODEL__URL=http://localhost:11434/v1
```

### Option D — Self-hosted vLLM (production setup)

On a GPU box (Linux + CUDA), launch two vLLM servers in `tmux`:

```bash
# Orchestrator — Hermes-4-70B (AWQ 4-bit, ~40 GB on disk)
huggingface-cli download cyankiwi/Hermes-4-70B-AWQ-4bit
MAX_JOBS=2 python3 -m vllm.entrypoints.openai.api_server \
    --model cyankiwi/Hermes-4-70B-AWQ-4bit \
    --served-model-name Hermes-4-70B \
    --host 0.0.0.0 --port 8082 \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.55 \
    --enable-auto-tool-choice --tool-call-parser hermes

# SQL sub-agent — SQLcoder-8B (~16 GB)
python3 -m vllm.entrypoints.openai.api_server \
    --model defog/llama-3-sqlcoder-8b \
    --served-model-name sqlcoder-8b \
    --host 0.0.0.0 --port 8001 \
    --max-model-len 8192 --gpu-memory-utilization 0.25
```

Then in `.env` (replace IP if not on the same host):

```env
LARGE_MODEL__TYPE=vllm
LARGE_MODEL__NAME=Hermes-4-70B
LARGE_MODEL__URL=http://<gpu-host>:8082/v1

SQL_MODEL__TYPE=vllm
SQL_MODEL__NAME=sqlcoder-8b
SQL_MODEL__URL=http://<gpu-host>:8001/v1
```

Verify the endpoints from the app host:

```bash
curl http://<gpu-host>:8082/v1/models
curl http://<gpu-host>:8001/v1/models
```

## 6. Start the backend and frontend

**Option A — Docker (recommended, replaces steps 1–4 above too):**

Once `.env` is configured (step 5), skip `make init` / `make generate-data`
/ `ingest_rag_corpus.py` entirely and run the whole stack (backend +
frontend, hot-reload preserved) in containers instead:

```bash
make docker-up
# → backend on http://localhost:8000, frontend on http://localhost:3000
```

First boot auto-generates demo data and builds the RAG index inside the
container (idempotent — safe to restart). Requires Docker Desktop (or
another BuildKit-capable Docker) running locally. See
[`deploy/README.md`](./deploy/README.md) for the corporate-proxy CA-cert
note and `make clickhouse-up` for the optional ClickHouse backend. Stop
with `make docker-down`.

**Option B — bare-metal:**

```bash
make api
# → FastAPI on http://localhost:8000
```

Health check: `curl http://localhost:8000/api/health` → `{"status":"ok"}`.

```bash
make frontend-install   # one-time
make frontend           # separate terminal
# → Next.js on http://localhost:3000
```

Either way, open http://localhost:3000 and try:

> daywise job count grouped by project_domain

You should see:
1. A `SQL Query` tool card with the generated SQL + a result table.
2. Below the table, **Simple** and **Advanced** chart tabs.
3. Advanced tab → set Group=`project_domain` → multi-line chart.

## 7. (Optional) Try the syslog monitor

Using `make docker-up`: nothing to do — the entrypoint generates both files
automatically on first boot, same as the demo job data and RAG index. Just
open <http://localhost:3000/syslog>.

Bare-metal:

```bash
.venv/bin/python scripts/build_placeholder_causal_edges.py  # writes .data/causal_edges_placeholder.csv
.venv/bin/python scripts/build_demo_cascades.py              # writes .data/syslog_demo.jsonl
# make api and make frontend already running from step 6
open http://localhost:3000/syslog
```

Skip the first line and every row's upstream-cause panel will show "no
dependents" — the click-to-explain walker has no edges to traverse without it.
Skip the second and the monitor has no source file to stream at all (404 on
`/api/syslog/stream`).

The cascade-demo JSONL has four verified causal cascades (Lustre
eviction, slow-step OOM, OST fabric storm, fabric PHY degrade). In the
UI, click **Connect**, then click any cascade-effect row (e.g.
`APP_INFRA_FAIL`) to see the upstream-cause DAG and an LLM-generated
operator advisory.

From the chat tab (`http://localhost:3000`) the same data is reachable via
three syslog tools: `lookup_syslog_event`, `syslog_recent_activity`,
`query_syslog_history`. Sample prompts:

> What causes APP_INFRA_FAIL?
> Which nodes had the most NET_CXI_TIMEOUT events in the last hour?
> List every Manual-tier causal edge in the database.

The proposal queue at `/syslog/proposals` reviews LLM-suggested regex
patterns for unmatched lines (the SC paper's iterative-taxonomy loop).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Spinner never clears | Backend can't reach the model | `curl <LARGE_MODEL__URL>/models` |
| `from_timezone does not exist` | LLM hallucinated a function | Switch SQL model to SQLcoder (Option D) |
| Chart truncated to N rows | `query_output_limit_table` in `src/config.py` | The UI fetches full rows via `/api/sql-result/{token}` already |
| `make frontend` fails on nvm | Native Node ≥18 works fine | `cd frontend && npm install && npm run dev` |
| 16k context error | Long multi-turn conversation | Increase vLLM `--max-model-len`, or clear the chat |

## Project layout

```
.
├── src/
│   ├── agent/herald_agent.py     # PydanticAI orchestrator + tool definitions
│   ├── server/api.py           # FastAPI + Vercel AI SDK adapter
│   ├── server/sql_cache.py     # Side-channel for full SQL rows
│   ├── sql/                    # text-to-SQL sub-agent
│   ├── rag/                    # documentation RAG sub-agent
│   ├── job_pred/               # regression-based job prediction
│   ├── mcp/servers/            # MCP servers (for external clients)
│   └── models/                 # ModelConfig + provider factories
├── frontend/
│   ├── app/                    # Next.js 15 routes
│   ├── components/
│   │   ├── ChatInterface.tsx       # chat loop, draggable bubble width
│   │   ├── ToolCallCard.tsx        # tool result rendering, side-channel fetch
│   │   ├── PlotlyChart.tsx         # Simple tab
│   │   └── PlotlyChartAdvanced.tsx # Advanced tab (custom panel)
│   └── lib/
├── agent_orchestration_deployments/
│   ├── hermes/                 # Hermes-4-14B-FP8 vLLM launch script
│   └── nemotron/               # Nemotron-Super-120B (parked)
├── scripts/generate_frontier_job_data.py
└── Makefile                    # init / api / frontend / generate-data / fetch-models
```
