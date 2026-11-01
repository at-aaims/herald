#
# Description: Makefile for the dev lifecycle of the herald-app project
#

APPNAME := herald
VENV := .venv
SYS_PY := python3.12
PY := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip3
REQUIREMENTS := requirements.txt
DOCKER_BINARY := docker
DOTENV := .env
JUPYTER_HOST := 127.0.0.1
JUPYTER_PORT := 8888
JUPYTER_NBDIR := nb
SH := bash
SHELL := bash
SITE_PROFILE ?= localdev
ENVS_SCRIPT := $(SITE_PROFILE)-envs.sh

help:
	-@echo ""
	-@echo "Usage: make <target>"
	-@echo ""
	-@echo "[development environment]"
	-@echo "  init / fini:       create / destroy local dev environment"
	-@echo "  api:               Run FastAPI backend on http://localhost:8000"
	-@echo "  frontend:          Run Next.js dev server on http://localhost:3000"
	-@echo "  frontend-install:  One-time: install Next.js frontend dependencies"
	-@echo "  shell:             Jump into a shell with the virtual environment activated"
	-@echo "  ipython:           Jump into a python shell"
	-@echo "  jupyter:           Start a local jupyter lab server"
	-@echo ""
	-@echo "[Environment setup]"
	-@echo "  env / env-fini: fetch remote credentials from ./site/***"
	-@echo "  generate-data: generate synthetic data for the repository"
	-@echo "  fetch-models: prefetch models to local cache from Hugging Face"
	-@echo ""
	-@echo "[development cycle]"
	-@echo "  test: Run unit tests"
	-@echo "  integration-test: Run integration tests"
	-@echo "  pipeline-test: Run tests for the pipelines"
	-@echo "  test-all: Run all tests"
	-@echo ""
	-@echo "[docker]"
	-@echo "  up / docker-up:       Run HERALD (backend + frontend) fully containerized"
	-@echo "  down / docker-down:   Stop the containerized backend + frontend"
	-@echo "  clickhouse-up:        Start only the local ClickHouse dev sandbox (bare-metal dev)"
	-@echo "  clickhouse-down:      Stop the ClickHouse dev sandbox"
	-@echo ""

.PHONY: help all freeze init fini
all: help

#
# Virtual environment management
#
# Fulfills the requirements from the requirements.lock.txt file but falls
# back to the requirements.txt file if the lock file does not exist.
#
# The requirements.lock.txt file is updated with the freeze target and can be
# updated by erasing the requirements.lock.txt file first, run `make fini` and then running
# `make init` again.
#
init:
	@echo "Initializing..."
	@echo "Creating virtual environment..."
	@$(SYS_PY) -m venv $(VENV)
	@echo "Activating virtual environment..."
	@. $(VENV)/bin/activate
	@echo "Installing requirements..."
	@$(PIP) install -U pip && $(PIP) install -r $(REQUIREMENTS)
	@$(PY) -m ipykernel install --user --name=$(APPNAME)
	@$(PIP) install -e .
	@mkdir -p ./.metaflow
	@echo "Installing node (for the Next.js frontend)"
	@curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
	@source ~/.nvm/nvm.sh && nvm install v20
	@source ~/.nvm/nvm.sh && nvm use v20 && cd frontend && npm install
	@echo "Initialization complete."

fini:
	@echo "Removing virtual environment..."
	-@$(VENV)/bin/jupyter kernelspec remove $(APPNAME)
	-@rm -rf $(VENV)
	@echo "Finalization complete."


.PHONY: env env-fini
env:
	@echo "Setting up environment (.env) using site profile $(SITE_PROFILE)"
	@source $(VENV)/bin/activate && ./site/$(ENVS_SCRIPT) setup
	@rm -rf ./site/_current.sh && ln -s $(ENVS_SCRIPT) ./site/_current.sh

env-fini:
	@echo "Tearing down environment (.env)"
	@if test -e ./site/_current.sh ; then source $(VENV)/bin/activate && ./site/_current.sh teardown ; fi
	@rm -rf ./site/_current.sh


.PHONY: build push
build:
	@echo "Building using docker using the $(DOTENV) environment file"
	@source $(DOTENV) && $(DOCKER_BINARY) build -t $${REGISTRY}/$${APPIMAGE}:${APPTAG} .

push:
	@echo "Pushng the image using the $(DOTENV) environment file"
	@source $(DOTENV) && $(DOCKER_BINARY) push -t $${REGISTRY}/$${APPIMAGE}:${APPTAG}

