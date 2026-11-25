#!/bin/sh
# Starts the online test (see backend/README.md, "Online test through Vercel").
#
# The online site runs the code from GitHub (main), not this folder: a separate copy in
# ~/flatty-online is used only for it. Every 3 minutes it checks GitHub; when anyone on the team
# has pushed to main, it pulls, rebuilds and restarts by itself. If the new version doesn't
# build or start, the previous one keeps running. Half-finished edits here never go online.
#
# Data stays on this Mac and is shared with this folder: the database and models in
# backend/data and backend/models, and the password in backend/site_password.txt.
#
# Vercel forwards everything to this Mac through Tailscale Funnel (port 8100). Ctrl+C stops it.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
ONLINE="${FLATTY_ONLINE_DIR:-$HOME/flatty-online}"
BRANCH=main
PORT=8100
CHECK_SECONDS=180
LOG="$ONLINE.log"

export FLATTY_DATA_DIR="$HERE/backend/data"
export FLATTY_MODEL_DIR="$HERE/backend/models"
export FLATTY_SITE_PASSWORD_FILE="$HERE/backend/site_password.txt"
export FLATTY_STATIC_DIR="$ONLINE/dist"

say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
fail() { say "$*"; exit 1; }

[ -s "$FLATTY_SITE_PASSWORD_FILE" ] || fail "No developer password: put it in backend/site_password.txt first."

# The Mac app keeps its command-line tool inside the app unless it was added to the PATH.
if ! command -v tailscale >/dev/null; then
  [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] || fail "Tailscale isn't installed (see backend/README.md)."
  tailscale() { /Applications/Tailscale.app/Contents/MacOS/Tailscale "$@"; }
fi

# Ollama: several requests at once (the team testing in parallel), model kept loaded all day.
# launchctl settings are lost at restart, so set them each time and restart Ollama if needed.
launchctl setenv OLLAMA_NUM_PARALLEL 4
launchctl setenv OLLAMA_KEEP_ALIVE 24h
if ! ps -ax -o command | grep -q "llama-server.*-np 4" && [ -d /Applications/Ollama.app ]; then
  say "Restarting Ollama with 4 parallel requests ..."
  pkill -f "/Applications/Ollama.app/Contents/MacOS/Ollama" 2>/dev/null || true
  pkill -f "ollama serve" 2>/dev/null || true
  sleep 2
  open -a Ollama
  sleep 5
fi
curl -s http://127.0.0.1:11434/api/tags >/dev/null || say "Warning: Ollama isn't running, so e-mails come from templates."

# --- The online copy -----------------------------------------------------------------
if [ ! -d "$ONLINE/.git" ]; then
  say "Cloning $BRANCH into $ONLINE ..."
  git clone -q --branch "$BRANCH" "$(git -C "$HERE" remote get-url origin)" "$ONLINE" || fail "Couldn't clone the repository."
fi
cd "$ONLINE" || fail "Can't open $ONLINE"

install_deps() {
  say "Installing dependencies ..."
  [ -x backend/.venv/bin/python ] || "$HERE/backend/.venv/bin/python3" -m venv backend/.venv || return 1
  backend/.venv/bin/pip install -q -r backend/requirements.txt || return 1
  npx -y pnpm@10.34.3 install --frozen-lockfile --silent || return 1
}

build() {  # into dist.new first, so a failed build never touches the running version
  rm -rf dist.new
  npx vite build --outDir dist.new >/dev/null 2>>"$LOG" || return 1
  rm -rf dist.old
  [ -d dist ] && mv dist dist.old
  mv dist.new dist
}

SERVER=""
start_server() {
  (cd backend && exec .venv/bin/uvicorn app.main:app --port "$PORT" --log-level warning >>"$LOG" 2>&1) &
  SERVER=$!
  for _ in $(seq 1 60); do  # healthy = it answers (401 = the password page)
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/__gate")
    [ "$code" = "401" ] || [ "$code" = "200" ] && return 0
    kill -0 "$SERVER" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}
stop_server() { [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null && wait "$SERVER" 2>/dev/null; SERVER=""; }

cleanup() {
  stop_server
  tailscale funnel --https=443 off >/dev/null 2>&1 || true
  say "Stopped. The site is offline."
  exit 0
}
trap cleanup INT TERM

git fetch -q origin "$BRANCH" && git reset -q --hard "origin/$BRANCH"
if [ ! -x backend/.venv/bin/uvicorn ] || [ ! -d node_modules ]; then install_deps || fail "Installing dependencies failed (see $LOG)."; fi
build || fail "The front-end doesn't build (see $LOG)."
start_server || fail "Flatty didn't start (see $LOG)."
say "Online with $(git log -1 --format='%h %s')"

tailscale funnel --https=443 off >/dev/null 2>&1 || true
tailscale funnel --bg "$PORT" >/dev/null || fail "Couldn't open Tailscale Funnel."
caffeinate -s -w $$ &   # keep the Mac awake while this runs
say "Reachable through Vercel. Checking GitHub every $((CHECK_SECONDS / 60)) minutes. Ctrl+C stops it."

# --- Follow GitHub ---------------------------------------------------------------------
SKIP=""  # a commit that failed, so it isn't retried every few minutes
while :; do
  sleep "$CHECK_SECONDS" &
  wait $!
  git fetch -q origin "$BRANCH" 2>>"$LOG" || continue
  OLD=$(git rev-parse HEAD)
  NEW=$(git rev-parse "origin/$BRANCH")
  [ "$OLD" = "$NEW" ] || [ "$NEW" = "$SKIP" ] && continue

  say "New on GitHub: $(git log -1 --format='%h %s' "$NEW"). Updating ..."
  git reset -q --hard "$NEW"
  if git diff --name-only "$OLD" "$NEW" | grep -qE '(^|/)(requirements\.txt|package\.json|pnpm-lock\.yaml)$'; then
    install_deps || { say "Dependencies failed; staying on $(git log -1 --format=%h "$OLD")."; git reset -q --hard "$OLD"; SKIP=$NEW; continue; }
  fi
  if ! build; then
    say "Build failed; staying on $(git log -1 --format=%h "$OLD")."
    git reset -q --hard "$OLD"; SKIP=$NEW; continue
  fi
  stop_server
  if start_server; then
    say "Updated to $(git log -1 --format='%h %s')"
  else
    say "New version didn't start; going back to $(git log -1 --format=%h "$OLD")."
    stop_server
    git reset -q --hard "$OLD"; SKIP=$NEW
    build && start_server || say "The previous version didn't start either. Check $LOG."
  fi
done
