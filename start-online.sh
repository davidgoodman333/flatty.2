#!/bin/sh
# Starts the online test: the whole site from this Mac, reachable through Tailscale Funnel,
# with Vercel forwarding every request here (vercel/vercel.json). See backend/README.md,
# "Online test through Vercel". Stop with Ctrl+C; the site is offline while this isn't running.
set -e
cd "$(dirname "$0")"

if [ ! -s backend/site_password.txt ] && ! grep -q '^FLATTY_SITE_PASSWORD=.' backend/.env 2>/dev/null; then
  echo "No developer password: put it in backend/site_password.txt before going online." >&2
  exit 1
fi
# The Mac app keeps its command-line tool inside the app unless it was added to the PATH.
if ! command -v tailscale >/dev/null; then
  [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] || { echo "Tailscale isn't installed (see backend/README.md)." >&2; exit 1; }
  tailscale() { /Applications/Tailscale.app/Contents/MacOS/Tailscale "$@"; }
fi
curl -s http://127.0.0.1:11434/api/tags >/dev/null || echo "Warning: Ollama isn't running, so e-mails come from templates."

echo "Building the front-end ..."
npx vite build

echo "Opening port 8000 through Tailscale Funnel ..."
tailscale funnel --bg 8000
trap 'tailscale funnel --https=443 off >/dev/null 2>&1 || true' EXIT INT TERM

echo "Starting Flatty (Ctrl+C to stop) ..."
cd backend
if [ -f .env ]; then
  caffeinate -s .venv/bin/uvicorn app.main:app --port 8000 --env-file .env
else
  caffeinate -s .venv/bin/uvicorn app.main:app --port 8000
fi