.PHONY: generate-data fetch-data fetch-models
generate-data:
	@echo "Generating synthetic data (last 3 months through today)"
	mkdir -p .data
	./scripts/generate_frontier_job_data.py --out .data/private/ornl/frontier/jobsummary

fetch-data:
	mkdir -p .data/shared/riken/fugaku
	curl https://zenodo.org/api/records/11467483/files-archive -o .data/shared/riken/fugaku/fugaku.zip
	unzip .data/shared/riken/fugaku/fugaku.zip -d .data/shared/riken/fugaku
	rm .data/shared/riken/fugaku/fugaku.zip

fetch-models:
	@echo ""
	@echo "Fetching Hugging Face Models (pre-download)"
	@echo ""
	@echo "- SQL model"
	$(VENV)/bin/huggingface-cli download defog/llama-3-sqlcoder-8b
	@echo ""
	@echo "- General Purpose Instruct model - Llama3.1-8B"
	$(VENV)/bin/huggingface-cli download meta-llama/Meta-Llama-3.1-8B-Instruct
	@echo ""
	@echo "- General Purpose Instruct model - Llama3.2-3B"
	$(VENV)/bin/huggingface-cli download meta-llama/Llama-3.2-3B-Instruct
	@echo ""
	@echo "- RAG Embedding model"
	$(VENV)/bin/huggingface-cli download mixedbread-ai/mxbai-embed-large-v1
	@echo ""
	@echo "- RAG Reranker model"
	$(VENV)/bin/huggingface-cli download mixedbread-ai/mxbai-rerank-large-v1


.PHONY: api frontend frontend-install shell ipython up down jupyter
# FastAPI + PydanticAI agent (replaces the legacy Chainlit Python loop)
api:
	@echo "Starting FastAPI backend on http://localhost:8000"
	@if [ -f $(DOTENV) ]; then set -a && source $(DOTENV) && set +a; fi; \
		source $(VENV)/bin/activate && uvicorn src.server.api:app --reload --port 8000

# New stack: Next.js frontend (replaces Chainlit UI)
# Run `make frontend-install` once before this.
frontend:
	@echo "Starting Next.js frontend on http://localhost:3000"
	@if [ -f $(DOTENV) ]; then set -a && source $(DOTENV) && set +a; fi; \
		source ~/.nvm/nvm.sh && nvm use v20 && cd frontend && npm run dev

frontend-install:
	@echo "Installing Next.js frontend dependencies"
	@source ~/.nvm/nvm.sh && nvm use v20 && cd frontend && npm install


shell:
	@echo "Jumping into shell"
	@source $(VENV)/bin/activate && $(SH)

ipython:
	@echo "Jumping into an ipython shell"
	@source $(VENV)/bin/activate && ipython

.PHONY: clickhouse-up clickhouse-down
clickhouse-up:
	@echo "Starting local ClickHouse (P8 syslog scaling dev sandbox)"
	@docker compose -f deploy/docker-compose.yml up -d clickhouse
	@echo "ClickHouse HTTP at http://localhost:8123 — see src/syslog/README.md to switch SYSLOG_STORE_BACKEND"

clickhouse-down:
	@echo "Stopping local ClickHouse (data volume kept — use 'docker compose -f deploy/docker-compose.yml down -v' to wipe it)"
	@docker compose -f deploy/docker-compose.yml stop clickhouse

.PHONY: docker-up docker-down
docker-up:
	@touch .env
	@echo "Starting HERALD (backend + frontend) in Docker"
	@docker compose -f deploy/docker-compose.yml up --build backend frontend

docker-down:
	@docker compose -f deploy/docker-compose.yml down

# Short aliases for the common case (documented above in `help`) — `up`/
# `down` were unimplemented stubs before the Docker work landed, so this is
# not a change from any prior working behavior.
up: docker-up

down: docker-down

jupyter:
	@echo "Running the jupyter server"
	@source $(VENV)/bin/activate && jupyter lab --ip $(JUPYTER_HOST) --port $(JUPYTER_PORT) --notebook-dir=$(JUPYTER_NBDIR)


.PHONY: test integration-test pipeline-test test-all
test:
	@$(VENV)/bin/pytest -m unit

integration-test:
	@$(VENV)/bin/pytest -m integration

pipeline-test:
	@$(VENV)/bin/pytest -m pipeline

test-all:
	@$(VENV)/bin/pytest
