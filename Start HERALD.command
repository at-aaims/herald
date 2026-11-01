#!/usr/bin/env bash
# Start HERALD.command — double-click this in Finder. macOS runs .command
# files by opening Terminal and executing them as a shell script; no typing
# required. (First run: macOS Gatekeeper will likely refuse to open it —
# right-click → Open once to approve it, same as any unsigned downloaded
# script. After that, double-click works normally.)
#
# Starts Docker Desktop if it isn't running, builds/starts the stack, waits
# for the backend to actually be ready, then opens your browser straight to
# /setup (first run) or the chat page (already configured) — so the only
# manual step left, ever, is picking a model backend once in the browser.
set -uo pipefail
cd "$(dirname "$0")"

say() { echo ""; echo "==> $1"; }

if ! command -v docker &>/dev/null; then
    # AppleScript string literals don't interpret \n as a newline (needs
    # `return` concatenation instead) — kept to one line to sidestep that
    # entirely rather than risk a dialog showing literal backslash-n's.
    osascript -e 'display dialog "Docker isn'"'"'t installed — install Docker Desktop first, then try again: https://www.docker.com/products/docker-desktop" buttons {"OK"} with icon stop with title "HERALD"'
    exit 1
fi

if ! docker info &>/dev/null; then
    say "Starting Docker Desktop (this can take a minute)..."
    open -a Docker
    until docker info &>/dev/null; do sleep 2; done
fi

touch .env

# Captured before the build/start so the log check below only sees
# warnings from THIS launch, not a stale one from a long-running
# container's past history (e.g. you fixed the cert days ago, but
# docker compose up -d on an unchanged image doesn't necessarily
# recreate the container or clear docker logs' scrollback).
launch_time=$(date -u +%Y-%m-%dT%H:%M:%S)

say "Starting HERALD — first run builds images and can take a few minutes..."
docker compose -f deploy/docker-compose.yml up --build -d backend frontend

say "Waiting for the backend to come up..."
echo "First run also downloads a few GB of ML models for documentation search"
echo "before the server can start at all -- this step alone can take anywhere"
echo "from a couple of minutes to ~20 minutes, depending on your network."
echo "Cached after this, so every run after the first is fast (seconds, not"
echo "minutes). The browser tab that's about to open will show its own"
echo "'still starting up' message in the meantime."
tries=0
until curl -sf http://localhost:8000/api/health >/dev/null 2>&1; do
    sleep 2
    tries=$((tries + 1))
    # Periodic reassurance, not just silence, during a long first-run model
    # download.
    if [ "$tries" -eq 15 ] || [ "$tries" -eq 30 ] || [ "$tries" -eq 60 ] || { [ "$tries" -gt 60 ] && [ "$((tries % 60))" -eq 0 ]; }; then
        echo "... still waiting ($((tries * 2))s elapsed) — still downloading/starting, this is normal on first run."
    fi
    if [ "$tries" -gt 600 ]; then
        echo "Still not up after 20 minutes — check the logs below for what's wrong."
        break
    fi
done

# Surface a RAG-indexing failure (almost always the Netskope-style TLS-proxy
# cert issue — see deploy/README.md) as a popup instead of leaving it
# buried in docker logs where nobody but someone debugging would see it.
# Everything else (chat/SQL/job-prediction/syslog) is unaffected either way
# — backend-entrypoint.sh treats this as non-fatal — so this is informational,
# not a failure the user has to act on before continuing.
rag_warning=$(docker logs --since "$launch_time" herald-backend 2>&1 \
    | grep -c "WARNING: RAG documentation indexing failed") || rag_warning=0
if [ "${rag_warning:-0}" -gt 0 ]; then
    choice=$(osascript -e '
        set dlgResult to display dialog "RAG documentation search did not finish setting up." & return & return & "This is almost always a network/TLS issue — e.g. a corporate proxy that intercepts HTTPS. See deploy/README.md to fix it." & return & return & "Everything else works fine: chat, SQL, job prediction, and syslog are unaffected. Only document search is skipped until this is resolved." buttons {"Skip", "Open Guide"} default button "Skip" with title "HERALD" with icon caution
        return button returned of dlgResult
    ' 2>/dev/null) || choice="Skip"
    [ "$choice" = "Open Guide" ] && open deploy/README.md
fi

if curl -sf http://localhost:8000/api/setup/status 2>/dev/null | grep -q '"configured":true'; then
    open "http://localhost:3000"
else
    open "http://localhost:3000/setup"
fi

say "HERALD is running. Logs below — closing this window does NOT stop it."
say "To stop HERALD: docker compose -f deploy/docker-compose.yml down"
docker compose -f deploy/docker-compose.yml logs -f backend frontend
