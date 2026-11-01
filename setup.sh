#!/usr/bin/env bash
# setup.sh — interactive, command-line-light HERALD setup.
#
# Walks through picking a model backend and writes .env directly (doesn't
# go through `make env`, which is a separate ORNL-internal site-profile
# flow — see site/README.md). Ends by handing off to `make docker-up`,
# which auto-generates demo data and builds the RAG index on first boot
# (see deploy/backend-entrypoint.sh), so this script's only real job is
# the one step that can't be automated: picking a backend + a key.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

ENV_FILE=.env

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
step()  { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }

# set_env_var NAME VALUE — replace an existing "NAME=" line in $ENV_FILE,
# or append one if it isn't there yet. Re-running setup.sh is safe.
set_env_var() {
    local name="$1" value="$2"
    if grep -q "^${name}=" "$ENV_FILE" 2>/dev/null; then
        # | delimiter: avoids clashing with /-heavy URL values.
        sed -i.bak "s|^${name}=.*|${name}=${value}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
    else
        printf '%s=%s\n' "$name" "$value" >> "$ENV_FILE"
    fi
}

prompt() {
    # `read`'s EOF failure doesn't reliably trip `set -e` inside a $(...)
    # substitution (a well-known bash gotcha) — `|| reply=""` makes the
    # EOF case explicit instead of leaving $reply whatever it last was.
    local msg="$1" default="${2:-}" reply
    if [ -n "$default" ]; then
        read -r -p "$msg [$default]: " reply || reply=""
        echo "${reply:-$default}"
    else
        read -r -p "$msg: " reply || reply=""
        echo "$reply"
    fi
}

prompt_secret() {
    local msg="$1" reply
    read -r -s -p "$msg: " reply || reply=""
    echo "" >&2
    echo "$reply"
}

# prompt_azure_url DEPLOYMENT_NAME SUFFIX — returns a full Azure OpenAI URL.
# Defaults to building it from just a resource name (what Azure's portal
# actually shows you — endpoint + deployment, separately); offers pasting a
# full URL instead for anything non-standard (Gov cloud, a pinned
# api-version, a private endpoint) that the simple form can't express.
prompt_azure_url() {
    local deployment="$1" suffix="$2" full resource
    full=$(prompt "  Paste a full endpoint URL instead? (y/N)" "N")
    if [[ "$full" =~ ^[Yy] ]]; then
        prompt "  Full URL"
    else
        resource=$(prompt "  Azure resource name (the <x> in https://<x>.openai.azure.com)")
        # Catches pasting a full URL here by mistake -- the line below wraps
        # it in ANOTHER https://...azure.com/..., producing a doubled,
        # unreachable URL that only ever surfaces later as a cryptic
        # "Connection error" in chat, with nothing pointing back at this step.
        if [[ "$resource" == *":"* || "$resource" == *"/"* ]]; then
            echo "  WARNING: that looks like a full URL, not just the resource" >&2
            echo "  name (the bare <x> in https://<x>.openai.azure.com -- no" >&2
            echo "  https://, dots, or slashes). This will likely produce a" >&2
            echo "  broken URL -- re-run and answer 'y' to paste the full URL" >&2
            echo "  instead if that's what you meant." >&2
        fi
        echo "https://${resource}.openai.azure.com/openai/deployments/${deployment}${suffix}?api-version=2025-01-01-preview"
    fi
}

# configure_azure_model PREFIX URL_SUFFIX KEY_PROMPT_SUFFIX — prompts for an
# Azure deployment + URL (resource name or full) + key, sets PREFIX__* vars.
configure_azure_model() {
    local prefix="$1" suffix="$2" key_note="$3" name url key
    set_env_var "${prefix}__TYPE" openai
    name=$(prompt "  Deployment name" "gpt-4o")
    set_env_var "${prefix}__NAME" "$name"
    url=$(prompt_azure_url "$name" "$suffix")
    set_env_var "${prefix}__URL" "$url"
    key=$(prompt_secret "  Azure OpenAI key${key_note}")
    set_env_var "${prefix}__KEY" "$key"
}

# configure_sub_model PREFIX LABEL — Azure or local vLLM/Ollama for one
# sub-agent slot (SMALL_MODEL for RAG+jobpred, or SQL_MODEL for SQL).
configure_sub_model() {
    local prefix="$1" label="$2" sub_type name url
    echo "  -- $label --"
    sub_type=$(prompt "  A) Azure OpenAI   B) Local vLLM/Ollama" "A")
    sub_type=$(echo "$sub_type" | tr '[:lower:]' '[:upper:]')
    if [[ "$sub_type" == B ]]; then
        set_env_var "${prefix}__TYPE" vllm
        name=$(prompt "  Model name" "llama3.1:8b")
        set_env_var "${prefix}__NAME" "$name"
        url=$(prompt "  Server URL" "http://localhost:11434/v1")
        set_env_var "${prefix}__URL" "$url"
    else
        configure_azure_model "$prefix" "/chat/completions" ""
    fi
}

bold "HERALD setup"
echo "This writes .env for you — answer a few questions, then it starts the app."

if [ -f "$ENV_FILE" ]; then
    echo ""
    echo "$ENV_FILE already exists."
    overwrite=$(prompt "Reconfigure it? (y/N)" "N")
    if [[ ! "$overwrite" =~ ^[Yy] ]]; then
        step "Keeping existing $ENV_FILE — skipping to start"
        SKIP_CONFIG=1
    fi
