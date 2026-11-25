"""Background jobs for the local LLM: reading who the landlord is looking for, and English titles.

A search must never wait for the LLM: one listing takes a few seconds and there are hundreds.
So this worker goes through the listings one at a time and stores the results:

1. wishes (app/wishes.py): language, gender, age, occupation and smoking wishes in the text.
   They change the reply likelihood, so they come first. Listings without a sentence on these
   topics are done instantly, without an LLM call. Stored wishes of an older WISHES version
   are read again.
2. English titles. Lists show the glossary translation until the worker reaches a listing
   (matching.card).

One request at a time, and none while someone is waiting for an e-mail, a summary or a
translation (llm.for_a_person), so the team's requests get the full speed.
FLATTY_LLM_WORKER=0 turns it off (FLATTY_TRANSLATE_TITLES=0, the old name, still works).
"""

import os
import threading

from . import db, llm, wishes

ENABLED = os.getenv("FLATTY_LLM_WORKER", os.getenv("FLATTY_TRANSLATE_TITLES", "1")) != "0"
IDLE_SECONDS = 60  # wait this long when nothing is left to do or Ollama isn't running
BATCH = 20

_stop = threading.Event()
_thread: threading.Thread | None = None
state = {"wishes_pending": None}


def _pending_wishes() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM listings WHERE active=1 AND (wishes_version IS NULL OR wishes_version != ?) LIMIT ?",
            (wishes.VERSION, BATCH),
        ).fetchall()
        state["wishes_pending"] = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE active=1 AND (wishes_version IS NULL OR wishes_version != ?)",
            (wishes.VERSION,),
        ).fetchone()[0]
    return [db.row_to_listing(row) for row in rows]


def _pending_titles() -> list[tuple[str, str]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, title FROM listings WHERE active=1 AND title_en IS NULL AND TRIM(COALESCE(title, '')) != '' LIMIT ?",
            (BATCH,),
        ).fetchall()
    return [(row["id"], row["title"]) for row in rows]


def _wishes_batch() -> int:
    """Read the wishes of up to BATCH listings. Returns how many were done (0: nothing to do or no LLM)."""
    done = 0
    for listing in _pending_wishes():
        llm.wait_for_people(_stop)  # someone is waiting for an e-mail or a summary: let them go first
        if _stop.is_set():
            break
        found = wishes.extract(listing)
        if found is None:  # Ollama stopped answering: try again later
            break
        with db.connect() as conn:
            db.update_wishes(conn, listing["id"], found, wishes.VERSION)
        done += 1
    return done


def _titles_batch() -> int:
    done = 0
    for listing_id, title in _pending_titles():
        llm.wait_for_people(_stop)
        if _stop.is_set():
            break
        translated = llm.best_title(title)
        if translated is None:
            break
        with db.connect() as conn:
            db.update_title_en(conn, listing_id, translated)
        done += 1
    return done


def _run() -> None:
    while not _stop.is_set():
        done = 0
        try:
            if llm.available():
                done = _wishes_batch() or _titles_batch()
        except Exception:  # never let a database or network hiccup end the worker
            done = 0
        if not done:
            _stop.wait(IDLE_SECONDS)


def start() -> None:
    global _thread
    if not ENABLED or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="flatty-llm-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
