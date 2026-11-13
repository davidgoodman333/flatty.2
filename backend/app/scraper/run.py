"""Run the scraper once.

    python -m app.scraper.run                     # every enabled source
    python -m app.scraper.run --source unibe      # one source
    python -m app.scraper.run --max-listings 100

Only sources with scraping_allowed=True in sources.py are collected.
"""

import argparse

from .. import db
from ..config import BERN_BBOX
from ..scoring import rescore_all
from . import flatfox, studentlodge, unibe
from .compliance import BudgetExhausted, PoliteClient, ScrapeBlocked
from .sources import SOURCES

MIN_SHARE_SEEN = 0.5  # a run must see at least half of the active listings before hiding the rest
COLLECTORS = {"flatfox": flatfox.collect, "unibe": unibe.collect, "studentlodge": studentlodge.collect}


def run(max_listings: int = 5000, only: str | list[str] | None = None) -> dict:
    only = [only] if isinstance(only, str) else only
    summary = {}
    with db.connect() as conn:
        for source in SOURCES:
            if only and source.key not in only:
                continue
            if not source.scraping_allowed or source.key not in COLLECTORS:
                summary[source.key] = f"skipped: {source.decision}"
                continue
            run_id, started = db.start_run(conn, source.key)
            active_before = db.count_active(conn, source.key)
            saved = 0

            def save(listing: dict) -> None:
                nonlocal saved
                db.upsert_listing(conn, listing)
                saved += 1
                conn.commit()  # never hold the write lock while waiting for the next HTTP response

            with PoliteClient(max_requests=source.max_requests) as client:
                status, message, complete = "ok", "", False
                try:
                    complete = COLLECTORS[source.key](client, BERN_BBOX, max_listings, save)
                except (ScrapeBlocked, BudgetExhausted) as error:
                    status, message = "stopped", str(error)
                except Exception as error:  # network errors etc.: record and continue with other sources
                    status, message = "error", f"{type(error).__name__}: {error}"

                # Hide listings this source no longer shows, but only after a complete run, and not
                # when the run found suspiciously few listings (a site change, not a mass rent-out).
                hidden = 0
                if status == "ok" and not complete:
                    status, message = "partial", "run did not see every listing; nothing hidden"
                elif status == "ok" and saved < MIN_SHARE_SEEN * active_before:
                    status, message = "partial", f"only {saved} of {active_before} listings seen; nothing hidden"
                elif status == "ok":
                    hidden = db.deactivate_missing(conn, source.key, started)
                db.finish_run(conn, run_id, client.requests, saved, status, message)
                conn.commit()
                summary[source.key] = f"{status}: {saved} listings saved, {hidden} no longer online, {client.requests} requests {message}".strip()
        removed = db.delete_stale(conn)
        scored = rescore_all(conn)
        summary["maintenance"] = f"removed {removed} stale listings, scored {scored}"
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-listings", type=int, default=5000)
    parser.add_argument("--source", choices=sorted(COLLECTORS))
    args = parser.parse_args()
    for key, line in run(args.max_listings, args.source).items():
        print(f"{key:16} {line}")


if __name__ == "__main__":
    main()
