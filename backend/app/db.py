"""SQLite storage for normalised listings.

Only listing facts are stored. Contact persons, phone numbers, e-mail addresses and
images are never saved (data minimisation under the Swiss revDSG).
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .config import DB_PATH, RETENTION_DAYS

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT,
    title_en      TEXT,
    description   TEXT,
    price         REAL,
    rooms         REAL,
    surface       REAL,
    category      TEXT,
    object_type   TEXT,
    zipcode       TEXT,
    city          TEXT,
    address       TEXT,
    lat           REAL,
    lng           REAL,
    is_private    INTEGER,
    is_furnished  INTEGER,
    is_temporary  INTEGER,
    moving_date   TEXT,
    agency        TEXT,
    published     TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    risk_score    REAL,
    risk_flags    TEXT,
    model_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_listings_last_seen ON listings(last_seen);
CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    started    TEXT NOT NULL,
    finished   TEXT,
    requests   INTEGER DEFAULT 0,
    saved      INTEGER DEFAULT 0,
    status     TEXT,
    message    TEXT
);
"""

LISTING_FIELDS = [
    "id", "source", "source_id", "url", "title", "title_en", "description", "price", "rooms", "surface",
    "category", "object_type", "zipcode", "city", "address", "lat", "lng", "is_private",
    "is_furnished", "is_temporary", "moving_date", "agency", "published",
    "rent_net", "rent_charges", "floor", "year_built", "year_renovated", "available_text",
    "attributes", "images",
]
JSON_FIELDS = ("attributes", "images")

# Columns added after the first release; created on existing databases automatically.
MIGRATIONS = {
    "title_en": "TEXT",
    "rent_net": "REAL", "rent_charges": "REAL", "floor": "INTEGER", "year_built": "INTEGER",
    "year_renovated": "INTEGER", "available_text": "TEXT", "attributes": "TEXT", "images": "TEXT",
    "risk_details": "TEXT",
    "active": "INTEGER DEFAULT 1",   # 0 = taken offline at the source (hidden, kept until retention ends)
    "inactive_since": "TEXT",
    "last_checked": "TEXT",          # last single-listing check while a student viewed it
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    # The refresher writes while the API reads and checks listings: WAL lets readers proceed,
    # and the timeout makes a second writer wait for its turn instead of failing.
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript(SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(listings)")}
        for column, kind in MIGRATIONS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE listings ADD COLUMN {column} {kind}")
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_listing(conn: sqlite3.Connection, listing: dict) -> None:
    seen = now_iso()
    values = {field: listing.get(field) for field in LISTING_FIELDS}
    for field in JSON_FIELDS:
        values[field] = json.dumps(values[field] or [])
    columns = ", ".join(LISTING_FIELDS)
    placeholders = ", ".join(f":{field}" for field in LISTING_FIELDS)
    updates = ", ".join(f"{field}=excluded.{field}" for field in LISTING_FIELDS if field != "id")
    conn.execute(
        f"""INSERT INTO listings ({columns}, first_seen, last_seen)
            VALUES ({placeholders}, :seen, :seen)
            ON CONFLICT(id) DO UPDATE SET {updates}, last_seen=:seen, active=1, inactive_since=NULL""",
        {**values, "seen": seen},
    )


def save_risk(conn: sqlite3.Connection, listing_id: str, result: dict, version: str) -> None:
    raising = result["text_flags"] + [s["key"] for s in result["signals"] if s["weight"] > 0]
    conn.execute(
        "UPDATE listings SET risk_score=?, risk_flags=?, risk_details=?, model_version=? WHERE id=?",
        (result["score"], json.dumps(raising), json.dumps(result), version, listing_id),
    )


def row_to_listing(row: sqlite3.Row) -> dict:
    listing = dict(row)
    for field in ("risk_flags", *JSON_FIELDS):
        listing[field] = json.loads(listing[field] or "[]")
    listing["risk_details"] = json.loads(listing.get("risk_details") or "{}")
    for key in ("is_private", "is_furnished", "is_temporary"):
        listing[key] = bool(listing[key])
    return listing


def all_listings(conn: sqlite3.Connection, include_inactive: bool = False) -> list[dict]:
    query = "SELECT * FROM listings" + ("" if include_inactive else " WHERE active=1")
    return [row_to_listing(row) for row in conn.execute(query)]


def get_listing(conn: sqlite3.Connection, listing_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
    return row_to_listing(row) if row else None


def count_active(conn: sqlite3.Connection, source: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM listings WHERE source=? AND active=1", (source,)).fetchone()[0]


def deactivate_missing(conn: sqlite3.Connection, source: str, run_started: str) -> int:
    """After a complete run: listings of this source that the run did not see are offline."""
    return conn.execute(
        "UPDATE listings SET active=0, inactive_since=? WHERE source=? AND active=1 AND last_seen < ?",
        (now_iso(), source, run_started),
    ).rowcount


def mark_inactive(conn: sqlite3.Connection, listing_id: str) -> None:
    conn.execute(
        "UPDATE listings SET active=0, inactive_since=COALESCE(inactive_since, ?), last_checked=? WHERE id=?",
        (now_iso(), now_iso(), listing_id),
    )


def mark_checked(conn: sqlite3.Connection, listing_id: str) -> None:
    conn.execute("UPDATE listings SET last_checked=? WHERE id=?", (now_iso(), listing_id))


def update_title_en(conn: sqlite3.Connection, listing_id: str, title_en: str) -> None:
    conn.execute("UPDATE listings SET title_en=? WHERE id=?", (title_en, listing_id))


def delete_stale(conn: sqlite3.Connection) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
    return conn.execute("DELETE FROM listings WHERE last_seen < ?", (cutoff,)).rowcount


def start_run(conn: sqlite3.Connection, source: str) -> tuple[int, str]:
    started = now_iso()
    cursor = conn.execute("INSERT INTO scrape_runs (source, started, status) VALUES (?, ?, 'running')", (source, started))
    conn.commit()
    return cursor.lastrowid, started


def finish_run(conn: sqlite3.Connection, run_id: int, requests: int, saved: int, status: str, message: str = "") -> None:
    conn.execute(
        "UPDATE scrape_runs SET finished=?, requests=?, saved=?, status=?, message=? WHERE id=?",
        (now_iso(), requests, saved, status, message, run_id),
    )


def last_run(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def mark_interrupted(conn: sqlite3.Connection) -> int:
    """Runs still marked 'running' when the API starts were cut off (restart, crash)."""
    return conn.execute(
        "UPDATE scrape_runs SET status='interrupted', finished=?, message='API restarted during the run' WHERE status='running'",
        (now_iso(),),
    ).rowcount


def last_attempts(conn: sqlite3.Connection) -> dict[str, dict]:
    """Source -> its most recent run (any status)."""
    rows = conn.execute("SELECT * FROM scrape_runs WHERE id IN (SELECT MAX(id) FROM scrape_runs GROUP BY source)")
    return {row["source"]: dict(row) for row in rows}


def last_successful_runs(conn: sqlite3.Connection) -> dict[str, str]:
    """Source -> finish time of its latest complete run."""
    rows = conn.execute("SELECT source, MAX(finished) FROM scrape_runs WHERE status='ok' GROUP BY source")
    return {source: finished for source, finished in rows}
