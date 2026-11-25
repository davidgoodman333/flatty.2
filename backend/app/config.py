"""Central settings. Everything can be overridden with environment variables."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FLATTY_DATA_DIR", BACKEND_DIR / "data"))
MODEL_DIR = Path(os.getenv("FLATTY_MODEL_DIR", BACKEND_DIR / "models"))
LABEL_DIR = DATA_DIR / "labels"
DB_PATH = DATA_DIR / "flatty.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
LABEL_DIR.mkdir(parents=True, exist_ok=True)

# The scraper identifies itself honestly. Put a real contact address in FLATTY_CONTACT
# before running it regularly, so site operators can reach the team.
CONTACT = os.getenv("FLATTY_CONTACT", "student project, University of Bern")
USER_AGENT = f"FlattyBot/0.1 (non-commercial student prototype; {CONTACT})"

# Politeness: minimum seconds between two requests to the same host.
MIN_REQUEST_INTERVAL = float(os.getenv("FLATTY_MIN_INTERVAL", "2.0"))
# Hard cap on requests per scraper run and host.
MAX_REQUESTS_PER_RUN = int(os.getenv("FLATTY_MAX_REQUESTS", "40"))
# Listings not seen again for this many days are deleted (data minimisation). Listings that
# disappear from a source are hidden right away; this only controls when the row is erased.
RETENTION_DAYS = int(os.getenv("FLATTY_RETENTION_DAYS", "14"))

# Automatic refresh while the API runs: every REFRESH_HOURS; after a failed or partial run,
# try again after RETRY_HOURS. Set FLATTY_AUTO_REFRESH=0 to turn it off.
AUTO_REFRESH = os.getenv("FLATTY_AUTO_REFRESH", "1") != "0"
REFRESH_HOURS = float(os.getenv("FLATTY_REFRESH_HOURS", "24"))
RETRY_HOURS = float(os.getenv("FLATTY_RETRY_HOURS", "3"))
# A listing a student opens is re-checked at its source at most once per this many minutes.
RECHECK_MINUTES = float(os.getenv("FLATTY_RECHECK_MINUTES", "60"))

# Local LLM through Ollama (runs on this machine, no external API).
OLLAMA_URL = os.getenv("FLATTY_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("FLATTY_OLLAMA_MODEL", "qwen3:8b")

# Accounts. A private test starts as soon as one of these two is set: then only invited people
# can create an account, and listings, link checks and e-mail drafts need a log-in.
#   FLATTY_ALLOWED_EMAILS  comma-separated e-mail addresses that may create an account and log in
#   FLATTY_INVITE_CODE     a code that must be entered when creating an account
ALLOWED_EMAILS = {item.strip().lower() for item in os.getenv("FLATTY_ALLOWED_EMAILS", "").split(",") if item.strip()}
INVITE_CODE = os.getenv("FLATTY_INVITE_CODE", "").strip()
# Online test: cookies only travel over https. Set when the site is reached through a tunnel
# that doesn't tell Flatty the visitor used https (then it can't detect it by itself).
SECURE_COOKIES = os.getenv("FLATTY_SECURE_COOKIES", "0") == "1"
PRIVATE = bool(ALLOWED_EMAILS or INVITE_CODE)
SESSION_DAYS = int(os.getenv("FLATTY_SESSION_DAYS", "30"))

# The built front-end (`pnpm build` writes dist/). When it exists, the API serves it too, so
# one process on one port is the whole website.
STATIC_DIR = Path(os.getenv("FLATTY_STATIC_DIR", BACKEND_DIR.parent / "dist"))

# Search area: City of Bern plus the closest suburbs (west, south, east, north).
BERN_BBOX = (7.37, 46.91, 7.51, 46.99)