fi

if [ -z "${SKIP_CONFIG:-}" ]; then
    : > "$ENV_FILE"

    step "Orchestrator model (the one you chat with)"
    echo "  A) Anthropic Claude   — simplest, no GPU, needs an Anthropic API key"
    echo "  B) Azure OpenAI       — needs a resource (or full URL) + deployment + key"
    echo "  C) Local Ollama       — free, needs Ollama running locally"
    echo "  D) Self-hosted vLLM   — needs a running vLLM server (see agent_orchestration_deployments/)"
    choice=$(prompt "Choice (A/B/C/D)" "A")
    choice=$(echo "$choice" | tr '[:lower:]' '[:upper:]')

    case "$choice" in
        A)
            set_env_var LARGE_MODEL__TYPE anthropic
            set_env_var LARGE_MODEL__NAME claude-opus-4-7
            key=$(prompt_secret "Anthropic API key")
            set_env_var LARGE_MODEL__KEY "$key"
            ;;
        B)
            configure_azure_model LARGE_MODEL "" ""
            ;;
        C)
            set_env_var LARGE_MODEL__TYPE vllm
            name=$(prompt "Ollama model tag" "llama3.1:8b")
            set_env_var LARGE_MODEL__NAME "$name"
            set_env_var LARGE_MODEL__URL "http://localhost:11434/v1"
            echo "  Make sure you've run: ollama pull $name"
            ;;
        D)
            set_env_var LARGE_MODEL__TYPE vllm
            name=$(prompt "Served model name" "Hermes-4-70B")
            set_env_var LARGE_MODEL__NAME "$name"
            url=$(prompt "vLLM server URL" "http://localhost:8082/v1")
            set_env_var LARGE_MODEL__URL "$url"
            ;;
        *)
            echo "Unrecognized choice '$choice' — defaulting to Anthropic."
            set_env_var LARGE_MODEL__TYPE anthropic
            set_env_var LARGE_MODEL__NAME claude-opus-4-7
            key=$(prompt_secret "Anthropic API key")
            set_env_var LARGE_MODEL__KEY "$key"
            ;;
    esac

    step "SQL / RAG / job-prediction sub-agents"
    echo "  These need a separate OpenAI-compatible endpoint (Azure or vLLM) —"
    echo "  Anthropic only covers the orchestrator above."
    sub=$(prompt "Configure now? (y/N)" "N")

    if [[ "$sub" =~ ^[Yy] ]]; then
        same=$(prompt "Same model for SQL and RAG/job-prediction? (Y/n)" "Y")
        if [[ "$same" =~ ^[Yy] ]]; then
            configure_sub_model SMALL_MODEL "SQL + RAG/job-prediction (shared)"
            # Mirror whatever SMALL_MODEL ended up as onto SQL_MODEL exactly —
            # re-prompting would risk the two drifting apart by accident when
            # the user asked for "same".
            for var in TYPE NAME URL KEY; do
                val=$(grep "^SMALL_MODEL__${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-) || val=""
                [ -n "$val" ] && set_env_var "SQL_MODEL__${var}" "$val"
            done
        else
            configure_sub_model SMALL_MODEL "RAG + job-prediction"
            configure_sub_model SQL_MODEL "SQL"
        fi
        set_env_var ENABLED_TOOLS '["sql", "rag", "jobpred"]'
    else
        echo "  Skipping — disabling sql/rag/jobpred tools so the app doesn't try to use them."
        set_env_var ENABLED_TOOLS '["jobpred"]'
    fi

    # Fixed defaults — no reason to prompt for these.
    set_env_var DB_MODULE src.site.ornl.frontier.db
    set_env_var CUDA_VISIBLE_DEVICES 0
    set_env_var DATA_BASE .data/shared
    set_env_var DATA_PRIV_BASE .data/private
    set_env_var HERALD_API_URL http://localhost:8000

    step "Wrote $ENV_FILE"
fi

step "Starting HERALD"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    echo "Docker found — this single command also generates demo data and"
    echo "builds the RAG index automatically on first boot."
    echo "First boot also downloads a few GB of ML models for documentation"
    echo "search before the server can respond to anything at all -- this"
    echo "step alone can take anywhere from a couple of minutes to ~20"
    echo "minutes, depending on your network. Cached after this, so every"
    echo "boot after the first is fast (seconds, not minutes). You'll see"
    echo "the build/startup logs scroll by below once it starts."
    # Require a real terminal for this specific prompt: piped/exhausted
    # stdin must never silently default into launching a real build.
    if [ -t 0 ]; then
        go=$(prompt "Run 'make docker-up' now? (Y/n)" "Y")
    else
        echo "(non-interactive input — not auto-launching. Run 'make docker-up' yourself when ready.)"
        go="n"
    fi
    if [[ "$go" =~ ^[Yy] ]]; then
        exec make docker-up
    fi
else
    echo "Docker not found/running. Bare-metal path:"
    echo "  make init             # one-time: venv + deps"
    echo "  make generate-data    # synthetic demo data"
    echo "  .venv/bin/python scripts/ingest_rag_corpus.py   # RAG index (optional)"
    echo "  make api              # backend, in one terminal"
    echo "  make frontend-install && make frontend  # frontend, in another"
fi

echo ""
echo "Done. See ONBOARDING.md for the syslog-monitor demo and troubleshooting."
