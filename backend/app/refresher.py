"""Keeps the listings fresh while the API is running.

A background thread checks every 15 minutes whether a scraper run is due:
  - no complete run of every enabled source within REFRESH_HOURS (default 24), or
  - the last attempt failed or was partial and RETRY_HOURS (default 3) have passed.
It never runs two scrapes at once, and /api/scrape uses the same lock.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone

from . import db
from .config import AUTO_REFRESH, REFRESH_HOURS, RETRY_HOURS
from .scraper.run import COLLECTORS
from .scraper.run import run as run_scraper
from .scraper.sources import SOURCES

log = logging.getLogger("flatty.refresher")
CHECK_EVERY_SECONDS = 15 * 60
STARTUP_DELAY_SECONDS = 10

_lock = threading.Lock()
_stop = threading.Event()
state = {"running": False, "last_result": None, "started_at": None}


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def enabled_sources() -> list[str]:
    return [source.key for source in SOURCES if source.scraping_allowed and source.key in COLLECTORS]


def freshness() -> dict:
    """When each enabled source last completed, the oldest of those, and when the next run is due."""
    with db.connect() as conn:
        successful = db.last_successful_runs(conn)
        attempts = db.last_attempts(conn)
    keys = enabled_sources()
    sources = {key: successful.get(key) for key in keys}
    oldest = None if None in sources.values() else min(_parse(v) for v in sources.values())
    due = datetime.now(timezone.utc) if oldest is None else oldest + timedelta(hours=REFRESH_HOURS)
    # A source whose last attempt failed or was partial is retried after RETRY_HOURS, not sooner.
    failed = [
        _parse(attempts[k]["started"]) for k in keys
        if k in attempts and attempts[k]["status"] not in ("ok", "interrupted", "running")
    ]
    if failed:
        due = max(due, max(failed) + timedelta(hours=RETRY_HOURS))
    # Sources to include in the next run: never completed, or completed too long ago.
    stale_before = datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOURS)
    due_sources = [k for k in keys if not sources[k] or _parse(sources[k]) <= stale_before]
    return {
        "sources": sources,
        "updatedAt": oldest.isoformat() if oldest else None,
        "nextRefresh": due.isoformat() if AUTO_REFRESH else None,
        "dueSources": due_sources,
        "refreshing": state["running"],
        "autoRefresh": AUTO_REFRESH,
    }


def run_now(sources: list[str] | None = None) -> bool:
    """Run the scraper (all sources, or only `sources`) unless one is already running.
    Returns False if it was busy."""
    if not _lock.acquire(blocking=False):
        return False
    state.update(running=True, started_at=datetime.now(timezone.utc).isoformat())
    try:
        state["last_result"] = run_scraper(only=sources)
        log.info("refresh finished: %s", state["last_result"])
    except Exception:  # keep the thread alive; the next check will retry
        log.exception("refresh failed")
    finally:
        state["running"] = False
        _lock.release()
    return True


def start_in_background() -> None:
    threading.Thread(target=run_now, daemon=True).start()


def _loop() -> None:
    if _stop.wait(STARTUP_DELAY_SECONDS):
        return
    while not _stop.is_set():
        try:
            fresh = freshness()
            if fresh["dueSources"] and datetime.fromisoformat(fresh["nextRefresh"]) <= datetime.now(timezone.utc):
                run_now(fresh["dueSources"])
        except Exception:
            log.exception("refresh check failed")
        _stop.wait(CHECK_EVERY_SECONDS)


def start() -> None:
    with db.connect() as conn:
        db.mark_interrupted(conn)  # an interrupted run is retried right away, not after RETRY_HOURS
    if AUTO_REFRESH:
        _stop.clear()
        threading.Thread(target=_loop, name="flatty-refresher", daemon=True).start()


def stop() -> None:
    _stop.set()
