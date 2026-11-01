#!/bin/bash
# deploy/backend-entrypoint.sh — one-time setup (idempotent) then exec uvicorn.
#
# Mirrors ONBOARDING.md's manual steps 2 and 3 so a container does them
# automatically on first boot instead of requiring a human to run them.
#
# Uses .done sentinel files, not bare directory existence: `make
# generate-data`/ingest_rag_corpus.py both create their target directory
# before they finish populating it, so a container killed mid-run would
# otherwise leave a partial directory that looks "done" on the next restart
# and never gets retried.
set -euo pipefail
cd /app

# Bind-mounted .data/src/rag/chroma_db can already be fully populated from
# before this sentinel scheme existed (or from a bare-metal setup sharing
# the same checkout) — in that case treat a non-empty target dir as done
# too, not just the sentinel, and backfill it. Without this, a missing
# sentinel over already-real data reruns generation, which isn't
# idempotent (mkdir(parents=True) with no exist_ok) and crashes instead of
# just confirming what's already there.
if [ ! -f ".data/.demo_data.done" ]; then
    if [ -d ".data/private/ornl/frontier/jobsummary" ] && [ -n "$(ls -A .data/private/ornl/frontier/jobsummary 2>/dev/null)" ]; then
        echo "[entrypoint] demo job data already present, backfilling sentinel..."
    else
        echo "[entrypoint] generating demo job data..."
        make generate-data
    fi
    touch ".data/.demo_data.done"
fi

# No sentinel/"non-empty = done" shortcut here, unlike the two blocks above:
# chroma_db is one shared sqlite file for the whole corpus, so a prior run
# interrupted partway through (network blip, SSL error, etc.) leaves it
# non-empty but incomplete -- "non-empty = skip" would silently treat that
# as fully done forever, masking the gap. ingest_rag_corpus.py is idempotent
# per-file (skips filenames already in the manifest), so just running it
# every boot is both correct and cheap once the corpus is actually done.
#
# Deliberately non-fatal: this is the one step in this script that needs the
# network (downloading the embedding model), so it's the one most likely to
# fail on a network that intercepts/blocks HTTPS (corporate TLS-inspecting
# proxy, offline, etc.) -- and a RAG failure has no business taking down
# chat/SQL/syslog/job-prediction too. ingest_rag_corpus.py itself detects a
# connectivity-shaped failure and stops after one clear message instead of
# retrying the same failure 12 times; `if !` (not bare `set -e`) is what lets
# that non-zero exit continue past this step instead of killing the container.
if [ "${SKIP_RAG_INDEX:-}" = "1" ]; then
    echo "[entrypoint] SKIP_RAG_INDEX=1 — skipping RAG documentation index"
elif ! python scripts/ingest_rag_corpus.py; then
    echo ""
    echo "[entrypoint] WARNING: RAG documentation indexing failed (see above)."
    echo "[entrypoint] Continuing without it — chat/SQL/syslog/job-prediction"
    echo "[entrypoint] are unaffected. Set SKIP_RAG_INDEX=1 to skip this step"
    echo "[entrypoint] on future boots once you know it won't succeed here."
    echo ""
fi

# Mirrors ONBOARDING.md's optional step 7 (syslog monitor demo) — without
# these two, the causal walker has no edges and the syslog monitor's
# stream has no source file at all (404 on /api/syslog/stream).
if [ ! -f ".data/.causal_edges.done" ]; then
    if [ -s ".data/causal_edges_placeholder.csv" ]; then
        echo "[entrypoint] causal-edges CSV already present, backfilling sentinel..."
    else
        echo "[entrypoint] generating placeholder causal-edges CSV..."
        python scripts/build_placeholder_causal_edges.py
    fi
    touch ".data/.causal_edges.done"
fi

if [ ! -f ".data/.demo_cascades.done" ]; then
    if [ -s ".data/syslog_demo.jsonl" ]; then
        echo "[entrypoint] syslog demo data already present, backfilling sentinel..."
    else
        echo "[entrypoint] generating syslog demo cascades..."
        python scripts/build_demo_cascades.py
    fi
    touch ".data/.demo_cascades.done"
fi

echo "[entrypoint] starting uvicorn..."
# --reload-dir src: without it, uvicorn watches the ENTIRE bind-mounted
# repo (scripts/, frontend/, deploy/, .data/, ...), so editing anything
# anywhere — not just backend code — triggers a reload. --reload-exclude
# on chroma_db additionally skips the RAG index's own binary writes during
# a rebuild.
#
# --timeout-graceful-shutdown 3: even a legitimate reload (a real src/
# change) still does a graceful shutdown that by default waits FOREVER
# for open connections to close — and a live SSE stream (the syslog
# monitor with loop=on) never closes on its own, so any backend edit made
# while someone has the monitor open hangs the server indefinitely with
# no error, until someone notices and force-restarts the container. 3s is
# enough for a normal in-flight HTTP request to finish; past that, force-
# close rather than wait on a stream that isn't going to end.
exec uvicorn src.server.api:app --host 0.0.0.0 --port 8000 --reload \
    --reload-dir src --reload-exclude 'src/rag/chroma_db/*' \
    --timeout-graceful-shutdown 3
