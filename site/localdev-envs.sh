#!/bin/bash
# This script is used to setup a local development environment

echo ""
echo "Localdev environment setup teardown"
echo ""
ROOT_DIR=$(cd $(dirname $(dirname $0)) && pwd)
APP_NAME=$(basename ${ROOT_DIR})
SITE_PROFILE=localdev
echo ${ROOT_DIR}
if [ $# -lt 1 ]; then
	echo "Usage: $(basename $0) <setup|teardown>"
	exit 1
fi
CMD=$1

#
# Environment variables for generic localhost development
#
# Passed to the .env file for the application
#

# A posix based local path used for local storage
SCRATCH_BASE=$(pwd)/.scratch
SHARED_BASE=$(pwd)/.shared
DEFAULT_PREFIX=$(pwd)/.data

# Object storage location (posix in this case)
DATA_BASE=${DEFAULT_PREFIX}/shared
DATA_PRIV_BASE=${DEFAULT_PREFIX}/private

# Compilation of the final .env file.
#
# NOTE: secrets are placeholders — fill in real keys AFTER running 'make env'.
# Re-running 'make env' regenerates this file and overwrites your edits, so keep
# real keys out of version control (.env is gitignored).
DOTENV_PAYLOAD="
# Site profile
SITE_PROFILE=${SITE_PROFILE}

# Application information
APP_NAME=${APP_NAME}
# BASE_PATH=\"\"

# ────────────────────────────────────────────────────────────────────────────
# TWO-TIER MODEL SETUP (recommended): a reasoning model orchestrates; fast
# non-reasoning models do the worker tasks (text-to-SQL, RAG synthesis, ingest).
# Measured ~2.6x faster end-to-end vs all-reasoning, keeping planning quality.
#
# Large model — the agent orchestrator (PydanticAI). Pick ONE backend.
# ────────────────────────────────────────────────────────────────────────────
LARGE_MODEL__TYPE=openai
LARGE_MODEL__NAME=gpt-5.5-2      # reasoning model for planning/tool-routing
# reasoning_effort with function tools needs the Responses API; the builder
# auto-routes to /v1/responses when reasoning_effort is set (needs api-version
# >= 2025-03-01-preview, hence the bump below).
LARGE_MODEL__EXTRA_ARGS={\"reasoning_effort\": \"low\", \"verbosity\": \"low\"}
LARGE_MODEL__URL=https://<your-resource>.openai.azure.com/openai/deployments/gpt-5.5-2/chat/completions?api-version=2025-04-01-preview
LARGE_MODEL__KEY=<your-azure-openai-key>
# --- Local, no external API: serve via vLLM / Ollama (OpenAI-compatible) ---
# LARGE_MODEL__TYPE=vllm
# LARGE_MODEL__NAME=llama-3.1-8b-instruct
# LARGE_MODEL__URL=http://localhost:8000/v1
# LARGE_MODEL__KEY=local
# --- Anthropic Claude ---
# LARGE_MODEL__TYPE=anthropic
# LARGE_MODEL__NAME=claude-opus-4-7
# LARGE_MODEL__KEY=<your-anthropic-key>

# ────────────────────────────────────────────────────────────────────────────
# Small model — RAG + jobpred sub-agents (ingest table descriptions + answers)
# ────────────────────────────────────────────────────────────────────────────
SMALL_MODEL__TYPE=openai
SMALL_MODEL__NAME=gpt-chat-latest-3      # fast non-reasoning chat model (~3-4x faster)
SMALL_MODEL__URL=https://<your-resource>.openai.azure.com/openai/deployments/gpt-chat-latest-3/chat/completions?api-version=2025-04-01-preview
SMALL_MODEL__KEY=<your-azure-openai-key>
# Leave EXTRA_ARGS unset: gpt-5.x rejects custom temperature/top_p, and the fast
# chat model needs no tuning. For a local model that accepts them:
# SMALL_MODEL__EXTRA_ARGS={\"temperature\": 0.1, \"top_p\": 0.9}
# --- API-free RAG: point at a local OpenAI-compatible server (e.g. Ollama) ---
# SMALL_MODEL__TYPE=vllm
# SMALL_MODEL__NAME=llama3.1:8b
# SMALL_MODEL__URL=http://localhost:11434/v1
# SMALL_MODEL__KEY=local
# SMALL_MODEL__EXTRA_ARGS={\"temperature\": 0.1, \"top_p\": 0.9}

# ────────────────────────────────────────────────────────────────────────────
# SQL model — the SQL sub-agent (text-to-SQL)
# ────────────────────────────────────────────────────────────────────────────
SQL_MODEL__TYPE=openai
SQL_MODEL__NAME=gpt-chat-latest-3   # fast non-reasoning chat model for text-to-SQL
SQL_MODEL__URL=https://<your-resource>.openai.azure.com/openai/deployments/gpt-chat-latest-3/chat/completions?api-version=2025-04-01-preview
SQL_MODEL__KEY=<your-azure-openai-key>
# If text-to-SQL accuracy drops on complex queries, switch back to a reasoning
# deployment (e.g. gpt-5.5-2).

# ────────────────────────────────────────────────────────────────────────────
# Tool enable/disable — remove a name to disable that sub-agent globally
# ────────────────────────────────────────────────────────────────────────────
ENABLED_TOOLS=[\"sql\", \"rag\", \"jobpred\", \"syslog\"]

# ────────────────────────────────────────────────────────────────────────────
# Database / data paths / GPUs
# ────────────────────────────────────────────────────────────────────────────
DB_MODULE=src.site.ornl.frontier.db
SCRATCH_BASE=${SCRATCH_BASE}
SHARED_BASE=${SHARED_BASE}
DATA_BASE=${DATA_BASE}
DATA_PRIV_BASE=${DATA_PRIV_BASE}
CUDA_VISIBLE_DEVICES=0

# ────────────────────────────────────────────────────────────────────────────
# Frontend → backend (used by frontend/next.config.ts during 'npm run dev')
# ────────────────────────────────────────────────────────────────────────────
HERALD_API_URL=http://localhost:8000

# ────────────────────────────────────────────────────────────────────────────
# RAG: base dir for resolving relative image paths in the docs image collection
# (repo-relative; resolved against the project root). Bundled diagrams live
# under src/rag/rag_assets/images.
# ────────────────────────────────────────────────────────────────────────────
RAG_IMAGE_BASE_DIR=src/rag/rag_assets
"

#
# Main script
#

case ${CMD} in
setup)
	# Setup environment variables via dotenv
	touch ${ROOT_DIR}/.env
	chmod 600 ${ROOT_DIR}/.env
	echo "${DOTENV_PAYLOAD}" > ${ROOT_DIR}/.env

	echo "@ credential setup success"
	;;
teardown)
	echo "@ removing local credentials"
	# Remove environment variables
	rm ${ROOT_DIR}/.env

	echo "@ logout success"
	;;
esac
echo ""
exit 0